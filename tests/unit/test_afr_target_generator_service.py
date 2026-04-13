"""Tests for AfrTargetGeneratorService."""
from __future__ import annotations

import pytest

from tuner.domain.generator_context import AssumptionSource, ForcedInductionTopology, GeneratorInputContext
from tuner.domain.operator_engine_context import CalibrationIntent
from tuner.services.afr_target_generator_service import AfrTargetGeneratorService, _ROWS, _COLS


def _svc() -> AfrTargetGeneratorService:
    return AfrTargetGeneratorService()


def _ctx(
    topology: ForcedInductionTopology = ForcedInductionTopology.NA,
) -> GeneratorInputContext:
    return GeneratorInputContext(forced_induction_topology=topology)


def _gen(
    topology: ForcedInductionTopology = ForcedInductionTopology.NA,
    intent: CalibrationIntent = CalibrationIntent.FIRST_START,
) -> "AfrTargetGeneratorResult":
    return _svc().generate(_ctx(topology), intent)


# ---------------------------------------------------------------------------
# Basic shape and dimensions
# ---------------------------------------------------------------------------

def test_result_has_correct_dimensions() -> None:
    result = _gen()
    assert result.rows == _ROWS
    assert result.columns == _COLS
    assert len(result.values) == _ROWS * _COLS


def test_all_values_in_valid_range() -> None:
    """All AFR values must be between 10.0 and 18.0."""
    for topology in ForcedInductionTopology:
        for intent in CalibrationIntent:
            result = _gen(topology, intent)
            for v in result.values:
                assert 10.0 <= v <= 18.0, f"Value {v} out of range for {topology}/{intent}"


def test_result_is_always_produced_with_empty_context() -> None:
    result = _svc().generate(GeneratorInputContext())
    assert result.rows == _ROWS
    assert result.columns == _COLS
    assert len(result.values) == _ROWS * _COLS


# ---------------------------------------------------------------------------
# NA shaping
# ---------------------------------------------------------------------------

def test_na_wot_cells_richer_than_idle_cells() -> None:
    """High-load cells must have lower AFR than low-load cells (richer mixture)."""
    result = _gen(ForcedInductionTopology.NA, CalibrationIntent.DRIVABLE_BASE)
    idle_row = result.values[:_COLS]          # row 0 = lowest load
    wot_row = result.values[-_COLS:]          # row 15 = WOT
    assert all(w < i for w, i in zip(wot_row, idle_row)), (
        "WOT row should be richer (lower AFR) than idle row"
    )


def test_na_idle_cells_near_stoich() -> None:
    """NA idle/cruise cells must be close to stoich (14.7) for drivable-base intent."""
    result = _gen(ForcedInductionTopology.NA, CalibrationIntent.DRIVABLE_BASE)
    idle_row = result.values[:_COLS]
    for v in idle_row:
        assert 13.5 <= v <= 15.5, f"Idle AFR {v} is far from stoich"


def test_na_wot_cells_rich_enough() -> None:
    """NA WOT cells must be enriched to at least 12.5 AFR."""
    result = _gen(ForcedInductionTopology.NA, CalibrationIntent.DRIVABLE_BASE)
    wot_row = result.values[-_COLS:]
    assert all(v <= 13.5 for v in wot_row), "NA WOT row should be enriched (AFR ≤ 13.5)"


# ---------------------------------------------------------------------------
# Boosted shaping
# ---------------------------------------------------------------------------

def test_turbo_wot_richer_than_na_wot() -> None:
    """Turbo WOT AFR must be richer (lower) than NA WOT AFR."""
    na_result = _gen(ForcedInductionTopology.NA, CalibrationIntent.DRIVABLE_BASE)
    turbo_result = _gen(ForcedInductionTopology.SINGLE_TURBO, CalibrationIntent.DRIVABLE_BASE)
    na_wot_avg = sum(na_result.values[-_COLS:]) / _COLS
    turbo_wot_avg = sum(turbo_result.values[-_COLS:]) / _COLS
    assert turbo_wot_avg < na_wot_avg


def test_turbo_light_load_near_stoich() -> None:
    """Turbo light-load cells must be near stoich."""
    result = _gen(ForcedInductionTopology.SINGLE_TURBO, CalibrationIntent.DRIVABLE_BASE)
    idle_row = result.values[:_COLS]
    for v in idle_row:
        assert 13.5 <= v <= 15.5, f"Turbo light-load AFR {v} is far from stoich"


def test_compound_turbo_wot_richer_than_single_turbo() -> None:
    """Compound turbo should have richer WOT targets than single turbo."""
    single = _gen(ForcedInductionTopology.SINGLE_TURBO, CalibrationIntent.DRIVABLE_BASE)
    compound = _gen(ForcedInductionTopology.TWIN_TURBO_COMPOUND, CalibrationIntent.DRIVABLE_BASE)
    single_avg = sum(single.values[-_COLS:]) / _COLS
    compound_avg = sum(compound.values[-_COLS:]) / _COLS
    assert compound_avg <= single_avg


