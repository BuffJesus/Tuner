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
# Table dimensions — match standard Speeduino spark advance table
# ---------------------------------------------------------------------------

_ROWS = 16   # load / MAP axis (row 0 = lowest load, row 15 = highest load)
_COLS = 16   # RPM axis       (col 0 = lowest RPM, col 15 = highest RPM)

# ---------------------------------------------------------------------------
# Conservative timing constants (degrees BTDC)
# ---------------------------------------------------------------------------

# Base timing for a first-start calibration at idle / very low load.
_IDLE_TIMING_BASE = 10.0

# Maximum conservative advance for a naturally-aspirated engine at WOT, high RPM.
# Real WOT timing is engine-specific and must be tuned; keep this cautious.
_NA_WOT_MAX = 28.0

# Mid-cruise advance target (moderate load, mid RPM).
_NA_MID_ADVANCE = 22.0

# Compression ratio effect: high-CR engines are more knock-prone.
# Reduce maximum timing by this many degrees per unit of CR above the reference.
_CR_REFERENCE = 9.5          # typical NA engine reference
_CR_TIMING_PENALTY_PER_UNIT = 1.5    # degrees per unit above reference

# Knock-sensitive cutoff: above this CR, add extra conservatism at WOT.
_HIGH_CR_THRESHOLD = 11.0
_HIGH_CR_WOT_PENALTY = 3.0

# Drivable-base intent: slightly more advance than first-start so the engine
# pulls properly for a first road drive.
_DRIVABLE_BONUS = 3.0

# Forced-induction timing retard: boost increases knock risk significantly.
# These are applied as a load-normalised reduction so that non-boosted cells
# are unaffected (pre-boost cells keep NA timing).
_TURBO_WOT_RETARD = 10.0      # degrees pulled from WOT rows
_SUPERCHARGER_WOT_RETARD = 6.0  # less retard — boost onset is known/controlled
_TWIN_CHARGE_WOT_RETARD = 8.0
_BOOST_RETARD_BASELINE_KPA_ABS = 170.0
_BOOST_RETARD_PER_50KPA = 1.0
_NO_INTERCOOLER_EXTRA_RETARD = 1.5

# Low-RPM cranking floor: timing should not be negative at cranking RPM.
_CRANK_TIMING_FLOOR = 5.0

# Very high RPM (cols 13–15): mildly reduce advance conservatively even on NA
# engines — cylinder filling limitations make extra advance unhelpful.
_HIGH_RPM_TAPER_START_COL = 13
_HIGH_RPM_TAPER_DEG = 2.0      # total reduction at col 15


@dataclass(slots=True, frozen=True)
class SparkTableGeneratorResult:
    """Result of the conservative spark advance table generator.

    ``values`` is a flat row-major list of ``rows × columns`` ignition advance
    values in degrees BTDC.  Row 0 is the lowest load bin; row 15 is WOT.
    Column 0 is the lowest RPM bin (cranking); column 15 is the highest RPM.

    The result is always produced regardless of missing inputs.  When key inputs
    are absent the generator falls back to maximally conservative defaults and
    records them in ``warnings``.

    The result is *staged only* — it must never be applied automatically.
    """

    values: tuple[float, ...]
    rows: int
    columns: int
    topology: ForcedInductionTopology
    compression_ratio: float | None
    calibration_intent: CalibrationIntent
    summary: str
    warnings: tuple[str, ...]
    assumptions: tuple[GeneratorAssumption, ...] = ()

    def as_list(self) -> list[float]:
        return list(self.values)


