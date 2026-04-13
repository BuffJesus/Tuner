from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.generator_context import (
    AssumptionSource,
    ForcedInductionTopology,
    GeneratorAssumption,
    GeneratorInputContext,
    SuperchargerType,
)
from tuner.domain.operator_engine_context import CalibrationIntent

# ---------------------------------------------------------------------------
# Table dimensions
# ---------------------------------------------------------------------------

_ROWS = 16   # load / MAP axis (row 0 = lowest load, row 15 = highest load)
_COLS = 16   # RPM axis       (col 0 = lowest RPM, col 15 = highest RPM)

# ---------------------------------------------------------------------------
# Conservative VE shaping constants
# ---------------------------------------------------------------------------

# Fraction of the RPM range (0-1) where VE peaks for a NA engine.
_NA_RPM_PEAK_NORM = 0.55

# Typical conservative VE range for a NA engine (percent).
_NA_VE_MIN = 38.0    # very low load / idle
_NA_VE_MID = 78.0    # cruise / mid-range plateau
_NA_VE_WOT = 85.0    # WOT peak

# High-cam engines get a modest boost at high load/RPM.
_HIGH_CAM_BONUS = 4.0          # degrees threshold: > 270
_HIGH_CAM_THRESHOLD_DEG = 270.0

# Short-cam engines retain slightly better low-RPM VE.
_SHORT_CAM_IDLE_BONUS = 3.0    # degrees threshold: < 220
_SHORT_CAM_THRESHOLD_DEG = 220.0

_HEAD_FLOW_MILD_BONUS = 2.0
_HEAD_FLOW_RACE_BONUS = 4.0
_HEAD_FLOW_RACE_IDLE_PENALTY = 2.0

_LONG_RUNNER_LOW_RPM_BONUS = 2.0
_LONG_RUNNER_HIGH_RPM_PENALTY = 1.5
_SHORT_RUNNER_LOW_RPM_PENALTY = 1.5
_SHORT_RUNNER_HIGH_RPM_BONUS = 2.5
_ITB_IDLE_PENALTY = 3.0
_ITB_HIGH_RPM_BONUS = 3.0
_LOG_MANIFOLD_LOW_RPM_BONUS = 1.5
_LOG_MANIFOLD_HIGH_RPM_PENALTY = 1.0

# Drivable-base intent raises the table slightly (more fuel for first road drive).
_DRIVABLE_BASE_BONUS = 2.0

# Small reqFuel values imply large injectors for the engine size and tend to
# make idle / light-load fueling more sensitive to deadtime. Bias those cells
# down slightly in the starter VE table.
_LOW_REQFUEL_THRESHOLD_MS = 6.0
_VERY_LOW_REQFUEL_THRESHOLD_MS = 4.0
_LOW_REQFUEL_IDLE_REDUCTION = 3.0
_VERY_LOW_REQFUEL_IDLE_REDUCTION = 5.0
_NOMINAL_FLOW_ONLY_IDLE_REDUCTION = 2.5
_SINGLE_DEADTIME_IDLE_REDUCTION = 1.0

# ---------------------------------------------------------------------------
# Turbo / forced-induction corrections
# ---------------------------------------------------------------------------

# Injector sizing for boosted applications means the injectors are larger than
# needed at low RPM; reduce VE in the pre-spool region so the engine runs
# without flooding on first start.

# RPM index (0-15) below which pre-spool corrections apply.
_SPOOL_START_COL = 5    # roughly 30 % of the RPM range
_SPOOL_END_COL = 9      # roughly 55 % of the RPM range

_SINGLE_TURBO_PRE_SPOOL_REDUCTION = 12.0   # percentage points
_SINGLE_TURBO_MID_SPOOL_RAMP_FACTOR = 0.5  # fraction of reduction removed per bin

_TWIN_TURBO_PRE_SPOOL_REDUCTION = 10.0     # slightly less (smaller turbos spool faster)

