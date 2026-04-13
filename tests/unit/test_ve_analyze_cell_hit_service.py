"""Tests for VeAnalyzeCellHitService and VeAnalyzeCellHitAccumulator.

Covers:
- Correction factor math (lambda-based)
- AFR-channel records converted to lambda correctly
- Minimum sample gating per cell
- Confidence level assignment
- VE clamping at ve_min / ve_max
- Accumulator stateful feeding and reset
- Batch service passes same results as manual accumulator feeding
- Rejected records track correct gate names
- Empty log produces zero-data summary
- Proposals only generated for cells passing min_samples threshold
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalyzeCellHitAccumulator,
    VeAnalyzeCellHitService,
)

_NOW = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
_NO_GATE_CONFIG = SampleGatingConfig(enabled_gates=frozenset())  # disable all gates


def _snapshot(
    rows: int = 2,
    columns: int = 3,
    cells: list[list[str]] | None = None,
    x_labels: tuple[str, ...] = ("500", "1000", "1500"),
    y_labels: tuple[str, ...] = ("30", "60"),
    x_param: str = "rpmBins",
    y_param: str = "loadBins",
) -> TablePageSnapshot:
    if cells is None:
        cells = [["50", "55", "60"], ["65", "70", "75"]]
    return TablePageSnapshot(
        page_id="table-editor:ve",
        group_id="fuel",
        title="VE Table",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="",
        validation_summary="",
        diff_summary="",
        diff_text="",
        diff_entries=(),
        axis_summary="",
        details_text="",
        help_topic=None,
        x_parameter_name=x_param,
        y_parameter_name=y_param,
        x_labels=x_labels,
        y_labels=y_labels,
        table_model=TableViewModel(rows=rows, columns=columns, cells=cells),
        auxiliary_sections=(),
        can_undo=False,
        can_redo=False,
    )


def _rec(rpm: float, map_: float, lambda_: float | None = None, afr: float | None = None, **extra: float) -> DataLogRecord:
    values: dict[str, float] = {"rpm": rpm, "map": map_}
    if lambda_ is not None:
        values["lambda"] = lambda_
    if afr is not None:
        values["afr"] = afr
    values.update(extra)
    return DataLogRecord(timestamp=_NOW, values=values)


# ---------------------------------------------------------------------------
# Correction factor math
# ---------------------------------------------------------------------------

class TestCorrectionFactor:
    def test_lean_sample_produces_correction_above_one(self) -> None:
        """Lean running → measured lambda > target → correction > 1 → increase VE."""
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.1)])
        snap = _snapshot()
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log,
            ve_table_snapshot=snap,
            lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG,
            min_samples_for_correction=1,
        )
        assert result.accepted_records == 1
        assert len(result.cell_corrections) == 1
        cf = result.cell_corrections[0].mean_correction_factor
        assert pytest.approx(cf, abs=0.001) == 1.1  # 1.1 / 1.0

    def test_rich_sample_produces_correction_below_one(self) -> None:
        """Rich running → measured lambda < target → correction < 1 → decrease VE."""
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=0.9)])
        snap = _snapshot()
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        cf = result.cell_corrections[0].mean_correction_factor
        assert pytest.approx(cf, abs=0.001) == 0.9

    def test_stoich_sample_produces_correction_of_one(self) -> None:
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.0)])
        snap = _snapshot()
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        assert pytest.approx(result.cell_corrections[0].mean_correction_factor, abs=0.001) == 1.0

    def test_mean_correction_is_arithmetic_mean(self) -> None:
        """Two samples in the same cell → mean correction."""
        log = DataLog(name="t", records=[
            _rec(900.0, 45.0, lambda_=1.1),
            _rec(950.0, 45.0, lambda_=0.9),
        ])
        snap = _snapshot()
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        # Both map to same cell; mean = (1.1 + 0.9) / 2 = 1.0
        assert pytest.approx(result.cell_corrections[0].mean_correction_factor, abs=0.001) == 1.0

    def test_custom_lambda_target(self) -> None:
        """Non-stoich target shifts the correction factor accordingly."""
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.1)])
        snap = _snapshot()
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.1,  # target is what we see
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        assert pytest.approx(result.cell_corrections[0].mean_correction_factor, abs=0.001) == 1.0

    def test_afr_channel_converted_to_lambda(self) -> None:
        """AFR channels are converted to lambda using 14.7 stoich."""
        # afr=14.7 → lambda=1.0, target=1.0 → correction=1.0
        log = DataLog(name="t", records=[_rec(900.0, 45.0, afr=14.7)])
        snap = _snapshot()
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        assert result.accepted_records == 1
        assert pytest.approx(result.cell_corrections[0].mean_correction_factor, abs=0.01) == 1.0

    def test_afr_lean_correction(self) -> None:
        # afr=16.17 → lambda≈1.1; target=1.0 → correction≈1.1
        log = DataLog(name="t", records=[_rec(900.0, 45.0, afr=16.17)])
        snap = _snapshot()
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        cf = result.cell_corrections[0].mean_correction_factor
        assert pytest.approx(cf, abs=0.01) == 1.1


# ---------------------------------------------------------------------------
# Proposed VE value calculation
# ---------------------------------------------------------------------------

class TestProposedVe:
    def test_proposed_ve_applies_correction_to_current(self) -> None:
        """proposed_ve = current_ve × mean_correction, rounded."""
        # Cell (0, 0): current VE = 50, lean λ=1.1 → proposed = 50 × 1.1 = 55.0
        log = DataLog(name="t", records=[_rec(400.0, 25.0, lambda_=1.1)])
        snap = _snapshot(x_labels=("500", "1000", "1500"), y_labels=("30", "60"))
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        assert len(result.proposals) == 1
        p = result.proposals[0]
        assert p.current_ve == 50.0
        assert pytest.approx(p.proposed_ve, abs=0.1) == 55.0

    def test_proposed_ve_clamped_at_max(self) -> None:
        snap = _snapshot(cells=[["95", "50", "50"], ["50", "50", "50"]])
        log = DataLog(name="t", records=[
            _rec(400.0, 25.0, lambda_=1.2),  # 95 × 1.2 = 114 → clamped to 100
        ])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
            ve_max=100.0,
        )
        assert result.proposals[0].proposed_ve == 100.0

    def test_proposed_ve_clamped_at_min(self) -> None:
        # current VE = 20, correction = 0.5 → raw proposed = 10.0 → clamped to ve_min=15
        snap = _snapshot(cells=[["20", "50", "50"], ["50", "50", "50"]])
        log = DataLog(name="t", records=[
            _rec(400.0, 25.0, lambda_=0.5),  # 20 × 0.5 = 10.0, below ve_min=15
        ])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
            ve_min=15.0,
        )
        assert result.proposals[0].proposed_ve == 15.0

    def test_no_proposal_when_cell_value_unparseable(self) -> None:
        snap = _snapshot(cells=[["--", "50", "50"], ["50", "50", "50"]])
        log = DataLog(name="t", records=[_rec(400.0, 25.0, lambda_=1.1)])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        assert len(result.proposals) == 0
        assert result.cell_corrections[0].proposed_ve is None
        assert result.cell_corrections[0].current_ve is None


# ---------------------------------------------------------------------------
# Minimum sample gating
# ---------------------------------------------------------------------------

class TestMinSampleGating:
    def test_no_proposal_below_min_samples(self) -> None:
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.1)])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log,
            ve_table_snapshot=_snapshot(),
            lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG,
            min_samples_for_correction=3,  # need 3, only have 1
        )
        assert len(result.proposals) == 0
        assert result.cell_corrections[0].proposed_ve is None
        assert result.cell_corrections[0].confidence == "insufficient"

    def test_proposal_at_exactly_min_samples(self) -> None:
        log = DataLog(name="t", records=[
            _rec(900.0, 45.0, lambda_=1.1),
            _rec(920.0, 45.0, lambda_=1.1),
            _rec(940.0, 45.0, lambda_=1.1),
        ])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=3,
        )
        assert len(result.proposals) == 1
        assert result.cell_corrections[0].confidence == "low"

    def test_min_samples_one_accepts_single_record(self) -> None:
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.0)])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        assert len(result.proposals) == 1


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------

class TestConfidenceLevels:
    def _run_n_samples(self, n: int) -> str:
        records = [_rec(900.0, 45.0, lambda_=1.0) for _ in range(n)]
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        return result.cell_corrections[0].confidence

    def test_insufficient(self) -> None:
        assert self._run_n_samples(1) == "insufficient"
        assert self._run_n_samples(2) == "insufficient"

    def test_low(self) -> None:
        assert self._run_n_samples(3) == "low"
        assert self._run_n_samples(9) == "low"

    def test_medium(self) -> None:
        assert self._run_n_samples(10) == "medium"
        assert self._run_n_samples(29) == "medium"

    def test_high(self) -> None:
        assert self._run_n_samples(30) == "high"
        assert self._run_n_samples(100) == "high"


# ---------------------------------------------------------------------------
# Gate rejection tracking
# ---------------------------------------------------------------------------

class TestGateRejections:
    def test_records_without_lambda_rejected(self) -> None:
        """Default gates include std_DeadLambda which rejects missing lambda."""
        log = DataLog(name="t", records=[_rec(900.0, 45.0)])  # no lambda/AFR
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(log=log, ve_table_snapshot=_snapshot())
        assert result.accepted_records == 0
        assert result.rejected_records == 1
        assert dict(result.rejection_counts_by_gate).get("std_DeadLambda") == 1

    def test_cold_coolant_rejected(self) -> None:
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.0, coolant=40.0)])
        cfg = SampleGatingConfig(enabled_gates=frozenset({"minCltFilter"}))
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(log=log, ve_table_snapshot=_snapshot(), gating_config=cfg)
        assert result.rejected_records == 1
        assert dict(result.rejection_counts_by_gate) == {"minCltFilter": 1}

    def test_accel_enrichment_rejected(self) -> None:
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.0, engine=16.0)])
        cfg = SampleGatingConfig(enabled_gates=frozenset({"accelFilter"}))
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(log=log, ve_table_snapshot=_snapshot(), gating_config=cfg)
        assert result.rejected_records == 1
        assert dict(result.rejection_counts_by_gate) == {"accelFilter": 1}

    def test_unmappable_axes_tracked(self) -> None:
        """Record with no RPM/MAP → can't map to cell → tracked as unmappable_axes."""
        log = DataLog(name="t", records=[
            DataLogRecord(timestamp=_NOW, values={"lambda": 1.0, "coolant": 80.0})
        ])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), gating_config=_NO_GATE_CONFIG,
        )
        assert result.rejected_records == 1
        assert dict(result.rejection_counts_by_gate).get("unmappable_axes") == 1


