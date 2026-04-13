from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.session import SessionInfo, SessionState
from tuner.domain.sync_state import SyncMismatch, SyncMismatchKind, SyncState
from tuner.services.evidence_replay_service import EvidenceReplayService
from tuner.services.tuning_workspace_presenter import (
    CatalogSnapshot,
    OperationLogSnapshot,
    TuningWorkspaceSnapshot,
    WorkspaceReviewSnapshot,
)


def _workspace_snapshot(
    *,
    staged_summary_text: str = "No staged changes across the workspace.",
    staged_count: int = 0,
    operation_summary_text: str = "No operations recorded this session.",
    session_count: int = 0,
    latest_write_text: str | None = None,
    latest_burn_text: str | None = None,
    has_unwritten: bool = False,
    sync_state: SyncState | None = None,
) -> TuningWorkspaceSnapshot:
    return TuningWorkspaceSnapshot(
        navigation=(),
        active_page_kind="empty",
        table_page=None,
        parameter_page=None,
        catalog=CatalogSnapshot(entries=(), selected_name=None, details_text=""),
        operation_log=OperationLogSnapshot(
            summary_text=operation_summary_text,
            entry_count=0 if operation_summary_text.startswith("No operations") else 1,
            has_unwritten=has_unwritten,
            session_count=session_count,
            latest_write_text=latest_write_text,
            latest_burn_text=latest_burn_text,
        ),
        workspace_review=WorkspaceReviewSnapshot(
            summary_text=staged_summary_text,
            entries=tuple(object() for _ in range(staged_count)),
        ),
        sync_state=sync_state,
    )


def test_evidence_replay_service_captures_runtime_and_operation_context() -> None:
    now = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    snapshot = EvidenceReplayService().build(
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(
            staged_summary_text="2 staged changes across the workspace. 1 not yet written to RAM.",
            staged_count=2,
            operation_summary_text="Evidence summary: latest staged work has been written to RAM but not burned.",
            session_count=1,
            latest_write_text="11:59:58  written  reqFuel = 9.2",
            has_unwritten=True,
        ),
        runtime_snapshot=OutputChannelSnapshot(
            timestamp=now - timedelta(seconds=4),
            values=[
                OutputChannelValue(name="rpm", value=950.0, units="rpm"),
                OutputChannelValue(name="map", value=42.0, units="kPa"),
            ],
        ),
        now=now,
    )

    assert snapshot.captured_at == now
    assert snapshot.runtime_channel_count == 2
    assert snapshot.runtime_age_seconds == 4.0
    assert snapshot.operation_session_count == 1
    assert snapshot.latest_write_text == "11:59:58  written  reqFuel = 9.2"
    assert snapshot.runtime_channels[0].name == "rpm"
    assert "Captured: 2026-04-03T12:00:00+00:00" in snapshot.evidence_summary_text
    assert "Runtime channels captured: 2 (4s old)" in snapshot.evidence_summary_text


def test_evidence_replay_service_includes_sync_mismatch_details() -> None:
    snapshot = EvidenceReplayService().build(
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(
            sync_state=SyncState(
                mismatches=(SyncMismatch(SyncMismatchKind.SIGNATURE_MISMATCH, "signature drift"),),
                has_ecu_ram=True,
                connection_state=SessionState.CONNECTED.value,
            ),
            latest_burn_text="12:00:00  burned   reqFuel = 9.2",
            session_count=1,
        ),
        runtime_snapshot=None,
        now=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
    )

    assert snapshot.sync_summary_text == "Sync  1 mismatch(s)"
    assert snapshot.sync_mismatch_details == ("signature drift",)
    assert snapshot.latest_burn_text == "12:00:00  burned   reqFuel = 9.2"
    assert "Sync mismatch: signature drift" in snapshot.evidence_summary_text
    assert "Runtime channels captured: none" in snapshot.evidence_summary_text