# Compound turbo maintains low-RPM VE better (small primary spools earlier).
_COMPOUND_TURBO_PRE_SPOOL_REDUCTION = 7.0

# Sequential twin: second turbo comes in late; keep first-turbo region conservative.
_SEQUENTIAL_TWIN_PRE_SPOOL_REDUCTION = 9.0

# Superchargers are driven by the engine so deliver boost immediately.
# No pre-spool reduction needed; moderate WOT bonus instead.
_SUPERCHARGER_LOW_RPM_BOOST = 3.0
_SUPERCHARGER_WOT_BOOST = 5.0

# Twin-charge: supercharger covers low RPM, turbo takes over mid/high.
_TWIN_CHARGE_LOW_RPM_BOOST = 2.0
_TWIN_CHARGE_SPOOL_REDUCTION = 5.0   # transition zone conservative
_CENTRIFUGAL_SUPERCHARGER_PRE_SPOOL_REDUCTION = 4.0


@dataclass(slots=True, frozen=True)
class VeTableGeneratorResult:
    """Result of the conservative VE table generator.

    ``values`` is a flat row-major list of ``rows × columns`` VE percentages
    (e.g. 80.0 = 80 % VE).  Row 0 is the lowest load bin; row 15 is WOT.
    Column 0 is the lowest RPM bin; column 15 is the highest RPM bin.

    The result is always produced regardless of missing inputs.  When key
    inputs are absent the generator falls back to maximally conservative
    defaults and records them in ``warnings``.

    The result is *staged only* — it must never be applied automatically.
    """

    values: tuple[float, ...]
    rows: int
    columns: int
    topology: ForcedInductionTopology
    summary: str
    warnings: tuple[str, ...]
    assumptions: tuple[GeneratorAssumption, ...] = ()

    def as_list(self) -> list[float]:
        return list(self.values)


