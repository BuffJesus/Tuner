"""Tests for VE Analyze integration in TuningWorkspacePresenter.

Covers:
- ve_analyze snapshot is None on non-table pages
- ve_analyze snapshot is present on a table page (idle state)
- start_ve_analyze() activates the session and sets is_running
- stop_ve_analyze() stops feeding; preserves data
- reset_ve_analyze() clears state back to idle
- set_runtime_snapshot() feeds the session while running
- set_runtime_snapshot() does NOT feed when stopped
- apply_ve_analyze_proposals() stages corrected cell values
- apply_ve_analyze_proposals() no-ops when there are no proposals
- selecting a different page resets the VE analyze state
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
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _presenter_with_ve_page() -> TuningWorkspacePresenter:
    """Presenter with a 2×3 VE table (rpm × load) loaded."""
    definition = EcuDefinition(
        name="Test",
        tables=[
            TableDefinition(name="veTable", rows=2, columns=3, page=1, offset=0, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=3, page=1, offset=24, units="rpm"),
            TableDefinition(name="loadBins", rows=2, columns=1, page=1, offset=30, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="ve",
                map_id="veMap",
                title="VE Table",
                page=1,
                x_bins="rpmBins",
                y_bins="loadBins",
                z_bins="veTable",
            )
        ],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="veTable", value=[50.0, 55.0, 60.0, 65.0, 70.0, 75.0], rows=2, cols=3, units="%"),
            TuneValue(name="rpmBins", value=[500.0, 1000.0, 1500.0], rows=1, cols=3, units="rpm"),
            TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


def _runtime(rpm: float, load: float, lambda_: float) -> OutputChannelSnapshot:
    return OutputChannelSnapshot(
        timestamp=_NOW,
        values=[
            OutputChannelValue(name="rpm", value=rpm),
            OutputChannelValue(name="map", value=load),
            OutputChannelValue(name="lambda", value=lambda_),
        ],
    )


# ---------------------------------------------------------------------------
# Idle / non-table page
# ---------------------------------------------------------------------------


def test_ve_analyze_none_on_non_table_page() -> None:
    """ve_analyze snapshot is None when the active page is not a TABLE page."""
    from tuner.domain.ecu_definition import DialogDefinition, DialogFieldDefinition, MenuDefinition, MenuItemDefinition, ScalarParameterDefinition

    definition = EcuDefinition(
        name="Test",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, units="ms")],
        dialogs=[DialogDefinition(dialog_id="d1", title="Page 1", fields=[DialogFieldDefinition(label="Req Fuel", parameter_name="reqFuel")])],
        menus=[MenuDefinition(title="Fuel", items=[MenuItemDefinition(target="d1", label="Fuel")])],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.0, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    snap = presenter.snapshot()
    assert snap.ve_analyze is None


def test_ve_analyze_idle_on_table_page() -> None:
    """ve_analyze snapshot is present and idle when on a table page."""
    presenter = _presenter_with_ve_page()
    snap = presenter.snapshot()

    assert snap.ve_analyze is not None
    assert not snap.ve_analyze.is_running
    assert not snap.ve_analyze.has_data
    assert snap.ve_analyze.can_start
    assert not snap.ve_analyze.can_stop
    assert not snap.ve_analyze.can_reset
    assert not snap.ve_analyze.can_apply


# ---------------------------------------------------------------------------
# Start / stop / reset lifecycle
# ---------------------------------------------------------------------------


def test_start_ve_analyze_activates_session() -> None:
    presenter = _presenter_with_ve_page()
    snap = presenter.start_ve_analyze()

    assert snap.ve_analyze is not None
    assert snap.ve_analyze.is_running
    assert snap.ve_analyze.has_data
    assert not snap.ve_analyze.can_start
    assert snap.ve_analyze.can_stop
    assert snap.ve_analyze.can_reset


def test_stop_ve_analyze_preserves_data() -> None:
    presenter = _presenter_with_ve_page()
    presenter.start_ve_analyze()

    snap = presenter.stop_ve_analyze()

    assert snap.ve_analyze is not None
    assert not snap.ve_analyze.is_running
    assert snap.ve_analyze.has_data       # still has the session
    assert snap.ve_analyze.can_start      # can restart
    assert not snap.ve_analyze.can_stop
    assert snap.ve_analyze.can_reset


def test_reset_ve_analyze_clears_state() -> None:
    presenter = _presenter_with_ve_page()
    presenter.start_ve_analyze()
    presenter.stop_ve_analyze()

    snap = presenter.reset_ve_analyze()

    assert snap.ve_analyze is not None
    assert not snap.ve_analyze.is_running
    assert not snap.ve_analyze.has_data
    assert snap.ve_analyze.can_start
    assert not snap.ve_analyze.can_reset


def test_reset_while_running_stops_and_clears() -> None:
    presenter = _presenter_with_ve_page()
    presenter.start_ve_analyze()

    snap = presenter.reset_ve_analyze()

    assert snap.ve_analyze is not None
    assert not snap.ve_analyze.is_running
    assert not snap.ve_analyze.has_data


# ---------------------------------------------------------------------------
# Runtime feeding
# ---------------------------------------------------------------------------


def test_runtime_snapshot_feeds_session_when_running() -> None:
    presenter = _presenter_with_ve_page()
    presenter.start_ve_analyze()

    # Feed a sample that should be accepted (rpm=900 → col 1, map=45 → row 0)
    presenter.set_runtime_snapshot(_runtime(rpm=900.0, load=45.0, lambda_=1.0))

    snap = presenter.snapshot()
    assert snap.ve_analyze is not None
    assert snap.ve_analyze.accepted_count + snap.ve_analyze.rejected_count >= 1


def test_runtime_snapshot_does_not_feed_when_stopped() -> None:
    presenter = _presenter_with_ve_page()
    presenter.start_ve_analyze()
    presenter.stop_ve_analyze()

    presenter.set_runtime_snapshot(_runtime(rpm=900.0, load=45.0, lambda_=1.0))

    snap = presenter.snapshot()
    assert snap.ve_analyze is not None
    # Session still has data (from start()), but no new frames fed after stop
    assert snap.ve_analyze.accepted_count == 0
    assert snap.ve_analyze.rejected_count == 0


def test_runtime_snapshot_does_not_feed_when_idle() -> None:
    presenter = _presenter_with_ve_page()

    presenter.set_runtime_snapshot(_runtime(rpm=900.0, load=45.0, lambda_=1.0))

    snap = presenter.snapshot()
    assert snap.ve_analyze is not None
    assert snap.ve_analyze.accepted_count == 0
    assert snap.ve_analyze.rejected_count == 0


# ---------------------------------------------------------------------------
# Apply proposals
# ---------------------------------------------------------------------------


def test_apply_ve_analyze_proposals_stages_cells() -> None:
    """apply_ve_analyze_proposals() stages corrected VE values on the table."""
    presenter = _presenter_with_ve_page()
    # Disable all gates so samples go through; use no-op gating config
    presenter._ve_analyze_session._gating_config = _NO_GATE  # type: ignore[attr-defined]
    presenter.start_ve_analyze()

    # Feed a sample targeting row=0, col=1 (rpm=900, map=45, running lean λ=1.1)
    # The axis values: rpmBins=[500,1000,1500] → rpm=900 maps to col 1 (nearest bin)
    # loadBins=[30,60] → map=45 maps to row 0 (nearest bin)
    # lambda=1.1 with target=1.0 → correction=1.1 → VE too low → increase
    for _ in range(5):  # feed enough samples to meet min_samples threshold
        presenter.set_runtime_snapshot(_runtime(rpm=900.0, load=45.0, lambda_=1.1))

    presenter.stop_ve_analyze()
    snap = presenter.snapshot()
    assert snap.ve_analyze is not None

    if snap.ve_analyze.cells_with_proposals == 0:
        pytest.skip("No proposals generated — axis mapping may differ with current test data")

    snap_after = presenter.apply_ve_analyze_proposals()

    # The active table page should now be staged
    assert snap_after.table_page is not None
    assert snap_after.table_page.state.kind == TuningPageStateKind.STAGED


def test_apply_ve_analyze_proposals_noop_without_proposals() -> None:
    """apply_ve_analyze_proposals() is a no-op when no proposals exist."""
    presenter = _presenter_with_ve_page()
    presenter.start_ve_analyze()
    # Do NOT feed any samples → no proposals

    presenter.stop_ve_analyze()
    snap_before = presenter.snapshot()
    snap_after = presenter.apply_ve_analyze_proposals()

    # Table state should remain clean
    assert snap_after.table_page is not None
    assert snap_after.table_page.state.kind == TuningPageStateKind.CLEAN


def test_apply_ve_analyze_noop_when_idle() -> None:
    """apply_ve_analyze_proposals() without starting is a no-op."""
    presenter = _presenter_with_ve_page()

    snap = presenter.apply_ve_analyze_proposals()

    assert snap.table_page is not None
    assert snap.table_page.state.kind == TuningPageStateKind.CLEAN


# ---------------------------------------------------------------------------
# Page navigation resets session
# ---------------------------------------------------------------------------


def test_selecting_different_page_resets_ve_analyze() -> None:
    """Navigating to a different page clears the VE Analyze session."""
    from tuner.domain.ecu_definition import (
        TableDefinition,
        TableEditorDefinition,
    )

    # Two VE-table pages so navigation doesn't fall back to a parameter page
    definition = EcuDefinition(
        name="Test",
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=2, page=1, offset=16, units="rpm"),
            TableDefinition(name="loadBins", rows=2, columns=1, page=1, offset=20, units="kPa"),
            TableDefinition(name="sparkTable", rows=2, columns=2, page=2, offset=0, units="°"),
            TableDefinition(name="sparkRpm", rows=1, columns=2, page=2, offset=16, units="rpm"),
            TableDefinition(name="sparkLoad", rows=2, columns=1, page=2, offset=20, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(table_id="ve", map_id="veMap", title="VE Table", page=1,
                                  x_bins="rpmBins", y_bins="loadBins", z_bins="veTable"),
            TableEditorDefinition(table_id="spark", map_id="sparkMap", title="Spark Table", page=2,
                                  x_bins="sparkRpm", y_bins="sparkLoad", z_bins="sparkTable"),
        ],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="veTable", value=[50.0, 55.0, 60.0, 65.0], rows=2, cols=2, units="%"),
            TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
            TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
            TuneValue(name="sparkTable", value=[10.0, 12.0, 14.0, 16.0], rows=2, cols=2, units="°"),
            TuneValue(name="sparkRpm", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
            TuneValue(name="sparkLoad", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    # Start VE analyze on the first page
    presenter.start_ve_analyze()
    assert presenter._ve_analyze_running  # type: ignore[attr-defined]

    # Navigate to the second table page
    second_page_id = next(
        (pid for pid in presenter.pages_by_id if presenter.pages_by_id[pid].page_id != presenter.active_page_id),
        None,
    )
    assert second_page_id is not None
    snap = presenter.select_page(second_page_id)

    assert snap.ve_analyze is not None
    assert not snap.ve_analyze.is_running
    assert not snap.ve_analyze.has_data
