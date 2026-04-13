from __future__ import annotations

import pytest

from tuner.domain.ecu_definition import (
    DialogDefinition,
    DialogFieldDefinition,
    EcuDefinition,
    MenuDefinition,
    MenuItemDefinition,
    ScalarParameterDefinition,
)
from tuner.domain.generator_context import ForcedInductionTopology, SuperchargerType
from tuner.domain.operator_engine_context import CalibrationIntent, OperatorEngineContext
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.hardware_setup_generator_context_service import HardwareSetupGeneratorContextService
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.tuning_page_service import TuningPageService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pages_and_edits(scalar_defs: list[ScalarParameterDefinition], tune_values: list[TuneValue]):
    dialog = DialogDefinition(
        dialog_id="hwPage",
        title="Hardware Setup",
        fields=[
            DialogFieldDefinition(label=s.label or s.name, parameter_name=s.name)
            for s in scalar_defs
        ],
    )
    definition = EcuDefinition(
        name="Test",
        scalars=scalar_defs,
        dialogs=[dialog],
        menus=[MenuDefinition(title="Setup", items=[MenuItemDefinition(target="hwPage", label="Hardware Setup")])],
    )
    pages = tuple(
        page
        for group in TuningPageService().build_pages(definition)
        for page in group.pages
    )
    tune = TuneFile(constants=tune_values)
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)
    return pages, edits


def _service() -> HardwareSetupGeneratorContextService:
    return HardwareSetupGeneratorContextService()


# ---------------------------------------------------------------------------
# Injector inputs
# ---------------------------------------------------------------------------

def test_injector_flow_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min")],
        [TuneValue(name="injectorFlow", value=550.0, units="cc/min")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.injector_flow_ccmin == 550.0


def test_dead_time_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="deadTime", data_type="U16", page=1, offset=0, units="ms")],
        [TuneValue(name="deadTime", value=1.1, units="ms")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.injector_dead_time_ms == 1.1


def test_req_fuel_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, units="ms")],
        [TuneValue(name="reqFuel", value=8.4, units="ms")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.required_fuel_ms == 8.4


# ---------------------------------------------------------------------------
# Engine geometry
# ---------------------------------------------------------------------------

def test_displacement_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="engineSize", data_type="U16", page=1, offset=0, units="cc")],
        [TuneValue(name="engineSize", value=2000.0, units="cc")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.displacement_cc == 2000.0


def test_cylinder_count_captured_as_int() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=0)],
        [TuneValue(name="nCylinders", value=4.0)],
    )
    ctx = _service().build(pages, edits)
    assert ctx.cylinder_count == 4


def test_rev_limit_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="rpmHard", data_type="U16", page=1, offset=0, units="rpm")],
        [TuneValue(name="rpmHard", value=7000.0, units="rpm")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.rev_limit_rpm == 7000.0


# ---------------------------------------------------------------------------
# Forced induction detection
# ---------------------------------------------------------------------------

def test_boost_enabled_sets_single_turbo_topology() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="boostEnabled", data_type="U08", page=1, offset=0)],
        [TuneValue(name="boostEnabled", value=1.0)],
    )
    ctx = _service().build(pages, edits)
    assert ctx.forced_induction_topology == ForcedInductionTopology.SINGLE_TURBO


def test_boost_disabled_leaves_na_topology() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="boostEnabled", data_type="U08", page=1, offset=0)],
        [TuneValue(name="boostEnabled", value=0.0)],
    )
    ctx = _service().build(pages, edits)
    assert ctx.forced_induction_topology == ForcedInductionTopology.NA


def test_no_boost_parameter_leaves_na_topology() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0)],
        [TuneValue(name="injectorFlow", value=550.0)],
    )
    ctx = _service().build(pages, edits)
    assert ctx.forced_induction_topology == ForcedInductionTopology.NA


# ---------------------------------------------------------------------------
# Sensor inputs
# ---------------------------------------------------------------------------

def test_ego_type_index_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0)],
        [TuneValue(name="egoType", value=2.0)],
    )
    ctx = _service().build(pages, edits)
    assert ctx.ego_type_index == 2


def test_afr_cal_presence_detected() -> None:
    pages, edits = _pages_and_edits(
        [
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="afrCal", data_type="U08", page=1, offset=1),
        ],
        [
            TuneValue(name="egoType", value=2.0),
            TuneValue(name="afrCal", value=14.7),
        ],
    )
    ctx = _service().build(pages, edits)
    assert ctx.afr_calibration_present is True


def test_stoich_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="stoich", data_type="U08", page=1, offset=0)],
        [TuneValue(name="stoich", value=14.7)],
    )
    ctx = _service().build(pages, edits)
    assert ctx.stoich_ratio == 14.7


