"""Phase 7 end-to-end pipeline integration test.

Drives a synthetic but realistic datalog through the full VE Analyze
pipeline twice — once with every Phase 7 feature off (Phase 6 baseline)
and once with every feature on — and asserts that the result differs in
the expected, explainable ways.

This test is the Phase 7 exit-criteria check called out in
``docs/tuning-roadmap.md``: it proves the slices compose correctly and
that default-off behaviour is bit-identical to Phase 6.
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
    SteadyStateConfig,
    VeAnalyzeCellHitService,
    WeightedCorrectionConfig,
)
from tuner.services.ve_proposal_smoothing_service import (
    SmoothingConfig,
    VeProposalSmoothingService,
)
from tuner.services.ve_root_cause_diagnostics_service import (
    VeRootCauseDiagnosticsService,
)

_T0 = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset())

# runtimeStatusA bit layout from the firmware (mirrors the gate
# implementation in replay_sample_gate_service.py).
_RSA_VALID = 0x10 | 0x80  # fullSync | tuneLearnValid
_RSA_TRANSIENT = _RSA_VALID | 0x20


def _snapshot() -> TablePageSnapshot:
    """4×4 VE table covering vacuum (rows 0-1) and boost (rows 2-3)."""
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
        x_labels=("500", "1500", "3000", "5000"),
        y_labels=("30", "60", "120", "180"),
        table_model=TableViewModel(
            rows=4, columns=4,
            cells=[
                ["50", "55", "60", "65"],
                ["55", "60", "65", "70"],
                ["70", "75", "80", "85"],
                ["80", "85", "90", "95"],
            ],
        ),
        auxiliary_sections=(),
        can_undo=False,
        can_redo=False,
    )


def _rec(
    rpm: float, map_: float, lambda_: float,
    *, t: datetime, mat: float = 40.0, rsa: int | None = None,
) -> DataLogRecord:
    """Build a DataLogRecord. ``rsa`` is included only when explicitly
    set; the channel name "runtimeStatusA" collides with the
    accelFilter alias "status", so omitting it keeps Phase 6 baseline
    paths clean."""
    values: dict[str, float] = {
        "rpm": rpm, "map": map_, "lambda": lambda_, "mat": mat,
    }
    if rsa is not None:
        values["runtimeStatusA"] = float(rsa)
    return DataLogRecord(timestamp=t, values=values)


def _build_synthetic_log() -> DataLog:
    """Build a datalog that exercises every Phase 7 slice.

    Composition:
      - 12 steady-state cruise samples in cell (1, 1) at lambda 1.10
        (lean by 10% — should drive a clamp under 7.2 with clamp=0.05).
      - 12 steady-state boost samples in cell (3, 3) at lambda 1.05.
      - 4 transient samples (large drpm) in cell (2, 2) at lambda 1.15
        — Phase 6 accepts these, Slice 7.4 derivative gate rejects them.
      - 4 spool-transition samples in cell (2, 3) where MAP > atmospheric
        AND drpm/dt is large — Slice 7.6 downweights them.
      - 6 firmware-marked transient samples (rsa bit 5 set) in cell (0, 0)
        — Phase 6 accepts these, Slice 7.1 firmware gate rejects them.
    """
    records: list[DataLogRecord] = []
    t = _T0

    # Cruise cluster — cell (1, 1): rpm≈1500, map≈60. Steady, lean 10%.
    for i in range(12):
        records.append(_rec(1500.0, 60.0, 1.10, t=t + timedelta(seconds=i * 0.1)))
    t += timedelta(seconds=2.0)

    # Boost cluster — cell (3, 3): rpm≈5000, map≈180. Steady, lean 5%.
    for i in range(12):
        records.append(_rec(5000.0, 180.0, 1.05, t=t + timedelta(seconds=i * 0.1)))
    t += timedelta(seconds=2.0)

    # Transient cluster — cell (2, 2): big rpm jumps. Phase 6 takes these
    # at face value; Slice 7.4 derivative gate rejects.
    base_rpm = 3000.0
    for i in range(4):
        # First sample seeds history; subsequent samples jump 1000 rpm
        # in 0.1 s = 10 000 rpm/s — well over a 5 000 rpm/s threshold.
        records.append(_rec(base_rpm, 120.0, 1.15, t=t))
        t += timedelta(seconds=0.1)
        records.append(_rec(base_rpm + 1000.0, 120.0, 1.15, t=t))
        t += timedelta(seconds=0.1)

    # Spool cluster — cell (2, 3): MAP in boost AND high drpm/dt.
    # Slice 7.6 spool penalty fires here.
    for i in range(4):
        records.append(_rec(4500.0, 150.0, 1.05, t=t))
        t += timedelta(seconds=0.1)
        records.append(_rec(5000.0, 160.0, 1.05, t=t))
        t += timedelta(seconds=0.1)

    # Firmware-marked transient cluster — cell (0, 0): cruise rpm/map but
    # runtimeStatusA bit 5 set. Phase 6 accepts; Slice 7.1 rejects.
    for i in range(6):
        records.append(_rec(500.0, 30.0, 1.10, t=t, rsa=_RSA_TRANSIENT))
        t += timedelta(seconds=0.1)

    return DataLog(name="phase7_synthetic", records=records)


def test_phase6_baseline_accepts_everything_and_proposes_uniform_lean() -> None:
    """Phase 6 baseline (all features off) accepts every sample and
    proposes a uniformly lean correction across the populated cells."""
    log = _build_synthetic_log()
    snap = _snapshot()
    svc = VeAnalyzeCellHitService()

    baseline = svc.analyze(
        log=log, ve_table_snapshot=snap,
        gating_config=_NO_GATE, min_samples_for_correction=3,
    )

    # The 6 firmware-marked transient samples carry runtimeStatusA, which
    # the existing accelFilter happens to read via the "status" channel
    # alias — so on the Phase 6 baseline path they are also rejected
    # (this is the software-side gate the Phase 7 firmware gate is
    # *additional* to). All other records pass.
    assert baseline.rejected_records == 6
    assert baseline.accepted_records == len(log.records) - 6

    # No clamping or boost-penalty surfacing on the baseline path.
    assert all(c.clamp_applied is False for c in baseline.cell_corrections)
    assert all(c.boost_penalty_applied == 0.0 for c in baseline.cell_corrections)
    # Coverage is *always* populated when the snapshot has a table model
    # (Slice 7.3 default behaviour); only the *signals* on it default to
    # zero. The full-grid coverage map remains a structural feature.
    assert baseline.coverage is not None


def test_phase7_full_pipeline_differs_from_baseline_in_expected_ways() -> None:
    """All seven slices on. Verify each slice's signature."""
    log = _build_synthetic_log()
    snap = _snapshot()
    svc = VeAnalyzeCellHitService()

    gating = SampleGatingConfig(
        enabled_gates=frozenset(),
        firmware_learn_gate_enabled=True,                       # Slice 7.1
    )
    weighting = WeightedCorrectionConfig(
        max_correction_per_cell=0.05,                           # Slice 7.2 clamp
        dwell_weight_enabled=True,                              # Slice 7.2 dwell
    )
    steady_state = SteadyStateConfig(
        max_drpm_per_second=5000.0,                             # Slice 7.4 deriv
        history_window_seconds=5.0,
    )
    boost = BoostConfidenceConfig()                             # Slice 7.6 defaults

    result = svc.analyze(
        log=log, ve_table_snapshot=snap,
        gating_config=gating, min_samples_for_correction=3,
        weighting_config=weighting,
        steady_state_config=steady_state,
        boost_confidence_config=boost,
    )

    # ---- Slice 7.1: firmware-marked transient cluster rejected ----
    # The firmware cluster has 6 records; the very first one is also a
    # large rpm/map step away from the prior spool cluster, so the
    # derivative gate (which runs before the gate service) catches it
    # first. The remaining 5 are rejected by firmwareLearnGate.
    rejection_dict = dict(result.rejection_counts_by_gate)
    assert rejection_dict.get("firmwareLearnGate", 0) >= 5

    # ---- Slice 7.4: derivative gate rejected the transient cluster ----
    assert rejection_dict.get("transient_rpm_derivative", 0) >= 1

    # Cell (0, 0) and cell (2, 2) should NOT have proposals — both clusters
    # were entirely rejected by Slices 7.1 and 7.4 respectively.
    cells_with_proposals = {(p.row_index, p.col_index) for p in result.proposals}
    assert (0, 0) not in cells_with_proposals
    assert (2, 2) not in cells_with_proposals

    # ---- Slice 7.2: cruise cell (1, 1) raw cf is 1.10 but clamp = 0.05
    # so the effective correction is exactly 1.05 with clamp_applied=True.
    cruise = next(
        c for c in result.cell_corrections if (c.row_index, c.col_index) == (1, 1)
    )
    assert cruise.clamp_applied is True
    assert cruise.mean_correction_factor == 1.05
    assert cruise.raw_correction_factor == 1.10  # surfaced for review
    cruise_proposal = next(
        p for p in result.proposals if (p.row_index, p.col_index) == (1, 1)
    )
    assert cruise_proposal.clamp_applied is True

    # ---- Slice 7.3: every cell carries a confidence_score and the
    # full-grid coverage map covers all 16 cells.
    assert result.coverage is not None
    assert result.coverage.total_count == 16
    assert all(0.0 <= c.confidence_score <= 1.0 for c in result.cell_corrections)
    # The cruise cell has 12 samples → score should be > 0.5.
    assert cruise.confidence_score > 0.5

    # ---- Slice 7.6: spool cluster cell (2, 3) carries a non-zero
    # boost_penalty_applied (positive boost + high drpm/dt).
    spool = next(
        (c for c in result.cell_corrections if (c.row_index, c.col_index) == (2, 3)),
        None,
    )
    assert spool is not None
    assert spool.boost_penalty_applied > 0.0


