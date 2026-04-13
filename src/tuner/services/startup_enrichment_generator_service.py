"""Conservative startup-enrichment table generators.

Produces conservative starter values for three Speeduino enrichment curves:

- **Warmup Enrichment (WUE)**: ``wueBins`` (10 CLT bins, °C) + ``wueRates``
  (10 enrichment %).  Tapers from a cold-start value to 100 % at normal
  operating temperature.

- **Cranking Enrichment**: ``crankingEnrichBins`` (4 CLT bins, °C) +
  ``crankingEnrichValues`` (4 enrichment %).  Extra fuel during cranking,
  scaled by compression ratio.

- **After-Start Enrichment (ASE)**: ``aseBins`` (4 CLT bins, °C) +
  ``asePct`` (4 added % on top of WUE) + ``aseCount`` (4 durations in
  seconds).

Reference values are the Speeduino u16p2 Ford300 Twin-GT28 base-startup tune:
  WUE bins  : -40, -26, 10, 19, 28, 37, 46, 58, 63, 64 °C
  WUE rates : 180, 175, 168, 154, 134, 121, 112, 104, 102, 100 %
  Crank bins: -40, 0, 30, 70 °C
  Crank vals: 140, 115, 105, 100 %
  ASE bins  : -20, 0, 40, 80 °C
  ASE pct   : 25, 20, 15, 10 %
  ASE count : 25, 20, 15, 6 s

All outputs are conservative starting points for operator review and staging.
They are never applied automatically.
"""
from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.generator_context import (
    AssumptionSource,
    ForcedInductionTopology,
    GeneratorAssumption,
    GeneratorInputContext,
)
from tuner.domain.operator_engine_context import CalibrationIntent

# ---------------------------------------------------------------------------
# Reference bins and values (Speeduino u16p2 / Ford300 base-startup tune)
# ---------------------------------------------------------------------------

_WUE_BINS: tuple[float, ...] = (
    -40.0, -26.0, 10.0, 19.0, 28.0, 37.0, 46.0, 58.0, 63.0, 64.0
)
_WUE_RATES_REF: tuple[float, ...] = (
    180.0, 175.0, 168.0, 154.0, 134.0, 121.0, 112.0, 104.0, 102.0, 100.0
)
_WUE_REF_COLD = 180.0   # cold-end value of the reference curve

_CRANK_BINS: tuple[float, ...] = (-40.0, 0.0, 30.0, 70.0)
_CRANK_RATES_REF: tuple[float, ...] = (140.0, 115.0, 105.0, 100.0)
_CRANK_REF_COLD = 140.0

_ASE_BINS: tuple[float, ...] = (-20.0, 0.0, 40.0, 80.0)
_ASE_PCT_REF: tuple[float, ...] = (25.0, 20.0, 15.0, 10.0)
_ASE_COUNT_REF: tuple[float, ...] = (25.0, 20.0, 15.0, 6.0)

# ---------------------------------------------------------------------------
# Cold-end enrichment by fuel type (WUE, drivable-base intent)
# ---------------------------------------------------------------------------

_STOICH_PETROL = 14.7
_STOICH_E85_THRESHOLD = 10.5   # stoich ≤ this → treat as E85-like
_STOICH_BLEND_THRESHOLD = 13.8  # stoich < this → proportionally blend

_WUE_COLD_PETROL = 180.0    # petrol / E10 cold-end enrichment %
_WUE_COLD_E85 = 210.0       # E85 needs substantially more cold enrichment

# ---------------------------------------------------------------------------
# Calibration-intent adjustments
# ---------------------------------------------------------------------------

_FIRST_START_WUE_EXTRA = 8.0    # additional % added to cold end for first-start
_FIRST_START_CRANK_EXTRA = 8.0  # same for cranking
_FIRST_START_ASE_PCT_EXTRA = 5.0
_FIRST_START_ASE_COUNT_EXTRA = 5.0

# ---------------------------------------------------------------------------
# Compression-ratio adjustments for cranking
# ---------------------------------------------------------------------------

