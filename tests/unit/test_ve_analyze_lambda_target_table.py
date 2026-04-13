"""Tests for per-cell lambda target table lookup in VeAnalyzeCellHitService.

Covers:
- Lambda-unit target table (values ≤ 2.0 used directly)
- AFR-unit target table (values > 2.0 divided by 14.7)
- Mixed table auto-detection per cell
- Scalar fallback when target snapshot is None
- Scalar fallback for unparseable cell
- Per-cell target varying across the table changes correction factors cell-by-cell
"""

from __future__ import annotations

import pytest

from datetime import UTC, datetime

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.ve_analyze_cell_hit_service import VeAnalyzeCellHitService

_NOW = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset())
_STOICH = 14.7


def _snap(cells: list[list[str]], x: tuple[str, ...] = ("500", "1000"),
          y: tuple[str, ...] = ("30", "60")) -> TablePageSnapshot:
    rows = len(cells)
    cols = len(cells[0]) if cells else 0
    return TablePageSnapshot(
        page_id="ve", group_id="fuel", title="VE Table",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="", validation_summary="", diff_summary="", diff_text="",
        diff_entries=(), axis_summary="", details_text="", help_topic=None,
        x_parameter_name="rpmBins", y_parameter_name="loadBins",
        x_labels=x, y_labels=y,
        table_model=TableViewModel(rows=rows, columns=cols, cells=cells),
        auxiliary_sections=(), can_undo=False, can_redo=False,
    )


def _rec(rpm: float, map_: float, lam: float) -> DataLogRecord:
    return DataLogRecord(timestamp=_NOW, values={"rpm": rpm, "map": map_, "lambda": lam})


def _log(*records: DataLogRecord) -> DataLog:
    return DataLog(name="t", records=list(records))


# ---------------------------------------------------------------------------
# Lambda-unit target table
# ---------------------------------------------------------------------------

def test_lambda_unit_target_used_directly() -> None:
    ve_snap = _snap([["50", "55"], ["60", "65"]])
    # target = 0.9 λ for all cells → correction = 1.0 / 0.9 ≈ 1.111
    target_snap = _snap([["0.9", "0.9"], ["0.9", "0.9"]])
    log = _log(_rec(400.0, 25.0, 1.0))
    svc = VeAnalyzeCellHitService()
    result = svc.analyze(
        log=log, ve_table_snapshot=ve_snap, lambda_target=1.0,
        lambda_target_snapshot=target_snap,
        gating_config=_NO_GATE, min_samples_for_correction=1,
    )
    assert result.accepted_records == 1
    cf = result.cell_corrections[0].mean_correction_factor
    assert pytest.approx(cf, abs=0.001) == 1.0 / 0.9


# ---------------------------------------------------------------------------
# AFR-unit target table (auto-detected by value > 2.0)
# ---------------------------------------------------------------------------

def test_afr_unit_target_converted_to_lambda() -> None:
    ve_snap = _snap([["50", "55"], ["60", "65"]])
    # AFR target = 13.23 → lambda = 13.23 / 14.7 ≈ 0.9; measured = 1.0 → cf ≈ 1.111
    target_snap = _snap([["13.23", "13.23"], ["13.23", "13.23"]])
    log = _log(_rec(400.0, 25.0, 1.0))
    svc = VeAnalyzeCellHitService()
    result = svc.analyze(
        log=log, ve_table_snapshot=ve_snap,
        lambda_target_snapshot=target_snap,
        gating_config=_NO_GATE, min_samples_for_correction=1,
    )
    cf = result.cell_corrections[0].mean_correction_factor
    assert pytest.approx(cf, abs=0.005) == 1.0 / (13.23 / _STOICH)


# ---------------------------------------------------------------------------
# Scalar fallback when no target snapshot
# ---------------------------------------------------------------------------

def test_scalar_fallback_when_no_target_snapshot() -> None:
    ve_snap = _snap([["50", "55"], ["60", "65"]])
    log = _log(_rec(400.0, 25.0, 1.1))
    svc = VeAnalyzeCellHitService()
    result = svc.analyze(
        log=log, ve_table_snapshot=ve_snap, lambda_target=1.0,
        lambda_target_snapshot=None,  # explicit None
        gating_config=_NO_GATE, min_samples_for_correction=1,
    )
    assert pytest.approx(result.cell_corrections[0].mean_correction_factor, abs=0.001) == 1.1


# ---------------------------------------------------------------------------
# Scalar fallback for unparseable cell
# ---------------------------------------------------------------------------

def test_scalar_fallback_for_unparseable_target_cell() -> None:
    ve_snap = _snap([["50", "55"], ["60", "65"]])
    target_snap = _snap([["--", "0.9"], ["0.9", "0.9"]])  # (0,0) is unparseable
    log = _log(_rec(400.0, 25.0, 1.1))  # maps to cell (0,0)
    svc = VeAnalyzeCellHitService()
    result = svc.analyze(
        log=log, ve_table_snapshot=ve_snap,
        lambda_target=1.0,  # scalar fallback for bad cell
        lambda_target_snapshot=target_snap,
        gating_config=_NO_GATE, min_samples_for_correction=1,
    )
    # Should use scalar lambda_target=1.0 → correction = 1.1
    cf = result.cell_corrections[0].mean_correction_factor
    assert pytest.approx(cf, abs=0.001) == 1.1


# ---------------------------------------------------------------------------
# Per-cell targets vary correction factor per cell
# ---------------------------------------------------------------------------

def test_per_cell_targets_differ_between_cells() -> None:
    ve_snap = _snap([["50", "50"], ["50", "50"]])
    # Different targets per cell
    target_snap = _snap([["0.9", "1.0"], ["1.1", "0.8"]])
    measured = 1.0  # same measured lambda for all records

    records = [
        _rec(400.0, 25.0, measured),   # → cell (0,0), target=0.9 → cf≈1.111
        _rec(900.0, 25.0, measured),   # → cell (0,1), target=1.0 → cf=1.0
    ]
    log = DataLog(name="t", records=records)
    svc = VeAnalyzeCellHitService()
    result = svc.analyze(
        log=log, ve_table_snapshot=ve_snap,
        lambda_target_snapshot=target_snap,
        gating_config=_NO_GATE, min_samples_for_correction=1,
    )
    cell_map = {(c.row_index, c.col_index): c.mean_correction_factor
                for c in result.cell_corrections}

    assert pytest.approx(cell_map[(0, 0)], abs=0.005) == 1.0 / 0.9  # lean target
    assert pytest.approx(cell_map[(0, 1)], abs=0.001) == 1.0         # stoich target