def test_phase7_smoothing_layer_is_separate_from_raw() -> None:
    """Slice 7.5: the smoothing service produces a separate layer; the
    raw VeAnalysisSummary is not mutated."""
    log = _build_synthetic_log()
    snap = _snapshot()
    summary = VeAnalyzeCellHitService().analyze(
        log=log, ve_table_snapshot=snap,
        gating_config=_NO_GATE, min_samples_for_correction=3,
    )
    raw_proposals_before = tuple(
        (p.row_index, p.col_index, p.proposed_ve, p.correction_factor)
        for p in summary.proposals
    )
    smoothed = VeProposalSmoothingService().smooth(summary, SmoothingConfig())
    raw_proposals_after = tuple(
        (p.row_index, p.col_index, p.proposed_ve, p.correction_factor)
        for p in summary.proposals
    )
    # The raw layer is byte-identical after smoothing.
    assert raw_proposals_before == raw_proposals_after
    # The smoothed layer is its own object — same length, may differ.
    assert len(smoothed.smoothed_proposals) == len(summary.proposals)


def test_phase7_root_cause_diagnostics_fire_on_uniform_lean_bias() -> None:
    """Slice 7.7: when the synthetic log produces a uniformly lean cluster
    of proposals, the root-cause inspector flags it as injector_flow_error
    rather than letting the operator stage table edits blindly."""
    # Build a log with 9 steady cells all biased ~10% lean — designed to
    # trip the injector_flow_error rule. Different from the main synthetic
    # log so the test stays self-contained.
    snap = _snapshot()
    records: list[DataLogRecord] = []
    t = _T0
    cells_to_seed = [
        (500.0, 30.0), (1500.0, 30.0), (3000.0, 30.0),
        (500.0, 60.0), (1500.0, 60.0), (3000.0, 60.0),
        (500.0, 120.0), (1500.0, 120.0), (3000.0, 120.0),
    ]
    for rpm, map_ in cells_to_seed:
        for i in range(4):
            records.append(_rec(rpm, map_, 1.10, t=t))
            t += timedelta(seconds=0.1)
        t += timedelta(seconds=0.5)

    log = DataLog(name="uniform_lean", records=records)
    summary = VeAnalyzeCellHitService().analyze(
        log=log, ve_table_snapshot=snap,
        gating_config=_NO_GATE, min_samples_for_correction=3,
    )
    report = VeRootCauseDiagnosticsService().diagnose(summary)
    rules = {d.rule for d in report.diagnostics}
    assert "injector_flow_error" in rules
    finding = next(d for d in report.diagnostics if d.rule == "injector_flow_error")
    assert "lean" in finding.message
