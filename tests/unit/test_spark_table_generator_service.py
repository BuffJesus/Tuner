from __future__ import annotations

import pytest

from tuner.domain.generator_context import ForcedInductionTopology, GeneratorInputContext
from tuner.domain.operator_engine_context import CalibrationIntent
from tuner.services.spark_table_generator_service import (
    SparkTableGeneratorService,
    _COLS,
    _ROWS,
    _CRANK_TIMING_FLOOR,
    _NA_WOT_MAX,
    _IDLE_TIMING_BASE,
)


def _generate(
    topology=ForcedInductionTopology.NA,
    calibration_intent=CalibrationIntent.FIRST_START,
    **kwargs,
):
    ctx = GeneratorInputContext(forced_induction_topology=topology, **kwargs)
    return SparkTableGeneratorService().generate(ctx, calibration_intent)


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

def test_all_values_above_cranking_floor() -> None:
    for topology in ForcedInductionTopology:
        result = _generate(topology=topology)
        for v in result.values:
            assert v >= _CRANK_TIMING_FLOOR, (
                f"Value {v} below cranking floor {_CRANK_TIMING_FLOOR} for {topology}"
            )


def test_all_values_at_most_45_degrees() -> None:
    for topology in ForcedInductionTopology:
        result = _generate(topology=topology, compression_ratio=8.0)
        for v in result.values:
            assert v <= 45.0, f"Advance {v} exceeds 45° for {topology}"


# ---------------------------------------------------------------------------
# NA shape invariants
# ---------------------------------------------------------------------------

def test_na_wot_higher_than_idle_average() -> None:
    result = _generate(topology=ForcedInductionTopology.NA)
    values = result.values
    wot_row = [values[15 * _COLS + col] for col in range(_COLS)]
    idle_row = [values[0 * _COLS + col] for col in range(_COLS)]
    assert sum(wot_row) > sum(idle_row)


def test_na_higher_load_higher_advance_on_average() -> None:
    result = _generate(topology=ForcedInductionTopology.NA)
    values = result.values
    row_avgs = [
        sum(values[r * _COLS:(r + 1) * _COLS]) / _COLS for r in range(_ROWS)
    ]
    for r in range(1, _ROWS):
        assert row_avgs[r] >= row_avgs[r - 1] - 0.5, (
            f"Row {r} avg {row_avgs[r]:.1f} unexpectedly below row {r-1} avg {row_avgs[r-1]:.1f}"
        )


def test_low_rpm_cols_have_lower_advance_than_mid() -> None:
    result = _generate(topology=ForcedInductionTopology.NA)
    values = result.values
    # Compare col 0 (cranking) to col 8 (mid RPM) at mid-load row
    mid_row = 8
    crank_advance = values[mid_row * _COLS + 0]
    mid_advance = values[mid_row * _COLS + 8]
    assert mid_advance > crank_advance


# ---------------------------------------------------------------------------
# Compression ratio effect
# ---------------------------------------------------------------------------

def test_high_cr_reduces_wot_advance() -> None:
    low_cr = _generate(topology=ForcedInductionTopology.NA, compression_ratio=8.5)
    high_cr = _generate(topology=ForcedInductionTopology.NA, compression_ratio=12.5)
    # WOT row average should be lower for high CR
    wot_low = sum(low_cr.values[15 * _COLS:(15 + 1) * _COLS]) / _COLS
    wot_high = sum(high_cr.values[15 * _COLS:(15 + 1) * _COLS]) / _COLS
    assert wot_high < wot_low


def test_low_cr_idle_cells_not_penalised() -> None:
    low_cr = _generate(compression_ratio=8.5)
    high_cr = _generate(compression_ratio=12.5)
    # Idle/very-low-load row (row 0) should be nearly identical — CR penalty
    # only applies at load_norm >= 0.4
    idle_diff = abs(
        sum(low_cr.values[0:_COLS]) - sum(high_cr.values[0:_COLS])
    )
    assert idle_diff < 2.0, f"Idle row differs by {idle_diff:.1f} — CR penalty leaking into idle"


def test_missing_cr_adds_warning() -> None:
    result = _generate()
    assert any("compression ratio" in w.lower() for w in result.warnings)


