from __future__ import annotations

from dataclasses import dataclass, replace

from tuner.domain.datalog import DataLog
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.session import SessionInfo, SessionState
from tuner.services.evidence_replay_service import EvidenceReplayService, EvidenceReplaySnapshot


@dataclass(slots=True, frozen=True)
class DatalogReplaySelectionSnapshot:
    selected_index: int
    total_rows: int
    channel_count: int
    summary_text: str
    preview_text: str
    runtime_snapshot: OutputChannelSnapshot
    evidence_snapshot: EvidenceReplaySnapshot


class DatalogReplayService:
    def __init__(self, evidence_replay_service: EvidenceReplayService | None = None) -> None:
        self._evidence_replay_service = evidence_replay_service or EvidenceReplayService()

    def select_row(
        self,
        *,
        log: DataLog,
        index: int,
        workspace_snapshot,
    ) -> DatalogReplaySelectionSnapshot:
        if not log.records:
            raise ValueError("Datalog is empty.")
        bounded_index = max(0, min(index, len(log.records) - 1))
        record = log.records[bounded_index]
        runtime_snapshot = OutputChannelSnapshot(
            timestamp=record.timestamp,
            values=[OutputChannelValue(name=name, value=value) for name, value in record.values.items()],
        )
        evidence_snapshot = self._evidence_replay_service.build(
            session_info=SessionInfo(state=SessionState.DISCONNECTED),
            workspace_snapshot=workspace_snapshot,
            runtime_snapshot=runtime_snapshot,
            now=record.timestamp,
        )
        evidence_snapshot = replace(
            evidence_snapshot,
            session_state="replay",
            connection_text="Connection  replay",
            source_text="Source  Datalog Replay",
        )
        preview_text = ", ".join(f"{name}={value}" for name, value in list(record.values.items())[:8])
        summary_text = (
            f"Replay row {bounded_index + 1} of {len(log.records)} "
            f"with {len(record.values)} channel(s) at {record.timestamp.isoformat()}."
        )
        return DatalogReplaySelectionSnapshot(
            selected_index=bounded_index,
            total_rows=len(log.records),
            channel_count=len(record.values),
            summary_text=summary_text,
            preview_text=preview_text,
            runtime_snapshot=runtime_snapshot,
            evidence_snapshot=evidence_snapshot,
        )
