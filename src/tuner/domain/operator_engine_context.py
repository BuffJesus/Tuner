from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from tuner.domain.generator_context import ForcedInductionTopology, SuperchargerType


class CalibrationIntent(StrEnum):
    """Describes the operator's target for the generated base tune.

    first_start:     Maximally conservative — engine should idle and not damage
                     itself on first key-on.  Timing retarded, fuel slightly
                     rich, idle assist enabled.
    drivable_base:   Conservative but drivable — suitable for a first road
                     drive and autotune starting point.
    """

    FIRST_START = "first_start"
    DRIVABLE_BASE = "drivable_base"


@dataclass(slots=True, frozen=True)
class OperatorEngineContext:
    """Engine facts supplied by the operator that are not stored in the ECU.

    These values complement what can be read from the tune file.  They are
    needed by the required fuel calculator and conservative base tune
    generators but are deliberately absent from Speeduino EEPROM (e.g.
    engine displacement is only used to *calculate* reqFuel, not stored).

    All fields are optional; None means the operator has not yet provided the
    value.  Downstream services treat None as "input not available" and
    reduce confidence or skip generation steps that require the missing value.
    """

    displacement_cc: float | None = None
    """Total engine displacement in cubic centimetres."""

    cylinder_count: int | None = None
    """Number of cylinders.  When set, overrides any value extracted from the
    tune file so the wizard works before or without a loaded tune."""

    compression_ratio: float | None = None
    """Static compression ratio (e.g. 9.5 for a naturally-aspirated engine)."""

    cam_duration_deg: float | None = None
    """Cam duration at 0.050-in lift in degrees, if known (influences idle and
    low-speed VE shaping)."""

    head_flow_class: str | None = None
    """Coarse cylinder-head airflow class such as stock, mild ported, or race ported."""

    intake_manifold_style: str | None = None
    """Intake manifold style such as long runner, short runner, ITB, or plenum."""

    base_fuel_pressure_psi: float | None = None
    """Base injector differential pressure in psi, used to scale nominal injector
    flow presets when the rated pressure differs from the installed setup."""

    injector_pressure_model: str | None = None
    """How injector pressure compensation is expected to behave:
    fixed_pressure, vacuum_referenced, or not_modeled."""

    secondary_injector_reference_pressure_psi: float | None = None
    """Reference differential pressure for staged / secondary injectors when
    that bank differs from the primary injector setup."""

    injector_preset_key: str | None = None
    """Identifier for the selected injector hardware preset, if one is in use."""

    ignition_preset_key: str | None = None
    """Identifier for the selected ignition hardware preset, if one is in use."""

    wideband_preset_key: str | None = None
    """Identifier for the selected wideband controller preset, if one is in use."""

    wideband_reference_table_label: str | None = None
    """Selected AFR calibration preset label from the definition-backed
    reference table, if the operator picked one in the wizard."""

    turbo_preset_key: str | None = None
    """Identifier for the selected turbo hardware preset, if one is in use."""

    injector_characterization: str | None = None
    """Describes how complete the injector characterization data is, from nominal flow only to full table data."""

    calibration_intent: CalibrationIntent = CalibrationIntent.FIRST_START
    """Operator's intended use for the generated base tune."""

    # ------------------------------------------------------------------
    # Induction / forced-induction setup
    # ------------------------------------------------------------------

    forced_induction_topology: ForcedInductionTopology = ForcedInductionTopology.NA
    """Induction arrangement — NA, single/twin turbo variant, supercharger, or
    twin-charge.  When set here it overrides the naive boost-flag detection used
    by the generator context extraction service."""

    supercharger_type: SuperchargerType | None = None
    """Supercharger technology when topology is SINGLE_SUPERCHARGER or TWIN_CHARGE.
    Roots/twin-screw produce near-instant boost; centrifugal rises with RPM."""

    boost_target_kpa: float | None = None
    """Absolute MAP target at full boost in kPa.  101 kPa = atmospheric.
    e.g. 200 kPa ≈ 14.5 psi gauge boost.  Used to shape conservative VE
    tables in boosted regions."""

    intercooler_present: bool = False
    """True if an intercooler (FMIC or TMIC) is fitted.  Affects charge-air
    temperature assumptions in generator helpers."""

    # ------------------------------------------------------------------
    # Simple compressor data (no map image yet — future Phase 5.5)
    # ------------------------------------------------------------------
    # These let the operator record what they know about their compressor
    # without requiring a full map import.  All fields are optional; missing
    # values cause the generator to fall back to conservative generic shaping.

    compressor_corrected_flow_lbmin: float | None = None
    """Maximum corrected airflow at the compressor's peak-efficiency island,
    in lb/min.  Typical small turbo: 30–50 lb/min; large turbo: 60–100 lb/min."""

    compressor_pressure_ratio: float | None = None
    """Pressure ratio at peak efficiency (P_outlet / P_inlet, absolute).
    e.g. 2.0 ≈ 14.7 psi gauge at sea level."""

    compressor_inducer_mm: float | None = None
    """Compressor wheel inducer (inlet) diameter in mm."""

    compressor_exducer_mm: float | None = None
    """Compressor wheel exducer (outlet) diameter in mm."""

    compressor_ar: float | None = None
    """Turbine housing A/R ratio.  Lower A/R = quicker spool, lower peak flow.
    Higher A/R = slower spool, higher peak flow."""
