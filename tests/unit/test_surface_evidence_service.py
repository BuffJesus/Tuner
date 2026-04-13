from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.session import SessionInfo, SessionState
from tuner.domain.sync_state import SyncMismatch, SyncMismatchKind, SyncState
from tuner.services.surface_evidence_service import SurfaceEvidenceService
from tuner.services.tuning_workspace_presenter import (
    CatalogSnapshot,
    OperationLogSnapshot,
    TuningWorkspaceSnapshot,
    WorkspaceReviewSnapshot,
)


def _workspace_snapshot(
    *,
    staged_count: int = 0,
    sync_state: SyncState | None = None,
    log_summary: str = "",
    log_count: int = 0,
    has_unwritten: bool = False,
) -> TuningWorkspaceSnapshot:
    return TuningWorkspaceSnapshot(
        navigation=(),
        active_page_kind="empty",
        table_page=None,
        parameter_page=None,
        catalog=CatalogSnapshot(entries=(), selected_name=None, details_text=""),
        operation_log=OperationLogSnapshot(
            summary_text=log_summary,
            entry_count=log_count,
            has_unwritten=has_unwritten,
        ),
        workspace_review=WorkspaceReviewSnapshot(
            summary_text="",
            entries=tuple(object() for _ in range(staged_count)),
        ),
        sync_state=sync_state,
    )


def test_surface_evidence_service_marks_fresh_runtime_with_latest_op() -> None:
    now = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    snapshot = SurfaceEvidenceService().build(
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(
            staged_count=1,
            sync_state=SyncState(mismatches=(), has_ecu_ram=True, connection_state=SessionState.CONNECTED.value),
            log_summary="11:59:59  staged   reqFuel: 8.0 → 8.2",
            log_count=1,
            has_unwritten=True,
        ),
        runtime_snapshot=OutputChannelSnapshot(
            timestamp=now - timedelta(seconds=2),
            values=[OutputChannelValue(name="rpm", value=950.0)],
        ),
        now=now,
    )

    assert snapshot.runtime_text == "Runtime  1 channel(s)"
    assert snapshot.runtime_severity == "accent"
    assert snapshot.log_text == "Ops  1 event(s) pending"
    assert "Latest runtime sample is 2s old." in snapshot.summary_text
    assert "Latest op: 11:59:59  staged   reqFuel: 8.0 → 8.2" in snapshot.summary_text


def test_surface_evidence_service_marks_stale_runtime_as_warning() -> None:
    now = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    snapshot = SurfaceEvidenceService().build(
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(),
        runtime_snapshot=OutputChannelSnapshot(
            timestamp=now - timedelta(seconds=95),
            values=[OutputChannelValue(name="rpm", value=950.0)],
        ),
        now=now,
    )

    assert snapshot.runtime_text == "Runtime  stale (1m 35s)"
    assert snapshot.runtime_severity == "warning"
    assert "stale" in snapshot.summary_text.lower()
    assert "1m 35s old" in snapshot.summary_text


def test_surface_evidence_service_prioritizes_sync_mismatch_warning() -> None:
    snapshot = SurfaceEvidenceService().build(
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(
            sync_state=SyncState(
                mismatches=(SyncMismatch(SyncMismatchKind.SIGNATURE_MISMATCH, "signature drift"),),
                has_ecu_ram=True,
                connection_state=SessionState.CONNECTED.value,
            ),
            log_summary="12:00:00  written  veTable = updated",
            log_count=1,
        ),
        runtime_snapshot=None,
    )

    assert snapshot.sync_text == "Sync  1 mismatch(s)"
    assert snapshot.sync_severity == "warning"
    assert "sync mismatches" in snapshot.summary_text.lower()
