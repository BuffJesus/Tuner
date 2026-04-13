from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.domain.session import SessionInfo, SessionState


@dataclass(slots=True, frozen=True)
class SurfaceEvidenceSnapshot:
    connection_text: str
    connection_severity: str
    source_text: str
    source_severity: str
    sync_text: str
    sync_severity: str
    changes_text: str
    changes_severity: str
    log_text: str
    log_severity: str
    runtime_text: str
    runtime_severity: str
    summary_text: str


class SurfaceEvidenceService:
    def build(
        self,
        *,
        session_info: SessionInfo,
        workspace_snapshot,
        runtime_snapshot: OutputChannelSnapshot | None,
        now: datetime | None = None,
    ) -> SurfaceEvidenceSnapshot:
        sync_state = workspace_snapshot.sync_state if workspace_snapshot is not None else None
        operation_log = workspace_snapshot.operation_log if workspace_snapshot is not None else None
        review = workspace_snapshot.workspace_review if workspace_snapshot is not None else None
        connected = session_info.state == SessionState.CONNECTED
        mismatch_count = len(sync_state.mismatches) if sync_state is not None else 0
        staged_count = len(review.entries) if review is not None else 0
        log_count = operation_log.entry_count if operation_log is not None else 0
        has_unwritten = operation_log.has_unwritten if operation_log is not None else False

        connection_text = f"Connection  {session_info.state.value}"
        connection_severity = "accent" if connected else "info"

        if connected and sync_state is not None and sync_state.has_ecu_ram:
            source_text = "Source  ECU RAM"
            source_severity = "accent"
        elif staged_count:
            source_text = "Source  Staged Tune"
            source_severity = "accent"
        else:
            source_text = "Source  Project Tune"
            source_severity = "ok"

        if mismatch_count:
            sync_text = f"Sync  {mismatch_count} mismatch(s)"
            sync_severity = "warning"
        elif sync_state is not None:
            sync_text = "Sync  clean"
            sync_severity = "ok"
        else:
            sync_text = "Sync  unavailable"
            sync_severity = "info"

        changes_text = f"Changes  {staged_count} staged"
        changes_severity = "accent" if staged_count else "ok"

        if log_count:
            log_text = f"Ops  {log_count} event(s)"
            if has_unwritten:
                log_text += " pending"
            log_severity = "warning" if has_unwritten else "info"
        else:
            log_text = "Ops  idle"
            log_severity = "ok"

        runtime_text, runtime_severity, runtime_detail = self._runtime_status(
            connected=connected,
            runtime_snapshot=runtime_snapshot,
            now=now,
        )
        log_detail = self._latest_operation_text(operation_log.summary_text if operation_log is not None else "")

        summary_parts: list[str] = []
        if mismatch_count:
            summary_parts.append("Review sync mismatches before trusting runtime evidence or applying writes.")
        elif staged_count and connected:
            summary_parts.append("Runtime data is live while staged changes remain pending review or write.")
        elif staged_count:
            summary_parts.append("Staged changes exist, but runtime evidence is offline until a controller is connected.")
        elif connected and runtime_snapshot is not None and runtime_snapshot.values:
            if runtime_severity == "warning":
                summary_parts.append("Runtime evidence is present but stale. Refresh channels before trusting live conditions.")
            else:
                summary_parts.append("Live runtime evidence is available. Cross-check channels, sync state, and recent operations before making changes.")
        elif connected:
            summary_parts.append("Connected, but runtime evidence has not populated yet. Refresh channels or verify the controller is streaming.")
        else:
            summary_parts.append("Offline context only. Connect to gather runtime evidence and compare it against the current tune state.")

        if has_unwritten:
            summary_parts.append("Unwritten operation history exists in this session.")
        if runtime_detail:
            summary_parts.append(runtime_detail)
        if log_detail:
            summary_parts.append(f"Latest op: {log_detail}")

        return SurfaceEvidenceSnapshot(
            connection_text=connection_text,
            connection_severity=connection_severity,
            source_text=source_text,
            source_severity=source_severity,
            sync_text=sync_text,
            sync_severity=sync_severity,
            changes_text=changes_text,
            changes_severity=changes_severity,
            log_text=log_text,
            log_severity=log_severity,
            runtime_text=runtime_text,
            runtime_severity=runtime_severity,
            summary_text=" ".join(summary_parts),
        )

    @staticmethod
    def _runtime_status(
        *,
        connected: bool,
        runtime_snapshot: OutputChannelSnapshot | None,
        now: datetime | None,
    ) -> tuple[str, str, str]:
        if runtime_snapshot is None or not runtime_snapshot.values:
            if connected:
                return "Runtime  waiting", "warning", ""
            return "Runtime  offline", "info", ""

        if not connected:
            return f"Runtime  {len(runtime_snapshot.values)} cached", "info", "Runtime snapshot is cached from an earlier session."

        age_seconds = SurfaceEvidenceService._runtime_age_seconds(runtime_snapshot, now)
        if age_seconds is None:
            return f"Runtime  {len(runtime_snapshot.values)} channel(s)", "accent", ""
        age_text = SurfaceEvidenceService._format_age(age_seconds)
        if age_seconds > 30:
            return f"Runtime  stale ({age_text})", "warning", f"Latest runtime sample is {age_text} old."
        return f"Runtime  {len(runtime_snapshot.values)} channel(s)", "accent", f"Latest runtime sample is {age_text} old."

    @staticmethod
    def _runtime_age_seconds(runtime_snapshot: OutputChannelSnapshot, now: datetime | None) -> float | None:
        timestamp = runtime_snapshot.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        delta = (current - timestamp).total_seconds()
        if delta < 0:
            return 0.0
        return delta

    @staticmethod
    def _format_age(age_seconds: float) -> str:
        rounded = int(round(age_seconds))
        if rounded < 60:
            return f"{rounded}s"
        minutes, seconds = divmod(rounded, 60)
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"

    @staticmethod
    def _latest_operation_text(summary_text: str) -> str:
        for line in summary_text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""
