"""Tests for Phase 7 Slice 7.2 — per-cell weighted correction with bounded edits.

Covers:
- Default-off WeightedCorrectionConfig reproduces Phase 6 arithmetic mean exactly
- max_correction_per_cell clamps lean and rich extremes; clamp_applied flag set
- raw_correction_factor surfaces the pre-clamp value when clamped
- Dwell weighting: longer time-in-cell increases sample weight
- Sample-age decay: older samples contribute less to the weighted mean
- Clamp does not move proposals when raw mean is already inside bounds
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalyzeCellHitService,
    WeightedCorrectionConfig,
)

_T0 = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset())


def _snapshot() -> TablePageSnapshot:
    return TablePageSnapshot(
        page_id="ve",
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
        x_parameter_name="rpmBins",
        y_parameter_name="loadBins",
        x_labels=("500", "1000", "1500"),
        y_labels=("30", "60"),
        table_model=TableViewModel(
            rows=2, columns=3,
            cells=[["50", "55", "60"], ["65", "70", "75"]],
        ),
        auxiliary_sections=(),
        can_undo=False,
        can_redo=False,
    )


def _rec(rpm: float, map_: float, lambda_: float, *, t: datetime = _T0) -> DataLogRecord:
    return DataLogRecord(timestamp=t, values={"rpm": rpm, "map": map_, "lambda": lambda_})


def _all_into_first_cell(lambdas: list[float], *, dt_seconds: float = 0.0) -> list[DataLogRecord]:
    """Build a record list that maps every record to (row=0, col=0)."""
    return [
        _rec(500.0, 30.0, lam, t=_T0 + timedelta(seconds=i * dt_seconds))
        for i, lam in enumerate(lambdas)
    ]


# ---------------------------------------------------------------------------
# Default-off no-regression guarantee
# ---------------------------------------------------------------------------

class TestDefaultOffNoRegression:
    def test_none_config_matches_phase6_baseline(self) -> None:
        """Passing weighting_config=None must produce bit-identical output
        to the Phase 6 path that has no weighting code."""
        records = _all_into_first_cell([1.05, 1.10, 1.15])
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        baseline = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
        )
        explicit_off = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            weighting_config=WeightedCorrectionConfig(),
        )
        assert baseline.cell_corrections == explicit_off.cell_corrections
        assert baseline.proposals == explicit_off.proposals

    def test_default_config_clamp_field_is_none(self) -> None:
        cfg = WeightedCorrectionConfig()
        assert cfg.max_correction_per_cell is None
        assert cfg.dwell_weight_enabled is False
        assert cfg.sample_age_decay_per_second is None


# ---------------------------------------------------------------------------
# Per-cell max-correction clamp
# ---------------------------------------------------------------------------

class TestMaxCorrectionClamp:
    def test_lean_clamp_caps_proposed_correction(self) -> None:
        """A 50% lean correction with clamp 0.10 → effective correction 1.10."""
        records = _all_into_first_cell([1.5, 1.5, 1.5])  # 50% lean, three samples
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        cfg = WeightedCorrectionConfig(max_correction_per_cell=0.10)
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            weighting_config=cfg,
        )
        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.correction_factor == 1.10
        assert proposal.clamp_applied is True
        assert proposal.raw_correction_factor == 1.5
        # current 50 × 1.10 = 55.0
        assert proposal.proposed_ve == 55.0

    def test_rich_clamp_caps_proposed_correction(self) -> None:
        records = _all_into_first_cell([0.5, 0.5, 0.5])  # 50% rich
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        cfg = WeightedCorrectionConfig(max_correction_per_cell=0.10)
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            weighting_config=cfg,
        )
        proposal = result.proposals[0]
        assert proposal.correction_factor == 0.90
        assert proposal.clamp_applied is True
        assert proposal.raw_correction_factor == 0.5
        assert proposal.proposed_ve == 45.0  # 50 × 0.90

    def test_clamp_inactive_when_raw_inside_bounds(self) -> None:
        """A 5% correction with a 10% clamp must pass through unchanged
        and clamp_applied must be False."""
        records = _all_into_first_cell([1.05, 1.05, 1.05])
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        cfg = WeightedCorrectionConfig(max_correction_per_cell=0.10)
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            weighting_config=cfg,
        )
        proposal = result.proposals[0]
        assert proposal.correction_factor == 1.05
        assert proposal.clamp_applied is False
        assert proposal.raw_correction_factor is None  # only set when clamped

    def test_clamp_zero_pins_correction_to_one(self) -> None:
        """max_correction_per_cell=0 freezes the cell — useful as a
        do-not-touch sentinel."""
        records = _all_into_first_cell([1.20, 1.20])
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        cfg = WeightedCorrectionConfig(max_correction_per_cell=0.0)
        result = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            weighting_config=cfg,
        )
        proposal = result.proposals[0]
        assert proposal.correction_factor == 1.0
        assert proposal.clamp_applied is True
        assert proposal.proposed_ve == 50.0  # unchanged


# ---------------------------------------------------------------------------
# Dwell weighting
# ---------------------------------------------------------------------------

class TestDwellWeighting:
    def test_longer_dwell_increases_sample_influence(self) -> None:
        """Two samples with the same correction value have weight 1.0; a
        third sample arriving 1 s later in the same cell gets dwell weight
        1 + 1 = 2.0. The weighted mean should be pulled toward the dwell-
        weighted sample."""
        # Two leans (1.10) + one richer (0.90) at +1 s. Arithmetic mean is
        # (1.10+1.10+0.90)/3 ≈ 1.0333. Dwell-weighted: weights 1, 1, 2
        # → (1*1.10 + 1*1.10 + 2*0.90)/(1+1+2) = 4.0/4 = 1.00.
        records = [
            _rec(500.0, 30.0, 1.10, t=_T0),
            _rec(500.0, 30.0, 1.10, t=_T0),
            _rec(500.0, 30.0, 0.90, t=_T0 + timedelta(seconds=1.0)),
        ]
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        baseline = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
        )
        weighted = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            weighting_config=WeightedCorrectionConfig(dwell_weight_enabled=True),
        )
        assert baseline.proposals[0].correction_factor == round(31/30, 4)
        assert weighted.proposals[0].correction_factor == 1.0

    def test_dwell_weight_capped_so_long_pause_does_not_dominate(self) -> None:
        """A 60-second pause must not give the late sample 60× weight; the
        cap defaults to 2 s."""
        records = [
            _rec(500.0, 30.0, 1.20, t=_T0),
            _rec(500.0, 30.0, 0.80, t=_T0 + timedelta(seconds=60.0)),
        ]
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        weighted = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            weighting_config=WeightedCorrectionConfig(
                dwell_weight_enabled=True, dwell_weight_cap_seconds=2.0,
            ),
        )
        # Weights: 1.0, 1.0+2.0=3.0 → (1*1.20 + 3*0.80)/4 = 3.6/4 = 0.90.
        # Without the cap a 60 s pause would give 0.804.
        assert weighted.proposals[0].correction_factor == 0.90


# ---------------------------------------------------------------------------
# Sample-age decay
# ---------------------------------------------------------------------------

class TestSampleAgeDecay:
    def test_old_sample_contributes_less_after_decay(self) -> None:
        """An old lean sample (10 s back) and a recent rich sample with a
        decay constant that halves the old sample's weight should pull the
        weighted mean toward the recent value."""
        # decay = ln(2)/10 → 10 s old sample weight = 0.5
        import math
        decay = math.log(2) / 10.0
        records = [
            _rec(500.0, 30.0, 1.20, t=_T0),
            _rec(500.0, 30.0, 0.90, t=_T0 + timedelta(seconds=10.0)),
        ]
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        weighted = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            weighting_config=WeightedCorrectionConfig(
                sample_age_decay_per_second=decay,
            ),
        )
        # Weights: old=0.5, new=1.0 → (0.5*1.20 + 1.0*0.90)/1.5 = 1.50/1.5 = 1.0
        assert abs(weighted.proposals[0].correction_factor - 1.0) < 0.001
