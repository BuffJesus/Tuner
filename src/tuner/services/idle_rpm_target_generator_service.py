"""Conservative idle RPM target generator.

Produces starter values for the closed-loop idle RPM target curve:

- ``iacBins``    — 10 CLT breakpoints in °C (x-axis)
- ``iacCLValues`` — 10 RPM targets (y-axis)

The curve tapers from a high cold-idle RPM down to a stable warm-idle RPM.
High cold-idle helps the engine warm up quickly and maintain stable combustion
when cold.  The warm-idle target depends on engine character (cam, topology).

Reference: Speeduino u16p2 Ford300 Twin-GT28 base-startup tune
  iacBins    : -26,  2, 22, 39, 53,  66,  79,  94, 107, 117 °C
  iacCLValues:  1200, 1100, 1050, 1000, 940, 840, 830, 790, 790, 780 RPM

All values are in physical RPM units (the u16p2 INI stores them as U08 ×10;
the MSQ parser exposes them already scaled to RPM).  All outputs are staged
only — never applied automatically.
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
# Reference bins and shape (Ford300 / Speeduino u16p2)
# ---------------------------------------------------------------------------

_IAC_BINS: tuple[float, ...] = (
    -26.0, 2.0, 22.0, 39.0, 53.0, 66.0, 79.0, 94.0, 107.0, 117.0
)
_IAC_BIN_COUNT = len(_IAC_BINS)  # 10

# Normalised cold-fraction at each bin: 1.0 = full cold bump, 0.0 = warm RPM.
# Derived from the Ford300 reference curve (warm RPM = 780, cold bump = 420).
_IAC_SHAPE: tuple[float, ...] = (
    1.000, 0.762, 0.643, 0.524, 0.381, 0.143, 0.119, 0.024, 0.024, 0.000
)

# ---------------------------------------------------------------------------
# Warm idle RPM by induction topology
# ---------------------------------------------------------------------------

_WARM_RPM_NA = 800.0
_WARM_RPM_BOOSTED = 850.0   # boosted engines benefit from slightly higher warm idle

# ---------------------------------------------------------------------------
# Cold-end RPM bump (added to warm RPM at the coldest bin)
# ---------------------------------------------------------------------------

_COLD_BUMP_DRIVABLE = 400.0    # Ford300 reference: 1200 - 780 ≈ 420
_COLD_BUMP_FIRST_START = 500.0  # extra caution for first-start intent

# High-cam adjustment: aggressive cam profiles need a higher idle to stay stable
_HIGH_CAM_THRESHOLD_DEG = 270.0
_HIGH_CAM_RPM_EXTRA = 100.0     # added to both warm RPM and cold bump
_MILD_PORTED_IDLE_EXTRA = 20.0
_RACE_PORTED_IDLE_EXTRA = 50.0
_SHORT_RUNNER_IDLE_EXTRA = 20.0
_ITB_IDLE_EXTRA = 80.0
_LOG_COMPACT_IDLE_EXTRA = 10.0
_LONG_RUNNER_IDLE_REDUCTION = 10.0

# RPM clamp: Speeduino U08 ×10 → 0..2550 RPM in 10 RPM steps
_RPM_MIN = 500.0
_RPM_MAX = 2550.0


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class IdleRpmTargetGeneratorResult:
    """Generated idle RPM target curve.

    ``clt_bins`` and ``rpm_targets`` are parallel 10-element tuples.
    ``rpm_targets`` tapers from a high cold-idle RPM to a stable warm-idle RPM.
    Values are in RPM (physical units).
    """

    clt_bins: tuple[float, ...]
    rpm_targets: tuple[float, ...]
    summary: str
    warnings: tuple[str, ...]
    assumptions: tuple[GeneratorAssumption, ...] = ()

    def as_bins_list(self) -> list[float]:
        return list(self.clt_bins)

    def as_targets_list(self) -> list[float]:
        return list(self.rpm_targets)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class IdleRpmTargetGeneratorService:
    """Generates a conservative starter idle RPM target curve.

    The curve always produces a result.  Missing inputs fall back to safe
    reference values with warnings recorded.  All outputs should be reviewed
    by the operator before staging and then by the engine on first startup.
    """

    def generate(
        self,
        ctx: GeneratorInputContext,
        calibration_intent: CalibrationIntent = CalibrationIntent.FIRST_START,
    ) -> IdleRpmTargetGeneratorResult:
        """Generate idle RPM target bins and values.

        Parameters
        ----------
        ctx:
            Generator input context (forced_induction_topology and
            cam_duration_deg used for RPM target shaping).
        calibration_intent:
            FIRST_START raises the cold-end RPM target for maximum stability
            on the first key-on.
        """
        warnings: list[str] = []

        warm_rpm, cold_bump = self._rpm_params(ctx, calibration_intent, warnings)
        rpm_targets = tuple(
            round(max(_RPM_MIN, min(_RPM_MAX, warm_rpm + cold_bump * s)) / 10) * 10
            for s in _IAC_SHAPE
        )

        intent_label = "first-start" if calibration_intent == CalibrationIntent.FIRST_START else "drivable base"
        summary = (
            f"Conservative idle RPM targets ({intent_label}). "
            f"Warm idle: {warm_rpm:.0f} RPM; "
            f"cold idle: {rpm_targets[0]:.0f} RPM at {_IAC_BINS[0]:.0f}\u00b0C. "
            "Review after first cold start — adjust warm target to match desired idle quality."
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
                label="Induction topology",
                value_str=ctx.forced_induction_topology.value,
                source=_src,
            ),
            GeneratorAssumption(
                label="Cam duration",
                value_str=f"{ctx.cam_duration_deg:.0f} deg" if ctx.cam_duration_deg is not None else "not set",
                source=_src if ctx.cam_duration_deg is not None else _fb,
            ),
            GeneratorAssumption(
                label="Head flow class",
                value_str=ctx.head_flow_class or "not set",
                source=_src if ctx.head_flow_class is not None else _fb,
            ),
            GeneratorAssumption(
                label="Manifold style",
                value_str=ctx.intake_manifold_style or "not set",
                source=_src if ctx.intake_manifold_style is not None else _fb,
            ),
        )

        return IdleRpmTargetGeneratorResult(
            clt_bins=_IAC_BINS,
            rpm_targets=rpm_targets,
            summary=summary,
            warnings=tuple(warnings),
            assumptions=assumptions,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rpm_params(
        ctx: GeneratorInputContext,
        intent: CalibrationIntent,
        warnings: list[str],
    ) -> tuple[float, float]:
        """Return (warm_rpm, cold_bump) based on topology, cam, and intent."""
        is_boosted = ctx.forced_induction_topology != ForcedInductionTopology.NA
        warm_rpm = _WARM_RPM_BOOSTED if is_boosted else _WARM_RPM_NA

        cold_bump = (
            _COLD_BUMP_FIRST_START
            if intent == CalibrationIntent.FIRST_START
            else _COLD_BUMP_DRIVABLE
        )

        cam = ctx.cam_duration_deg
        if cam is not None and cam >= _HIGH_CAM_THRESHOLD_DEG:
            warm_rpm += _HIGH_CAM_RPM_EXTRA
            cold_bump += _HIGH_CAM_RPM_EXTRA
            warnings.append(
                f"High cam duration ({cam:.0f}\u00b0) detected: warm idle target raised by "
                f"{_HIGH_CAM_RPM_EXTRA:.0f} RPM for stability."
            )
        elif cam is None:
            warnings.append(
                "Cam duration not set — using standard idle RPM targets. "
                "Raise warm idle if the engine has an aggressive cam profile."
            )

        if ctx.head_flow_class == "mild_ported":
            warm_rpm += _MILD_PORTED_IDLE_EXTRA
            cold_bump += _MILD_PORTED_IDLE_EXTRA * 0.5
        elif ctx.head_flow_class == "race_ported":
            warm_rpm += _RACE_PORTED_IDLE_EXTRA
            cold_bump += _RACE_PORTED_IDLE_EXTRA * 0.6
            warnings.append(
                "Race-ported head selected - warm idle target raised for first-start stability."
            )

        if ctx.intake_manifold_style == "long_runner_plenum":
            warm_rpm -= _LONG_RUNNER_IDLE_REDUCTION
        elif ctx.intake_manifold_style == "short_runner_plenum":
            warm_rpm += _SHORT_RUNNER_IDLE_EXTRA
            cold_bump += _SHORT_RUNNER_IDLE_EXTRA * 0.5
        elif ctx.intake_manifold_style == "itb":
            warm_rpm += _ITB_IDLE_EXTRA
            cold_bump += _ITB_IDLE_EXTRA * 0.75
            warnings.append(
                "ITB manifold selected - idle targets raised because low-load airflow and MAP signal are less forgiving."
            )
        elif ctx.intake_manifold_style == "log_compact":
            warm_rpm += _LOG_COMPACT_IDLE_EXTRA

        return warm_rpm, cold_bump
