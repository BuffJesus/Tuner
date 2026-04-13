from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.domain.session import SessionInfo
from tuner.services.surface_evidence_service import SurfaceEvidenceService, SurfaceEvidenceSnapshot


@dataclass(slots=True, frozen=True)
class EvidenceReplayChannel:
    name: str
    value: float
    units: str | None = None


@dataclass(slots=True, frozen=True)
class EvidenceReplaySnapshot:
    captured_at: datetime
    session_state: str
    connection_text: str
    source_text: str
    sync_summary_text: str
    sync_mismatch_details: tuple[str, ...]
    staged_summary_text: str
    operation_summary_text: str
    operation_session_count: int
    latest_write_text: str | None
    latest_burn_text: str | None
    runtime_summary_text: str
    runtime_channel_count: int
    runtime_age_seconds: float | None
    runtime_channels: tuple[EvidenceReplayChannel, ...]
    evidence_summary_text: str


class EvidenceReplayService:
    def __init__(self, surface_evidence_service: SurfaceEvidenceService | None = None) -> None:
        self._surface_evidence_service = surface_evidence_service or SurfaceEvidenceService()

    def build(
        self,
        *,
        session_info: SessionInfo,
        workspace_snapshot,
        runtime_snapshot: OutputChannelSnapshot | None,
        now: datetime | None = None,
    ) -> EvidenceReplaySnapshot:
        captured_at = self._normalized_now(now)
        evidence_snapshot = self._surface_evidence_service.build(
            session_info=session_info,
            workspace_snapshot=workspace_snapshot,
            runtime_snapshot=runtime_snapshot,
            now=captured_at,
        )
        sync_state = workspace_snapshot.sync_state if workspace_snapshot is not None else None
        operation_log = workspace_snapshot.operation_log if workspace_snapshot is not None else None
        workspace_review = workspace_snapshot.workspace_review if workspace_snapshot is not None else None
        mismatch_details = tuple(item.detail for item in sync_state.mismatches) if sync_state is not None else ()
        runtime_channels = tuple(
            EvidenceReplayChannel(name=item.name, value=item.value, units=item.units)
            for item in (runtime_snapshot.values if runtime_snapshot is not None else ())
        )
        runtime_age_seconds = (
            SurfaceEvidenceService._runtime_age_seconds(runtime_snapshot, captured_at)  # noqa: SLF001
            if runtime_snapshot is not None and runtime_snapshot.values
            else None
        )
        return EvidenceReplaySnapshot(
            captured_at=captured_at,
            session_state=session_info.state.value,
            connection_text=evidence_snapshot.connection_text,
            source_text=evidence_snapshot.source_text,
            sync_summary_text=evidence_snapshot.sync_text,
            sync_mismatch_details=mismatch_details,
            staged_summary_text=workspace_review.summary_text if workspace_review is not None else "No staged changes.",
            operation_summary_text=operation_log.summary_text if operation_log is not None else "No operations recorded this session.",
            operation_session_count=operation_log.session_count if operation_log is not None else 0,
            latest_write_text=operation_log.latest_write_text if operation_log is not None else None,
            latest_burn_text=operation_log.latest_burn_text if operation_log is not None else None,
            runtime_summary_text=evidence_snapshot.runtime_text,
            runtime_channel_count=len(runtime_channels),
            runtime_age_seconds=runtime_age_seconds,
            runtime_channels=runtime_channels,
            evidence_summary_text=self._compose_summary(
                captured_at=captured_at,
                evidence_snapshot=evidence_snapshot,
                workspace_snapshot=workspace_snapshot,
                runtime_channels=runtime_channels,
                runtime_age_seconds=runtime_age_seconds,
            ),
        )

    @staticmethod
    def _normalized_now(now: datetime | None) -> datetime:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            return current.replace(tzinfo=UTC)
        return current

    @staticmethod
    def _compose_summary(
        *,
        captured_at: datetime,
        evidence_snapshot: SurfaceEvidenceSnapshot,
        workspace_snapshot,
        runtime_channels: tuple[EvidenceReplayChannel, ...],
        runtime_age_seconds: float | None,
    ) -> str:
        lines = [
            f"Captured: {captured_at.isoformat()}",
            evidence_snapshot.summary_text,
        ]
        if workspace_snapshot is not None:
            lines.append(workspace_snapshot.workspace_review.summary_text)
            if workspace_snapshot.operation_log.latest_write_text:
                lines.append(f"Latest write: {workspace_snapshot.operation_log.latest_write_text}")
            if workspace_snapshot.operation_log.latest_burn_text:
                lines.append(f"Latest burn: {workspace_snapshot.operation_log.latest_burn_text}")
            if workspace_snapshot.sync_state is not None and workspace_snapshot.sync_state.mismatches:
                lines.extend(
                    f"Sync mismatch: {mismatch.detail}"
                    for mismatch in workspace_snapshot.sync_state.mismatches
                )
        if runtime_channels:
            runtime_header = f"Runtime channels captured: {len(runtime_channels)}"
            if runtime_age_seconds is not None:
                runtime_header += f" ({SurfaceEvidenceService._format_age(runtime_age_seconds)} old)"  # noqa: SLF001
            lines.append(runtime_header)
        else:
            lines.append("Runtime channels captured: none")
        return "\n".join(lines)
