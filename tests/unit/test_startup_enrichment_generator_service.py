"""Tests for StartupEnrichmentGeneratorService."""
from __future__ import annotations

import pytest

from tuner.domain.generator_context import ForcedInductionTopology, GeneratorInputContext
from tuner.domain.operator_engine_context import CalibrationIntent
from tuner.services.startup_enrichment_generator_service import (
    StartupEnrichmentGeneratorService,
    _WUE_BINS,
    _CRANK_BINS,
    _ASE_BINS,
)


def _svc() -> StartupEnrichmentGeneratorService:
    return StartupEnrichmentGeneratorService()


def _ctx(**kwargs) -> GeneratorInputContext:
    return GeneratorInputContext(**kwargs)


# ===========================================================================
# Warmup Enrichment (WUE)
# ===========================================================================

class TestWarmupEnrichment:

    def test_result_has_correct_shape(self) -> None:
        result = _svc().generate_wue(_ctx())
        assert len(result.clt_bins) == 10
        assert len(result.enrichment_pct) == 10

    def test_bins_match_reference(self) -> None:
        result = _svc().generate_wue(_ctx())
        assert result.clt_bins == _WUE_BINS

    def test_warm_end_is_exactly_100_pct(self) -> None:
        """Last bin must be exactly 100 % — no enrichment at operating temp."""
        result = _svc().generate_wue(_ctx())
        assert result.enrichment_pct[-1] == pytest.approx(100.0)

    def test_cold_end_is_richer_than_warm_end(self) -> None:
        result = _svc().generate_wue(_ctx())
        assert result.enrichment_pct[0] > result.enrichment_pct[-1]

    def test_values_are_monotonically_decreasing(self) -> None:
        """Enrichment should taper monotonically from cold to warm."""
        result = _svc().generate_wue(_ctx())
        pcts = result.enrichment_pct
        for a, b in zip(pcts, pcts[1:]):
            assert a >= b, f"Not monotone: {a} followed by {b}"

    def test_all_values_at_or_above_100_pct(self) -> None:
        for intent in CalibrationIntent:
            result = _svc().generate_wue(_ctx(), intent)
            for v in result.enrichment_pct:
                assert v >= 100.0, f"WUE {v} is below 100 %"

    def test_all_values_within_u08_range(self) -> None:
        for intent in CalibrationIntent:
            result = _svc().generate_wue(_ctx(), intent)
            for v in result.enrichment_pct:
                assert 100.0 <= v <= 255.0

    def test_first_start_richer_than_drivable_base(self) -> None:
        first = _svc().generate_wue(_ctx(), CalibrationIntent.FIRST_START)
        drivable = _svc().generate_wue(_ctx(), CalibrationIntent.DRIVABLE_BASE)
        assert first.enrichment_pct[0] > drivable.enrichment_pct[0]

    def test_e85_richer_than_petrol_at_cold_end(self) -> None:
        """E85 (stoich ≈ 9.8) needs significantly more cold enrichment than petrol."""
        petrol = _svc().generate_wue(_ctx(stoich_ratio=14.7), CalibrationIntent.DRIVABLE_BASE)
        e85 = _svc().generate_wue(_ctx(stoich_ratio=9.8), CalibrationIntent.DRIVABLE_BASE)
        assert e85.enrichment_pct[0] > petrol.enrichment_pct[0]

    def test_missing_stoich_produces_warning(self) -> None:
        result = _svc().generate_wue(_ctx())  # stoich_ratio = None
        assert any("stoich" in w.lower() for w in result.warnings)

    def test_known_stoich_produces_no_stoich_warning(self) -> None:
        result = _svc().generate_wue(_ctx(stoich_ratio=14.7), CalibrationIntent.DRIVABLE_BASE)
        assert not any("stoich" in w.lower() for w in result.warnings)

    def test_summary_is_non_empty(self) -> None:
        result = _svc().generate_wue(_ctx())
        assert len(result.summary) > 0

    def test_warnings_is_tuple(self) -> None:
        result = _svc().generate_wue(_ctx())
        assert isinstance(result.warnings, tuple)

    def test_e10_blend_between_petrol_and_e85(self) -> None:
        """An E10-like stoich ratio should produce enrichment between petrol and E85."""
        petrol = _svc().generate_wue(_ctx(stoich_ratio=14.7), CalibrationIntent.DRIVABLE_BASE)
        blend = _svc().generate_wue(_ctx(stoich_ratio=13.5), CalibrationIntent.DRIVABLE_BASE)
        e85 = _svc().generate_wue(_ctx(stoich_ratio=9.8), CalibrationIntent.DRIVABLE_BASE)
        assert petrol.enrichment_pct[0] <= blend.enrichment_pct[0] <= e85.enrichment_pct[0]

    def test_flow_only_injector_data_increases_cold_wue(self) -> None:
        full = _svc().generate_wue(
            _ctx(injector_characterization="full_characterization"),
            CalibrationIntent.DRIVABLE_BASE,
        )
        flow_only = _svc().generate_wue(
            _ctx(injector_characterization="nominal_flow_only"),
            CalibrationIntent.DRIVABLE_BASE,
        )
        assert flow_only.enrichment_pct[0] > full.enrichment_pct[0]


