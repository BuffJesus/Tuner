from __future__ import annotations

from dataclasses import dataclass

from tuner.services.operation_log_service import OperationEntry, OperationKind


@dataclass(slots=True, frozen=True)
class OperationEvidenceSession:
    sequence: int
    entry_count: int
    has_burn: bool
    has_write: bool
    has_unwritten_stage: bool
    latest_entry: OperationEntry | None


@dataclass(slots=True, frozen=True)
class OperationEvidenceSnapshot:
    summary_text: str
    session_count: int
    latest_write_entry: OperationEntry | None
    latest_burn_entry: OperationEntry | None
    active_session: OperationEvidenceSession | None


class OperationEvidenceService:
    def build(
        self,
        *,
        entries: tuple[OperationEntry, ...],
        has_unwritten: bool,
        limit: int = 12,
    ) -> OperationEvidenceSnapshot:
        sessions = self._sessions(entries)
        latest_write = next((entry for entry in reversed(entries) if entry.kind == OperationKind.WRITTEN), None)
        latest_burn = next((entry for entry in reversed(entries) if entry.kind == OperationKind.BURNED), None)
        active_session = sessions[-1] if sessions else None
        summary_text = self._summary_text(
            entries=entries,
            sessions=sessions,
            latest_write=latest_write,
            latest_burn=latest_burn,
            has_unwritten=has_unwritten,
            limit=limit,
        )
        return OperationEvidenceSnapshot(
            summary_text=summary_text,
            session_count=len(sessions),
            latest_write_entry=latest_write,
            latest_burn_entry=latest_burn,
            active_session=active_session,
        )

    def _sessions(self, entries: tuple[OperationEntry, ...]) -> tuple[OperationEvidenceSession, ...]:
        if not entries:
            return ()
        sessions: list[OperationEvidenceSession] = []
        current_entries: list[OperationEntry] = []
        sequence = 1
        for entry in entries:
            current_entries.append(entry)
            if entry.kind == OperationKind.BURNED:
                sessions.append(self._build_session(sequence, tuple(current_entries)))
                current_entries = []
                sequence += 1
        if current_entries:
            sessions.append(self._build_session(sequence, tuple(current_entries)))
        return tuple(sessions)

    @staticmethod
    def _build_session(sequence: int, entries: tuple[OperationEntry, ...]) -> OperationEvidenceSession:
        return OperationEvidenceSession(
            sequence=sequence,
            entry_count=len(entries),
            has_burn=any(entry.kind == OperationKind.BURNED for entry in entries),
            has_write=any(entry.kind == OperationKind.WRITTEN for entry in entries),
            has_unwritten_stage=any(entry.kind == OperationKind.STAGED for entry in entries)
            and not any(entry.kind in {OperationKind.WRITTEN, OperationKind.BURNED} for entry in entries),
            latest_entry=entries[-1] if entries else None,
        )

    def _summary_text(
        self,
        *,
        entries: tuple[OperationEntry, ...],
        sessions: tuple[OperationEvidenceSession, ...],
        latest_write: OperationEntry | None,
        latest_burn: OperationEntry | None,
        has_unwritten: bool,
        limit: int,
    ) -> str:
        if not entries:
            return "No operations recorded this session."

        lines: list[str] = []
        lines.append(
            "Evidence summary: "
            + self._active_status_text(
                sessions=sessions,
                latest_write=latest_write,
                latest_burn=latest_burn,
                has_unwritten=has_unwritten,
            )
        )
        if latest_write is not None:
            lines.append(f"Last write: {latest_write.summary_line()}")
        if latest_burn is not None:
            lines.append(f"Last burn: {latest_burn.summary_line()}")
        if sessions:
            active = sessions[-1]
            lines.append(
                f"Active review session: #{active.sequence} | {active.entry_count} event(s)"
                f" | {'burned' if active.has_burn else 'not burned'}"
                f" | {'written' if active.has_write else 'not written'}"
            )
        lines.append("")
        lines.append("Recent operations:")
        for entry in reversed(entries[-limit:]):
            lines.append(entry.summary_line())
        return "\n".join(lines)

    @staticmethod
    def _active_status_text(
        *,
        sessions: tuple[OperationEvidenceSession, ...],
        latest_write: OperationEntry | None,
        latest_burn: OperationEntry | None,
        has_unwritten: bool,
    ) -> str:
        if has_unwritten:
            return "unwritten staged changes are still pending review or RAM write."
        if latest_burn is not None:
            return "latest staged work has been burned; verify persisted values before trusting it."
        if latest_write is not None:
            return "latest staged work has been written to RAM but not burned."
        if sessions:
            return "session history exists, but no writes have been recorded yet."
        return "idle."
