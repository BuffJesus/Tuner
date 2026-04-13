from __future__ import annotations

from datetime import UTC, datetime

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.services.datalog_replay_service import DatalogReplayService
from tuner.services.tuning_workspace_presenter import CatalogSnapshot, OperationLogSnapshot, TuningWorkspaceSnapshot, WorkspaceReviewSnapshot


def _workspace_snapshot() -> TuningWorkspaceSnapshot:
    return TuningWorkspaceSnapshot(
        navigation=(),
        active_page_kind="empty",
        table_page=None,
        parameter_page=None,
        catalog=CatalogSnapshot(entries=(), selected_name=None, details_text=""),
        operation_log=OperationLogSnapshot(summary_text="", entry_count=0, has_unwritten=False),
        workspace_review=WorkspaceReviewSnapshot(summary_text="", entries=()),
        sync_state=None,
    )


def test_datalog_replay_service_builds_replay_evidence_snapshot() -> None:
    log = DataLog(
        name="session",
        records=[
            DataLogRecord(
                timestamp=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
                values={"rpm": 950.0, "map": 42.0},
            )
        ],
    )

    selection = DatalogReplayService().select_row(
        log=log,
        index=0,
        workspace_snapshot=_workspace_snapshot(),
    )

    assert selection.channel_count == 2
    assert selection.evidence_snapshot.session_state == "replay"
    assert selection.evidence_snapshot.connection_text == "Connection  replay"
    assert selection.evidence_snapshot.source_text == "Source  Datalog Replay"
    assert selection.runtime_snapshot.as_dict() == {"rpm": 950.0, "map": 42.0}