# ===========================================================================
# Cranking Enrichment
# ===========================================================================

class TestCrankingEnrichment:

    def test_result_has_correct_shape(self) -> None:
        result = _svc().generate_cranking(_ctx())
        assert len(result.clt_bins) == 4
        assert len(result.enrichment_pct) == 4

    def test_bins_match_reference(self) -> None:
        result = _svc().generate_cranking(_ctx())
        assert result.clt_bins == _CRANK_BINS

    def test_warm_end_is_exactly_100_pct(self) -> None:
        result = _svc().generate_cranking(_ctx())
        assert result.enrichment_pct[-1] == pytest.approx(100.0)

    def test_cold_end_is_richer_than_warm_end(self) -> None:
        result = _svc().generate_cranking(_ctx())
        assert result.enrichment_pct[0] > result.enrichment_pct[-1]

    def test_all_values_at_or_above_100_pct(self) -> None:
        for intent in CalibrationIntent:
            result = _svc().generate_cranking(_ctx(), intent)
            for v in result.enrichment_pct:
                assert v >= 100.0

    def test_first_start_richer_than_drivable_base(self) -> None:
        first = _svc().generate_cranking(_ctx(), CalibrationIntent.FIRST_START)
        drivable = _svc().generate_cranking(_ctx(), CalibrationIntent.DRIVABLE_BASE)
        assert first.enrichment_pct[0] > drivable.enrichment_pct[0]

    def test_high_compression_less_enrichment_than_low_compression(self) -> None:
        """High-CR engine cranks easier cold — needs less enrichment."""
        high_cr = _svc().generate_cranking(
            _ctx(compression_ratio=12.0), CalibrationIntent.DRIVABLE_BASE
        )
        low_cr = _svc().generate_cranking(
            _ctx(compression_ratio=7.5), CalibrationIntent.DRIVABLE_BASE
        )
        assert high_cr.enrichment_pct[0] < low_cr.enrichment_pct[0]

    def test_missing_compression_ratio_produces_warning(self) -> None:
        result = _svc().generate_cranking(_ctx())
        assert any("compression" in w.lower() for w in result.warnings)

    def test_known_cr_produces_no_cr_warning(self) -> None:
        result = _svc().generate_cranking(_ctx(compression_ratio=9.5), CalibrationIntent.DRIVABLE_BASE)
        assert not any("compression" in w.lower() for w in result.warnings)

    def test_summary_is_non_empty(self) -> None:
        assert len(_svc().generate_cranking(_ctx()).summary) > 0

    def test_warnings_is_tuple(self) -> None:
        assert isinstance(_svc().generate_cranking(_ctx()).warnings, tuple)

    def test_values_within_u08_range(self) -> None:
        for intent in CalibrationIntent:
            result = _svc().generate_cranking(_ctx(), intent)
            for v in result.enrichment_pct:
                assert 100.0 <= v <= 255.0

    def test_flow_only_injector_data_increases_cranking_enrichment(self) -> None:
        full = _svc().generate_cranking(
            _ctx(injector_characterization="full_characterization"),
            CalibrationIntent.DRIVABLE_BASE,
        )
        flow_only = _svc().generate_cranking(
            _ctx(injector_characterization="nominal_flow_only"),
            CalibrationIntent.DRIVABLE_BASE,
        )
        assert flow_only.enrichment_pct[0] > full.enrichment_pct[0]


# ===========================================================================
# After-Start Enrichment (ASE)
# ===========================================================================

