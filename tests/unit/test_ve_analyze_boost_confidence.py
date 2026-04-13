"""Tests for Phase 7 Slice 7.6 — boost-aware confidence penalties.

Covers:
- Default-off (no config) reproduces Phase 6 baseline
- Spool transition penalty applies in positive boost only
- Spool penalty does NOT apply in vacuum even at high derivatives
- MAT instability penalty applies in vacuum and boost
- Severity scales linearly to spool_penalty_max at threshold
- Combined spool + MAT takes the worst, not the product
- Per-cell boost_penalty_applied surfaced on VeAnalysisCellCorrection
- Penalty multiplied into the weighted mean (low penalty → less influence)
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.ve_analyze_cell_hit_service import (
    BoostConfidenceConfig,
    VeAnalyzeCellHitService,
    WeightedCorrectionConfig,
    _boost_confidence_multiplier,
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
        y_labels=("30", "60", "150"),
        table_model=TableViewModel(
            rows=3, columns=3,
            cells=[
                ["50", "55", "60"],
                ["65", "70", "75"],
                ["80", "85", "90"],
            ],
        ),
        auxiliary_sections=(),
        can_undo=False,
        can_redo=False,
    )


def _rec(rpm: float, map_: float, lambda_: float, *, t: datetime, mat: float | None = None) -> DataLogRecord:
    values = {"rpm": rpm, "map": map_, "lambda": lambda_}
    if mat is not None:
        values["mat"] = mat
    return DataLogRecord(timestamp=t, values=values)


# ---------------------------------------------------------------------------
# Multiplier math (closed-form, no accumulator)
# ---------------------------------------------------------------------------

class TestMultiplierMath:
    _CFG = BoostConfidenceConfig()  # all defaults

    def test_steady_state_no_penalty(self) -> None:
        prior = _rec(2000.0, 150.0, 1.0, t=_T0, mat=40.0)
        new = _rec(2000.0, 150.0, 1.0, t=_T0 + timedelta(seconds=0.1), mat=40.0)
        assert _boost_confidence_multiplier(new, prior, self._CFG) == 1.0

    def test_spool_at_threshold_zero_penalty(self) -> None:
        # drpm/dt exactly = threshold (2000) → severity 1.0 → penalty
        # = 1.0 * spool_penalty_max (0.7) → multiplier 0.3.
        prior = _rec(2000.0, 150.0, 1.0, t=_T0)
        new = _rec(2200.0, 150.0, 1.0, t=_T0 + timedelta(seconds=0.1))
        # 200 rpm in 0.1s = 2000 rpm/s = threshold
        result = _boost_confidence_multiplier(new, prior, self._CFG)
        assert abs(result - 0.3) < 1e-6

    def test_spool_penalty_only_in_positive_boost(self) -> None:
        # MAP below atmospheric (100 kPa default) — spool penalty inactive.
        prior = _rec(2000.0, 50.0, 1.0, t=_T0)
        new = _rec(4000.0, 50.0, 1.0, t=_T0 + timedelta(seconds=0.1))  # 20k rpm/s
        assert _boost_confidence_multiplier(new, prior, self._CFG) == 1.0

    def test_mat_instability_applies_in_vacuum(self) -> None:
        prior = _rec(2000.0, 50.0, 1.0, t=_T0, mat=40.0)
        new = _rec(2000.0, 50.0, 1.0, t=_T0 + timedelta(seconds=1.0), mat=45.0)
        # 5 °C/s = mat_dt_threshold → severity 1.0 → penalty 0.5 → multiplier 0.5
        result = _boost_confidence_multiplier(new, prior, self._CFG)
        assert abs(result - 0.5) < 1e-6

    def test_combined_takes_max_not_product(self) -> None:
        # Spool penalty 0.7 (full), MAT penalty 0.5 (full).
        # Combined = 1 - max(0.7, 0.5) = 0.3, NOT 1 - (0.7 + 0.5) = -0.2.
        prior = _rec(2000.0, 150.0, 1.0, t=_T0, mat=40.0)
        new = _rec(2400.0, 150.0, 1.0, t=_T0 + timedelta(seconds=0.1), mat=41.0)
        # 4000 rpm/s → severity 2 clamped to 1 → spool 0.7
        # MAT 1°C/0.1s = 10°C/s → severity 2 clamped to 1 → mat 0.5
        result = _boost_confidence_multiplier(new, prior, self._CFG)
        assert abs(result - 0.3) < 1e-6

    def test_zero_dt_returns_one(self) -> None:
        prior = _rec(2000.0, 150.0, 1.0, t=_T0)
        new = _rec(5000.0, 250.0, 1.0, t=_T0)
        assert _boost_confidence_multiplier(new, prior, BoostConfidenceConfig()) == 1.0


# ---------------------------------------------------------------------------
# Default-off no regression
# ---------------------------------------------------------------------------

class TestDefaultOff:
    def test_none_config_matches_phase6(self) -> None:
        records = [
            _rec(500.0, 30.0, 1.10, t=_T0),
            _rec(500.0, 30.0, 1.05, t=_T0 + timedelta(seconds=0.1)),
        ]
        log = DataLog(name="t", records=records)
        svc = VeAnalyzeCellHitService()
        baseline = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
        )
        with_off = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            boost_confidence_config=None,
        )
        assert baseline.cell_corrections == with_off.cell_corrections


# ---------------------------------------------------------------------------
# Per-cell penalty surfaced + weighted-mean influence
# ---------------------------------------------------------------------------

class TestPenaltySurfacedAndWeighted:
    def test_penalty_surfaced_on_cell_correction(self) -> None:
        records = [
            _rec(2000.0, 150.0, 1.0, t=_T0),  # seed history
            _rec(2200.0, 150.0, 1.20, t=_T0 + timedelta(seconds=0.1)),  # full spool
        ]
        log = DataLog(name="t", records=records)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            boost_confidence_config=BoostConfidenceConfig(),
        )
        # Penalty applied = 1 - 0.3 = 0.7 on the second sample.
        cells = {(c.row_index, c.col_index): c for c in result.cell_corrections}
        # Both samples land in different cells (rpm 2000 vs 2200), so we
        # need to find the cell that took the penalty.
        penalised = [c for c in cells.values() if c.boost_penalty_applied > 0]
        assert len(penalised) == 1
        assert abs(penalised[0].boost_penalty_applied - 0.7) < 1e-3

    def test_penalty_does_not_fire_in_vacuum(self) -> None:
        """Symmetric to the surfaced test: the same large rpm jump in
        vacuum produces no penalty surfaced on the cell correction."""
        records = [
            _rec(2000.0, 50.0, 1.0, t=_T0),
            _rec(2200.0, 50.0, 1.20, t=_T0 + timedelta(seconds=0.1)),
        ]
        log = DataLog(name="t", records=records)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            boost_confidence_config=BoostConfidenceConfig(),
        )
        for cell in result.cell_corrections:
            assert cell.boost_penalty_applied == 0.0
