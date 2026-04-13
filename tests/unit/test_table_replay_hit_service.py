from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.table_replay_hit_service import TableReplayHitService
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot


def _table_snapshot() -> TablePageSnapshot:
    return TablePageSnapshot(
        page_id="table-editor:ve",
        group_id="fuel",
        title="VE Table",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="Fuel map",
        validation_summary="Ready",
        diff_summary="No staged changes.",
        diff_text="",
        diff_entries=(),
        axis_summary="X Axis: rpmBins | Y Axis: loadBins",
        details_text="",
        help_topic=None,
        x_parameter_name="rpmBins",
        y_parameter_name="loadBins",
        x_labels=("500", "1000", "1500"),
        y_labels=("30", "60"),
        table_model=TableViewModel(
            rows=2,
            columns=3,
            cells=[["40", "45", "50"], ["55", "60", "65"]],
        ),
        auxiliary_sections=(),
        can_undo=False,
        can_redo=False,
    )


def test_table_replay_hit_service_summarizes_hot_cells() -> None:
    start = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    log = DataLog(
        name="session",
        records=[
            DataLogRecord(timestamp=start, values={"rpm": 950.0, "map": 58.0, "afr": 13.2}),
            DataLogRecord(timestamp=start + timedelta(seconds=0.5), values={"rpm": 990.0, "map": 61.0, "afr": 13.8}),
            DataLogRecord(timestamp=start + timedelta(seconds=1.0), values={"rpm": 1490.0, "map": 58.0, "afr": 12.9}),
            DataLogRecord(timestamp=start + timedelta(seconds=1.5), values={"clt": 80.0}),
            DataLogRecord(timestamp=start + timedelta(seconds=2.0), values={"rpm": 950.0, "map": 58.0, "afr": 40.0}),
        ],
    )

    summary = TableReplayHitService().build(
        table_snapshot=_table_snapshot(),
        log=log,
    )

    assert summary is not None
    assert summary.hot_cells[0].row_index == 1
    assert summary.hot_cells[0].column_index == 1
    assert summary.hot_cells[0].hit_count == 2
    assert summary.hot_cells[0].mean_afr == 13.5
    assert summary.accepted_row_count == 3
    assert summary.rejected_row_count == 2
    # Both rejections now come from std_DeadLambda: record with only clt (no AFR channel)
    # and record with AFR=40 (out of plausible range) are both caught by the gate.
    assert summary.rejected_reason_counts == (("std_DeadLambda", 2),)
    assert "Hot cell row 2, column 2: 2 hit(s), mean AFR 13.50." in summary.detail_text
    assert "Rejections: std_DeadLambda=2." in summary.detail_text
