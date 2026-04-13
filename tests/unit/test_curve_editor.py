"""Tests for the CurveEditorWidget service layer: CurvePageSnapshot, stage_curve_cell,
undo/redo, and multi-line curve support.

These tests exercise the presenter's CurvePageSnapshot building and staging path
without touching any Qt widgets.
"""
from __future__ import annotations

import pytest

from tuner.domain.ecu_definition import (
    CurveDefinition,
    CurveYBins,
    EcuDefinition,
    TableDefinition,
)
from tuner.domain.tune import TuneFile, TuneValue
from tuner.domain.tuning_pages import TuningPageKind, TuningPageStateKind
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wue_curve() -> CurveDefinition:
    return CurveDefinition(
        name="warmup_curve",
        title="Warmup Enrichment (WUE) Curve",
        x_bins_param="wueBins",
        x_channel="coolant",
        y_bins_list=[CurveYBins(param="wueRates")],
        x_label="Coolant Temp",
        y_label="WUE %",
        gauge="cltGauge",
    )


def _analyzer_curve() -> CurveDefinition:
    """Multi-line curve: current WUE + recommended WUE."""
    return CurveDefinition(
        name="warmup_analyzer_curve",
        title="WUE Analyzer",
        x_bins_param="wueBins",
        x_channel="coolant",
        y_bins_list=[
            CurveYBins(param="wueRates", label="Current WUE"),
            CurveYBins(param="wueRecommended", label="Recommended WUE"),
        ],
        x_label="Coolant Temp",
        y_label="WUE %",
    )


def _definition_with_curve(curve: CurveDefinition) -> EcuDefinition:
    return EcuDefinition(
        name="test",
        tables=[
            TableDefinition(
                name="wueBins",
                rows=1, columns=10,
                page=1, offset=0,
                units="°C",
                digits=0,
            ),
            TableDefinition(
                name="wueRates",
                rows=1, columns=10,
                page=1, offset=10,
                units="%",
                digits=1,
            ),
            TableDefinition(
                name="wueRecommended",
                rows=1, columns=10,
                page=1, offset=20,
                units="%",
                digits=1,
            ),
        ],
        curve_definitions=[curve],
    )


def _tune_with_wue() -> TuneFile:
    return TuneFile(constants=[
        TuneValue(name="wueBins",        value=[float(t) for t in range(-40, 61, 11)],  rows=1, cols=10, units="°C"),
        TuneValue(name="wueRates",       value=[170.0, 150.0, 130.0, 110.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0], rows=1, cols=10, units="%"),
        TuneValue(name="wueRecommended", value=[165.0, 145.0, 125.0, 108.0,  99.0,  99.0,  99.0,  99.0,  99.0,  99.0], rows=1, cols=10, units="%"),
    ])


def _presenter(curve: CurveDefinition | None = None) -> TuningWorkspacePresenter:
    c = curve or _wue_curve()
    defn = _definition_with_curve(c)
    tune = _tune_with_wue()
    svc = LocalTuneEditService()
    svc.set_tune_file(tune)
    p = TuningWorkspacePresenter(local_tune_edit_service=svc)
    p.load(defn, tune)
    # Navigate to the curve page — it is now in p.pages_by_id via load()
    curve_page_id = f"curve:{c.name}"
    p.select_page(curve_page_id)
    return p


# ---------------------------------------------------------------------------
# Snapshot is produced for CURVE pages
# ---------------------------------------------------------------------------

def test_curve_page_snapshot_is_produced() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert snap.table_page is None
    assert snap.parameter_page is None


def test_curve_page_kind_in_snapshot() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.active_page_kind == "curve"


def test_curve_page_title() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert snap.curve_page.title == "Warmup Enrichment (WUE) Curve"


def test_curve_page_x_label() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert snap.curve_page.x_label == "Coolant Temp"


def test_curve_page_x_channel() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert snap.curve_page.x_channel == "coolant"


def test_curve_page_y_param_names() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert "wueRates" in snap.curve_page.y_param_names


def test_curve_page_has_correct_row_count() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert len(snap.curve_page.rows) == 10


