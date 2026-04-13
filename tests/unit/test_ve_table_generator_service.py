from __future__ import annotations

from tuner.domain.generator_context import AssumptionSource, ForcedInductionTopology, GeneratorInputContext, SuperchargerType
from tuner.services.ve_table_generator_service import VeTableGeneratorService, _COLS, _ROWS


def _generate(topology=ForcedInductionTopology.NA, **kwargs):
    ctx = GeneratorInputContext(forced_induction_topology=topology, **kwargs)
    return VeTableGeneratorService().generate(ctx)


# ---------------------------------------------------------------------------
# Result dimensions
# ---------------------------------------------------------------------------

def test_result_has_correct_dimensions() -> None:
    result = _generate()
    assert result.rows == 16
    assert result.columns == 16
    assert len(result.values) == 256


def test_as_list_matches_values() -> None:
    result = _generate()
    assert result.as_list() == list(result.values)


# ---------------------------------------------------------------------------
# Value range
# ---------------------------------------------------------------------------

def test_all_values_in_valid_range() -> None:
    for topology in ForcedInductionTopology:
        result = _generate(topology=topology)
        for v in result.values:
            assert 20.0 <= v <= 100.0, f"Out-of-range VE {v} for topology {topology}"


# ---------------------------------------------------------------------------
# NA shape invariants
# ---------------------------------------------------------------------------

def test_na_wot_higher_than_idle() -> None:
    result = _generate(topology=ForcedInductionTopology.NA)
    values = result.values
    # WOT row (row 15, last 16 cells): cells 15*16 .. 15*16+15
    wot_row = [values[15 * _COLS + col] for col in range(_COLS)]
    # Idle row (row 0, first 16 cells)
    idle_row = [values[0 * _COLS + col] for col in range(_COLS)]
    assert sum(wot_row) > sum(idle_row)


def test_na_higher_load_yields_higher_ve_on_average() -> None:
    result = _generate(topology=ForcedInductionTopology.NA)
    values = result.values
    row_avgs = [
        sum(values[r * _COLS:(r + 1) * _COLS]) / _COLS for r in range(_ROWS)
    ]
    # Each row should be >= the one below it (load ramp)
    for r in range(1, _ROWS):
        assert row_avgs[r] >= row_avgs[r - 1] - 0.5, (
            f"Row {r} avg {row_avgs[r]:.1f} is much lower than row {r-1} {row_avgs[r-1]:.1f}"
        )


def test_na_mid_rpm_not_lower_than_extremes() -> None:
    """Mid-RPM columns should not be lower than the edge columns at the same load."""
    result = _generate(topology=ForcedInductionTopology.NA)
    values = result.values
    # Check a mid-load row (row 8)
    row = [values[8 * _COLS + col] for col in range(_COLS)]
    mid_col = _COLS // 2
    # Mid-range average should be >= edge average
    mid_avg = sum(row[mid_col - 2:mid_col + 2]) / 4
    edge_avg = (row[0] + row[-1]) / 2
    assert mid_avg >= edge_avg - 2.0


# ---------------------------------------------------------------------------
# Turbo pre-spool reduction
# ---------------------------------------------------------------------------

def test_single_turbo_reduces_ve_at_low_rpm() -> None:
    na = _generate(topology=ForcedInductionTopology.NA)
    turbo = _generate(topology=ForcedInductionTopology.SINGLE_TURBO)
    # In the pre-spool region (col 0..4), turbo VE should be less than NA
    for row in range(_ROWS):
        for col in range(5):
            na_val = na.values[row * _COLS + col]
            turbo_val = turbo.values[row * _COLS + col]
            assert turbo_val < na_val, (
                f"row={row} col={col}: turbo VE {turbo_val} not less than NA {na_val}"
            )


def test_single_turbo_ve_recovers_post_spool() -> None:
    na = _generate(topology=ForcedInductionTopology.NA)
    turbo = _generate(topology=ForcedInductionTopology.SINGLE_TURBO)
    # Post-spool (col >= 9): turbo VE should match NA (no reduction)
    for row in range(_ROWS):
        for col in range(9, _COLS):
            na_val = na.values[row * _COLS + col]
            turbo_val = turbo.values[row * _COLS + col]
            assert abs(turbo_val - na_val) < 0.5, (
                f"row={row} col={col}: post-spool turbo VE {turbo_val} differs from NA {na_val}"
            )


