"""Tests for Phase 7 Slice 7.4 — steady-state refinements with EGO transport
delay compensation and explicit derivative gating.

Covers:
- Default-off SteadyStateConfig reproduces Phase 6 baseline exactly
- EGO transport-delay compensation pairs current lambda with delayed engine
  state (verified by a record at one cell whose lambda is meant to be
  attributed to a different cell delay seconds earlier)
- delay_buffer_cold rejection until the history window covers the delay
- max_drpm_per_second rejects high-derivative samples; below threshold passes
- max_dmap_per_second rejects high-derivative samples
- History buffer trimmed to history_window_seconds
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.ve_analyze_cell_hit_service import (
    SteadyStateConfig,
    VeAnalyzeCellHitAccumulator,
    VeAnalyzeCellHitService,
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


def _rec(rpm: float, map_: float, lambda_: float, *, t: datetime) -> DataLogRecord:
    return DataLogRecord(timestamp=t, values={"rpm": rpm, "map": map_, "lambda": lambda_})


# ---------------------------------------------------------------------------
# Default-off no-regression
# ---------------------------------------------------------------------------

class TestDefaultOffNoRegression:
    def test_none_config_matches_phase6_baseline(self) -> None:
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
        explicit_off = svc.analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            steady_state_config=SteadyStateConfig(),
        )
        assert baseline.cell_corrections == explicit_off.cell_corrections
        assert baseline.proposals == explicit_off.proposals

    def test_default_field_values(self) -> None:
        cfg = SteadyStateConfig()
        assert cfg.ego_transport_delay_seconds == 0.0
        assert cfg.max_drpm_per_second is None
        assert cfg.max_dmap_per_second is None
        assert cfg.history_window_seconds == 2.0


# ---------------------------------------------------------------------------
# EGO transport-delay compensation
# ---------------------------------------------------------------------------

class TestEgoTransportDelay:
    def test_lambda_is_paired_with_delayed_engine_state(self) -> None:
        """At t=0 the engine sits at (rpm=500, map=30) → cell (0,0).
        At t=0.5 the engine has moved to (rpm=1500, map=60) → cell (1,2)
        and the wideband finally sees the lean reading from the earlier
        operating point. With delay=0.5 s, that lean reading should be
        attributed to cell (0,0), not (1,2)."""
        records = [
            _rec(500.0, 30.0, 1.0, t=_T0),                              # warm history
            _rec(1500.0, 60.0, 1.20, t=_T0 + timedelta(seconds=0.5)),   # delayed lambda
        ]
        log = DataLog(name="t", records=records)
        cfg = SteadyStateConfig(ego_transport_delay_seconds=0.5)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            steady_state_config=cfg,
        )
        # The 1.20 lambda must be attributed to cell (0,0), not (1,2).
        cells = {(c.row_index, c.col_index): c for c in result.cell_corrections}
        assert (0, 0) in cells
        assert (1, 2) not in cells
        # The first record is dropped (no history to delay-pair against).
        assert cells[(0, 0)].sample_count == 1
        assert cells[(0, 0)].mean_correction_factor == 1.20

    def test_delay_buffer_cold_rejects_until_history_covers_delay(self) -> None:
        """First sample has nothing in the history → rejected as
        delay_buffer_cold."""
        records = [_rec(500.0, 30.0, 1.10, t=_T0)]
        log = DataLog(name="t", records=records)
        cfg = SteadyStateConfig(ego_transport_delay_seconds=0.3)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            steady_state_config=cfg,
        )
        assert result.accepted_records == 0
        assert result.rejected_records == 1
        rejection_dict = dict(result.rejection_counts_by_gate)
        assert rejection_dict.get("delay_buffer_cold") == 1


# ---------------------------------------------------------------------------
# Derivative steady-state gates
# ---------------------------------------------------------------------------

class TestDerivativeGates:
    def test_high_drpm_rejected(self) -> None:
        # 500 → 2000 rpm in 100 ms = 15 000 rpm/s. Threshold 5000 rpm/s.
        records = [
            _rec(500.0, 30.0, 1.0, t=_T0),
            _rec(2000.0, 30.0, 1.0, t=_T0 + timedelta(seconds=0.1)),
        ]
        log = DataLog(name="t", records=records)
        cfg = SteadyStateConfig(max_drpm_per_second=5000.0)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            steady_state_config=cfg,
        )
        # First record passes (no prior history); second record exceeds threshold.
        assert result.accepted_records == 1
        assert result.rejected_records == 1
        rejection_dict = dict(result.rejection_counts_by_gate)
        assert rejection_dict.get("transient_rpm_derivative") == 1

    def test_below_threshold_drpm_accepted(self) -> None:
        # 500 → 700 rpm in 100 ms = 2 000 rpm/s. Threshold 5000 rpm/s.
        records = [
            _rec(500.0, 30.0, 1.0, t=_T0),
            _rec(700.0, 30.0, 1.0, t=_T0 + timedelta(seconds=0.1)),
        ]
        log = DataLog(name="t", records=records)
        cfg = SteadyStateConfig(max_drpm_per_second=5000.0)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            steady_state_config=cfg,
        )
        assert result.accepted_records == 2
        assert result.rejected_records == 0

    def test_high_dmap_rejected(self) -> None:
        records = [
            _rec(800.0, 30.0, 1.0, t=_T0),
            _rec(800.0, 90.0, 1.0, t=_T0 + timedelta(seconds=0.1)),  # 600 kPa/s
        ]
        log = DataLog(name="t", records=records)
        cfg = SteadyStateConfig(max_dmap_per_second=200.0)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
            steady_state_config=cfg,
        )
        rejection_dict = dict(result.rejection_counts_by_gate)
        assert rejection_dict.get("transient_map_derivative") == 1


# ---------------------------------------------------------------------------
# History trimming
# ---------------------------------------------------------------------------

class TestHistoryWindow:
    def test_history_trimmed_to_window(self) -> None:
        """Records older than history_window_seconds are dropped from the
        delay-comp lookup buffer. With a 1.0 s window and a 1.5 s delay,
        the delay target sits *outside* the trimmed window, so a sample
        arriving long after the prior records can no longer be paired
        and is rejected as delay_buffer_cold — proving the trim ran."""
        accumulator = VeAnalyzeCellHitAccumulator()
        snap = _snapshot()
        cfg = SteadyStateConfig(
            ego_transport_delay_seconds=1.5, history_window_seconds=1.0,
        )
        # Seed history at t=0 and t=0.5.
        accumulator.add_record(
            _rec(500.0, 30.0, 1.0, t=_T0),
            snap, gating_config=_NO_GATE, steady_state_config=cfg,
        )
        accumulator.add_record(
            _rec(500.0, 30.0, 1.0, t=_T0 + timedelta(seconds=0.5)),
            snap, gating_config=_NO_GATE, steady_state_config=cfg,
        )
        # Sample at t=3.0: trim cutoff is t >= 2.0, which drops both
        # seed records, so the lookup buffer is empty and the sample is
        # rejected as delay_buffer_cold.
        accepted = accumulator.add_record(
            _rec(1500.0, 60.0, 1.10, t=_T0 + timedelta(seconds=3.0)),
            snap, gating_config=_NO_GATE, steady_state_config=cfg,
        )
        assert accepted is False
        assert accumulator.rejected_count >= 1

    def test_history_within_window_allows_pairing(self) -> None:
        """Symmetric case: with the same delay but a wider window, the
        seed record stays in history and the delay pairing succeeds."""
        accumulator = VeAnalyzeCellHitAccumulator()
        snap = _snapshot()
        cfg = SteadyStateConfig(
            ego_transport_delay_seconds=0.4, history_window_seconds=2.0,
        )
        accumulator.add_record(
            _rec(500.0, 30.0, 1.0, t=_T0),
            snap, gating_config=_NO_GATE, steady_state_config=cfg,
        )
        accepted = accumulator.add_record(
            _rec(1500.0, 60.0, 1.10, t=_T0 + timedelta(seconds=0.4)),
            snap, gating_config=_NO_GATE, steady_state_config=cfg,
        )
        assert accepted is True
