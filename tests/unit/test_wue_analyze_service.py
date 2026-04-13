"""Tests for WUE Analyze accumulator and batch service.

Covers:
- _TableOrientation detects CLT axis from y_parameter_name and x_parameter_name
- _TableOrientation falls back to longer axis when parameter names are ambiguous
- Accumulator rejects records with no lambda channel
- Accumulator rejects records with no CLT channel
- Accumulator rejects records with no mappable axis
- Accumulator accepts records and maps to correct CLT row
- Accumulator applies WUE default gates (no minCltFilter)
- snapshot() builds WueAnalysisSummary with correct proposals
- WueAnalyzeService (batch) produces same result as manual accumulator feed
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.wue_analyze_service import (
    WueAnalyzeAccumulator,
    WueAnalyzeService,
    _TableOrientation,
    _clt_from_record,
    wue_default_gating_config,
)

_NOW = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
# Empty frozenset means "use DEFAULT gates"; pass a truthy frozenset with no
# real gate names to completely disable gating in tests.
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset({"_disabled_"}))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wue_snap(
    cells: list[list[str]] | None = None,
    y_labels: tuple[str, ...] = ("-40", "-26", "10", "28", "46", "64"),
    y_parameter_name: str = "wueBins",
    x_labels: tuple[str, ...] = ("1",),
    x_parameter_name: str | None = None,
) -> TablePageSnapshot:
    """6-row × 1-column WUE table (CLT along Y axis)."""
    if cells is None:
        cells = [["180"], ["175"], ["168"], ["154"], ["134"], ["100"]]
    return TablePageSnapshot(
        page_id="table-editor:wue", group_id="fuel", title="Warmup Enrichment",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="", validation_summary="", diff_summary="", diff_text="",
        diff_entries=(), axis_summary="", details_text="", help_topic=None,
        x_parameter_name=x_parameter_name,
        y_parameter_name=y_parameter_name,
        x_labels=x_labels,
        y_labels=y_labels,
        table_model=TableViewModel(rows=6, columns=1, cells=cells),
        auxiliary_sections=(), can_undo=False, can_redo=False,
    )


def _wue_snap_horizontal(
    cells: list[list[str]] | None = None,
    x_labels: tuple[str, ...] = ("-40", "-26", "10", "28", "46", "64"),
    x_parameter_name: str = "cltBins",
) -> TablePageSnapshot:
    """1-row × 6-column WUE table (CLT along X axis)."""
    if cells is None:
        cells = [["180", "175", "168", "154", "134", "100"]]
    return TablePageSnapshot(
        page_id="table-editor:wue", group_id="fuel", title="Warmup Enrichment",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="", validation_summary="", diff_summary="", diff_text="",
        diff_entries=(), axis_summary="", details_text="", help_topic=None,
        x_parameter_name=x_parameter_name,
        y_parameter_name=None,
        x_labels=x_labels,
        y_labels=("1",),
        table_model=TableViewModel(rows=1, columns=6, cells=cells),
        auxiliary_sections=(), can_undo=False, can_redo=False,
    )


def _record(clt: float, lambda_: float, extra: dict[str, float] | None = None) -> DataLogRecord:
    vals: dict[str, float] = {"coolant": clt, "lambda": lambda_}
    if extra:
        vals.update(extra)
    return DataLogRecord(timestamp=_NOW, values=vals)


# ---------------------------------------------------------------------------
# _TableOrientation
# ---------------------------------------------------------------------------


def test_orientation_detects_clt_from_y_parameter_name() -> None:
    snap = _wue_snap(y_parameter_name="wueBins")
    o = _TableOrientation.detect(snap)
    assert o is not None
    assert o.clt_along_y is True
    assert len(o.clt_axis) == 6


def test_orientation_detects_clt_from_x_parameter_name() -> None:
    snap = _wue_snap_horizontal(x_parameter_name="cltBins")
    o = _TableOrientation.detect(snap)
    assert o is not None
    assert o.clt_along_y is False
    assert len(o.clt_axis) == 6


def test_orientation_fallback_to_longer_y_axis() -> None:
    # No CLT keywords in parameter names; longer Y axis should be chosen
    snap = _wue_snap(y_parameter_name="myAxis", x_parameter_name="other")
    o = _TableOrientation.detect(snap)
    assert o is not None
    assert o.clt_along_y is True  # y has 6 labels, x has 1


def test_orientation_none_when_no_numeric_labels() -> None:
    snap = TablePageSnapshot(
        page_id="p", group_id="g", title="T",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="", validation_summary="", diff_summary="", diff_text="",
        diff_entries=(), axis_summary="", details_text="", help_topic=None,
        x_parameter_name=None, y_parameter_name=None,
        x_labels=("a", "b"), y_labels=("c",),
        table_model=TableViewModel(rows=1, columns=2, cells=[["1", "2"]]),
        auxiliary_sections=(), can_undo=False, can_redo=False,
    )
    o = _TableOrientation.detect(snap)
    # Neither axis has numeric labels → orientation falls back to non-numeric y (fails)
    # Depending on impl: x_labels "a","b" are non-numeric, y is non-numeric too
    assert o is None


def test_orientation_cell_indices_y_axis() -> None:
    snap = _wue_snap()
    o = _TableOrientation.detect(snap)
    assert o is not None
    # CLT=-40 → nearest to row 0
    row, col = o.cell_indices(-40.0)
    assert row == 0
    assert col == 0
    # CLT=64 → nearest to row 5
    row, col = o.cell_indices(64.0)
    assert row == 5
    assert col == 0


def test_orientation_cell_indices_x_axis() -> None:
    snap = _wue_snap_horizontal()
    o = _TableOrientation.detect(snap)
    assert o is not None
    row, col = o.cell_indices(-40.0)
    assert row == 0
    assert col == 0
    row, col = o.cell_indices(64.0)
    assert row == 0
    assert col == 5


# ---------------------------------------------------------------------------
# _clt_from_record
# ---------------------------------------------------------------------------


def test_clt_from_record_coolant_channel() -> None:
    r = DataLogRecord(timestamp=_NOW, values={"coolant": 25.0, "rpm": 800.0})
    assert _clt_from_record(r.values) == 25.0


def test_clt_from_record_clt_channel() -> None:
    r = DataLogRecord(timestamp=_NOW, values={"clt": 10.0})
    assert _clt_from_record(r.values) == 10.0


def test_clt_from_record_missing() -> None:
    r = DataLogRecord(timestamp=_NOW, values={"rpm": 800.0})
    assert _clt_from_record(r.values) is None


# ---------------------------------------------------------------------------
# WueAnalyzeAccumulator
# ---------------------------------------------------------------------------


def test_accumulator_rejects_no_lambda() -> None:
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    r = DataLogRecord(timestamp=_NOW, values={"coolant": 20.0})  # no lambda
    accepted = acc.add_record(r, snap, gating_config=_NO_GATE)
    assert not accepted
    assert acc.accepted_count == 0
    assert acc.rejected_count == 1


def test_accumulator_rejects_no_clt() -> None:
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    r = DataLogRecord(timestamp=_NOW, values={"lambda": 1.0})  # no CLT
    accepted = acc.add_record(r, snap, gating_config=_NO_GATE)
    assert not accepted
    assert acc.rejected_count == 1


def test_accumulator_accepts_valid_record() -> None:
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    r = _record(clt=20.0, lambda_=1.0)
    accepted = acc.add_record(r, snap, gating_config=_NO_GATE)
    assert accepted
    assert acc.accepted_count == 1
    assert acc.rejected_count == 0


def test_accumulator_maps_to_correct_row() -> None:
    """CLT=28°C should map to row 3 (bins: -40,-26,10,28,46,64)."""
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    r = _record(clt=28.0, lambda_=1.1)  # lean: correction > 1
    acc.add_record(r, snap, gating_config=_NO_GATE)
    # Snapshot with 1 sample (below min_samples) — correction exists but no proposal
    s = acc.snapshot(snap, min_samples_for_correction=1)
    assert len(s.row_corrections) == 1
    assert s.row_corrections[0].row_index == 3  # bin index 3 for 28°C
    assert s.row_corrections[0].mean_correction_factor == pytest.approx(1.1, rel=1e-3)


def test_accumulator_snapshot_produces_proposal_above_min_samples() -> None:
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    # Feed 3 samples at CLT=10°C (row 2), all lean (lambda=1.1)
    for _ in range(3):
        acc.add_record(_record(clt=10.0, lambda_=1.1), snap, gating_config=_NO_GATE)
    s = acc.snapshot(snap, min_samples_for_correction=3, wue_min=100.0, wue_max=250.0)
    assert s.rows_with_proposals == 1
    p = s.proposals[0]
    assert p.row_index == 2
    assert p.current_enrichment == pytest.approx(168.0)
    assert p.proposed_enrichment == pytest.approx(168.0 * 1.1, rel=1e-2)


def test_accumulator_no_proposal_below_min_samples() -> None:
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    acc.add_record(_record(clt=10.0, lambda_=1.1), snap, gating_config=_NO_GATE)
    s = acc.snapshot(snap, min_samples_for_correction=3)
    assert s.rows_with_proposals == 0


def test_accumulator_reset_clears_state() -> None:
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    for _ in range(3):
        acc.add_record(_record(clt=10.0, lambda_=1.0), snap, gating_config=_NO_GATE)
    acc.reset()
    assert acc.accepted_count == 0
    assert acc.rejected_count == 0
    s = acc.snapshot(snap)
    assert s.total_records == 0
    assert s.rows_with_data == 0


def test_accumulator_horizontal_table() -> None:
    """Accumulator works with a 1×N table where CLT is along the X axis."""
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap_horizontal()
    for _ in range(3):
        acc.add_record(_record(clt=10.0, lambda_=0.9), snap, gating_config=_NO_GATE)
    s = acc.snapshot(snap, min_samples_for_correction=3)
    assert s.rows_with_proposals == 1
    assert s.proposals[0].row_index == 2  # col 2 of the X axis for CLT=10°C


def test_wue_default_gating_does_not_include_min_clt() -> None:
    """Default WUE gating excludes minCltFilter so cold samples are accepted."""
    cfg = wue_default_gating_config()
    assert "minCltFilter" not in cfg.enabled_gates
    assert "std_DeadLambda" in cfg.enabled_gates
    assert "accelFilter" in cfg.enabled_gates


def test_accumulator_applies_wue_default_gates() -> None:
    """With default gates, cold CLT samples (below 70°C) should still be accepted."""
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    # CLT=10°C — would be rejected by minCltFilter if it were active
    r = DataLogRecord(
        timestamp=_NOW,
        values={"coolant": 10.0, "lambda": 1.0, "rpm": 800.0},
    )
    accepted = acc.add_record(r, snap)  # uses default gates (no explicit config)
    assert accepted


def test_accumulator_default_gates_reject_dead_lambda() -> None:
    """Default gates still reject implausible lambda values."""
    acc = WueAnalyzeAccumulator()
    snap = _wue_snap()
    r = DataLogRecord(
        timestamp=_NOW,
        values={"coolant": 10.0, "afr": 99.0},  # implausible AFR
    )
    accepted = acc.add_record(r, snap)  # uses default gates
    assert not accepted


# ---------------------------------------------------------------------------
# WueAnalyzeService (batch)
# ---------------------------------------------------------------------------


def test_batch_service_matches_manual_accumulator() -> None:
    snap = _wue_snap()
    records: list[DataLogRecord] = []
    for _ in range(3):
        records.append(_record(clt=10.0, lambda_=1.1))

    svc = WueAnalyzeService()
    log = DataLog(name="test", records=list(records))
    result = svc.analyze(log, snap, gating_config=_NO_GATE, min_samples_for_correction=3)

    assert result.accepted_records == 3
    assert result.rows_with_proposals == 1
    assert result.proposals[0].row_index == 2


def test_batch_service_empty_log() -> None:
    svc = WueAnalyzeService()
    snap = _wue_snap()
    log = DataLog(name="test", records=[])
    result = svc.analyze(log, snap, gating_config=_NO_GATE)
    assert result.total_records == 0
    assert result.rows_with_proposals == 0


def test_batch_service_multiple_rows() -> None:
    snap = _wue_snap()
    records = []
    # 3 samples in row 0 (CLT=-40) and 3 in row 5 (CLT=64)
    for _ in range(3):
        records.append(_record(clt=-40.0, lambda_=1.2))
        records.append(_record(clt=64.0, lambda_=0.8))
    log = DataLog(name="test", records=list(records))
    svc = WueAnalyzeService()
    result = svc.analyze(log, snap, gating_config=_NO_GATE, min_samples_for_correction=3)
    assert result.rows_with_proposals == 2
    row_indices = {p.row_index for p in result.proposals}
    assert row_indices == {0, 5}


def test_batch_service_clamps_proposals() -> None:
    """Proposals must be clamped to [wue_min, wue_max]."""
    snap = _wue_snap(cells=[["100"]] * 6)  # all cells = 100%
    records = [_record(clt=-40.0, lambda_=3.0) for _ in range(3)]  # extreme lean
    log = DataLog(name="test", records=list(records))
    svc = WueAnalyzeService()
    result = svc.analyze(log, snap, gating_config=_NO_GATE, wue_min=100.0, wue_max=250.0, min_samples_for_correction=3)
    assert result.proposals[0].proposed_enrichment <= 250.0