def test_twin_turbo_has_smaller_reduction_than_single() -> None:
    turbo_single = _generate(topology=ForcedInductionTopology.SINGLE_TURBO)
    turbo_twin = _generate(topology=ForcedInductionTopology.TWIN_TURBO_IDENTICAL)
    # Twin turbo should have less reduction at low RPM (smaller turbos spool faster)
    low_rpm_single = sum(turbo_single.values[0 * _COLS + col] for col in range(5))
    low_rpm_twin = sum(turbo_twin.values[0 * _COLS + col] for col in range(5))
    assert low_rpm_twin > low_rpm_single


def test_compound_turbo_has_smallest_pre_spool_reduction() -> None:
    turbo_single = _generate(topology=ForcedInductionTopology.SINGLE_TURBO)
    turbo_compound = _generate(topology=ForcedInductionTopology.TWIN_TURBO_COMPOUND)
    low_rpm_single = sum(turbo_single.values[0 * _COLS + col] for col in range(5))
    low_rpm_compound = sum(turbo_compound.values[0 * _COLS + col] for col in range(5))
    assert low_rpm_compound > low_rpm_single


# ---------------------------------------------------------------------------
# Supercharger: no pre-spool reduction
# ---------------------------------------------------------------------------

def test_supercharger_not_lower_than_na_at_low_rpm() -> None:
    na = _generate(topology=ForcedInductionTopology.NA)
    sc = _generate(topology=ForcedInductionTopology.SINGLE_SUPERCHARGER)
    for col in range(5):
        na_val = na.values[8 * _COLS + col]
        sc_val = sc.values[8 * _COLS + col]
        assert sc_val >= na_val - 0.5, (
            f"Supercharger VE {sc_val} unexpectedly below NA {na_val} at low RPM col {col}"
        )


# ---------------------------------------------------------------------------
# Cam duration effect
# ---------------------------------------------------------------------------

def test_high_cam_raises_high_rpm_high_load_ve() -> None:
    stock = _generate(cam_duration_deg=220.0)
    perf  = _generate(cam_duration_deg=290.0)  # above _HIGH_CAM_THRESHOLD_DEG
    # At high RPM (col 12+), high load (row 12+) performance cam should be higher
    for row in range(12, _ROWS):
        for col in range(12, _COLS):
            stock_val = stock.values[row * _COLS + col]
            perf_val  = perf.values[row * _COLS + col]
            assert perf_val > stock_val, (
                f"row={row} col={col}: perf cam VE {perf_val} not > stock {stock_val}"
            )


def test_missing_cam_duration_adds_warning() -> None:
    result = _generate()
    assert any("cam" in w.lower() for w in result.warnings)


def test_provided_cam_duration_suppresses_cam_warning() -> None:
    result = _generate(cam_duration_deg=240.0)
    assert not any("cam" in w.lower() for w in result.warnings)


def test_race_ported_head_raises_high_rpm_high_load_ve() -> None:
    stock = _generate(cam_duration_deg=240.0)
    ported = _generate(cam_duration_deg=240.0, head_flow_class="race_ported")
    assert ported.values[15 * _COLS + 15] > stock.values[15 * _COLS + 15]


def test_itb_manifold_reduces_idle_and_raises_high_rpm_ve() -> None:
    plenum = _generate(intake_manifold_style="long_runner_plenum")
    itb = _generate(intake_manifold_style="itb")
    assert itb.values[0] < plenum.values[0]
    assert itb.values[15 * _COLS + 15] > plenum.values[15 * _COLS + 15]


def test_flow_only_injector_characterization_adds_idle_penalty_and_warning() -> None:
    full = _generate(
        required_fuel_ms=8.0,
        injector_dead_time_ms=0.9,
        injector_characterization="full_characterization",
    )
    flow_only = _generate(
        required_fuel_ms=8.0,
        injector_dead_time_ms=0.9,
        injector_characterization="nominal_flow_only",
    )
    assert flow_only.values[0] < full.values[0]
    assert any("flow-only" in w.lower() for w in flow_only.warnings)


def test_twin_turbo_unequal_adds_warning_note() -> None:
    result = _generate(topology=ForcedInductionTopology.TWIN_TURBO_UNEQUAL)
    assert any("unequal" in warning.lower() for warning in result.warnings)


def test_centrifugal_supercharger_is_lower_than_roots_at_low_rpm() -> None:
    roots = _generate(
        topology=ForcedInductionTopology.SINGLE_SUPERCHARGER,
        supercharger_type=SuperchargerType.ROOTS,
    )
    centrifugal = _generate(
        topology=ForcedInductionTopology.SINGLE_SUPERCHARGER,
        supercharger_type=SuperchargerType.CENTRIFUGAL,
    )
    assert centrifugal.values[8 * _COLS] < roots.values[8 * _COLS]