_CR_HIGH_THRESHOLD = 11.0   # engines at or above this CR need slightly less
_CR_LOW_THRESHOLD = 8.0     # engines at or below this CR need slightly more

_CRANK_CR_HIGH_DELTA = -8.0     # subtract from cold-end value for high-CR
_CRANK_CR_LOW_DELTA = 12.0      # add to cold-end value for low-CR

_FLOW_ONLY_WUE_EXTRA = 6.0
_FLOW_ONLY_CRANK_EXTRA = 5.0
_FLOW_ONLY_ASE_PCT_EXTRA = 4.0
_FLOW_ONLY_ASE_COUNT_EXTRA = 3.0
_SINGLE_DEADTIME_WUE_EXTRA = 3.0
_SINGLE_DEADTIME_CRANK_EXTRA = 2.0
_SINGLE_DEADTIME_ASE_PCT_EXTRA = 2.0
_SINGLE_DEADTIME_ASE_COUNT_EXTRA = 1.0

_ITB_ASE_PCT_EXTRA = 3.0
_ITB_ASE_COUNT_EXTRA = 2.0
_RACE_PORTED_ASE_PCT_EXTRA = 2.0
_RACE_PORTED_ASE_COUNT_EXTRA = 1.0


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class WarmupEnrichmentGeneratorResult:
    """Generated warmup enrichment (WUE) starter curve.

    ``clt_bins`` and ``enrichment_pct`` are parallel 10-element tuples.
    ``enrichment_pct`` tapers from a cold-start peak to exactly 100 % at the
    last (warmest) bin.  All values are in the Speeduino U08 scale where
    100 = no enrichment.
    """

    clt_bins: tuple[float, ...]
    enrichment_pct: tuple[float, ...]
    summary: str
    warnings: tuple[str, ...]
    assumptions: tuple[GeneratorAssumption, ...] = ()

    def as_bins_list(self) -> list[float]:
        return list(self.clt_bins)

    def as_rates_list(self) -> list[float]:
        return list(self.enrichment_pct)


@dataclass(slots=True, frozen=True)
class CrankingEnrichmentGeneratorResult:
    """Generated cranking enrichment starter curve.

    ``clt_bins`` and ``enrichment_pct`` are parallel 4-element tuples.
    ``enrichment_pct`` tapers from a cold peak to 100 % at the warmest bin.
    """

    clt_bins: tuple[float, ...]
    enrichment_pct: tuple[float, ...]
    summary: str
    warnings: tuple[str, ...]
    assumptions: tuple[GeneratorAssumption, ...] = ()

    def as_bins_list(self) -> list[float]:
        return list(self.clt_bins)

    def as_values_list(self) -> list[float]:
        return list(self.enrichment_pct)