class VeTableGeneratorService:
    """Generates a conservative starter VE table from available engine inputs.

    The generator shapes VE conservatively so that:
    - Low load / idle regions are lean-safe (lower VE = less fuel commanded).
    - Mid-range cruise regions are reasonable starting points.
    - WOT regions are conservative but not so low as to cause lean misfires.
    - For forced-induction engines, pre-spool regions are reduced to account
      for oversized injectors chosen for boosted operation.
    - Cam duration shifts the high-RPM peak up (more lift duration → engines
      breathe better at high RPM) and the idle region down (longer duration
      reduces low-speed cylinder filling).

    All outputs should be reviewed and optionally adjusted by the operator
    before writing to the ECU.
    """

    def generate(self, ctx: GeneratorInputContext) -> VeTableGeneratorResult:
        """Generate a conservative 16 × 16 VE table from available context.

        Parameters
        ----------
        ctx:
            Generator input context aggregated from hardware setup pages and
            the operator engine context service.

        Returns
        -------
        VeTableGeneratorResult
            Always returns a result.  ``warnings`` lists any inputs that were
            absent and caused the generator to fall back to defaults.
        """
        warnings: list[str] = []
        assumptions: list[GeneratorAssumption] = []
        topology = ctx.forced_induction_topology

        # --- calibration intent ----------------------------------------
        # OperatorEngineContext.calibration_intent is carried through
        # GeneratorInputContext indirectly (the presenter passes the operator
        # context when building the generator context).  For now we infer it
        # conservatively: if the context has a displacement and the operator
        # explicitly chose DRIVABLE_BASE we add a small bonus.
        # The GeneratorInputContext does not currently expose calibration_intent
        # directly, so we default to FIRST_START conservatism.
        calibration_bonus = 0.0  # future: wire CalibrationIntent through context

        characterization_idle_penalty = 0.0

        effective_req_fuel = ctx.required_fuel_ms or ctx.computed_req_fuel_ms
        injector_idle_penalty = 0.0
        if effective_req_fuel is None:
            warnings.append("Required fuel not available — injector sizing could not influence idle shaping")
        elif effective_req_fuel < _VERY_LOW_REQFUEL_THRESHOLD_MS:
            injector_idle_penalty = _VERY_LOW_REQFUEL_IDLE_REDUCTION
            warnings.append("Very low reqFuel detected — applying extra idle VE reduction for oversized injectors")
        elif effective_req_fuel < _LOW_REQFUEL_THRESHOLD_MS:
            injector_idle_penalty = _LOW_REQFUEL_IDLE_REDUCTION
            warnings.append("Low reqFuel detected — applying mild idle VE reduction for oversized injectors")

        if ctx.injector_dead_time_ms is None:
            warnings.append("Injector dead time not provided — idle and low pulsewidth regions may need extra review")

        if ctx.injector_characterization == "nominal_flow_only":
            characterization_idle_penalty = _NOMINAL_FLOW_ONLY_IDLE_REDUCTION
            warnings.append(
                "Injector characterization is flow-only - applying extra low-pulsewidth conservatism."
            )
        elif ctx.injector_characterization == "flow_plus_deadtime":
            characterization_idle_penalty = _SINGLE_DEADTIME_IDLE_REDUCTION
            warnings.append(
                "Injector characterization uses only a single dead-time value - low-voltage idle may need review."
            )
        elif ctx.injector_characterization is None:
            warnings.append(
                "Injector characterization depth not set - using generic low-pulsewidth assumptions."
            )

        # --- cam duration effect ----------------------------------------
        cam_bonus = 0.0
        if ctx.cam_duration_deg is not None:
            if ctx.cam_duration_deg > _HIGH_CAM_THRESHOLD_DEG:
                cam_bonus = _HIGH_CAM_BONUS
            elif ctx.cam_duration_deg < _SHORT_CAM_THRESHOLD_DEG:
                cam_bonus = -_SHORT_CAM_IDLE_BONUS  # mild idle penalty vs high-RPM gain
        else:
            warnings.append("Cam duration not provided — using stock cam shaping")

        if ctx.displacement_cc is None:
            warnings.append("Engine displacement not provided — using default shaping")
        if ctx.cylinder_count is None:
            warnings.append("Cylinder count not provided — using default shaping")

        # --- build structured assumption list ----------------------------
        _ve_src = AssumptionSource.FROM_CONTEXT
        _fb = AssumptionSource.CONSERVATIVE_FALLBACK
        assumptions.append(GeneratorAssumption(
            label="Displacement",
            value_str=f"{ctx.displacement_cc:.0f} cc" if ctx.displacement_cc is not None else "not set",
            source=_ve_src if ctx.displacement_cc is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Cylinders",
            value_str=str(ctx.cylinder_count) if ctx.cylinder_count is not None else "not set",
            source=_ve_src if ctx.cylinder_count is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Compression ratio",
            value_str=f"{ctx.compression_ratio:.1f}:1" if ctx.compression_ratio is not None else "not set",
            source=_ve_src if ctx.compression_ratio is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Injector flow",
            value_str=f"{ctx.injector_flow_ccmin:.0f} cc/min" if ctx.injector_flow_ccmin is not None else "not set",
            source=_ve_src if ctx.injector_flow_ccmin is not None else _fb,
        ))
        if effective_req_fuel is not None:
            req_source = AssumptionSource.COMPUTED if ctx.required_fuel_ms is None else _ve_src
            assumptions.append(GeneratorAssumption(
                label="Required fuel",
                value_str=f"{effective_req_fuel:.2f} ms",
                source=req_source,
                note="Computed from displacement + injector flow" if req_source == AssumptionSource.COMPUTED else "",
            ))
        else:
            assumptions.append(GeneratorAssumption(
                label="Required fuel",
                value_str="not set",
                source=_fb,
            ))
        assumptions.append(GeneratorAssumption(
            label="Injector dead time",
            value_str=f"{ctx.injector_dead_time_ms:.3f} ms" if ctx.injector_dead_time_ms is not None else "not set",
            source=_ve_src if ctx.injector_dead_time_ms is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Injector pressure model",
            value_str=ctx.injector_pressure_model or "not set",
            source=_ve_src if ctx.injector_pressure_model is not None else _fb,
            note="" if ctx.injector_pressure_model is not None else "Used conservative generic fuel-pressure behavior.",
        ))
        assumptions.append(GeneratorAssumption(
            label="Cam duration",
            value_str=f"{ctx.cam_duration_deg:.0f} deg" if ctx.cam_duration_deg is not None else "not set",
            source=_ve_src if ctx.cam_duration_deg is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Head flow class",
            value_str=ctx.head_flow_class or "not set",
            source=_ve_src if ctx.head_flow_class is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Manifold style",
            value_str=ctx.intake_manifold_style or "not set",
            source=_ve_src if ctx.intake_manifold_style is not None else _fb,
        ))
        assumptions.append(GeneratorAssumption(
            label="Induction topology",
            value_str=topology.value,
            source=_ve_src,
        ))
        if topology != ForcedInductionTopology.NA:
            assumptions.append(GeneratorAssumption(
                label="Boost target",
                value_str=f"{ctx.boost_target_kpa:.0f} kPa" if ctx.boost_target_kpa is not None else "not set",
                source=_ve_src if ctx.boost_target_kpa is not None else _fb,
            ))
            assumptions.append(GeneratorAssumption(
                label="Intercooler",
                value_str="present" if ctx.intercooler_present else "absent",
                source=_ve_src,
            ))
        if topology in (ForcedInductionTopology.SINGLE_SUPERCHARGER, ForcedInductionTopology.TWIN_CHARGE):
            assumptions.append(GeneratorAssumption(
                label="Supercharger type",
                value_str=ctx.supercharger_type.value if ctx.supercharger_type is not None else "not set",
                source=_ve_src if ctx.supercharger_type is not None else _fb,
                note="" if ctx.supercharger_type is not None else "Assumed positive-displacement low-RPM behavior for starter shaping.",
            ))
        if topology == ForcedInductionTopology.TWIN_TURBO_UNEQUAL:
            assumptions.append(GeneratorAssumption(
                label="Unequal twin sizing",
                value_str="low-RPM VE kept conservative",
                source=_fb,
                note="Unequal turbo sizing was not modeled; review low-RPM and per-cylinder fueling once the engine is running.",
            ))

        # --- build base NA table ----------------------------------------
        values: list[float] = []
        for row in range(_ROWS):
            for col in range(_COLS):
                ve = self._base_ve_na(row, col, cam_bonus, calibration_bonus)
                ve += self._injector_idle_correction(row, col, injector_idle_penalty)
                ve += self._injector_idle_correction(row, col, characterization_idle_penalty)
                ve += self._airflow_correction(row, col, ctx.head_flow_class, ctx.intake_manifold_style)
                ve += self._topology_correction(row, col, topology, ctx.supercharger_type, warnings)
                values.append(round(max(20.0, min(100.0, ve)), 1))

        summary = self._build_summary(ctx, topology, warnings)
        return VeTableGeneratorResult(
            values=tuple(values),
            rows=_ROWS,
            columns=_COLS,
            topology=topology,
            summary=summary,
            warnings=tuple(warnings),
            assumptions=tuple(assumptions),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base_ve_na(row: int, col: int, cam_bonus: float, calibration_bonus: float) -> float:
        """Compute the base naturally-aspirated VE value for a table cell.

        Shape:
        - Load axis (row): linear ramp from ``_NA_VE_MIN`` at row 0 to
          ``_NA_VE_WOT`` at row 15.
        - RPM axis (col): gentle bell curve peaking around ``_NA_RPM_PEAK_NORM``
          of the column range.  Very low and very high RPM bins are slightly
          reduced.
        - cam_bonus shifts high-load, high-RPM cells up (performance cam) or
          low-RPM idle cells slightly down (short cam effect already accounted
          for conservatively).
        """
        load_norm = row / (_ROWS - 1)          # 0.0 → 1.0
        rpm_norm  = col / (_COLS - 1)          # 0.0 → 1.0

        # Load contribution
        load_ve = _NA_VE_MIN + (_NA_VE_WOT - _NA_VE_MIN) * load_norm

        # RPM bell: peak at _NA_RPM_PEAK_NORM, fall off towards extremes
        distance_from_peak = abs(rpm_norm - _NA_RPM_PEAK_NORM)
        rpm_factor = 1.0 - 0.18 * (distance_from_peak / _NA_RPM_PEAK_NORM)
        rpm_factor = max(0.82, min(1.0, rpm_factor))

        # Idle correction: additional reduction at very low RPM AND very low load
        if col <= 1 and row <= 2:
            idle_correction = -6.0 + 2.0 * (col + row)   # -6 at (0,0), 0 at (1,2)
        else:
            idle_correction = 0.0

        # Cam bonus applies at high RPM (col >= 10) and high load (row >= 10)
        effective_cam_bonus = cam_bonus if (col >= 10 and row >= 10) else 0.0

        return load_ve * rpm_factor + idle_correction + effective_cam_bonus + calibration_bonus

    @staticmethod
    def _topology_correction(
        row: int,
        col: int,
        topology: ForcedInductionTopology,
        supercharger_type: SuperchargerType | None,
        warnings: list[str],
    ) -> float:
        """Return the VE correction (positive or negative) for the induction topology."""
        if topology == ForcedInductionTopology.NA:
            return 0.0

        if topology == ForcedInductionTopology.SINGLE_TURBO:
            return VeTableGeneratorService._turbo_correction(
                col, _SINGLE_TURBO_PRE_SPOOL_REDUCTION
            )

        if topology in (
            ForcedInductionTopology.TWIN_TURBO_IDENTICAL,
            ForcedInductionTopology.TWIN_TURBO_UNEQUAL,
        ):
            if topology == ForcedInductionTopology.TWIN_TURBO_UNEQUAL:
                note = "Unequal twin turbo sizing not modeled - low-RPM VE is conservative on the larger-turbo side and needs per-cylinder review."
                if note not in warnings:
                    warnings.append(note)
            return VeTableGeneratorService._turbo_correction(
                col, _TWIN_TURBO_PRE_SPOOL_REDUCTION
            )

        if topology == ForcedInductionTopology.TWIN_TURBO_SEQUENTIAL:
            return VeTableGeneratorService._turbo_correction(
                col, _SEQUENTIAL_TWIN_PRE_SPOOL_REDUCTION
            )

        if topology == ForcedInductionTopology.TWIN_TURBO_COMPOUND:
            return VeTableGeneratorService._turbo_correction(
                col, _COMPOUND_TURBO_PRE_SPOOL_REDUCTION
            )

        if topology == ForcedInductionTopology.SINGLE_SUPERCHARGER:
            if supercharger_type == SuperchargerType.CENTRIFUGAL:
                return VeTableGeneratorService._turbo_correction(
                    col, _CENTRIFUGAL_SUPERCHARGER_PRE_SPOOL_REDUCTION
                )
            # Supercharger boosts from idle; slight low-RPM bonus, moderate WOT bonus
            load_norm = row / (_ROWS - 1)
            return _SUPERCHARGER_LOW_RPM_BOOST + _SUPERCHARGER_WOT_BOOST * load_norm

        if topology == ForcedInductionTopology.TWIN_CHARGE:
            # Supercharger at low RPM covers spool gap; conservative reduction through
            # the handoff zone where neither source is fully established.
            if col < _SPOOL_START_COL:
                return _TWIN_CHARGE_LOW_RPM_BOOST
            if _SPOOL_START_COL <= col < _SPOOL_END_COL:
                return -_TWIN_CHARGE_SPOOL_REDUCTION
            return 0.0

        return 0.0

    @staticmethod
    def _turbo_correction(col: int, pre_spool_reduction: float) -> float:
        """VE correction for a turbocharged engine at the given RPM column index."""
        if col < _SPOOL_START_COL:
            return -pre_spool_reduction
        if col < _SPOOL_END_COL:
            # Linear ramp from full reduction back to 0 across the spool zone
            spool_bins = _SPOOL_END_COL - _SPOOL_START_COL
            progress = (col - _SPOOL_START_COL) / spool_bins
            return -pre_spool_reduction * (1.0 - progress)
        return 0.0

    @staticmethod
    def _injector_idle_correction(row: int, col: int, injector_idle_penalty: float) -> float:
        if injector_idle_penalty <= 0.0:
            return 0.0
        if row <= 3 and col <= 4:
            return -injector_idle_penalty
        if row <= 5 and col <= 6:
            return -(injector_idle_penalty * 0.5)
        return 0.0

    @staticmethod
    def _airflow_correction(
        row: int,
        col: int,
        head_flow_class: str | None,
        intake_manifold_style: str | None,
    ) -> float:
        correction = 0.0

        if head_flow_class == "mild_ported":
            if row >= 10 and col >= 9:
                correction += _HEAD_FLOW_MILD_BONUS
        elif head_flow_class == "race_ported":
            if row >= 10 and col >= 9:
                correction += _HEAD_FLOW_RACE_BONUS
            if row <= 3 and col <= 3:
                correction -= _HEAD_FLOW_RACE_IDLE_PENALTY

        if intake_manifold_style == "long_runner_plenum":
            if row >= 6 and col <= 7:
                correction += _LONG_RUNNER_LOW_RPM_BONUS
            if row >= 10 and col >= 12:
                correction -= _LONG_RUNNER_HIGH_RPM_PENALTY
        elif intake_manifold_style == "short_runner_plenum":
            if row >= 6 and col <= 4:
                correction -= _SHORT_RUNNER_LOW_RPM_PENALTY
            if row >= 9 and col >= 10:
                correction += _SHORT_RUNNER_HIGH_RPM_BONUS
        elif intake_manifold_style == "itb":
            if row <= 3 and col <= 3:
                correction -= _ITB_IDLE_PENALTY
            if row >= 8 and col >= 9:
                correction += _ITB_HIGH_RPM_BONUS
        elif intake_manifold_style == "log_compact":
            if row >= 6 and col <= 6:
                correction += _LOG_MANIFOLD_LOW_RPM_BONUS
            if row >= 10 and col >= 12:
                correction -= _LOG_MANIFOLD_HIGH_RPM_PENALTY

        return correction

    @staticmethod
    def _build_summary(
        ctx: GeneratorInputContext,
        topology: ForcedInductionTopology,
        warnings: list[str],
    ) -> str:
        lines = ["Conservative 16 × 16 VE table generated."]
        lines.append(f"Topology: {topology.value.replace('_', ' ').title()}")
        if ctx.displacement_cc:
            lines.append(f"Displacement: {ctx.displacement_cc:.0f} cc")
        if ctx.cylinder_count:
            lines.append(f"Cylinders: {ctx.cylinder_count}")
        if ctx.cam_duration_deg:
            lines.append(f"Cam duration: {ctx.cam_duration_deg:.0f}°")
        if ctx.head_flow_class:
            lines.append(f"Head flow: {ctx.head_flow_class.replace('_', ' ')}")
        if ctx.intake_manifold_style:
            lines.append(f"Manifold: {ctx.intake_manifold_style.replace('_', ' ')}")
        if ctx.injector_characterization:
            lines.append(f"Injector data: {ctx.injector_characterization.replace('_', ' ')}")
        if warnings:
            lines.append(f"{len(warnings)} warning(s): " + "; ".join(warnings[:3]))
        lines.append(
            "Review staged values before writing to RAM. "
            "WOT cells are conservative — tune up with real data."
        )
        return "\n".join(lines)
