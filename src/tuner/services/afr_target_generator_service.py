"""Conservative AFR target table generator.

Produces a 16 × 16 starter AFR target table (in AFR units, e.g. 14.7 = stoich)
from engine topology and calibration intent.  The table is always safe for a
first start — it does not attempt to produce an optimal tune, only a starting
point that the operator can review and adjust before staging.

Layout
------
Row 0   = lowest MAP / load bin (idle / vacuum).
Row 15  = highest MAP / load bin (WOT or peak boost).
Column 0  = lowest RPM bin (cranking / idle RPM).
Column 15 = highest RPM bin (redline area).

Design rules
------------
- NA engines: stoich (14.7) at cruise, progressively richer toward WOT (~13.0).
- Boosted engines: stoich at light load, much richer at high load (11.5–12.5)
  to protect against heat and detonation.
- First-start intent: shift the table 0.5–1.0 AFR richer overall for safety.
- Drivable-base intent: use the nominal targets without extra enrichment.
- Missing context: fall back to a flat 14.0 table (conservative but universal).
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
# Table dimensions — must match VE / spark tables
# ---------------------------------------------------------------------------

_ROWS = 16
_COLS = 16

# ---------------------------------------------------------------------------
# Stoichiometric AFR constants
# ---------------------------------------------------------------------------

_STOICH_PETROL = 14.7   # standard petrol / gasoline
_STOICH_E10 = 14.1      # ~10 % ethanol blend
_STOICH_E85 = 9.8       # E85

# ---------------------------------------------------------------------------
# NA target shaping
# ---------------------------------------------------------------------------

# Cruise (low–mid load, mid RPM): target stoich for fuel economy.
_NA_CRUISE_AFR = 14.7

# Light load / idle: slightly lean is fine; stoich is safe.
_NA_IDLE_AFR = 14.7

# Moderate load enrichment as load increases toward WOT.
_NA_LOAD_ENRICHMENT = 1.5   # AFR reduction from cruise to WOT (14.7 → 13.2)

# WOT target.
_NA_WOT_AFR = _NA_CRUISE_AFR - _NA_LOAD_ENRICHMENT   # 13.2

# High-RPM WOT enrichment: very high RPM benefits from slightly more fuel.
_NA_HIGH_RPM_BONUS = 0.2    # extra AFR reduction at redline

# ---------------------------------------------------------------------------
# Forced-induction target shaping
# ---------------------------------------------------------------------------

# For boosted applications WOT AFR must be much richer to protect the engine.
_BOOST_WOT_AFR = 11.5        # single turbo / supercharger WOT
_BOOST_WOT_AFR_TWIN = 11.5   # twin turbo (same — conservative)
_BOOST_WOT_AFR_COMPOUND = 11.0  # compound: more aggressive boost → extra rich
_BOOST_WOT_AFR_SC = 12.0     # supercharger: intercooled, slightly less rich
_BOOST_WOT_AFR_TWIN_CHARGE = 11.5
_HIGH_BOOST_RICHER_AFR_STEP = 0.3
_HIGH_BOOST_THRESHOLD_KPA_ABS = 200.0
_NO_INTERCOOLER_RICHER_AFR_STEP = 0.2
_SEQUENTIAL_TRANSITION_BLEND_LOW = 0.35
_SEQUENTIAL_TRANSITION_BLEND_HIGH = 0.7
_TWIN_CHARGE_TRANSITION_START = 0.55

# Light-load / pre-boost cells: still near stoich.
_BOOST_LIGHT_LOAD_AFR = 14.7

# Row index at which boost enrichment starts (roughly half-load).
_BOOST_START_ROW = 8

# ---------------------------------------------------------------------------
# Calibration intent adjustments
# ---------------------------------------------------------------------------

# First-start: extra enrichment across the board for safety.
_FIRST_START_ENRICHMENT = 0.7   # AFR reduction everywhere


@dataclass(slots=True, frozen=True)
class AfrTargetGeneratorResult:
    """Result of the conservative AFR target table generator.

    ``values`` is a flat row-major list of ``rows × columns`` AFR values.
    Row 0 is the lowest load bin; row 15 is WOT / peak boost.
    Column 0 is the lowest RPM bin; column 15 is the highest RPM bin.

    Values are in standard AFR units (14.7 = stoich for petrol).

    The result is *staged only* — it must never be applied automatically.
    """

    values: tuple[float, ...]
    rows: int
    columns: int
    topology: ForcedInductionTopology
    stoich: float
    summary: str
    warnings: tuple[str, ...]
    assumptions: tuple[GeneratorAssumption, ...] = ()

    def as_list(self) -> list[float]:
        return list(self.values)


class AfrTargetGeneratorService:
    """Generates a conservative starter AFR target table.

    The generator always produces a result.  When context is incomplete it
    falls back to a flat conservative table and records warnings.

    All outputs must be reviewed by the operator before staging.
    """

    def generate(
        self,
        ctx: GeneratorInputContext,
        calibration_intent: CalibrationIntent = CalibrationIntent.FIRST_START,
    ) -> AfrTargetGeneratorResult:
        """Generate a conservative 16 × 16 AFR target table.

        Parameters
        ----------
        ctx:
            Generator input context from hardware setup pages and the operator
            engine context service.

        Returns
        -------
        AfrTargetGeneratorResult
            Always returns a result; ``warnings`` records any missing inputs
            that caused the generator to fall back to defaults.
        """
        warnings: list[str] = []
        assumptions: list[GeneratorAssumption] = []

        topology = ctx.forced_induction_topology
        intent = calibration_intent
        stoich = ctx.stoich_ratio if ctx.stoich_ratio is not None else _STOICH_PETROL

        if topology is None:
            topology = ForcedInductionTopology.NA
            warnings.append("Induction topology not set — assuming naturally-aspirated.")

        table = self._base_table(topology, stoich, ctx)

        if intent == CalibrationIntent.FIRST_START:
            table = self._apply_first_start_enrichment(table)

        table = self._clamp(table)

        topology_name = topology.value.replace("_", " ").title()
        intent_name = "first-start" if intent == CalibrationIntent.FIRST_START else "drivable base"
        summary = (
            f"Conservative AFR targets for {topology_name} engine, {intent_name} intent. "
            f"Stoich: {stoich:.1f}. Review WOT cells before first run under load."
        )

        _src = AssumptionSource.FROM_CONTEXT
        _fb = AssumptionSource.CONSERVATIVE_FALLBACK
        assumptions.append(GeneratorAssumption(
            label="Stoich ratio",
            value_str=f"{stoich:.1f}",
            source=_src if ctx.stoich_ratio is not None else _fb,
            note="" if ctx.stoich_ratio is not None else "Defaulted to petrol stoich (14.7)",
        ))
        assumptions.append(GeneratorAssumption(
            label="Calibration intent",
            value_str=intent.value,
            source=_src,
        ))
        assumptions.append(GeneratorAssumption(
            label="Induction topology",
            value_str=topology.value,
            source=_src,
        ))
        if topology != ForcedInductionTopology.NA:
            assumptions.append(GeneratorAssumption(
                label="Boost target",
                value_str=f"{ctx.boost_target_kpa:.0f} kPa" if ctx.boost_target_kpa is not None else "not set",
                source=_src if ctx.boost_target_kpa is not None else _fb,
            ))
            assumptions.append(GeneratorAssumption(
                label="Intercooler",
                value_str="present" if ctx.intercooler_present else "absent",
                source=_src,
            ))
            assumptions.append(GeneratorAssumption(
                label="Injector pressure model",
                value_str=ctx.injector_pressure_model or "not set",
                source=_src if ctx.injector_pressure_model is not None else _fb,
                note="" if ctx.injector_pressure_model is not None else "Boosted AFR targets assume a conservative generic pressure model.",
            ))
            if topology == ForcedInductionTopology.TWIN_TURBO_UNEQUAL:
                assumptions.append(GeneratorAssumption(
                    label="Unequal twin sizing",
                    value_str="starter table treated like identical twins",
                    source=_fb,
                    note="Unequal turbo sizing was not modeled in AFR shaping; review transition and WOT cells once logs exist.",
                ))

        return AfrTargetGeneratorResult(
            values=tuple(round(v, 2) for v in table),
            rows=_ROWS,
            columns=_COLS,
            topology=topology,
            stoich=stoich,
            summary=summary,
            warnings=tuple(warnings),
            assumptions=tuple(assumptions),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base_table(
        topology: ForcedInductionTopology,
        stoich: float,
        ctx: GeneratorInputContext,
    ) -> list[float]:
        """Build the base table before intent adjustments."""
        table: list[float] = []

        is_boosted = topology != ForcedInductionTopology.NA

        base_wot_afr = {
            ForcedInductionTopology.NA: _NA_WOT_AFR,
            ForcedInductionTopology.SINGLE_TURBO: _BOOST_WOT_AFR,
            ForcedInductionTopology.TWIN_TURBO_IDENTICAL: _BOOST_WOT_AFR_TWIN,
            ForcedInductionTopology.TWIN_TURBO_SEQUENTIAL: _BOOST_WOT_AFR,
            ForcedInductionTopology.TWIN_TURBO_COMPOUND: _BOOST_WOT_AFR_COMPOUND,
            ForcedInductionTopology.TWIN_TURBO_UNEQUAL: _BOOST_WOT_AFR_TWIN,
            ForcedInductionTopology.SINGLE_SUPERCHARGER: _BOOST_WOT_AFR_SC,
            ForcedInductionTopology.TWIN_CHARGE: _BOOST_WOT_AFR_TWIN_CHARGE,
        }.get(topology, _NA_WOT_AFR)

        if topology != ForcedInductionTopology.NA and ctx.boost_target_kpa is not None and ctx.boost_target_kpa >= _HIGH_BOOST_THRESHOLD_KPA_ABS:
            base_wot_afr -= _HIGH_BOOST_RICHER_AFR_STEP
        if topology != ForcedInductionTopology.NA and not ctx.intercooler_present:
            base_wot_afr -= _NO_INTERCOOLER_RICHER_AFR_STEP

        for row in range(_ROWS):
            load_norm = row / (_ROWS - 1)   # 0.0 = idle, 1.0 = WOT

            for col in range(_COLS):
                rpm_norm = col / (_COLS - 1)   # 0.0 = lowest RPM, 1.0 = redline
                wot_afr = _AfrTargetGeneratorService._topology_wot_afr(
                    topology=topology,
                    base_wot_afr=base_wot_afr,
                    rpm_norm=rpm_norm,
                    load_norm=load_norm,
                )

                if not is_boosted:
                    afr = _AfrTargetGeneratorService._na_afr(load_norm, rpm_norm, wot_afr)
                else:
                    afr = _AfrTargetGeneratorService._boosted_afr(
                        load_norm, rpm_norm, wot_afr, stoich
                    )

                table.append(afr)

        return table

    @staticmethod
    def _topology_wot_afr(
        topology: ForcedInductionTopology,
        base_wot_afr: float,
        rpm_norm: float,
        load_norm: float,
    ) -> float:
        if topology == ForcedInductionTopology.TWIN_TURBO_SEQUENTIAL:
            twin_wot = _BOOST_WOT_AFR_TWIN
            if load_norm < 0.5:
                return base_wot_afr
            blend = min(1.0, max(0.0, (rpm_norm - _SEQUENTIAL_TRANSITION_BLEND_LOW) / (_SEQUENTIAL_TRANSITION_BLEND_HIGH - _SEQUENTIAL_TRANSITION_BLEND_LOW)))
            return base_wot_afr + (twin_wot - base_wot_afr) * blend
        if topology == ForcedInductionTopology.TWIN_CHARGE:
            turbo_wot = _BOOST_WOT_AFR
            sc_wot = _BOOST_WOT_AFR_SC
            blend = min(1.0, max(0.0, (load_norm - _TWIN_CHARGE_TRANSITION_START) / (1.0 - _TWIN_CHARGE_TRANSITION_START)))
            return sc_wot + (turbo_wot - sc_wot) * blend
        return base_wot_afr

    @staticmethod
    def _na_afr(load_norm: float, rpm_norm: float, wot_afr: float) -> float:
        """Shape a single NA AFR target cell."""
        # At low load: stoich; progress toward richer as load increases.
        # At WOT, add a small high-RPM extra enrichment.
        base = _NA_CRUISE_AFR - load_norm * (_NA_CRUISE_AFR - wot_afr)
        rpm_bonus = rpm_norm * _NA_HIGH_RPM_BONUS if load_norm > 0.7 else 0.0
        return base - rpm_bonus

    @staticmethod
    def _boosted_afr(
        load_norm: float,
        rpm_norm: float,
        wot_afr: float,
        stoich: float,
    ) -> float:
        """Shape a single boosted AFR target cell.

        Below the boost onset row: stoich.
        Above: progressively richer toward wot_afr.
        """
        boost_row_norm = _BOOST_START_ROW / (_ROWS - 1)
        if load_norm <= boost_row_norm:
            return stoich
        boost_norm = (load_norm - boost_row_norm) / (1.0 - boost_row_norm)
        base = stoich - boost_norm * (stoich - wot_afr)
        return base

    @staticmethod
    def _apply_first_start_enrichment(table: list[float]) -> list[float]:
        return [v - _FIRST_START_ENRICHMENT for v in table]

    @staticmethod
    def _clamp(table: list[float]) -> list[float]:
        """Ensure all values stay within a safe range (10.0–18.0 AFR)."""
        return [max(10.0, min(18.0, v)) for v in table]


# Private alias used inside static methods to access class-level helpers cleanly.
_AfrTargetGeneratorService = AfrTargetGeneratorService