@dataclass(slots=True, frozen=True)
class AfterStartEnrichmentGeneratorResult:
    """Generated after-start enrichment (ASE) starter curve.

    ``clt_bins``, ``enrichment_pct``, and ``duration_seconds`` are parallel
    4-element tuples.  ``enrichment_pct`` is the *added* enrichment on top of
    WUE (0 = no ASE; 25 = 25 % extra for the ASE period).
    ``duration_seconds`` is how long each enrichment level stays active after
    the engine fires.
    """

    clt_bins: tuple[float, ...]
    enrichment_pct: tuple[float, ...]
    duration_seconds: tuple[float, ...]
    summary: str
    warnings: tuple[str, ...]
    assumptions: tuple[GeneratorAssumption, ...] = ()

    def as_bins_list(self) -> list[float]:
        return list(self.clt_bins)

    def as_pct_list(self) -> list[float]:
        return list(self.enrichment_pct)

    def as_count_list(self) -> list[float]:
        return list(self.duration_seconds)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class StartupEnrichmentGeneratorService:
    """Generates conservative starter values for WUE, cranking, and ASE curves.

    All three generators:

    - always produce a result (missing inputs fall back to reference values
      with warnings recorded)
    - scale from the Ford300 u16p2 reference curve shape
    - clamp to Speeduino U08 legal ranges
    - return summaries describing the output for operator review
    """

    def generate_wue(
        self,
        ctx: GeneratorInputContext,
        calibration_intent: CalibrationIntent = CalibrationIntent.FIRST_START,
    ) -> WarmupEnrichmentGeneratorResult:
        """Generate warmup enrichment bins and rates.

        Parameters
        ----------
        ctx:
            Generator input context (stoich_ratio used for fuel-type detection).
        calibration_intent:
            FIRST_START adds conservative extra enrichment at the cold end.

        Returns
        -------
        WarmupEnrichmentGeneratorResult
            Always returns a result; ``warnings`` records missing inputs.
        """
        warnings: list[str] = []

        cold_pct = self._wue_cold_pct(ctx, calibration_intent, warnings)
        raw = self._scale_from_reference(_WUE_RATES_REF, _WUE_REF_COLD, cold_pct)
        enrichment_pct = tuple(round(max(100.0, min(255.0, v)), 1) for v in raw)

        intent_label = _intent_label(calibration_intent)
        summary = (
            f"Conservative WUE starter ({intent_label}). "
            f"Cold enrichment: {cold_pct:.0f}% at {_WUE_BINS[0]:.0f}\u00b0C "
            f"\u2192 100% at {_WUE_BINS[-1]:.0f}\u00b0C. "
            "Review and adjust for your climate and cold-start idle quality."
        )

        _src = AssumptionSource.FROM_CONTEXT
        _fb = AssumptionSource.CONSERVATIVE_FALLBACK
        assumptions: tuple[GeneratorAssumption, ...] = (
            GeneratorAssumption(
                label="Stoich / fuel type",
                value_str=f"{ctx.stoich_ratio:.1f}" if ctx.stoich_ratio is not None else "not set (defaulted to petrol 14.7)",
                source=_src if ctx.stoich_ratio is not None else _fb,
            ),
            GeneratorAssumption(
                label="Injector data depth",
                value_str=ctx.injector_characterization or "not set",
                source=_src if ctx.injector_characterization is not None else _fb,
            ),
            GeneratorAssumption(
                label="Calibration intent",
                value_str=calibration_intent.value,
                source=_src,
            ),
        )

        return WarmupEnrichmentGeneratorResult(
            clt_bins=_WUE_BINS,
            enrichment_pct=enrichment_pct,
            summary=summary,
            warnings=tuple(warnings),
            assumptions=assumptions,
        )

    def generate_cranking(
        self,
        ctx: GeneratorInputContext,
        calibration_intent: CalibrationIntent = CalibrationIntent.FIRST_START,
    ) -> CrankingEnrichmentGeneratorResult:
        """Generate cranking enrichment bins and values.

        Parameters
        ----------
        ctx:
            Generator input context (compression_ratio used for cold-start scaling).
        calibration_intent:
            FIRST_START adds extra enrichment at the cold end.
        """
        warnings: list[str] = []

        cold_pct = self._crank_cold_pct(ctx, calibration_intent, warnings)
        raw = self._scale_from_reference(_CRANK_RATES_REF, _CRANK_REF_COLD, cold_pct)
        enrichment_pct = tuple(round(max(100.0, min(255.0, v)), 1) for v in raw)

        intent_label = _intent_label(calibration_intent)
        summary = (
            f"Conservative cranking enrichment ({intent_label}). "
            f"Cold: {cold_pct:.0f}% at {_CRANK_BINS[0]:.0f}\u00b0C "
            f"\u2192 100% at {_CRANK_BINS[-1]:.0f}\u00b0C. "
            "Review against your starter motor and cold-start fueling behavior."
        )

        _src = AssumptionSource.FROM_CONTEXT
        _fb = AssumptionSource.CONSERVATIVE_FALLBACK
        assumptions: tuple[GeneratorAssumption, ...] = (
            GeneratorAssumption(
                label="Compression ratio",
                value_str=f"{ctx.compression_ratio:.1f}:1" if ctx.compression_ratio is not None else "not set",
                source=_src if ctx.compression_ratio is not None else _fb,
            ),
            GeneratorAssumption(
                label="Stoich / fuel type",
                value_str=f"{ctx.stoich_ratio:.1f}" if ctx.stoich_ratio is not None else "not set (defaulted to petrol 14.7)",
                source=_src if ctx.stoich_ratio is not None else _fb,
            ),
            GeneratorAssumption(
                label="Calibration intent",
                value_str=calibration_intent.value,
                source=_src,
            ),
        )

        return CrankingEnrichmentGeneratorResult(
            clt_bins=_CRANK_BINS,
            enrichment_pct=enrichment_pct,
            summary=summary,
            warnings=tuple(warnings),
            assumptions=assumptions,
        )

    def generate_ase(
        self,
        ctx: GeneratorInputContext,
        calibration_intent: CalibrationIntent = CalibrationIntent.FIRST_START,
    ) -> AfterStartEnrichmentGeneratorResult:
        """Generate after-start enrichment (ASE) bins, percentages, and durations.

        Parameters
        ----------
        ctx:
            Generator input context (forced_induction_topology used for warnings).
        calibration_intent:
            FIRST_START adds extra enrichment % and duration at all CLT bins.
        """
        warnings: list[str] = []

        extra_pct = _FIRST_START_ASE_PCT_EXTRA if calibration_intent == CalibrationIntent.FIRST_START else 0.0
        extra_count = _FIRST_START_ASE_COUNT_EXTRA if calibration_intent == CalibrationIntent.FIRST_START else 0.0

        if ctx.injector_characterization == "nominal_flow_only":
            extra_pct += _FLOW_ONLY_ASE_PCT_EXTRA
            extra_count += _FLOW_ONLY_ASE_COUNT_EXTRA
            warnings.append(
                "Injector data is flow-only - ASE increased to cover startup transient uncertainty."
            )
        elif ctx.injector_characterization == "flow_plus_deadtime":
            extra_pct += _SINGLE_DEADTIME_ASE_PCT_EXTRA
            extra_count += _SINGLE_DEADTIME_ASE_COUNT_EXTRA

        if ctx.intake_manifold_style == "itb":
            extra_pct += _ITB_ASE_PCT_EXTRA
            extra_count += _ITB_ASE_COUNT_EXTRA
            warnings.append(
                "ITB manifold selected - ASE increased for low-speed airflow instability during startup."
            )
        if ctx.head_flow_class == "race_ported":
            extra_pct += _RACE_PORTED_ASE_PCT_EXTRA
            extra_count += _RACE_PORTED_ASE_COUNT_EXTRA

        enrichment_pct = tuple(
            round(max(0.0, min(155.0, v + extra_pct)), 1) for v in _ASE_PCT_REF
        )
        duration_seconds = tuple(
            round(max(0.0, min(255.0, v + extra_count)), 1) for v in _ASE_COUNT_REF
        )

        if ctx.forced_induction_topology != ForcedInductionTopology.NA:
            warnings.append(
                "Forced-induction engine detected: consider increasing ASE duration "
                "at cold CLT bins — boost at start can lean out the mixture briefly."
            )

        intent_label = _intent_label(calibration_intent)
        summary = (
            f"Conservative ASE starter ({intent_label}). "
            f"Added enrichment: {enrichment_pct[0]:.0f}% for {duration_seconds[0]:.0f}s "
            f"at {_ASE_BINS[0]:.0f}\u00b0C. "
            "Review enrichment levels against idle stability after first start."
        )

        _src = AssumptionSource.FROM_CONTEXT
        _fb = AssumptionSource.CONSERVATIVE_FALLBACK
        assumptions: tuple[GeneratorAssumption, ...] = (
            GeneratorAssumption(
                label="Calibration intent",
                value_str=calibration_intent.value,
                source=_src,
            ),
            GeneratorAssumption(
                label="Injector data depth",
                value_str=ctx.injector_characterization or "not set",
                source=_src if ctx.injector_characterization is not None else _fb,
            ),
            GeneratorAssumption(
                label="Manifold style",
                value_str=ctx.intake_manifold_style or "not set",
                source=_src if ctx.intake_manifold_style is not None else _fb,
            ),
            GeneratorAssumption(
                label="Induction topology",
                value_str=ctx.forced_induction_topology.value,
                source=_src,
            ),
        )

        return AfterStartEnrichmentGeneratorResult(
            clt_bins=_ASE_BINS,
            enrichment_pct=enrichment_pct,
            duration_seconds=duration_seconds,
            summary=summary,
            warnings=tuple(warnings),
            assumptions=assumptions,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wue_cold_pct(
        ctx: GeneratorInputContext,
        intent: CalibrationIntent,
        warnings: list[str],
    ) -> float:
        """Compute WUE cold-end enrichment % from stoich ratio and intent."""
        stoich = ctx.stoich_ratio

        if stoich is None:
            warnings.append(
                "Stoich ratio not set — assuming petrol (14.7). "
                "Review WUE if using E85 or high-ethanol blend."
            )
            cold_pct = _WUE_COLD_PETROL
        elif stoich <= _STOICH_E85_THRESHOLD:
            cold_pct = _WUE_COLD_E85
        elif stoich < _STOICH_BLEND_THRESHOLD:
            # Proportionally blend between E85 and petrol curves
            blend = (stoich - _STOICH_E85_THRESHOLD) / (
                _STOICH_BLEND_THRESHOLD - _STOICH_E85_THRESHOLD
            )
            cold_pct = _WUE_COLD_E85 + blend * (_WUE_COLD_PETROL - _WUE_COLD_E85)
        else:
            cold_pct = _WUE_COLD_PETROL

        if intent == CalibrationIntent.FIRST_START:
            cold_pct += _FIRST_START_WUE_EXTRA

        if ctx.injector_characterization == "nominal_flow_only":
            cold_pct += _FLOW_ONLY_WUE_EXTRA
            warnings.append(
                "Injector data is flow-only - adding extra cold-start enrichment for low-pulsewidth uncertainty."
            )
        elif ctx.injector_characterization == "flow_plus_deadtime":
            cold_pct += _SINGLE_DEADTIME_WUE_EXTRA
            warnings.append(
                "Injector data uses a single dead-time value - adding mild cold-start enrichment margin."
            )

        return cold_pct

    @staticmethod
    def _crank_cold_pct(
        ctx: GeneratorInputContext,
        intent: CalibrationIntent,
        warnings: list[str],
    ) -> float:
        """Compute cranking cold-end enrichment % from compression ratio and intent."""
        cr = ctx.compression_ratio
        cold_pct = _CRANK_REF_COLD

        if cr is None:
            warnings.append(
                "Compression ratio not set — using standard cranking enrichment baseline."
            )
        elif cr >= _CR_HIGH_THRESHOLD:
            cold_pct += _CRANK_CR_HIGH_DELTA
        elif cr <= _CR_LOW_THRESHOLD:
            cold_pct += _CRANK_CR_LOW_DELTA

        if intent == CalibrationIntent.FIRST_START:
            cold_pct += _FIRST_START_CRANK_EXTRA

        if ctx.injector_characterization == "nominal_flow_only":
            cold_pct += _FLOW_ONLY_CRANK_EXTRA
            warnings.append(
                "Injector data is flow-only - adding extra cranking enrichment for startup safety."
            )
        elif ctx.injector_characterization == "flow_plus_deadtime":
            cold_pct += _SINGLE_DEADTIME_CRANK_EXTRA

        return cold_pct

    @staticmethod
    def _scale_from_reference(
        ref_rates: tuple[float, ...],
        ref_cold: float,
        target_cold: float,
    ) -> tuple[float, ...]:
        """Scale a reference enrichment curve so its cold end matches ``target_cold``.

        The warm end (100 %) is anchored and not moved.  The shape of the
        intermediate values is preserved by scaling the excess above 100 %
        proportionally.
        """
        ref_excess = max(1e-6, ref_cold - 100.0)
        target_excess = target_cold - 100.0
        scale = target_excess / ref_excess
        return tuple(100.0 + (v - 100.0) * scale for v in ref_rates)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _intent_label(intent: CalibrationIntent) -> str:
    return "first-start" if intent == CalibrationIntent.FIRST_START else "drivable base"