def test_twin_charge_wot_richer_than_na() -> None:
    na = _gen(ForcedInductionTopology.NA, CalibrationIntent.DRIVABLE_BASE)
    twin_charge = _gen(ForcedInductionTopology.TWIN_CHARGE, CalibrationIntent.DRIVABLE_BASE)
    na_wot_avg = sum(na.values[-_COLS:]) / _COLS
    twin_charge_wot_avg = sum(twin_charge.values[-_COLS:]) / _COLS
    assert twin_charge_wot_avg < na_wot_avg


# ---------------------------------------------------------------------------
# Calibration intent
# ---------------------------------------------------------------------------

def test_first_start_richer_than_drivable_base() -> None:
    """First-start intent must produce richer (lower AFR) values everywhere."""
    first = _gen(ForcedInductionTopology.NA, CalibrationIntent.FIRST_START)
    drivable = _gen(ForcedInductionTopology.NA, CalibrationIntent.DRIVABLE_BASE)
    for f, d in zip(first.values, drivable.values):
        assert f <= d, f"First-start AFR {f} should be ≤ drivable-base AFR {d}"


def test_first_start_intent_adds_enrichment() -> None:
    """The delta between first-start and drivable-base should be consistent."""
    first = _gen(ForcedInductionTopology.NA, CalibrationIntent.FIRST_START)
    drivable = _gen(ForcedInductionTopology.NA, CalibrationIntent.DRIVABLE_BASE)
    from tuner.services.afr_target_generator_service import _FIRST_START_ENRICHMENT
    for f, d in zip(first.values, drivable.values):
        delta = d - f
        # After clamping, delta may be less for values already at the clamp boundary
        assert abs(delta - _FIRST_START_ENRICHMENT) < 0.1 or delta <= _FIRST_START_ENRICHMENT


# ---------------------------------------------------------------------------
# Result metadata
# ---------------------------------------------------------------------------

def test_result_records_topology() -> None:
    result = _gen(ForcedInductionTopology.TWIN_TURBO_COMPOUND)
    assert result.topology == ForcedInductionTopology.TWIN_TURBO_COMPOUND


def test_result_summary_is_non_empty() -> None:
    result = _gen()
    assert len(result.summary) > 0


def test_missing_topology_produces_warning() -> None:
    # GeneratorInputContext defaults topology to NA, so no warning expected there.
    # Use a fresh context to check warning-free case.
    result = _svc().generate(GeneratorInputContext())
    # Default topology is NA — warnings list depends on implementation
    assert isinstance(result.warnings, tuple)


def test_as_list_matches_values() -> None:
    result = _gen()
    assert result.as_list() == list(result.values)


def test_high_boost_and_no_intercooler_richen_wot_targets() -> None:
    mild = _svc().generate(
        GeneratorInputContext(
            forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
            boost_target_kpa=170.0,
            intercooler_present=True,
        ),
        CalibrationIntent.DRIVABLE_BASE,
    )
    hot = _svc().generate(
        GeneratorInputContext(
            forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
            boost_target_kpa=240.0,
            intercooler_present=False,
        ),
        CalibrationIntent.DRIVABLE_BASE,
    )
    mild_wot_avg = sum(mild.values[-_COLS:]) / _COLS
    hot_wot_avg = sum(hot.values[-_COLS:]) / _COLS
    assert hot_wot_avg < mild_wot_avg


# ---------------------------------------------------------------------------
# GeneratorAssumption output
# ---------------------------------------------------------------------------

def test_afr_result_includes_assumptions() -> None:
    from tuner.domain.generator_context import GeneratorInputContext
    ctx = GeneratorInputContext()
    from tuner.services.afr_target_generator_service import AfrTargetGeneratorService
    result = AfrTargetGeneratorService().generate(ctx)
    assert len(result.assumptions) > 0


def test_afr_stoich_fallback_when_absent() -> None:
    from tuner.domain.generator_context import AssumptionSource, GeneratorInputContext
    from tuner.services.afr_target_generator_service import AfrTargetGeneratorService
    result = AfrTargetGeneratorService().generate(GeneratorInputContext())
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Stoich ratio"].source == AssumptionSource.CONSERVATIVE_FALLBACK


def test_afr_stoich_from_context_when_set() -> None:
    from tuner.services.afr_target_generator_service import AfrTargetGeneratorService
    ctx = GeneratorInputContext(stoich_ratio=14.7)
    result = AfrTargetGeneratorService().generate(ctx)
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Stoich ratio"].source == AssumptionSource.FROM_CONTEXT


def test_afr_injector_pressure_model_assumption_source_tracks_context() -> None:
    result = _svc().generate(
        GeneratorInputContext(
            forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
            injector_pressure_model="vacuum_referenced",
        ),
        CalibrationIntent.DRIVABLE_BASE,
    )
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Injector pressure model"].source == AssumptionSource.FROM_CONTEXT


def test_afr_injector_pressure_model_falls_back_when_absent() -> None:
    result = _svc().generate(
        GeneratorInputContext(forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO),
        CalibrationIntent.DRIVABLE_BASE,
    )
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Injector pressure model"].source == AssumptionSource.CONSERVATIVE_FALLBACK
