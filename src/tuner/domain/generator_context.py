from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AssumptionSource(StrEnum):
    """How a particular generator input was obtained.

    Used by generator result types to communicate confidence to the operator.
    """

    FROM_CONTEXT = "from_context"
    """The value was present in the generator input context (from tune, preset,
    or operator entry).  The operator explicitly provided or confirmed this."""

    COMPUTED = "computed"
    """The value was derived from other available inputs (e.g. reqFuel computed
    from displacement + injector flow)."""

    CONSERVATIVE_FALLBACK = "conservative_fallback"
    """The input was absent; the generator used a safe conservative default.
    The operator should review and supply the missing value for better accuracy."""


@dataclass(slots=True, frozen=True)
class GeneratorAssumption:
    """One assumption made by a generator for a specific input.

    Generator result types include a tuple of these so the operator can see
    exactly which inputs were used versus which fell back to safe defaults.
    """

    label: str
    """Human-readable name for the input, e.g. ``"Injector flow"``."""

    value_str: str
    """Human-readable value used, e.g. ``"440 cc/min"`` or ``"conservative default"``."""

    source: AssumptionSource

    note: str = ""
    """Optional extra context, e.g. a warning about low-confidence data."""


class ForcedInductionTopology(StrEnum):
    """Describes the forced-induction arrangement of the engine.

    Used by conservative base tune generators to shape VE tables, boost
    targets, and airflow assumptions without overfitting unknown hardware.
    """

    NA = "na"
    SINGLE_TURBO = "single_turbo"
    TWIN_TURBO_IDENTICAL = "twin_turbo_identical"
    TWIN_TURBO_SEQUENTIAL = "twin_turbo_sequential"
    TWIN_TURBO_COMPOUND = "twin_turbo_compound"
    TWIN_TURBO_UNEQUAL = "twin_turbo_unequal"
    SINGLE_SUPERCHARGER = "single_supercharger"
    TWIN_CHARGE = "twin_charge"


class SuperchargerType(StrEnum):
    """Supercharger technology type.

    Affects the shape of low-RPM VE shaping and boost-onset assumptions.
    Roots and twin-screw units produce near-instant boost from idle; centrifugal
    units behave more like a small turbo (boost rises with RPM).
    """

    ROOTS = "roots"
    TWIN_SCREW = "twin_screw"
    CENTRIFUGAL = "centrifugal"


@dataclass(slots=True, frozen=True)
class GeneratorInputContext:
    """Hardware inputs captured from setup pages for conservative base tune generation.

    None fields indicate the value was not found or not yet set on any known
    setup page.  The missing_for_* tuples list human-readable input labels that
    are still absent but required for each generation task.

    All values reflect what has been read from the tune file; they are not
    normalised or sanity-checked here.
    """

    # -- Injector --
    injector_flow_ccmin: float | None = None
    """Primary injector flow rate in cc/min.  For staged injection this is the
    primary injector size; for single-stage injection this is the injector size."""

    injector_flow_secondary_ccmin: float | None = None
    """Secondary injector flow rate in cc/min (staged injection only).
    Zero or None means single-stage or secondary not configured."""

    injector_dead_time_ms: float | None = None
    required_fuel_ms: float | None = None
    injector_count: int | None = None

    # -- Engine geometry --
    displacement_cc: float | None = None
    cylinder_count: int | None = None
    compression_ratio: float | None = None
    rev_limit_rpm: float | None = None

    # -- Airflow / induction --
    forced_induction_topology: ForcedInductionTopology = ForcedInductionTopology.NA
    boost_target_kpa: float | None = None
    map_range_kpa: float | None = None
    intercooler_present: bool = False
    supercharger_type: SuperchargerType | None = None

    # -- Fuel --
    stoich_ratio: float | None = None
    fuel_pressure_kpa: float | None = None
    injector_pressure_model: str | None = None
    secondary_injector_pressure_kpa: float | None = None

    # -- Ignition --
    dwell_ms: float | None = None

    # -- Sensor --
    ego_type_index: int | None = None  # 0 = off, 1 = narrowband, 2+ = wideband
    afr_calibration_present: bool = False

    cam_duration_deg: float | None = None
    """Cam duration at 0.050-in lift (degrees), if provided by the operator.
    Influences high-RPM VE shaping in the conservative base tune generator."""

    head_flow_class: str | None = None
    """Coarse airflow class for the cylinder head, such as stock, mild ported,
    or race ported."""

    intake_manifold_style: str | None = None
    """Intake manifold style such as long-runner plenum, short-runner plenum,
    ITB, or compact/log manifold."""

    injector_characterization: str | None = None
    """How complete the injector data is, from nominal flow only to full
    pressure/voltage characterization."""

    # -- Computed suggestions --
    computed_req_fuel_ms: float | None = None
    """Required fuel pulse width computed from operator-supplied displacement when
    the value is not already present in the tune.  None if any required input
    (displacement, cylinder count, injector flow, stoich) is missing.  This is a
    suggestion only — the operator must apply it via the staged edit flow."""

    # -- What is still missing (per generation task) --
    # Each entry is a short human-readable label for the missing input.
    missing_for_ve_generation: tuple[str, ...] = ()
    missing_for_injector_helper: tuple[str, ...] = ()
    missing_for_spark_helper: tuple[str, ...] = ()