# ---------------------------------------------------------------------------
# Missing inputs reporting
# ---------------------------------------------------------------------------

def test_missing_for_ve_generation_reported_when_absent() -> None:
    # Only injector flow provided; displacement, cylinder count, req fuel, rev limit missing.
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0)],
        [TuneValue(name="injectorFlow", value=550.0)],
    )
    ctx = _service().build(pages, edits)
    assert "Engine displacement" in ctx.missing_for_ve_generation
    assert "Cylinder count" in ctx.missing_for_ve_generation
    assert "Required fuel (ms)" in ctx.missing_for_ve_generation
    assert "RPM limit / redline" in ctx.missing_for_ve_generation
    assert "Injector flow rate" not in ctx.missing_for_ve_generation


def test_no_missing_when_all_ve_inputs_present() -> None:
    pages, edits = _pages_and_edits(
        [
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0),
            ScalarParameterDefinition(name="engineSize", data_type="U16", page=1, offset=2),
            ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=4),
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=5),
            ScalarParameterDefinition(name="rpmHard", data_type="U16", page=1, offset=6),
        ],
        [
            TuneValue(name="injectorFlow", value=550.0),
            TuneValue(name="engineSize", value=2000.0),
            TuneValue(name="nCylinders", value=4.0),
            TuneValue(name="reqFuel", value=8.4),
            TuneValue(name="rpmHard", value=7000.0),
        ],
    )
    ctx = _service().build(pages, edits)
    assert not ctx.missing_for_ve_generation


def test_missing_for_spark_helper_reported() -> None:
    # No compression or rev limit → both spark inputs missing.
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0)],
        [TuneValue(name="injectorFlow", value=550.0)],
    )
    ctx = _service().build(pages, edits)
    assert "Compression ratio" in ctx.missing_for_spark_helper
    assert "RPM limit / redline" in ctx.missing_for_spark_helper


# ---------------------------------------------------------------------------
# Speeduino-specific parameter names (from real INI / MSQ)
# ---------------------------------------------------------------------------

def test_speeduino_staged_inj_size_pri_captured_as_injector_flow() -> None:
    # Speeduino uses stagedInjSizePri (contains "injsizepri" / "injsize")
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="stagedInjSizePri", data_type="U16", page=1, offset=0, units="cc/min")],
        [TuneValue(name="stagedInjSizePri", value=540.0, units="cc/min")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.injector_flow_ccmin == 540.0


def test_speeduino_staged_inj_size_sec_captured_as_secondary() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="stagedInjSizeSec", data_type="U16", page=1, offset=0, units="cc/min")],
        [TuneValue(name="stagedInjSizeSec", value=0.0, units="cc/min")],
    )
    ctx = _service().build(pages, edits)
    # Zero secondary injector should not be stored (treated as absent)
    assert ctx.injector_flow_secondary_ccmin is None


def test_speeduino_nonzero_secondary_injector_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="stagedInjSizeSec", data_type="U16", page=1, offset=0, units="cc/min")],
        [TuneValue(name="stagedInjSizeSec", value=300.0, units="cc/min")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.injector_flow_secondary_ccmin == 300.0


def test_speeduino_num_teeth_captured_as_tooth_count() -> None:
    # Speeduino uses "numTeeth" (contains "nteeth" substring)
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="numTeeth", data_type="U08", page=1, offset=0)],
        [TuneValue(name="numTeeth", value=36.0)],
    )
    # numTeeth is not directly captured in generator context, but the
    # generator context service should find cylinder count / displacement via other params.
    # This test verifies the keyword doesn't erroneously match unrelated fields.
    ctx = _service().build(pages, edits)
    assert ctx.displacement_cc is None  # numTeeth should not be confused with displacement


def test_speeduino_dwellrun_captured_as_dwell() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="dwellRun", data_type="U08", page=1, offset=0, units="ms")],
        [TuneValue(name="dwellRun", value=3.0, units="ms")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.dwell_ms == 3.0


def test_speeduino_mapmax_captured_as_map_range() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="mapMax", data_type="U16", page=1, offset=0, units="kpa")],
        [TuneValue(name="mapMax", value=260.0, units="kpa")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.map_range_kpa == 260.0


def test_speeduino_injopen_captured_as_dead_time() -> None:
    # Speeduino uses "injOpen" for dead time
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="injOpen", data_type="U08", page=1, offset=0, units="ms")],
        [TuneValue(name="injOpen", value=0.7, units="ms")],
    )
    ctx = _service().build(pages, edits)
    assert ctx.injector_dead_time_ms == 0.7


def test_speeduino_ncylinders_captured() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=0)],
        [TuneValue(name="nCylinders", value=6.0)],
    )
    ctx = _service().build(pages, edits)
    assert ctx.cylinder_count == 6