# ---------------------------------------------------------------------------
# Missing inputs generate warnings
# ---------------------------------------------------------------------------

def test_missing_displacement_adds_warning() -> None:
    result = _generate(cylinder_count=4)
    assert any("displacement" in w.lower() for w in result.warnings)


def test_missing_cylinder_count_adds_warning() -> None:
    result = _generate(displacement_cc=2000.0)
    assert any("cylinder" in w.lower() for w in result.warnings)


def test_low_reqfuel_reduces_idle_ve() -> None:
    normal = _generate(required_fuel_ms=8.0, injector_dead_time_ms=0.9)
    oversized = _generate(required_fuel_ms=3.5, injector_dead_time_ms=0.9)
    assert oversized.values[0] < normal.values[0]


def test_missing_injector_deadtime_adds_warning() -> None:
    result = _generate(required_fuel_ms=8.0)
    assert any("dead time" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summary_mentions_topology() -> None:
    result = _generate(topology=ForcedInductionTopology.SINGLE_TURBO)
    assert "turbo" in result.summary.lower()


def test_summary_mentions_displacement_when_provided() -> None:
    result = _generate(displacement_cc=1600.0)
    assert "1600" in result.summary


def test_summary_mentions_tier2_airflow_and_injector_inputs() -> None:
    result = _generate(
        head_flow_class="mild_ported",
        intake_manifold_style="itb",
        injector_characterization="full_characterization",
    )
    summary = result.summary.lower()
    assert "head flow" in summary
    assert "manifold" in summary
    assert "injector data" in summary


# ---------------------------------------------------------------------------
# Topology field preserved in result
# ---------------------------------------------------------------------------

def test_result_topology_matches_input() -> None:
    for topology in ForcedInductionTopology:
        result = _generate(topology=topology)
        assert result.topology == topology


# ---------------------------------------------------------------------------
# GeneratorAssumption output
# ---------------------------------------------------------------------------

def test_result_includes_assumptions() -> None:
    result = _generate()
    assert len(result.assumptions) > 0


def test_fallback_assumptions_when_no_context() -> None:
    result = _generate()
    labels = {a.label for a in result.assumptions}
    # These key inputs should always be reported
    assert "Displacement" in labels
    assert "Injector flow" in labels
    assert "Injector dead time" in labels
    fallback_labels = {a.label for a in result.assumptions if a.source == AssumptionSource.CONSERVATIVE_FALLBACK}
    assert "Displacement" in fallback_labels
    assert "Injector flow" in fallback_labels


def test_from_context_assumptions_when_inputs_provided() -> None:
    result = _generate(
        displacement_cc=2000.0,
        injector_flow_ccmin=440.0,
        injector_dead_time_ms=0.38,
        compression_ratio=9.5,
    )
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Displacement"].source == AssumptionSource.FROM_CONTEXT
    assert by_label["Injector flow"].source == AssumptionSource.FROM_CONTEXT
    assert by_label["Injector dead time"].source == AssumptionSource.FROM_CONTEXT
    assert by_label["Compression ratio"].source == AssumptionSource.FROM_CONTEXT


def test_computed_req_fuel_assumption_source() -> None:
    # When required_fuel_ms is None but computed_req_fuel_ms is set, source = COMPUTED
    result = _generate(
        computed_req_fuel_ms=8.5,
        injector_flow_ccmin=440.0,
        displacement_cc=2000.0,
    )
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Required fuel"].source == AssumptionSource.COMPUTED


def test_boosted_topology_adds_boost_assumptions() -> None:
    result = _generate(
        topology=ForcedInductionTopology.SINGLE_TURBO,
        boost_target_kpa=200.0,
    )
    labels = {a.label for a in result.assumptions}
    assert "Boost target" in labels
    assert "Intercooler" in labels


def test_ve_injector_pressure_model_assumption_source_tracks_context() -> None:
    result = _generate(
        topology=ForcedInductionTopology.SINGLE_TURBO,
        injector_pressure_model="vacuum_referenced",
    )
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Injector pressure model"].source == AssumptionSource.FROM_CONTEXT


def test_ve_injector_pressure_model_falls_back_when_absent() -> None:
    result = _generate(topology=ForcedInductionTopology.SINGLE_TURBO)
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Injector pressure model"].source == AssumptionSource.CONSERVATIVE_FALLBACK