# ---------------------------------------------------------------------------
# Multiple cells
# ---------------------------------------------------------------------------

class TestMultipleCells:
    def test_samples_accumulate_in_separate_cells(self) -> None:
        log = DataLog(name="t", records=[
            _rec(400.0, 25.0, lambda_=1.05),   # → row 0, col 0 (nearest 30 kPa, 500 rpm)
            _rec(1100.0, 55.0, lambda_=0.95),  # → row 1, col 1 (nearest 60 kPa, 1000 rpm)
        ])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        assert result.cells_with_data == 2
        assert result.accepted_records == 2

    def test_proposals_only_for_cells_above_threshold(self) -> None:
        """3 samples in one cell, 1 in another; only the first gets a proposal."""
        log = DataLog(name="t", records=[
            _rec(400.0, 25.0, lambda_=1.1),
            _rec(400.0, 25.0, lambda_=1.1),
            _rec(400.0, 25.0, lambda_=1.1),
            _rec(1100.0, 55.0, lambda_=0.9),  # only 1 sample in this cell
        ])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=3,
        )
        assert result.cells_with_data == 2
        assert result.cells_with_proposals == 1
        assert len(result.proposals) == 1
        p = result.proposals[0]
        assert p.sample_count == 3


# ---------------------------------------------------------------------------
# Stateful accumulator
# ---------------------------------------------------------------------------