# ---------------------------------------------------------------------------


def test_empty_pages_returns_all_none_context() -> None:
    ctx = _service().build((), LocalTuneEditService())
    assert ctx.injector_flow_ccmin is None
    assert ctx.displacement_cc is None
    assert ctx.dwell_ms is None
    assert ctx.forced_induction_topology == ForcedInductionTopology.NA
    assert ctx.missing_for_ve_generation  # all inputs missing


# ---------------------------------------------------------------------------
# Operator context merging
# ---------------------------------------------------------------------------

def test_operator_displacement_fills_missing_ecu_displacement() -> None:
    # No engineSize in tune; operator provides displacement_cc
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min")],
        [TuneValue(name="injectorFlow", value=550.0, units="cc/min")],
    )
    op_ctx = OperatorEngineContext(displacement_cc=2000.0)
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.displacement_cc == 2000.0


def test_operator_displacement_does_not_override_ecu_displacement() -> None:
    # ECU has engineSize; operator context should not override it
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="engineSize", data_type="U16", page=1, offset=0, units="cc")],
        [TuneValue(name="engineSize", value=3000.0, units="cc")],
    )
    op_ctx = OperatorEngineContext(displacement_cc=1500.0)
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.displacement_cc == 3000.0


def test_operator_compression_fills_missing_ecu_compression() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0)],
        [TuneValue(name="injectorFlow", value=550.0)],
    )
    op_ctx = OperatorEngineContext(compression_ratio=9.5)
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.compression_ratio == 9.5


def test_operator_advanced_engine_context_fields_flow_into_generator_context() -> None:
    pages, edits = _pages_and_edits([], [])
    op_ctx = OperatorEngineContext(
        head_flow_class="race_ported",
        intake_manifold_style="itb",
        injector_characterization="full_characterization",
    )
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.head_flow_class == "race_ported"
    assert ctx.intake_manifold_style == "itb"
    assert ctx.injector_characterization == "full_characterization"


def test_operator_injector_pressure_fields_flow_into_generator_context() -> None:
    pages, edits = _pages_and_edits([], [])
    op_ctx = OperatorEngineContext(
        base_fuel_pressure_psi=58.0,
        injector_pressure_model="vacuum_referenced",
        secondary_injector_reference_pressure_psi=52.0,
        injector_characterization="flow_plus_deadtime",
    )
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.fuel_pressure_kpa == pytest.approx(58.0 * 6.89476, abs=0.001)
    assert ctx.injector_pressure_model == "vacuum_referenced"
    assert ctx.secondary_injector_pressure_kpa == pytest.approx(52.0 * 6.89476, abs=0.001)
    assert ctx.injector_characterization == "flow_plus_deadtime"


def test_operator_supercharger_type_flows_into_generator_context() -> None:
    pages, edits = _pages_and_edits([], [])
    op_ctx = OperatorEngineContext(
        forced_induction_topology=ForcedInductionTopology.SINGLE_SUPERCHARGER,
        supercharger_type=SuperchargerType.CENTRIFUGAL,
    )
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.supercharger_type == SuperchargerType.CENTRIFUGAL


def test_operator_injector_preset_fills_missing_flow_and_deadtime() -> None:
    pages, edits = _pages_and_edits([], [])
    op_ctx = OperatorEngineContext(
        injector_preset_key="id1050x_xds",
        base_fuel_pressure_psi=43.5,
    )
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.injector_flow_ccmin == 1065.0
    assert ctx.injector_dead_time_ms == 0.925


def test_operator_ignition_preset_fills_missing_dwell() -> None:
    pages, edits = _pages_and_edits([], [])
    op_ctx = OperatorEngineContext(ignition_preset_key="gm_ls_19005218")
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.dwell_ms == 4.5


def test_operator_injector_preset_scales_flow_for_pressure() -> None:
    pages, edits = _pages_and_edits([], [])
    op_ctx = OperatorEngineContext(
        injector_preset_key="id1050x_xds",
        base_fuel_pressure_psi=58.0,
    )
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.injector_flow_ccmin == 1229.7560733739028


def test_operator_injector_preset_uses_pressure_compensated_dead_time_when_available() -> None:
    pages, edits = _pages_and_edits([], [])
    op_ctx = OperatorEngineContext(
        injector_preset_key="bosch_0280158117_ev14_52lb",
        base_fuel_pressure_psi=50.03,
    )
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.injector_dead_time_ms == pytest.approx(0.95, abs=0.001)


def test_operator_compression_does_not_override_ecu_compression() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="compressionRatio", data_type="U08", page=1, offset=0)],
        [TuneValue(name="compressionRatio", value=10.5)],
    )
    op_ctx = OperatorEngineContext(compression_ratio=8.0)
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.compression_ratio == 10.5