class TestAfterStartEnrichment:

    def test_result_has_correct_shape(self) -> None:
        result = _svc().generate_ase(_ctx())
        assert len(result.clt_bins) == 4
        assert len(result.enrichment_pct) == 4
        assert len(result.duration_seconds) == 4

    def test_bins_match_reference(self) -> None:
        result = _svc().generate_ase(_ctx())
        assert result.clt_bins == _ASE_BINS

    def test_cold_pct_higher_than_warm_pct(self) -> None:
        """Cold CLT bins should have higher added enrichment than warm bins."""
        result = _svc().generate_ase(_ctx())
        assert result.enrichment_pct[0] >= result.enrichment_pct[-1]

    def test_cold_duration_longer_than_warm_duration(self) -> None:
        result = _svc().generate_ase(_ctx())
        assert result.duration_seconds[0] >= result.duration_seconds[-1]

    def test_all_pct_values_non_negative(self) -> None:
        for intent in CalibrationIntent:
            result = _svc().generate_ase(_ctx(), intent)
            for v in result.enrichment_pct:
                assert v >= 0.0

    def test_all_duration_values_non_negative(self) -> None:
        for intent in CalibrationIntent:
            result = _svc().generate_ase(_ctx(), intent)
            for v in result.duration_seconds:
                assert v >= 0.0

    def test_first_start_larger_enrichment_than_drivable(self) -> None:
        first = _svc().generate_ase(_ctx(), CalibrationIntent.FIRST_START)
        drivable = _svc().generate_ase(_ctx(), CalibrationIntent.DRIVABLE_BASE)
        assert first.enrichment_pct[0] > drivable.enrichment_pct[0]

    def test_first_start_longer_duration_than_drivable(self) -> None:
        first = _svc().generate_ase(_ctx(), CalibrationIntent.FIRST_START)
        drivable = _svc().generate_ase(_ctx(), CalibrationIntent.DRIVABLE_BASE)
        assert first.duration_seconds[0] > drivable.duration_seconds[0]

    def test_forced_induction_produces_warning(self) -> None:
        result = _svc().generate_ase(
            _ctx(forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO)
        )
        assert len(result.warnings) > 0

    def test_na_produces_no_warnings(self) -> None:
        result = _svc().generate_ase(
            _ctx(forced_induction_topology=ForcedInductionTopology.NA),
            CalibrationIntent.DRIVABLE_BASE,
        )
        assert result.warnings == ()

    def test_summary_is_non_empty(self) -> None:
        assert len(_svc().generate_ase(_ctx()).summary) > 0

    def test_warnings_is_tuple(self) -> None:
        assert isinstance(_svc().generate_ase(_ctx()).warnings, tuple)

    def test_pct_within_u08_range(self) -> None:
        for intent in CalibrationIntent:
            result = _svc().generate_ase(_ctx(), intent)
            for v in result.enrichment_pct:
                assert 0.0 <= v <= 155.0

    def test_count_within_u08_range(self) -> None:
        for intent in CalibrationIntent:
            result = _svc().generate_ase(_ctx(), intent)
            for v in result.duration_seconds:
                assert 0.0 <= v <= 255.0

    def test_itb_and_flow_only_increase_ase(self) -> None:
        base = _svc().generate_ase(
            _ctx(injector_characterization="full_characterization"),
            CalibrationIntent.DRIVABLE_BASE,
        )
        shaped = _svc().generate_ase(
            _ctx(
                intake_manifold_style="itb",
                injector_characterization="nominal_flow_only",
                head_flow_class="race_ported",
            ),
            CalibrationIntent.DRIVABLE_BASE,
        )
        assert shaped.enrichment_pct[0] > base.enrichment_pct[0]
        assert shaped.duration_seconds[0] > base.duration_seconds[0]


# ---------------------------------------------------------------------------
# GeneratorAssumption output
# ---------------------------------------------------------------------------

def test_wue_result_includes_assumptions() -> None:
    from tuner.domain.generator_context import GeneratorInputContext
    from tuner.services.startup_enrichment_generator_service import StartupEnrichmentGeneratorService
    result = StartupEnrichmentGeneratorService().generate_wue(GeneratorInputContext())
    assert len(result.assumptions) > 0


def test_wue_stoich_fallback_when_absent() -> None:
    from tuner.domain.generator_context import AssumptionSource, GeneratorInputContext
    from tuner.services.startup_enrichment_generator_service import StartupEnrichmentGeneratorService
    result = StartupEnrichmentGeneratorService().generate_wue(GeneratorInputContext())
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Stoich / fuel type"].source == AssumptionSource.CONSERVATIVE_FALLBACK


def test_cranking_compression_fallback_when_absent() -> None:
    from tuner.domain.generator_context import AssumptionSource, GeneratorInputContext
    from tuner.services.startup_enrichment_generator_service import StartupEnrichmentGeneratorService
    result = StartupEnrichmentGeneratorService().generate_cranking(GeneratorInputContext())
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Compression ratio"].source == AssumptionSource.CONSERVATIVE_FALLBACK


def test_cranking_compression_from_context_when_set() -> None:
    from tuner.domain.generator_context import AssumptionSource, GeneratorInputContext
    from tuner.services.startup_enrichment_generator_service import StartupEnrichmentGeneratorService
    ctx = GeneratorInputContext(compression_ratio=10.0)
    result = StartupEnrichmentGeneratorService().generate_cranking(ctx)
    by_label = {a.label: a for a in result.assumptions}
    assert by_label["Compression ratio"].source == AssumptionSource.FROM_CONTEXT


def test_ase_result_includes_assumptions() -> None:
    from tuner.domain.generator_context import GeneratorInputContext
    from tuner.services.startup_enrichment_generator_service import StartupEnrichmentGeneratorService
    result = StartupEnrichmentGeneratorService().generate_ase(GeneratorInputContext())
    assert len(result.assumptions) > 0