def test_curve_page_x_display_uses_bin_values() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    # wueBins starts at -40
    assert snap.curve_page.rows[0].x_display == "-40"


def test_curve_page_y_display_uses_tune_values() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    # wueRates[0] = 170.0, digits=1
    assert snap.curve_page.rows[0].y_displays[0] == "170.0"


def test_curve_page_initial_state_is_clean() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert snap.curve_page.state.kind == TuningPageStateKind.CLEAN


# ---------------------------------------------------------------------------
# stage_curve_cell
# ---------------------------------------------------------------------------

def test_stage_curve_cell_changes_state_to_staged() -> None:
    p = _presenter()
    snap = p.stage_curve_cell("wueRates", 0, "180.0")
    assert snap.curve_page is not None
    assert snap.curve_page.state.kind == TuningPageStateKind.STAGED


def test_stage_curve_cell_updates_y_display() -> None:
    p = _presenter()
    snap = p.stage_curve_cell("wueRates", 0, "180.0")
    assert snap.curve_page is not None
    assert snap.curve_page.rows[0].y_displays[0] == "180.0"


def test_stage_curve_cell_marks_row_as_staged() -> None:
    p = _presenter()
    snap = p.stage_curve_cell("wueRates", 0, "180.0")
    assert snap.curve_page is not None
    assert snap.curve_page.rows[0].is_staged[0] is True


def test_stage_curve_cell_column_staged_for_all_rows() -> None:
    """Once any cell in wueRates is staged the whole column is considered staged.
    This mirrors TunerStudio's per-parameter (column-level) staged highlighting.
    """
    p = _presenter()
    snap = p.stage_curve_cell("wueRates", 0, "180.0")
    assert snap.curve_page is not None
    # All rows in the wueRates column are considered staged once any cell is edited
    for row in snap.curve_page.rows:
        assert row.is_staged[0] is True


def test_stage_curve_cell_preserves_other_rows() -> None:
    p = _presenter()
    snap = p.stage_curve_cell("wueRates", 2, "125.0")
    assert snap.curve_page is not None
    # Row 0 should still have original value 170.0
    assert snap.curve_page.rows[0].y_displays[0] == "170.0"


def test_stage_curve_cell_x_column_unchanged() -> None:
    p = _presenter()
    snap = p.stage_curve_cell("wueRates", 0, "180.0")
    assert snap.curve_page is not None
    # X display is always read from wueBins, unaffected by y edit
    assert snap.curve_page.rows[0].x_display == "-40"


def test_stage_curve_cell_invalid_value_marks_page_invalid() -> None:
    p = _presenter()
    snap = p.stage_curve_cell("wueRates", 0, "not-a-number")
    assert snap.curve_page is not None
    assert snap.curve_page.state.kind == TuningPageStateKind.INVALID


def test_stage_curve_cell_noop_on_wrong_page_kind() -> None:
    """stage_curve_cell is a no-op when no curve page is active."""
    defn = EcuDefinition(
        name="test",
        tables=[TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, units="%")],
    )
    tune = TuneFile(constants=[TuneValue(name="veTable", value=[10.0, 20.0, 30.0, 40.0], rows=2, cols=2)])
    svc = LocalTuneEditService()
    svc.set_tune_file(tune)
    p = TuningWorkspacePresenter(local_tune_edit_service=svc)
    p.load(defn, tune)
    snap = p.stage_curve_cell("veTable", 0, "99.0")
    # No curve page, so the call is a no-op
    assert snap.curve_page is None


# ---------------------------------------------------------------------------
# Undo / redo
# ---------------------------------------------------------------------------

def test_undo_curve_param_restores_original() -> None:
    p = _presenter()
    p.stage_curve_cell("wueRates", 0, "180.0")
    snap = p.undo_curve_param("wueRates")
    assert snap.curve_page is not None
    assert snap.curve_page.rows[0].y_displays[0] == "170.0"


