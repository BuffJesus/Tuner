from __future__ import annotations

from tuner.domain.generator_context import ForcedInductionTopology, GeneratorInputContext, SuperchargerType
from tuner.domain.operator_engine_context import OperatorEngineContext
from tuner.domain.tuning_pages import TuningPage
from tuner.services.hardware_preset_service import HardwarePresetService
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.required_fuel_calculator_service import RequiredFuelCalculatorService

# ---------------------------------------------------------------------------
# Keyword sets for parameter discovery
# ---------------------------------------------------------------------------

_KW_INJECTOR_FLOW = ("injectorflow", "injflow", "injsizepri", "injsize")
_KW_INJECTOR_FLOW_SEC = ("injsizesec", "injflowsec", "injectorflowsec", "secondaryinjector")
_KW_DEAD_TIME = ("deadtime", "injopen", "opentime", "injectoropen")
_KW_REQ_FUEL = ("reqfuel",)
_KW_INJECTOR_COUNT = ("ninjectors", "injectorcount", "injcount")
_KW_DISPLACEMENT = ("enginesize", "displacement", "enginecc")
_KW_CYLINDER_COUNT = ("ncylinders", "cylindercount", "cylcount")
_KW_COMPRESSION = ("compression", "compressionratio", "compratio")
_KW_REV_LIMIT = ("rpmhard", "revlimit", "maxrpm")
_KW_BOOST_ENABLED = ("boostenabled", "turboenabled", "boostcontrol")
_KW_BOOST_TARGET = ("boosttarget", "boostlimit", "targetboost")
_KW_STOICH = ("stoich",)
_KW_EGO_TYPE = ("egotype", "afrsensortype", "o2sensortype", "lambdatype")
_KW_AFR_CAL = ("afrcal", "widebandcal", "lambdacal")
_KW_DWELL = ("dwellrun", "dwell", "sparkdur", "coildwell")
_KW_MAP_RANGE = ("maprange", "mapmax", "mapmin", "mapsensor")
_KW_FUEL_PRESSURE = ("fuelpressure", "fuelpress", "fprpressure")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_numeric(
    pages: tuple[TuningPage, ...],
    local_tune_edit_service: LocalTuneEditService,
    keywords: tuple[str, ...],
) -> float | None:
    """Return the first non-None numeric value for any parameter matching keywords."""
    lowered = tuple(kw.lower() for kw in keywords)
    for page in pages:
        for param in page.parameters:
            haystack = f"{param.name} {param.label}".lower()
            if any(kw in haystack for kw in lowered):
                tv = local_tune_edit_service.get_value(param.name)
                if tv is not None and isinstance(tv.value, (int, float)):
                    return float(tv.value)
    return None


def _find_bool_enabled(
    pages: tuple[TuningPage, ...],
    local_tune_edit_service: LocalTuneEditService,
    keywords: tuple[str, ...],
    min_numeric: float = 0.5,
) -> bool:
    """Return True if a matching parameter is considered enabled."""
    lowered = tuple(kw.lower() for kw in keywords)
    for page in pages:
        for param in page.parameters:
            haystack = f"{param.name} {param.label}".lower()
            if any(kw in haystack for kw in lowered):
                tv = local_tune_edit_service.get_value(param.name)
                if tv is None:
                    continue
                v = tv.value
                if isinstance(v, (int, float)):
                    return float(v) >= min_numeric
                text = str(v).strip().lower()
                return text not in {"", "0", "off", "disabled", "false", "none"}
    return False


