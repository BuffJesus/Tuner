from __future__ import annotations

from datetime import UTC, datetime

from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.evidence_replay_service import EvidenceReplayChannel, EvidenceReplaySnapshot
from tuner.services.table_replay_context_service import TableReplayContextService
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


def _evidence_snapshot(*, rpm: float, map_kpa: float) -> EvidenceReplaySnapshot:
    return EvidenceReplaySnapshot(
        captured_at=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
        session_state="replay",
        connection_text="Connection  replay",
        source_text="Source  Datalog Replay",
        sync_summary_text="Sync  unavailable",
        sync_mismatch_details=(),
        staged_summary_text="No staged changes.",
        operation_summary_text="No operations recorded this session.",
        operation_session_count=0,
        latest_write_text=None,
        latest_burn_text=None,
        runtime_summary_text="Runtime  2 channel(s)",
        runtime_channel_count=2,
        runtime_age_seconds=0.0,
        runtime_channels=(
            EvidenceReplayChannel(name="rpm", value=rpm, units="rpm"),
            EvidenceReplayChannel(name="map", value=map_kpa, units="kPa"),
        ),
        evidence_summary_text="Captured replay bundle.",
    )


def test_table_replay_context_service_maps_replay_to_nearest_cell() -> None:
    context = TableReplayContextService().build(
        table_snapshot=_table_snapshot(),
        evidence_snapshot=_evidence_snapshot(rpm=1125.0, map_kpa=52.0),
    )

    assert context is not None
    assert context.row_index == 1
    assert context.column_index == 1
    assert context.cell_value_text == "60"
    assert "row 2, column 2" in context.summary_text