def test_undo_curve_param_restores_display_value() -> None:
    """After undo the y-display is restored to the original tune value.
    The page may still be marked STAGED (the parameter stays in staged_values
    after undo — undo restores the value, not the staged-vs-clean state).
    """
    p = _presenter()
    p.stage_curve_cell("wueRates", 0, "180.0")
    snap = p.undo_curve_param("wueRates")
    assert snap.curve_page is not None
    assert snap.curve_page.rows[0].y_displays[0] == "170.0"


def test_redo_curve_param_re_applies_staged_value() -> None:
    p = _presenter()
    p.stage_curve_cell("wueRates", 0, "180.0")
    p.undo_curve_param("wueRates")
    snap = p.redo_curve_param("wueRates")
    assert snap.curve_page is not None
    assert snap.curve_page.rows[0].y_displays[0] == "180.0"


def test_curve_can_undo_after_stage() -> None:
    p = _presenter()
    p.stage_curve_cell("wueRates", 0, "180.0")
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert snap.curve_page.can_undo is True


def test_curve_cannot_undo_before_any_stage() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert snap.curve_page.can_undo is False


def test_curve_can_redo_after_undo() -> None:
    p = _presenter()
    p.stage_curve_cell("wueRates", 0, "180.0")
    p.undo_curve_param("wueRates")
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert snap.curve_page.can_redo is True


# ---------------------------------------------------------------------------
# Multi-line curve (two y-params)
# ---------------------------------------------------------------------------

def test_multi_line_curve_has_two_y_param_names() -> None:
    p = _presenter(_analyzer_curve())
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert len(snap.curve_page.y_param_names) == 2
    assert "wueRates" in snap.curve_page.y_param_names
    assert "wueRecommended" in snap.curve_page.y_param_names


def test_multi_line_curve_rows_have_two_y_displays() -> None:
    p = _presenter(_analyzer_curve())
    snap = p.snapshot()
    assert snap.curve_page is not None
    for row in snap.curve_page.rows:
        assert len(row.y_displays) == 2


def test_multi_line_curve_y_labels() -> None:
    p = _presenter(_analyzer_curve())
    snap = p.snapshot()
    assert snap.curve_page is not None
    assert "Current WUE" in snap.curve_page.y_labels
    assert "Recommended WUE" in snap.curve_page.y_labels


def test_multi_line_curve_stage_first_y_column() -> None:
    p = _presenter(_analyzer_curve())
    snap = p.stage_curve_cell("wueRates", 0, "180.0")
    assert snap.curve_page is not None
    assert snap.curve_page.rows[0].y_displays[0] == "180.0"
    # Second column (wueRecommended) unchanged
    assert snap.curve_page.rows[0].y_displays[1] == "165.0"


def test_multi_line_curve_stage_second_y_column() -> None:
    p = _presenter(_analyzer_curve())
    snap = p.stage_curve_cell("wueRecommended", 0, "160.0")
    assert snap.curve_page is not None
    assert snap.curve_page.rows[0].y_displays[1] == "160.0"
    # First column unchanged
    assert snap.curve_page.rows[0].y_displays[0] == "170.0"


def test_multi_line_curve_staged_flag_per_column() -> None:
    """Staging wueRates marks column 0 staged; wueRecommended column 1 is not."""
    p = _presenter(_analyzer_curve())
    snap = p.stage_curve_cell("wueRates", 0, "180.0")
    assert snap.curve_page is not None
    assert snap.curve_page.rows[0].is_staged[0] is True
    assert snap.curve_page.rows[0].is_staged[1] is False


# ---------------------------------------------------------------------------
# Diff summary
# ---------------------------------------------------------------------------

def test_curve_diff_summary_after_stage() -> None:
    p = _presenter()
    snap = p.stage_curve_cell("wueRates", 0, "180.0")
    assert snap.curve_page is not None
    assert "staged" in snap.curve_page.diff_summary.lower() or "change" in snap.curve_page.diff_summary.lower()


def test_curve_diff_summary_clean_when_no_edits() -> None:
    p = _presenter()
    snap = p.snapshot()
    assert snap.curve_page is not None
    # No staged changes — diff service returns a "no changes" message, not empty string
    assert "staged" not in snap.curve_page.diff_summary.lower() or "no staged" in snap.curve_page.diff_summary.lower()