class TestAccumulator:
    def test_accumulator_accepts_records_incrementally(self) -> None:
        snap = _snapshot()
        acc = VeAnalyzeCellHitAccumulator()
        cfg = _NO_GATE_CONFIG

        acc.add_record(_rec(900.0, 45.0, lambda_=1.1), snap, gating_config=cfg)
        acc.add_record(_rec(920.0, 45.0, lambda_=0.9), snap, gating_config=cfg)

        assert acc.accepted_count == 2
        assert acc.rejected_count == 0

        summary = acc.snapshot(snap, min_samples_for_correction=1)
        assert summary.accepted_records == 2
        # Mean correction = (1.1 + 0.9) / 2 = 1.0
        cf = summary.cell_corrections[0].mean_correction_factor
        assert pytest.approx(cf, abs=0.001) == 1.0

    def test_accumulator_reset_clears_all_data(self) -> None:
        snap = _snapshot()
        acc = VeAnalyzeCellHitAccumulator()
        cfg = _NO_GATE_CONFIG

        acc.add_record(_rec(900.0, 45.0, lambda_=1.1), snap, gating_config=cfg)
        acc.reset()

        assert acc.accepted_count == 0
        summary = acc.snapshot(snap)
        assert summary.accepted_records == 0
        assert summary.cells_with_data == 0

    def test_accumulator_snapshot_does_not_clear_data(self) -> None:
        snap = _snapshot()
        acc = VeAnalyzeCellHitAccumulator()
        acc.add_record(_rec(900.0, 45.0, lambda_=1.0), snap, gating_config=_NO_GATE_CONFIG)

        _ = acc.snapshot(snap, min_samples_for_correction=1)
        # Calling snapshot again should return same data
        summary2 = acc.snapshot(snap, min_samples_for_correction=1)
        assert summary2.accepted_records == 1

    def test_accumulator_rejected_record_tracked(self) -> None:
        snap = _snapshot()
        acc = VeAnalyzeCellHitAccumulator()
        # Record has no lambda/AFR; with no-gate config it passes gates but
        # fails at lambda extraction
        acc.add_record(
            DataLogRecord(timestamp=_NOW, values={"rpm": 900.0, "map": 45.0}),
            snap,
            gating_config=_NO_GATE_CONFIG,
        )
        assert acc.rejected_count == 1
        assert acc.accepted_count == 0

    def test_accumulator_matches_batch_service(self) -> None:
        """Feeding records one at a time should produce same result as batch service."""
        records = [
            _rec(900.0, 45.0, lambda_=1.1),
            _rec(920.0, 45.0, lambda_=1.0),
            _rec(1100.0, 55.0, lambda_=0.95),
        ]
        log = DataLog(name="t", records=records)
        snap = _snapshot()

        # Batch
        batch = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=snap, lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )

        # Incremental
        acc = VeAnalyzeCellHitAccumulator()
        for record in records:
            acc.add_record(record, snap, gating_config=_NO_GATE_CONFIG)
        incremental = acc.snapshot(snap, min_samples_for_correction=1)

        assert batch.accepted_records == incremental.accepted_records
        assert batch.rejected_records == incremental.rejected_records
        assert batch.cells_with_data == incremental.cells_with_data
        assert batch.cells_with_proposals == incremental.cells_with_proposals


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_log_returns_zero_data(self) -> None:
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(log=DataLog(name="t", records=[]), ve_table_snapshot=_snapshot())
        assert result.total_records == 0
        assert result.accepted_records == 0
        assert result.cells_with_data == 0
        assert result.proposals == ()
        assert "0 accepted" in result.summary_text

    def test_summary_text_included_in_detail_lines(self) -> None:
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.0)])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), gating_config=_NO_GATE_CONFIG,
            min_samples_for_correction=1,
        )
        assert result.summary_text in result.detail_lines

    def test_proposals_appear_in_detail_lines(self) -> None:
        log = DataLog(name="t", records=[_rec(400.0, 25.0, lambda_=1.1)])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), lambda_target=1.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        detail = "\n".join(result.detail_lines)
        assert "Proposals:" in detail or "proposals" in detail.lower()

    def test_zero_lambda_target_guarded(self) -> None:
        """lambda_target=0 should not cause division by zero."""
        log = DataLog(name="t", records=[_rec(900.0, 45.0, lambda_=1.0)])
        svc = VeAnalyzeCellHitService()
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(), lambda_target=0.0,
            gating_config=_NO_GATE_CONFIG, min_samples_for_correction=1,
        )
        # Should not raise; correction factor falls back to lambda_target=1.0
        assert result.accepted_records == 1