def test_no_operator_context_leaves_displacement_none() -> None:
    pages, edits = _pages_and_edits(
        [ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0)],
        [TuneValue(name="injectorFlow", value=550.0)],
    )
    ctx = _service().build(pages, edits, operator_context=None)
    assert ctx.displacement_cc is None


# ---------------------------------------------------------------------------
# Computed reqFuel
# ---------------------------------------------------------------------------

def _pages_and_edits_full(
    injector_flow_ccmin: float,
    cylinder_count: int,
    displacement_cc: float | None,
    stoich: float | None,
) -> tuple:
    """Helper for computed reqFuel tests."""
    scalar_defs = [
        ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
        ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=2),
    ]
    tune_values = [
        TuneValue(name="injectorFlow", value=injector_flow_ccmin, units="cc/min"),
        TuneValue(name="nCylinders", value=float(cylinder_count)),
    ]
    if displacement_cc is not None:
        scalar_defs.append(
            ScalarParameterDefinition(name="engineSize", data_type="U16", page=1, offset=4, units="cc")
        )
        tune_values.append(TuneValue(name="engineSize", value=displacement_cc, units="cc"))
    if stoich is not None:
        scalar_defs.append(
            ScalarParameterDefinition(name="stoich", data_type="U08", page=1, offset=6)
        )
        tune_values.append(TuneValue(name="stoich", value=stoich))
    return _pages_and_edits(scalar_defs, tune_values)


def test_computed_req_fuel_populated_when_all_inputs_present() -> None:
    pages, edits = _pages_and_edits_full(
        injector_flow_ccmin=550.0,
        cylinder_count=4,
        displacement_cc=2000.0,
        stoich=14.7,
    )
    ctx = _service().build(pages, edits)
    assert ctx.computed_req_fuel_ms is not None
    assert 5.0 < ctx.computed_req_fuel_ms < 20.0  # sanity range for a 2L 4-cyl


def test_computed_req_fuel_uses_default_stoich_when_absent() -> None:
    # No stoich in tune; should fall back to 14.7 petrol default
    pages, edits = _pages_and_edits_full(
        injector_flow_ccmin=550.0,
        cylinder_count=4,
        displacement_cc=2000.0,
        stoich=None,
    )
    ctx_with_default = _service().build(pages, edits)

    pages2, edits2 = _pages_and_edits_full(
        injector_flow_ccmin=550.0,
        cylinder_count=4,
        displacement_cc=2000.0,
        stoich=14.7,
    )
    ctx_explicit = _service().build(pages2, edits2)
    assert ctx_with_default.computed_req_fuel_ms == ctx_explicit.computed_req_fuel_ms


def test_computed_req_fuel_none_when_displacement_absent() -> None:
    # No displacement in ECU; no operator context → no computed value
    pages, edits = _pages_and_edits_full(
        injector_flow_ccmin=550.0,
        cylinder_count=4,
        displacement_cc=None,
        stoich=14.7,
    )
    ctx = _service().build(pages, edits)
    assert ctx.computed_req_fuel_ms is None


def test_computed_req_fuel_populated_from_operator_displacement() -> None:
    # Displacement from operator context, not ECU
    pages, edits = _pages_and_edits_full(
        injector_flow_ccmin=550.0,
        cylinder_count=4,
        displacement_cc=None,
        stoich=14.7,
    )
    op_ctx = OperatorEngineContext(displacement_cc=2000.0)
    ctx = _service().build(pages, edits, operator_context=op_ctx)
    assert ctx.computed_req_fuel_ms is not None
    assert 5.0 < ctx.computed_req_fuel_ms < 20.0


def test_computed_req_fuel_none_when_injector_flow_absent() -> None:
    pages, edits = _pages_and_edits(
        [
            ScalarParameterDefinition(name="engineSize", data_type="U16", page=1, offset=0, units="cc"),
            ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=2),
        ],
        [
            TuneValue(name="engineSize", value=2000.0, units="cc"),
            TuneValue(name="nCylinders", value=4.0),
        ],
    )
    ctx = _service().build(pages, edits)
    assert ctx.computed_req_fuel_ms is None


def test_computed_req_fuel_none_when_cylinder_count_absent() -> None:
    pages, edits = _pages_and_edits(
        [
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
            ScalarParameterDefinition(name="engineSize", data_type="U16", page=1, offset=2, units="cc"),
        ],
        [
            TuneValue(name="injectorFlow", value=550.0, units="cc/min"),
            TuneValue(name="engineSize", value=2000.0, units="cc"),
        ],
    )
    ctx = _service().build(pages, edits)
    assert ctx.computed_req_fuel_ms is None
import pytest