def test_present_cr_no_cr_warning() -> None:
    result = _generate(compression_ratio=9.5)
    assert not any("compression ratio" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Calibration intent
# ---------------------------------------------------------------------------

def test_drivable_base_gives_more_advance_than_first_start() -> None:
    first_start = _generate(
        calibration_intent=CalibrationIntent.FIRST_START, compression_ratio=9.5
    )
    drivable = _generate(
        calibration_intent=CalibrationIntent.DRIVABLE_BASE, compression_ratio=9.5
    )
    # Drivable should have higher average across mid-to-high load rows
    fs_mid = sum(first_start.values[8 * _COLS:]) / (8 * _COLS)
    db_mid = sum(drivable.values[8 * _COLS:]) / (8 * _COLS)
    assert db_mid > fs_mid


# ---------------------------------------------------------------------------
# Forced-induction topology: WOT retard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("topology", [
    ForcedInductionTopology.SINGLE_TURBO,
    ForcedInductionTopology.TWIN_TURBO_IDENTICAL,
    ForcedInductionTopology.TWIN_TURBO_SEQUENTIAL,
    ForcedInductionTopology.TWIN_TURBO_COMPOUND,
    ForcedInductionTopology.TWIN_TURBO_UNEQUAL,
    ForcedInductionTopology.SINGLE_SUPERCHARGER,
    ForcedInductionTopology.TWIN_CHARGE,
])
def test_forced_induction_wot_less_than_na(topology: ForcedInductionTopology) -> None:
    na = _generate(topology=ForcedInductionTopology.NA, compression_ratio=9.5)
    fi = _generate(topology=topology, compression_ratio=9.5)
    wot_na = sum(na.values[15 * _COLS:(15 + 1) * _COLS]) / _COLS
    wot_fi = sum(fi.values[15 * _COLS:(15 + 1) * _COLS]) / _COLS
    assert wot_fi < wot_na, (
        f"WOT advance for {topology} ({wot_fi:.1f}°) not less than NA ({wot_na:.1f}°)"
    )


def test_forced_induction_idle_similar_to_na() -> None:
    """Pre-boost / idle cells should not be retarded for FI engines."""
    na = _generate(topology=ForcedInductionTopology.NA)
    turbo = _generate(topology=ForcedInductionTopology.SINGLE_TURBO)
    idle_na = sum(na.values[0:_COLS]) / _COLS
    idle_turbo = sum(turbo.values[0:_COLS]) / _COLS
    assert abs(idle_na - idle_turbo) < 2.0


# ---------------------------------------------------------------------------
# Result metadata
# ---------------------------------------------------------------------------

def test_result_topology_matches_input() -> None:
    for topology in ForcedInductionTopology:
        result = _generate(topology=topology)
        assert result.topology == topology


def test_result_calibration_intent_stored() -> None:
    result = _generate(calibration_intent=CalibrationIntent.DRIVABLE_BASE)
    assert result.calibration_intent == CalibrationIntent.DRIVABLE_BASE


def test_result_compression_ratio_stored() -> None:
    result = _generate(compression_ratio=10.5)
    assert result.compression_ratio == 10.5


def test_result_summary_non_empty() -> None:
    result = _generate(compression_ratio=9.5, cylinder_count=4)
    assert len(result.summary) > 0
    assert "spark" in result.summary.lower() or "advance" in result.summary.lower()


def test_missing_cylinder_count_adds_warning() -> None:
    result = _generate()
    assert any("cylinder count" in w.lower() for w in result.warnings)


def test_high_boost_no_intercooler_reduces_wot_advance_more() -> None:
    base = _generate(
        topology=ForcedInductionTopology.SINGLE_TURBO,
        compression_ratio=9.5,
        boost_target_kpa=170.0,
        intercooler_present=True,
        dwell_ms=4.5,
    )
    aggressive = _generate(
        topology=ForcedInductionTopology.SINGLE_TURBO,
        compression_ratio=9.5,
        boost_target_kpa=240.0,
        intercooler_present=False,
        dwell_ms=4.5,
    )
    base_wot = sum(base.values[15 * _COLS:(15 + 1) * _COLS]) / _COLS
    aggressive_wot = sum(aggressive.values[15 * _COLS:(15 + 1) * _COLS]) / _COLS
    assert aggressive_wot < base_wot


def test_missing_dwell_adds_warning() -> None:
    result = _generate(compression_ratio=9.5)
    assert any("dwell" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# GeneratorAssumption output
# ---------------------------------------------------------------------------

def test_spark_result_includes_assumptions() -> None:
    result = _generate()
    assert len(result.assumptions) > 0


def test_spark_fallback_when_no_compression() -> None:
    from tuner.domain.generator_context import AssumptionSource
    result = _generate()
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Compression ratio"].source == AssumptionSource.CONSERVATIVE_FALLBACK


def test_spark_from_context_when_inputs_provided() -> None:
    from tuner.domain.generator_context import AssumptionSource
    from tuner.domain.operator_engine_context import CalibrationIntent
    result = _generate(compression_ratio=10.5, dwell_ms=3.5)
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Compression ratio"].source == AssumptionSource.FROM_CONTEXT
    assert by_label["Dwell"].source == AssumptionSource.FROM_CONTEXT


def test_spark_boosted_adds_boost_assumptions() -> None:
    result = _generate(
        topology=ForcedInductionTopology.SINGLE_TURBO,
        boost_target_kpa=200.0,
    )
    labels = {a.label for a in result.assumptions}
    assert "Boost target" in labels
    assert "Intercooler" in labels


@pytest.mark.parametrize(
    ("topology", "label"),
    [
        (ForcedInductionTopology.TWIN_TURBO_COMPOUND, "Compound turbo timing"),
        (ForcedInductionTopology.TWIN_TURBO_SEQUENTIAL, "Sequential turbo timing"),
        (ForcedInductionTopology.TWIN_CHARGE, "Twin-charge timing"),
    ],
)
def test_topology_specific_spark_notes_are_added(topology: ForcedInductionTopology, label: str) -> None:
    result = _generate(topology=topology, compression_ratio=9.5)
    labels = {a.label for a in result.assumptions}
    assert label in labels
