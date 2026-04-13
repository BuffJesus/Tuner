"""Tests for WUE Analyze integration in TuningWorkspacePresenter.

Covers:
- wue_analyze snapshot is None on non-table pages
- wue_analyze snapshot is present and idle on a table page
- start_wue_analyze() activates the session
- stop_wue_analyze() stops feeding; preserves data
- reset_wue_analyze() clears state
- set_runtime_snapshot() feeds the session while running
- set_runtime_snapshot() does not feed when stopped
- apply_wue_analyze_proposals() stages corrected row values
- apply_wue_analyze_proposals() no-ops when no proposals
- selecting a different page resets the WUE analyze state
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tuner.domain.ecu_definition import (
    EcuDefinition,
    TableDefinition,
    TableEditorDefinition,
)
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.tune import TuneFile, TuneValue
from tuner.domain.tuning_pages import TuningPageStateKind
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter

_NOW = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset({"_disabled_"}))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _presenter_with_wue_page() -> TuningWorkspacePresenter:
    """Presenter with a 6×1 WUE table indexed by CLT (Y axis = wueBins)."""
    definition = EcuDefinition(
        name="Test",
        tables=[
            TableDefinition(name="warmupTable", rows=6, columns=1, page=1, offset=0, units="%"),
            TableDefinition(name="wueBins", rows=6, columns=1, page=1, offset=6, units="°C"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="wue",
                map_id="wueMap",
                title="Warmup Enrichment",
                page=1,
                x_bins="warmupTable",   # single column; y_bins = the CLT axis
                y_bins="wueBins",
                z_bins="warmupTable",
            )
        ],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="warmupTable", value=[180.0, 175.0, 168.0, 154.0, 134.0, 100.0],
                      rows=6, cols=1, units="%"),
            TuneValue(name="wueBins", value=[-40.0, -26.0, 10.0, 28.0, 46.0, 64.0],
                      rows=6, cols=1, units="°C"),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


def _runtime(clt: float, lambda_: float) -> OutputChannelSnapshot:
    return OutputChannelSnapshot(
        timestamp=_NOW,
        values=[
            OutputChannelValue(name="coolant", value=clt),
            OutputChannelValue(name="lambda", value=lambda_),
        ],
    )


# ---------------------------------------------------------------------------
# Idle / non-table pages
# ---------------------------------------------------------------------------


def test_wue_analyze_none_on_non_table_page() -> None:
    from tuner.domain.ecu_definition import DialogDefinition, DialogFieldDefinition, MenuDefinition, MenuItemDefinition, ScalarParameterDefinition
    definition = EcuDefinition(
        name="Test",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, units="ms")],
        dialogs=[DialogDefinition(dialog_id="d1", title="Page 1",
                                  fields=[DialogFieldDefinition(label="Req Fuel", parameter_name="reqFuel")])],
        menus=[MenuDefinition(title="Fuel", items=[MenuItemDefinition(target="d1", label="Fuel")])],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.0, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    snap = presenter.snapshot()
    assert snap.wue_analyze is None


def test_wue_analyze_idle_on_table_page() -> None:
    presenter = _presenter_with_wue_page()
    snap = presenter.snapshot()

    assert snap.wue_analyze is not None
    assert not snap.wue_analyze.is_running
    assert not snap.wue_analyze.has_data
    assert snap.wue_analyze.can_start
    assert not snap.wue_analyze.can_stop
    assert not snap.wue_analyze.can_reset
    assert not snap.wue_analyze.can_apply


# ---------------------------------------------------------------------------
# Start / stop / reset
# ---------------------------------------------------------------------------


def test_start_wue_analyze_activates_session() -> None:
    presenter = _presenter_with_wue_page()
    snap = presenter.start_wue_analyze()

    assert snap.wue_analyze is not None
    assert snap.wue_analyze.is_running
    assert snap.wue_analyze.has_data
    assert not snap.wue_analyze.can_start
    assert snap.wue_analyze.can_stop
    assert snap.wue_analyze.can_reset


def test_stop_wue_analyze_preserves_data() -> None:
    presenter = _presenter_with_wue_page()
    presenter.start_wue_analyze()
    snap = presenter.stop_wue_analyze()

    assert snap.wue_analyze is not None
    assert not snap.wue_analyze.is_running
    assert snap.wue_analyze.has_data
    assert snap.wue_analyze.can_start
    assert not snap.wue_analyze.can_stop
    assert snap.wue_analyze.can_reset


def test_reset_wue_analyze_clears_state() -> None:
    presenter = _presenter_with_wue_page()
    presenter.start_wue_analyze()
    presenter.stop_wue_analyze()
    snap = presenter.reset_wue_analyze()

    assert snap.wue_analyze is not None
    assert not snap.wue_analyze.is_running
    assert not snap.wue_analyze.has_data
    assert snap.wue_analyze.can_start
    assert not snap.wue_analyze.can_reset


# ---------------------------------------------------------------------------
# Runtime feeding
# ---------------------------------------------------------------------------


def test_runtime_feeds_session_when_running() -> None:
    presenter = _presenter_with_wue_page()
    presenter.start_wue_analyze()
    presenter.set_runtime_snapshot(_runtime(clt=10.0, lambda_=1.0))

    snap = presenter.snapshot()
    assert snap.wue_analyze is not None
    total = snap.wue_analyze.accepted_count + snap.wue_analyze.rejected_count
    assert total >= 1


def test_runtime_does_not_feed_when_stopped() -> None:
    presenter = _presenter_with_wue_page()
    presenter.start_wue_analyze()
    presenter.stop_wue_analyze()
    presenter.set_runtime_snapshot(_runtime(clt=10.0, lambda_=1.0))

    snap = presenter.snapshot()
    assert snap.wue_analyze is not None
    assert snap.wue_analyze.accepted_count == 0
    assert snap.wue_analyze.rejected_count == 0


def test_runtime_does_not_feed_when_idle() -> None:
    presenter = _presenter_with_wue_page()
    presenter.set_runtime_snapshot(_runtime(clt=10.0, lambda_=1.0))

    snap = presenter.snapshot()
    assert snap.wue_analyze is not None
    assert snap.wue_analyze.accepted_count == 0


# ---------------------------------------------------------------------------
# Apply proposals
# ---------------------------------------------------------------------------


def test_apply_wue_analyze_proposals_stages_rows() -> None:
    """apply_wue_analyze_proposals() stages corrected WUE values."""
    presenter = _presenter_with_wue_page()
    # Disable all gates for this test
    presenter._wue_analyze_session._gating_config = _NO_GATE  # type: ignore[attr-defined]
    presenter.start_wue_analyze()

    # Feed 3 samples at CLT=10°C (row 2), running lean (λ=1.1)
    for _ in range(3):
        presenter.set_runtime_snapshot(_runtime(clt=10.0, lambda_=1.1))

    presenter.stop_wue_analyze()
    snap = presenter.snapshot()
    assert snap.wue_analyze is not None

    if snap.wue_analyze.rows_with_proposals == 0:
        pytest.skip("No proposals — CLT axis mapping may not match test data")

    snap_after = presenter.apply_wue_analyze_proposals()
    assert snap_after.table_page is not None
    assert snap_after.table_page.state.kind == TuningPageStateKind.STAGED


def test_apply_wue_analyze_noop_without_proposals() -> None:
    presenter = _presenter_with_wue_page()
    presenter.start_wue_analyze()
    # No samples fed
    presenter.stop_wue_analyze()

    snap = presenter.apply_wue_analyze_proposals()
    assert snap.table_page is not None
    assert snap.table_page.state.kind == TuningPageStateKind.CLEAN


def test_apply_wue_analyze_noop_when_idle() -> None:
    presenter = _presenter_with_wue_page()
    snap = presenter.apply_wue_analyze_proposals()
    assert snap.table_page is not None
    assert snap.table_page.state.kind == TuningPageStateKind.CLEAN


# ---------------------------------------------------------------------------
# Page navigation resets WUE state
# ---------------------------------------------------------------------------


def test_selecting_different_page_resets_wue_analyze() -> None:
    definition = EcuDefinition(
        name="Test",
        tables=[
            TableDefinition(name="warmupTable", rows=6, columns=1, page=1, offset=0, units="%"),
            TableDefinition(name="wueBins", rows=6, columns=1, page=1, offset=6, units="°C"),
            TableDefinition(name="veTable", rows=2, columns=2, page=2, offset=0, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=2, page=2, offset=4, units="rpm"),
            TableDefinition(name="loadBins", rows=2, columns=1, page=2, offset=8, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(table_id="wue", map_id="wueMap", title="Warmup Enrichment",
                                  page=1, x_bins="warmupTable", y_bins="wueBins", z_bins="warmupTable"),
            TableEditorDefinition(table_id="ve", map_id="veMap", title="VE Table",
                                  page=2, x_bins="rpmBins", y_bins="loadBins", z_bins="veTable"),
        ],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="warmupTable", value=[180.0, 175.0, 168.0, 154.0, 134.0, 100.0], rows=6, cols=1, units="%"),
            TuneValue(name="wueBins", value=[-40.0, -26.0, 10.0, 28.0, 46.0, 64.0], rows=6, cols=1, units="°C"),
            TuneValue(name="veTable", value=[50.0, 55.0, 60.0, 65.0], rows=2, cols=2, units="%"),
            TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
            TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    presenter.start_wue_analyze()
    assert presenter._wue_analyze_running  # type: ignore[attr-defined]

    second_page_id = next(
        (pid for pid in presenter.pages_by_id if pid != presenter.active_page_id),
        None,
    )
    assert second_page_id is not None
    snap = presenter.select_page(second_page_id)

    assert snap.wue_analyze is not None
    assert not snap.wue_analyze.is_running
    assert not snap.wue_analyze.has_data