class SparkTableGeneratorService:
    """Generates a conservative starter ignition advance table.

    The generator shapes timing conservatively so that:
    - Cranking / very-low-RPM cells start near the minimum needed to fire.
    - Mid-range cruise cells carry moderate advance (20–24° for a typical NA).
    - WOT cells are conservative — real tuning against knock data is required.
    - High-compression engines receive additional retard at high load.
    - Forced-induction engines receive load-weighted retard in boosted cells.
    - ``DRIVABLE_BASE`` calibration intent allows a few extra degrees of advance
      over the maximally conservative FIRST_START values.

    All outputs should be reviewed and optionally adjusted by the operator
    before writing to the ECU.
    """

    def generate(
        self,
        ctx: GeneratorInputContext,
        calibration_intent: CalibrationIntent = CalibrationIntent.FIRST_START,
    ) -> SparkTableGeneratorResult:
        """Generate a conservative 16 × 16 spark advance table.

        Parameters
        ----------
        ctx:
            Generator input context from hardware setup pages and operator
            engine context.
        calibration_intent:
            Calibration target; ``DRIVABLE_BASE`` allows a few extra degrees.

        Returns
        -------
        SparkTableGeneratorResult
            Always returns a result.  ``warnings`` lists any absent inputs.
        """
        warnings: list[str] = []
        assumptions: list[GeneratorAssumption] = []
        topology = ctx.forced_induction_topology

        # --- compression ratio effect ---
        cr = ctx.compression_ratio
        cr_penalty = 0.0
        if cr is None:
            warnings.append("Compression ratio not provided — using default shaping")
        else:
            if cr > _CR_REFERENCE:
                cr_penalty = (cr - _CR_REFERENCE) * _CR_TIMING_PENALTY_PER_UNIT

        # --- calibration intent bonus ---
        intent_bonus = _DRIVABLE_BONUS if calibration_intent == CalibrationIntent.DRIVABLE_BASE else 0.0

        if ctx.cylinder_count is None:
            warnings.append("Cylinder count not provided — using default shaping")
        if ctx.dwell_ms is None:
            warnings.append("Dwell not provided — verify coil dwell separately before long key-on testing")

        values: list[float] = []
        for row in range(_ROWS):
            for col in range(_COLS):
                adv = self._base_advance(row, col)
                adv -= self._cr_correction(row, cr, cr_penalty)
                adv += self._topology_retard(row, topology)
                adv -= self._boost_target_retard(row, ctx)
                adv += intent_bonus * (row / (_ROWS - 1))  # scale with load
                adv = max(_CRANK_TIMING_FLOOR, adv)
                adv = round(min(45.0, adv), 1)
                values.append(adv)

        # --- build structured assumption list ----------------------------
        _src = AssumptionSource.FROM_CONTEXT
        _fb = AssumptionSource.CONSERVATIVE_FALLBACK
        assumptions.append(GeneratorAssumption(
            label="Compression ratio",
            value_str=f"{cr:.1f}:1" if cr is not None else "not set",
            source=_src if cr is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Calibration intent",
            value_str=calibration_intent.value,
            source=_src,
        ))
        assumptions.append(GeneratorAssumption(
            label="Induction topology",
            value_str=topology.value,
            source=_src,
        ))
        assumptions.append(GeneratorAssumption(
            label="Cylinders",
            value_str=str(ctx.cylinder_count) if ctx.cylinder_count is not None else "not set",
            source=_src if ctx.cylinder_count is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Dwell",
            value_str=f"{ctx.dwell_ms:.1f} ms" if ctx.dwell_ms is not None else "not set",
            source=_src if ctx.dwell_ms is not None else _fb,
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
            if topology == ForcedInductionTopology.TWIN_TURBO_COMPOUND:
                assumptions.append(GeneratorAssumption(
                    label="Compound turbo timing",
                    value_str="extra-conservative high-load retard",
                    source=_fb,
                    note="Compounded pressure ratio was treated as a higher knock-risk region at high load.",
                ))
            elif topology == ForcedInductionTopology.TWIN_TURBO_SEQUENTIAL:
                assumptions.append(GeneratorAssumption(
                    label="Sequential turbo timing",
                    value_str="transition zone requires review",
                    source=_fb,
                    note="Timing around the handoff between primary-only and both-turbo operation was not modeled from hardware data.",
                ))
            elif topology == ForcedInductionTopology.TWIN_CHARGE:
                assumptions.append(GeneratorAssumption(
                    label="Twin-charge timing",
                    value_str="supercharger-dominant low RPM",
                    source=_fb,
                    note="Low-RPM timing assumes the supercharger dominates before the turbo takes over.",
                ))

        summary = self._build_summary(ctx, topology, cr, calibration_intent, warnings)
        return SparkTableGeneratorResult(
            values=tuple(values),
            rows=_ROWS,
            columns=_COLS,
            topology=topology,
            compression_ratio=cr,
            calibration_intent=calibration_intent,
            summary=summary,
            warnings=tuple(warnings),
            assumptions=tuple(assumptions),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base_advance(row: int, col: int) -> float:
        """Compute the base naturally-aspirated advance for a cell.

        Shape:
        - Load (row): from ``_IDLE_TIMING_BASE`` at row 0 up to ``_NA_WOT_MAX``
          at row 15.  Mid-load stays near ``_NA_MID_ADVANCE``.
        - RPM (col): gentle ramp from cranking floor to a mid-RPM plateau, then
          a slight taper at very high RPM to keep things conservative.
        """
        load_norm = row / (_ROWS - 1)       # 0.0 → 1.0
        rpm_norm  = col / (_COLS - 1)       # 0.0 → 1.0

        # Load: smooth ramp from idle timing to WOT max
        load_advance = _IDLE_TIMING_BASE + (_NA_WOT_MAX - _IDLE_TIMING_BASE) * load_norm

        # RPM: cranking is low; advance rises to ~col 10, then gently tapers
        if col < 3:
            rpm_factor = 0.55 + 0.15 * col    # 0.55, 0.70, 0.85 for cols 0-2
        elif col <= 10:
            rpm_factor = 1.0
        else:
            taper_progress = (col - 10) / (_COLS - 1 - 10)   # 0→1 from col 10→15
            taper = _HIGH_RPM_TAPER_DEG * taper_progress
            rpm_factor = 1.0 - taper / max(load_advance, 1.0)
            rpm_factor = max(0.85, rpm_factor)

        return load_advance * rpm_factor

    @staticmethod
    def _cr_correction(row: int, cr: float | None, cr_penalty: float) -> float:
        """Timing reduction driven by compression ratio at mid-to-high loads."""
        if cr is None or cr_penalty <= 0.0:
            return 0.0
        load_norm = row / (_ROWS - 1)
        # Only penalise mid/high load cells — idle timing is already conservative
        if load_norm < 0.4:
            return 0.0
        scale = (load_norm - 0.4) / 0.6   # 0 at 40 % load, 1.0 at WOT
        penalty = cr_penalty * scale
        if cr is not None and cr > _HIGH_CR_THRESHOLD and load_norm > 0.75:
            penalty += _HIGH_CR_WOT_PENALTY * ((load_norm - 0.75) / 0.25)
        return penalty

    @staticmethod
    def _topology_retard(row: int, topology: ForcedInductionTopology) -> float:
        """Timing retard (negative value added) for forced-induction topologies.

        Applied as a load-weighted reduction so that lightly loaded / pre-boost
        cells are not penalised.
        """
        load_norm = row / (_ROWS - 1)
        if topology == ForcedInductionTopology.NA:
            return 0.0

        if topology in (
            ForcedInductionTopology.SINGLE_TURBO,
            ForcedInductionTopology.TWIN_TURBO_IDENTICAL,
            ForcedInductionTopology.TWIN_TURBO_UNEQUAL,
            ForcedInductionTopology.TWIN_TURBO_SEQUENTIAL,
            ForcedInductionTopology.TWIN_TURBO_COMPOUND,
        ):
            if load_norm < 0.4:
                return 0.0
            scale = (load_norm - 0.4) / 0.6
            return -_TURBO_WOT_RETARD * scale

        if topology == ForcedInductionTopology.SINGLE_SUPERCHARGER:
            if load_norm < 0.4:
                return 0.0
            scale = (load_norm - 0.4) / 0.6
            return -_SUPERCHARGER_WOT_RETARD * scale

        if topology == ForcedInductionTopology.TWIN_CHARGE:
            if load_norm < 0.4:
                return 0.0
            scale = (load_norm - 0.4) / 0.6
            return -_TWIN_CHARGE_WOT_RETARD * scale

        return 0.0

    @staticmethod
    def _boost_target_retard(row: int, ctx: GeneratorInputContext) -> float:
        if ctx.forced_induction_topology == ForcedInductionTopology.NA:
            return 0.0
        if ctx.boost_target_kpa is None or ctx.boost_target_kpa <= _BOOST_RETARD_BASELINE_KPA_ABS:
            return 0.0
        load_norm = row / (_ROWS - 1)
        extra_boost_kpa = ctx.boost_target_kpa - _BOOST_RETARD_BASELINE_KPA_ABS
        retard = (extra_boost_kpa / 50.0) * _BOOST_RETARD_PER_50KPA * load_norm
        if not ctx.intercooler_present:
            retard += _NO_INTERCOOLER_EXTRA_RETARD * load_norm
        return retard

    @staticmethod
    def _build_summary(
        ctx: GeneratorInputContext,
        topology: ForcedInductionTopology,
        cr: float | None,
        calibration_intent: CalibrationIntent,
        warnings: list[str],
    ) -> str:
        lines = ["Conservative 16 × 16 spark advance table generated."]
        topology_text = topology.value if isinstance(topology, ForcedInductionTopology) else str(topology)
        intent_text = calibration_intent.value if isinstance(calibration_intent, CalibrationIntent) else str(calibration_intent)
        lines.append(f"Topology: {topology_text.replace('_', ' ').title()}")
        if cr is not None:
            lines.append(f"Compression ratio: {cr:.1f}:1")
        if ctx.cylinder_count is not None:
            lines.append(f"Cylinders: {ctx.cylinder_count}")
        lines.append(f"Intent: {intent_text.replace('_', ' ').title()}")
        if warnings:
            lines.append(f"{len(warnings)} warning(s): " + "; ".join(warnings[:3]))
        lines.append(
            "Review staged values before writing to RAM. "
            "WOT advance is very conservative — verify against knock data before tuning."
        )
        return "\n".join(lines)