def _any_param_present(
    pages: tuple[TuningPage, ...],
    keywords: tuple[str, ...],
) -> bool:
    """Return True if any parameter matching keywords exists across pages."""
    lowered = tuple(kw.lower() for kw in keywords)
    for page in pages:
        for param in page.parameters:
            haystack = f"{param.name} {param.label}".lower()
            if any(kw in haystack for kw in lowered):
                return True
    return False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class HardwareSetupGeneratorContextService:
    """Extracts generator-ready hardware inputs from hardware setup pages.

    Scans all provided pages for scalar parameters that feed conservative
    base tune generation tasks (VE table, injector helper, spark helper) and
    returns a GeneratorInputContext that records what has been captured and
    what is still absent.

    The service uses keyword-based parameter discovery so it works across
    different ECU definition variants without hard-coded parameter names.
    """

    def build(
        self,
        pages: tuple[TuningPage, ...],
        local_tune_edit_service: LocalTuneEditService,
        operator_context: OperatorEngineContext | None = None,
    ) -> GeneratorInputContext:
        preset_service = HardwarePresetService()
        # -- Injector --
        injector_flow = _find_numeric(pages, local_tune_edit_service, _KW_INJECTOR_FLOW)
        injector_flow_sec = _find_numeric(pages, local_tune_edit_service, _KW_INJECTOR_FLOW_SEC)
        dead_time = _find_numeric(pages, local_tune_edit_service, _KW_DEAD_TIME)
        req_fuel = _find_numeric(pages, local_tune_edit_service, _KW_REQ_FUEL)
        inj_count_raw = _find_numeric(pages, local_tune_edit_service, _KW_INJECTOR_COUNT)
        injector_count = int(inj_count_raw) if inj_count_raw is not None else None
        injector_pressure_model: str | None = None
        secondary_injector_pressure_kpa: float | None = None

        # -- Engine geometry (ECU values first; operator context fills gaps) --
        displacement = _find_numeric(pages, local_tune_edit_service, _KW_DISPLACEMENT)
        cyl_count_raw = _find_numeric(pages, local_tune_edit_service, _KW_CYLINDER_COUNT)
        cylinder_count = int(cyl_count_raw) if cyl_count_raw is not None else None
        compression = _find_numeric(pages, local_tune_edit_service, _KW_COMPRESSION)
        rev_limit = _find_numeric(pages, local_tune_edit_service, _KW_REV_LIMIT)

        cam_duration: float | None = None
        head_flow_class: str | None = None
        intake_manifold_style: str | None = None
        injector_characterization: str | None = None
        supercharger_type = None
        if operator_context is not None:
            if displacement is None:
                displacement = operator_context.displacement_cc
            if cylinder_count is None:
                cylinder_count = operator_context.cylinder_count
            if compression is None:
                compression = operator_context.compression_ratio
            cam_duration = operator_context.cam_duration_deg
            head_flow_class = operator_context.head_flow_class
            intake_manifold_style = operator_context.intake_manifold_style
            injector_characterization = operator_context.injector_characterization
            injector_pressure_model = operator_context.injector_pressure_model
            supercharger_type = self._coerce_supercharger_type(operator_context.supercharger_type)
            if operator_context.secondary_injector_reference_pressure_psi is not None:
                secondary_injector_pressure_kpa = operator_context.secondary_injector_reference_pressure_psi * 6.89476
            if injector_flow is None and operator_context.injector_preset_key:
                injector_preset = next(
                    (item for item in preset_service.injector_presets() if item.key == operator_context.injector_preset_key),
                    None,
                )
                if injector_preset is not None:
                    target_pressure = operator_context.base_fuel_pressure_psi or injector_preset.reference_pressure_psi
                    injector_flow = preset_service.injector_flow_for_pressure(injector_preset, target_pressure)
                    if dead_time is None:
                        dead_time = preset_service.injector_dead_time_for_pressure(injector_preset, target_pressure)

        # -- Airflow / induction --
        boost_enabled = _find_bool_enabled(pages, local_tune_edit_service, _KW_BOOST_ENABLED)
        boost_target = _find_numeric(pages, local_tune_edit_service, _KW_BOOST_TARGET)
        map_range = _find_numeric(pages, local_tune_edit_service, _KW_MAP_RANGE)
        intercooler_present = False
        # Operator context topology takes precedence over naive boost-flag inference.
        # If the operator has explicitly set a topology, use it; otherwise fall back
        # to the simple boost-enabled heuristic (NA vs SINGLE_TURBO).
        if operator_context is not None and operator_context.forced_induction_topology != ForcedInductionTopology.NA:
            topology = self._coerce_topology(operator_context.forced_induction_topology)
        else:
            topology = ForcedInductionTopology.SINGLE_TURBO if boost_enabled else ForcedInductionTopology.NA
        if operator_context is not None:
            if boost_target is None:
                boost_target = operator_context.boost_target_kpa
            intercooler_present = operator_context.intercooler_present

        # -- Fuel --
        stoich = _find_numeric(pages, local_tune_edit_service, _KW_STOICH)
        fuel_pressure = _find_numeric(pages, local_tune_edit_service, _KW_FUEL_PRESSURE)
        if fuel_pressure is None and operator_context is not None and operator_context.base_fuel_pressure_psi is not None:
            fuel_pressure = operator_context.base_fuel_pressure_psi * 6.89476

        # -- Ignition --
        dwell = _find_numeric(pages, local_tune_edit_service, _KW_DWELL)
        if dwell is None and operator_context is not None and operator_context.ignition_preset_key:
            ignition_preset = next(
                (item for item in preset_service.ignition_presets() if item.key == operator_context.ignition_preset_key),
                None,
            )
            if ignition_preset is not None:
                dwell = ignition_preset.running_dwell_ms

        # -- Sensor --
        ego_raw = _find_numeric(pages, local_tune_edit_service, _KW_EGO_TYPE)
        ego_type_index = int(ego_raw) if ego_raw is not None else None
        afr_cal_present = _any_param_present(pages, _KW_AFR_CAL)

        # -- Computed reqFuel suggestion --
        # Use the effective stoich (or petrol default) when all other inputs are known.
        computed_req_fuel: float | None = None
        if displacement and cylinder_count and injector_flow:
            effective_stoich = stoich if stoich else 14.7
            result = RequiredFuelCalculatorService().calculate(
                displacement_cc=displacement,
                cylinder_count=cylinder_count,
                injector_flow_ccmin=injector_flow,
                target_afr=effective_stoich,
            )
            if result.is_valid:
                computed_req_fuel = result.req_fuel_ms

        # -- Missing inputs per task --
        missing_ve = self._ve_missing(displacement, cylinder_count, injector_flow, req_fuel, rev_limit)
        missing_inj = self._injector_missing(injector_flow, cylinder_count, displacement, stoich)
        missing_spark = self._spark_missing(compression, rev_limit)

        return GeneratorInputContext(
            injector_flow_ccmin=injector_flow,
            injector_flow_secondary_ccmin=injector_flow_sec if injector_flow_sec else None,
            injector_dead_time_ms=dead_time,
            required_fuel_ms=req_fuel,
            injector_count=injector_count,
            displacement_cc=displacement,
            cylinder_count=cylinder_count,
            compression_ratio=compression,
            cam_duration_deg=cam_duration,
            head_flow_class=head_flow_class,
            intake_manifold_style=intake_manifold_style,
            injector_characterization=injector_characterization,
            rev_limit_rpm=rev_limit,
            forced_induction_topology=topology,
            boost_target_kpa=boost_target,
            map_range_kpa=map_range,
            intercooler_present=intercooler_present,
            supercharger_type=supercharger_type,
            stoich_ratio=stoich,
            fuel_pressure_kpa=fuel_pressure,
            injector_pressure_model=injector_pressure_model,
            secondary_injector_pressure_kpa=secondary_injector_pressure_kpa,
            dwell_ms=dwell,
            ego_type_index=ego_type_index,
            afr_calibration_present=afr_cal_present,
            computed_req_fuel_ms=computed_req_fuel,
            missing_for_ve_generation=missing_ve,
            missing_for_injector_helper=missing_inj,
            missing_for_spark_helper=missing_spark,
        )

    @staticmethod
    def _coerce_topology(value: object) -> ForcedInductionTopology:
        if isinstance(value, ForcedInductionTopology):
            return value
        try:
            return ForcedInductionTopology(str(value))
        except ValueError:
            return ForcedInductionTopology.NA

    @staticmethod
    def _coerce_supercharger_type(value: object) -> SuperchargerType | None:
        if value is None or isinstance(value, SuperchargerType):
            return value
        try:
            return SuperchargerType(str(value))
        except ValueError:
            return None

    @staticmethod
    def _ve_missing(
        displacement: float | None,
        cylinder_count: int | None,
        injector_flow: float | None,
        req_fuel: float | None,
        rev_limit: float | None,
    ) -> tuple[str, ...]:
        missing: list[str] = []
        if not displacement:
            missing.append("Engine displacement")
        if not cylinder_count:
            missing.append("Cylinder count")
        if not injector_flow:
            missing.append("Injector flow rate")
        if not req_fuel:
            missing.append("Required fuel (ms)")
        if not rev_limit:
            missing.append("RPM limit / redline")
        return tuple(missing)

    @staticmethod
    def _injector_missing(
        injector_flow: float | None,
        cylinder_count: int | None,
        displacement: float | None,
        stoich: float | None,
    ) -> tuple[str, ...]:
        missing: list[str] = []
        if not injector_flow:
            missing.append("Injector flow rate")
        if not cylinder_count:
            missing.append("Cylinder count")
        if not displacement:
            missing.append("Engine displacement")
        if not stoich:
            missing.append("Stoich ratio")
        return tuple(missing)

    @staticmethod
    def _spark_missing(
        compression: float | None,
        rev_limit: float | None,
    ) -> tuple[str, ...]:
        missing: list[str] = []
        if not compression:
            missing.append("Compression ratio")
        if not rev_limit:
            missing.append("RPM limit / redline")
        return tuple(missing)
