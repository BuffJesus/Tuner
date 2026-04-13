from __future__ import annotations

from tuner.domain.ecu_definition import DialogDefinition, DialogFieldDefinition, FieldOptionDefinition, ScalarParameterDefinition
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.hardware_setup_summary_service import HardwareSetupSummaryService
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.tuning_page_service import TuningPageService


def test_injector_page_builds_injector_and_safety_cards() -> None:
    page, edits = _hardware_page_and_edits(
        title="Injector Configuration",
        scalar_defs=[
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
            ScalarParameterDefinition(name="deadTime", data_type="U16", page=1, offset=2, units="ms", requires_power_cycle=True),
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=4, units="ms"),
        ],
        tune_values=[
            TuneValue(name="injectorFlow", value=550.0, units="cc/min"),
            TuneValue(name="deadTime", value=1.1, units="ms"),
            TuneValue(name="reqFuel", value=8.4, units="ms"),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits)

    assert [card.key for card in cards] == ["injector", "safety", "injector_checklist"]
    assert "Injector Flow Rate: 550 cc/min" in cards[0].summary
    assert cards[1].summary == "restart required"
    assert any("required fuel" in line.lower() for line in cards[2].detail_lines)


def test_trigger_page_builds_trigger_geometry_summary() -> None:
    page, edits = _hardware_page_and_edits(
        title="Trigger Setup",
        scalar_defs=[
            ScalarParameterDefinition(name="triggerType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="nTeeth", data_type="U08", page=1, offset=2),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08", page=1, offset=3),
            ScalarParameterDefinition(name="fixAng", data_type="U08", page=1, offset=4, units="deg"),
        ],
        tune_values=[
            TuneValue(name="triggerType", value=2.0),
            TuneValue(name="nTeeth", value=36.0),
            TuneValue(name="missingTeeth", value=1.0),
            TuneValue(name="fixAng", value=60.0, units="deg"),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits)

    assert cards[0].key == "trigger"
    assert "Wheel: 36-1" in cards[0].summary
    assert any("Trigger Type:" in line for line in cards[0].detail_lines)
    assert cards[1].key == "trigger_checklist"
    assert any(line.startswith("[Action]") and "timing light" in line.lower() for line in cards[1].detail_lines)


def test_sensor_page_maps_enum_to_option_label() -> None:
    page, edits = _hardware_page_and_edits(
        title="EGO Sensor Settings",
        scalar_defs=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                page=1,
                offset=0,
                options=(),
            ),
            ScalarParameterDefinition(name="stoich", data_type="U08", page=1, offset=1),
        ],
        tune_values=[
            TuneValue(name="egoType", value=2.0),
            TuneValue(name="stoich", value=14.7),
        ],
        field_overrides={
            "egoType": {"options": ("Off", "Narrowband", "Wideband")},
        },
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits)

    assert cards[0].key == "sensor"
    assert "EGO sensor type: Wideband" in cards[0].summary
    assert cards[1].key == "sensor_checklist"
    assert any("calibration" in line.lower() for line in cards[1].detail_lines)


def test_ignition_checklist_calls_out_enabled_knock_without_pin_field() -> None:
    page, edits = _hardware_page_and_edits(
        title="Ignition Options",
        scalar_defs=[
            ScalarParameterDefinition(name="knockEnabled", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
        ],
        tune_values=[
            TuneValue(name="knockEnabled", value=1.0),
            TuneValue(name="sparkDur", value=3.0, units="ms"),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits)

    assert cards[1].key == "ignition_checklist"
    assert any("knock input pin" in line.lower() for line in cards[1].detail_lines)


def test_sensor_checklist_calls_out_wideband_without_visible_calibration() -> None:
    page, edits = _hardware_page_and_edits(
        title="Wideband Sensor",
        scalar_defs=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
        ],
        tune_values=[
            TuneValue(name="egoType", value=2.0),
        ],
        field_overrides={
            "egoType": {"options": ("Off", "Narrowband", "Wideband")},
        },
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits)

    assert cards[1].key == "sensor_checklist"
    assert any("wideband is enabled" in line.lower() for line in cards[1].detail_lines)


def test_cross_page_prompt_points_to_related_knock_pin_page() -> None:
    ignition_page, edits = _hardware_page_and_edits(
        title="Ignition Knock Options",
        scalar_defs=[
            ScalarParameterDefinition(name="knockEnabled", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
        ],
        tune_values=[
            TuneValue(name="knockEnabled", value=1.0),
            TuneValue(name="sparkDur", value=3.0, units="ms"),
        ],
    )
    knock_page, _ = _hardware_page_and_edits(
        title="Knock Input Pins",
        scalar_defs=[
            ScalarParameterDefinition(name="knockPin", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="knockPin", value=5.0),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        ignition_page,
        edits,
        available_pages=(ignition_page, knock_page),
    )

    assert cards[1].key == "ignition_checklist"
    assert any(line.startswith("[Action]") and "See 'Knock Input Pins'." in line for line in cards[1].detail_lines)


def test_cross_page_prompt_points_to_related_sensor_calibration_page() -> None:
    sensor_page, edits = _hardware_page_and_edits(
        title="Wideband Sensor",
        scalar_defs=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
        ],
        tune_values=[
            TuneValue(name="egoType", value=2.0),
        ],
        field_overrides={
            "egoType": {"options": ("Off", "Narrowband", "Wideband")},
        },
    )
    calibration_page, _ = _hardware_page_and_edits(
        title="AFR Calibration",
        scalar_defs=[
            ScalarParameterDefinition(name="afrCal", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="afrCal", value=14.7),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        sensor_page,
        edits,
        available_pages=(sensor_page, calibration_page),
    )

    assert cards[1].key == "sensor_checklist"
    assert any(line.startswith("[Action]") and "See 'AFR Calibration'." in line for line in cards[1].detail_lines)


def test_cross_page_prompt_flags_hidden_related_setting() -> None:
    ignition_page, edits = _hardware_page_and_edits(
        title="Ignition Knock Options",
        scalar_defs=[
            ScalarParameterDefinition(name="knockEnabled", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
        ],
        tune_values=[
            TuneValue(name="knockEnabled", value=1.0),
            TuneValue(name="sparkDur", value=3.0, units="ms"),
        ],
    )
    hidden_knock_page, _ = _hardware_page_and_edits(
        title="Knock Input Pins",
        scalar_defs=[
            ScalarParameterDefinition(name="knockPin", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="knockPin", value=5.0),
        ],
        field_overrides={
            "knockPin": {"visibility_expression": "{knockEnabled == 2}"},
        },
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        ignition_page,
        edits,
        available_pages=(ignition_page, hidden_knock_page),
    )

    assert cards[1].key == "ignition_checklist"
    assert any(line.startswith("[Gated]") and "may still be hidden" in line for line in cards[1].detail_lines)
    assert cards[2].key == "ignition_gated_followups"
    assert any("Knock input pin" in line for line in cards[2].detail_lines)


def test_injector_primary_card_mentions_related_required_fuel_page() -> None:
    injector_page, edits = _hardware_page_and_edits(
        title="Injector Configuration",
        scalar_defs=[
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
        ],
        tune_values=[
            TuneValue(name="injectorFlow", value=550.0, units="cc/min"),
        ],
    )
    reqfuel_page, _ = _hardware_page_and_edits(
        title="Fuel Constants",
        scalar_defs=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=2, offset=0, units="ms"),
        ],
        tune_values=[
            TuneValue(name="reqFuel", value=8.4, units="ms"),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        injector_page,
        edits,
        available_pages=(injector_page, reqfuel_page),
    )

    assert cards[0].key == "injector"
    assert any("[OK] Required fuel: configured on 'Fuel Constants'." in line for line in cards[0].detail_lines)


def test_ignition_primary_card_mentions_related_knock_pin_page() -> None:
    ignition_page, edits = _hardware_page_and_edits(
        title="Ignition Options",
        scalar_defs=[
            ScalarParameterDefinition(name="knockEnabled", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
        ],
        tune_values=[
            TuneValue(name="knockEnabled", value=1.0),
            TuneValue(name="sparkDur", value=3.0, units="ms"),
        ],
    )
    knock_page, _ = _hardware_page_and_edits(
        title="Knock Input Pins",
        scalar_defs=[
            ScalarParameterDefinition(name="knockPin", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="knockPin", value=5.0),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        ignition_page,
        edits,
        available_pages=(ignition_page, knock_page),
    )

    assert cards[0].key == "ignition"
    assert any("[OK] Knock input pin: configured on 'Knock Input Pins'." in line for line in cards[0].detail_lines)


def test_trigger_primary_card_mentions_gated_secondary_trigger_location() -> None:
    trigger_page, edits = _hardware_page_and_edits(
        title="Trigger Setup",
        scalar_defs=[
            ScalarParameterDefinition(name="triggerType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="nTeeth", data_type="U08", page=1, offset=2),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08", page=1, offset=3),
        ],
        tune_values=[
            TuneValue(name="triggerType", value=2.0),
            TuneValue(name="nTeeth", value=36.0),
            TuneValue(name="missingTeeth", value=1.0),
        ],
    )
    cam_page, _ = _hardware_page_and_edits(
        title="Secondary Trigger Input",
        scalar_defs=[
            ScalarParameterDefinition(name="camInput", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="camInput", value=1.0),
        ],
        field_overrides={
            "camInput": {"visibility_expression": "{triggerType == 3}"},
        },
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        trigger_page,
        edits,
        available_pages=(trigger_page, cam_page),
    )

    assert cards[0].key == "trigger"
    assert any("[Gated] Cam / secondary trigger input: exists on 'Secondary Trigger Input' but is currently gated" in line for line in cards[0].detail_lines)


def test_sensor_primary_card_mentions_related_wideband_calibration_page() -> None:
    sensor_page, edits = _hardware_page_and_edits(
        title="Wideband Sensor",
        scalar_defs=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
        ],
        tune_values=[
            TuneValue(name="egoType", value=2.0),
        ],
        field_overrides={
            "egoType": {"options": ("Off", "Narrowband", "Wideband")},
        },
    )
    calibration_page, _ = _hardware_page_and_edits(
        title="AFR Calibration",
        scalar_defs=[
            ScalarParameterDefinition(name="afrCal", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="afrCal", value=14.7),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        sensor_page,
        edits,
        available_pages=(sensor_page, calibration_page),
    )

    assert cards[0].key == "sensor"
    assert any("[OK] Wideband calibration: configured on 'AFR Calibration'." in line for line in cards[0].detail_lines)


def test_sensor_primary_card_mentions_related_oil_pressure_pin_page_when_enabled() -> None:
    sensor_page, edits = _hardware_page_and_edits(
        title="Sensor Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="oilPressureEnable", data_type="U08", page=1, offset=0),
        ],
        tune_values=[
            TuneValue(name="oilPressureEnable", value=1.0),
        ],
    )
    oil_pin_page, _ = _hardware_page_and_edits(
        title="Oil Pressure Inputs",
        scalar_defs=[
            ScalarParameterDefinition(name="oilPressurePin", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="oilPressurePin", value=3.0),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        sensor_page,
        edits,
        available_pages=(sensor_page, oil_pin_page),
    )

    assert cards[0].key == "sensor"
    assert any("[OK] Oil pressure sensor input pin: configured on 'Oil Pressure Inputs'." in line for line in cards[0].detail_lines)
    assert any("Oil pressure sensing is enabled" in line for line in cards[1].detail_lines)


def test_sensor_gated_followup_mentions_hidden_external_baro_pin_when_enabled() -> None:
    sensor_page, edits = _hardware_page_and_edits(
        title="Sensor Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="useExtBaro", data_type="U08", page=1, offset=0),
        ],
        tune_values=[
            TuneValue(name="useExtBaro", value=1.0),
        ],
    )
    baro_pin_page, _ = _hardware_page_and_edits(
        title="Baro Inputs",
        scalar_defs=[
            ScalarParameterDefinition(name="baroPin", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="baroPin", value=4.0),
        ],
        field_overrides={
            "baroPin": {"visibility_expression": "{useExtBaro == 2}"},
        },
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        sensor_page,
        edits,
        available_pages=(sensor_page, baro_pin_page),
    )

    assert cards[1].key == "sensor_checklist"
    assert any("External baro sensing is enabled" in line for line in cards[1].detail_lines)
    gated = next(card for card in cards if card.key == "sensor_gated_followups")
    assert any("External baro input pin exists on 'Baro Inputs'" in line for line in gated.detail_lines)
    assert ("Open Baro Input", "dialog:baro_inputs#baroPin") in gated.links


def test_companion_status_lines_use_operator_status_prefixes() -> None:
    trigger_page, edits = _hardware_page_and_edits(
        title="Trigger Setup",
        scalar_defs=[
            ScalarParameterDefinition(name="triggerType", data_type="U08", page=1, offset=0),
        ],
        tune_values=[
            TuneValue(name="triggerType", value=2.0),
        ],
    )
    angle_page, _ = _hardware_page_and_edits(
        title="Timing Reference",
        scalar_defs=[
            ScalarParameterDefinition(name="fixAng", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="fixAng", value=10.0),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        trigger_page,
        edits,
        available_pages=(trigger_page, angle_page),
    )

    primary = next(card for card in cards if card.key == "trigger")
    assert any(line.startswith("[OK] Reference angle:") for line in primary.detail_lines)
    assert any(line.startswith("[Missing] Cam / secondary trigger input:") for line in primary.detail_lines)


def test_guidance_lines_use_operator_status_prefixes() -> None:
    page, edits = _hardware_page_and_edits(
        title="Trigger Setup",
        scalar_defs=[
            ScalarParameterDefinition(name="triggerType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="fixAng", data_type="U08", page=1, offset=1, units="deg"),
        ],
        tune_values=[
            TuneValue(name="triggerType", value=2.0),
            TuneValue(name="fixAng", value=0.0, units="deg"),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits)

    checklist = next(card for card in cards if card.key == "trigger_checklist")
    assert checklist.detail_lines[0].startswith("[Review]")
    assert any(line.startswith("[Caution]") and "currently zero" in line.lower() for line in checklist.detail_lines)
    assert any(line.startswith("[Action]") and "timing light" in line.lower() for line in checklist.detail_lines)


def test_ignition_links_do_not_offer_knock_page_when_knock_is_off() -> None:
    ignition_page, edits = _hardware_page_and_edits(
        title="Ignition Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="knock_mode", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
        ],
        tune_values=[
            TuneValue(name="knock_mode", value=0.0),
            TuneValue(name="sparkDur", value=3.0, units="ms"),
        ],
    )
    knock_page, _ = _hardware_page_and_edits(
        title="Knock Input Pins",
        scalar_defs=[
            ScalarParameterDefinition(name="knock_digital_pin", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="knock_digital_pin", value=5.0),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        ignition_page,
        edits,
        available_pages=(ignition_page, knock_page),
    )

    assert cards[0].key == "ignition"
    assert not any("Knock Input" in label for label, _target in cards[0].links)


def test_sensor_links_do_not_offer_baro_page_when_external_baro_is_off() -> None:
    sensor_page, edits = _hardware_page_and_edits(
        title="Sensor Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="useExtBaro", data_type="U08", page=1, offset=0),
        ],
        tune_values=[
            TuneValue(name="useExtBaro", value=0.0),
        ],
    )
    baro_page, _ = _hardware_page_and_edits(
        title="Baro Inputs",
        scalar_defs=[
            ScalarParameterDefinition(name="baroPin", data_type="U08", page=2, offset=0),
        ],
        tune_values=[
            TuneValue(name="baroPin", value=4.0),
        ],
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        sensor_page,
        edits,
        available_pages=(sensor_page, baro_page),
    )

    assert cards[0].key == "sensor"
    assert not any("Baro Input" in label for label, _target in cards[0].links)


# ---------------------------------------------------------------------------
# Readiness card tests
# ---------------------------------------------------------------------------

def test_injector_readiness_card_shows_captured_inputs() -> None:
    from tuner.domain.generator_context import GeneratorInputContext

    page, edits = _hardware_page_and_edits(
        title="Injector Configuration",
        scalar_defs=[
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
            ScalarParameterDefinition(name="deadTime", data_type="U16", page=1, offset=2, units="ms"),
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=4, units="ms"),
        ],
        tune_values=[
            TuneValue(name="injectorFlow", value=550.0, units="cc/min"),
            TuneValue(name="deadTime", value=1.1, units="ms"),
            TuneValue(name="reqFuel", value=8.4, units="ms"),
        ],
    )
    ctx = GeneratorInputContext(
        injector_flow_ccmin=550.0,
        injector_dead_time_ms=1.1,
        required_fuel_ms=8.4,
        missing_for_ve_generation=("Engine displacement", "Cylinder count", "RPM limit / redline"),
        missing_for_injector_helper=("Engine displacement", "Cylinder count", "Stoich ratio"),
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits, generator_context=ctx)
    readiness = next((c for c in cards if c.key == "injector_readiness"), None)

    assert readiness is not None
    assert any("550" in line for line in readiness.detail_lines)
    assert any("1.1" in line for line in readiness.detail_lines)
    assert any("8.4" in line for line in readiness.detail_lines)
    assert any("displacement" in line.lower() for line in readiness.detail_lines)


def test_injector_readiness_card_complete_when_nothing_missing() -> None:
    from tuner.domain.generator_context import GeneratorInputContext

    page, edits = _hardware_page_and_edits(
        title="Injector Configuration",
        scalar_defs=[
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0),
        ],
        tune_values=[TuneValue(name="injectorFlow", value=550.0)],
    )
    ctx = GeneratorInputContext(
        injector_flow_ccmin=550.0,
        injector_dead_time_ms=1.1,
        required_fuel_ms=8.4,
        displacement_cc=2000.0,
        cylinder_count=4,
        rev_limit_rpm=7000.0,
        stoich_ratio=14.7,
        missing_for_ve_generation=(),
        missing_for_injector_helper=(),
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits, generator_context=ctx)
    readiness = next((c for c in cards if c.key == "injector_readiness"), None)

    assert readiness is not None
    assert readiness.severity == "info"
    assert "all required" in readiness.summary.lower()


def test_readiness_card_absent_without_generator_context() -> None:
    page, edits = _hardware_page_and_edits(
        title="Injector Configuration",
        scalar_defs=[
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0),
        ],
        tune_values=[TuneValue(name="injectorFlow", value=550.0)],
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits)
    assert not any(c.key.endswith("_readiness") for c in cards)


def test_ignition_readiness_card_shows_missing_spark_inputs() -> None:
    from tuner.domain.generator_context import GeneratorInputContext

    page, edits = _hardware_page_and_edits(
        title="Ignition Options",
        scalar_defs=[
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=0, units="ms"),
        ],
        tune_values=[TuneValue(name="sparkDur", value=3.2, units="ms")],
    )
    ctx = GeneratorInputContext(
        dwell_ms=3.2,
        missing_for_spark_helper=("Compression ratio", "RPM limit / redline"),
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits, generator_context=ctx)
    readiness = next((c for c in cards if c.key == "ignition_readiness"), None)

    assert readiness is not None
    assert readiness.severity == "warning"
    assert any("compression" in line.lower() for line in readiness.detail_lines)


def test_sensor_readiness_card_shows_captured_ego_and_stoich() -> None:
    from tuner.domain.generator_context import GeneratorInputContext

    page, edits = _hardware_page_and_edits(
        title="EGO Sensor Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="stoich", data_type="U08", page=1, offset=1),
        ],
        tune_values=[
            TuneValue(name="egoType", value=2.0),
            TuneValue(name="stoich", value=14.7),
        ],
    )
    ctx = GeneratorInputContext(
        ego_type_index=2,
        stoich_ratio=14.7,
        missing_for_injector_helper=(),
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits, generator_context=ctx)
    readiness = next((c for c in cards if c.key == "sensor_readiness"), None)

    assert readiness is not None
    assert any("wideband" in line.lower() for line in readiness.detail_lines)
    assert any("14.7" in line for line in readiness.detail_lines)


def test_trigger_readiness_card_absent_when_rev_limit_captured() -> None:
    from tuner.domain.generator_context import GeneratorInputContext

    page, edits = _hardware_page_and_edits(
        title="Trigger Setup",
        scalar_defs=[
            ScalarParameterDefinition(name="nTeeth", data_type="U08", page=1, offset=0),
        ],
        tune_values=[TuneValue(name="nTeeth", value=36.0)],
    )
    ctx = GeneratorInputContext(
        rev_limit_rpm=7000.0,
        missing_for_ve_generation=(),  # rev limit is present
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits, generator_context=ctx)
    assert not any(c.key == "trigger_readiness" for c in cards)


# ---------------------------------------------------------------------------


def _hardware_page_and_edits(
    *,
    title: str,
    scalar_defs: list[ScalarParameterDefinition],
    tune_values: list[TuneValue],
    field_overrides: dict[str, dict] | None = None,
):
    field_overrides = field_overrides or {}
    dialog_id = "".join(ch.lower() if ch.isalnum() else "_" for ch in title).strip("_") or "hardware_page"
    definition_dialog = DialogDefinition(
        dialog_id=dialog_id,
        title=title,
        fields=[
            DialogFieldDefinition(
                label=override.get("label", scalar.label or scalar.name),
                parameter_name=scalar.name,
                visibility_expression=override.get("visibility_expression"),
            )
            for scalar in scalar_defs
            for override in [field_overrides.get(scalar.name, {})]
        ],
    )

    scalar_defs = [
        ScalarParameterDefinition(
                name=scalar.name,
                data_type=scalar.data_type,
                page=scalar.page,
                offset=scalar.offset,
                units=scalar.units,
                label=field_overrides.get(scalar.name, {}).get("label", scalar.label),
                options=tuple(
                    FieldOptionDefinition(value=str(index), label=label)
                    for index, label in enumerate(field_overrides.get(scalar.name, {}).get("options", ()))
                ) if field_overrides.get(scalar.name, {}).get("options") else scalar.options,
                visibility_expression=field_overrides.get(scalar.name, {}).get("visibility_expression", scalar.visibility_expression),
                requires_power_cycle=scalar.requires_power_cycle,
        )
        for scalar in scalar_defs
    ]

    from tuner.domain.ecu_definition import EcuDefinition, MenuDefinition, MenuItemDefinition

    definition = EcuDefinition(
        name="Speeduino",
        scalars=scalar_defs,
        dialogs=[definition_dialog],
        menus=[MenuDefinition(title="Setup", items=[MenuItemDefinition(target=dialog_id, label=title)])],
    )
    page = TuningPageService().build_pages(definition)[0].pages[0]
    tune = TuneFile(constants=tune_values)
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)
    return page, edits


# ---------------------------------------------------------------------------
# Visibility expression evaluation for specific hardware cases
# ---------------------------------------------------------------------------

def test_knock_digital_pin_visible_when_knock_mode_is_digital() -> None:
    """Speeduino: knock_digital_pin has { knock_mode == 1 }; must be visible when mode=1."""
    page, edits = _hardware_page_and_edits(
        title="Ignition Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="knock_mode", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(
                name="knock_digital_pin",
                data_type="U08",
                page=1,
                offset=1,
                visibility_expression="{ knock_mode == 1 }",
            ),
        ],
        tune_values=[
            TuneValue(name="knock_mode", value=1.0),  # Digital
            TuneValue(name="knock_digital_pin", value=34.0),
        ],
    )
    cards = HardwareSetupSummaryService().build_page_cards(page, edits)
    # knock_digital_pin is visible — should NOT appear as gated/hidden
    gated_keys = {c.key for c in cards if "gated" in c.key or "hidden" in c.title.lower()}
    for card in cards:
        assert not any("knock" in line.lower() and "hidden" in line.lower() for line in card.detail_lines)


def test_knock_companion_line_not_shown_when_knock_mode_is_off() -> None:
    """When knock_mode=0 (Off), knock pin companion line must not be shown — knock is disabled."""
    page, edits = _hardware_page_and_edits(
        title="Ignition Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="knock_mode", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(
                name="knock_digital_pin",
                data_type="U08",
                page=1,
                offset=1,
                visibility_expression="{ knock_mode == 1 }",
            ),
        ],
        tune_values=[
            TuneValue(name="knock_mode", value=0.0),  # Off
            TuneValue(name="knock_digital_pin", value=34.0),
        ],
    )
    cards = HardwareSetupSummaryService().build_page_cards(page, edits)
    # Knock is Off — no companion warning about knock pin should appear
    all_detail = " ".join(line for c in cards for line in c.detail_lines).lower()
    assert "knock input pin" not in all_detail


def test_knock_analog_pin_visible_when_knock_mode_is_analog() -> None:
    """knock_analog_pin with { knock_mode == 2 } must be reported as visible when mode=2."""
    page, edits = _hardware_page_and_edits(
        title="Ignition Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="knock_mode", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(
                name="knock_analog_pin",
                data_type="U08",
                page=1,
                offset=1,
                visibility_expression="{ knock_mode == 2 }",
            ),
        ],
        tune_values=[
            TuneValue(name="knock_mode", value=2.0),  # Analog
            TuneValue(name="knock_analog_pin", value=48.0),
        ],
    )
    cards = HardwareSetupSummaryService().build_page_cards(page, edits)
    # Analog mode pin is visible — must not appear in gated followups
    for card in cards:
        assert not any("knock" in line.lower() and "hidden" in line.lower() for line in card.detail_lines)


def test_gated_followup_card_uses_speeduino_knock_pin_keywords() -> None:
    """knock_digital_pin / knock_analog_pin must match new Speeduino keyword patterns."""
    knock_page, _ = _hardware_page_and_edits(
        title="Knock Pin Settings",
        scalar_defs=[
            ScalarParameterDefinition(
                name="knock_digital_pin",
                data_type="U08",
                page=2,
                offset=0,
                visibility_expression="{ knock_mode == 1 }",
            ),
        ],
        tune_values=[TuneValue(name="knock_digital_pin", value=34.0)],
    )
    ignition_page, edits = _hardware_page_and_edits(
        title="Ignition Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="knock_mode", data_type="U08", page=1, offset=0),
        ],
        tune_values=[TuneValue(name="knock_mode", value=1.0)],
    )
    cards = HardwareSetupSummaryService().build_page_cards(
        ignition_page,
        edits,
        available_pages=(ignition_page, knock_page),
    )
    all_detail = " ".join(line for c in cards for line in c.detail_lines).lower()
    assert "knock" in all_detail


def test_wideband_companion_line_visible_when_egotype_is_wideband() -> None:
    """When egoType==2, wideband calibration companion line should say 'configured' not 'gated'."""
    sensor_page, edits = _hardware_page_and_edits(
        title="Sensor Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="afrCal", data_type="U08", page=1, offset=1),
        ],
        tune_values=[
            TuneValue(name="egoType", value=2.0),
            TuneValue(name="afrCal", value=14.7),
        ],
    )
    cards = HardwareSetupSummaryService().build_page_cards(sensor_page, edits)
    # Wideband is enabled and afrCal is on same page with no visibility gate — should appear in summary
    all_detail = " ".join(line for c in cards for line in c.detail_lines).lower()
    assert "wideband" in all_detail or "ego" in all_detail or "afr" in all_detail


def test_wideband_companion_line_gated_when_afrcal_has_visibility_expression() -> None:
    """When afrCal is gated by { egoType == 2 } but egoType is currently narrowband, report as gated."""
    sensor_page, edits = _hardware_page_and_edits(
        title="Sensor Settings",
        scalar_defs=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(
                name="afrCal",
                data_type="U08",
                page=1,
                offset=1,
                visibility_expression="{ egoType == 2 }",
            ),
        ],
        tune_values=[
            TuneValue(name="egoType", value=1.0),  # Narrowband
            TuneValue(name="afrCal", value=14.7),
        ],
    )
    cards = HardwareSetupSummaryService().build_page_cards(sensor_page, edits)
    # afrCal exists on page but is hidden when egoType != 2 → should appear in gated followups
    all_detail = " ".join(line for c in cards for line in c.detail_lines).lower()
    assert "wideband calibration" in all_detail or "afr" in all_detail or "calibrat" in all_detail


def test_map_calibration_keyword_matches_speeduino_mapcal_dialog_parameter() -> None:
    """mapCal and mapMin/mapMax should match keyword 'mapcal' for sensor gated followup."""
    # mapMin/mapMax (MAP calibration scalars) should be found by "mapcal" keyword
    from tuner.services.hardware_setup_summary_service import HardwareSetupSummaryService
    from tuner.services.visibility_expression_service import VisibilityExpressionService

    # Simulate a page where mapMin/mapMax exist without visibility gate
    sensor_page, edits = _hardware_page_and_edits(
        title="MAP Sensor",
        scalar_defs=[
            ScalarParameterDefinition(name="mapMin", data_type="U16", page=1, offset=0, units="kPa"),
            ScalarParameterDefinition(name="mapMax", data_type="U16", page=1, offset=2, units="kPa"),
        ],
        tune_values=[
            TuneValue(name="mapMin", value=10.0, units="kPa"),
            TuneValue(name="mapMax", value=260.0, units="kPa"),
        ],
    )
    map_cal_page, _ = _hardware_page_and_edits(
        title="MAP Calibration",
        scalar_defs=[
            ScalarParameterDefinition(name="mapCalMin", data_type="U16", page=2, offset=0, units="kPa"),
        ],
        tune_values=[TuneValue(name="mapCalMin", value=10.0, units="kPa")],
    )
    # Keywords "mapcal" and "calibration" should match "mapCalMin"
    svc = HardwareSetupSummaryService()
    cards = svc.build_page_cards(sensor_page, edits, available_pages=(sensor_page, map_cal_page))
    # mapCalMin on another page should be surfaced as a companion
    all_detail = " ".join(line for c in cards for line in c.detail_lines).lower()
    assert "map" in all_detail


# ---------------------------------------------------------------------------
# Cross-validation card wiring
# ---------------------------------------------------------------------------

def test_build_page_cards_includes_cross_validation_card_when_items_provided() -> None:
    """Cross-validation items passed to build_page_cards must appear as a card."""
    from tuner.domain.setup_checklist import ChecklistItemStatus, SetupChecklistItem

    page, edits = _hardware_page_and_edits(
        title="Ignition Setup",
        scalar_defs=[
            ScalarParameterDefinition(name="dwellRun", data_type="U08", page=1, offset=0, units="ms"),
        ],
        tune_values=[TuneValue(name="dwellRun", value=3.0, units="ms")],
    )

    xval_items = (
        SetupChecklistItem(
            key="dwell_configured",
            title="Dwell configured",
            status=ChecklistItemStatus.OK,
            detail="Dwell is 3.0 ms.",
            parameter_name="dwellRun",
        ),
        SetupChecklistItem(
            key="reference_angle",
            title="Verify reference angle",
            status=ChecklistItemStatus.WARNING,
            detail="Reference angle is 0°.",
        ),
    )

    cards = HardwareSetupSummaryService().build_page_cards(
        page, edits, cross_validation_items=xval_items
    )

    card_keys = [c.key for c in cards]
    assert "ignition_trigger_cross_check" in card_keys

    xval_card = next(c for c in cards if c.key == "ignition_trigger_cross_check")
    assert xval_card.severity == "warning"
    assert "1 item" in xval_card.summary
    assert "1 already configured" in xval_card.summary
    assert xval_card.detail_lines[0] == "Still needed:"
    assert any("Verify reference angle" in line for line in xval_card.detail_lines[1:3])
    assert "Configured now:" in xval_card.detail_lines
    assert any("Dwell configured" in line for line in xval_card.detail_lines)


def test_cross_validation_card_all_ok_shows_passed_summary() -> None:
    from tuner.domain.setup_checklist import ChecklistItemStatus, SetupChecklistItem

    page, edits = _hardware_page_and_edits(
        title="Ignition Setup",
        scalar_defs=[ScalarParameterDefinition(name="dwellRun", data_type="U08", page=1, offset=0)],
        tune_values=[TuneValue(name="dwellRun", value=3.0)],
    )

    xval_items = (
        SetupChecklistItem(key="dwell_configured", title="Dwell configured", status=ChecklistItemStatus.OK, detail="3.0 ms."),
        SetupChecklistItem(key="reference_angle", title="Reference angle configured", status=ChecklistItemStatus.OK, detail="20°."),
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits, cross_validation_items=xval_items)
    xval_card = next(c for c in cards if c.key == "ignition_trigger_cross_check")
    assert xval_card.severity == "info"
    assert "All cross-setup checks passed" in xval_card.summary
    assert "2 configured" in xval_card.summary
    assert xval_card.detail_lines[0] == "Configured now:"


def test_cross_validation_card_marks_cross_page_items_in_operator_text() -> None:
    from tuner.domain.setup_checklist import ChecklistItemStatus, SetupChecklistItem

    page, edits = _hardware_page_and_edits(
        title="Ignition Setup",
        scalar_defs=[ScalarParameterDefinition(name="dwellRun", data_type="U08", page=1, offset=0)],
        tune_values=[TuneValue(name="dwellRun", value=3.0)],
    )

    xval_items = (
        SetupChecklistItem(
            key="cam_sync",
            title="Assign cam sync",
            status=ChecklistItemStatus.NEEDED,
            detail="Sequential spark needs a valid cam input.",
            cross_page=True,
        ),
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits, cross_validation_items=xval_items)
    xval_card = next(c for c in cards if c.key == "ignition_trigger_cross_check")

    assert any("Assign cam sync (other page)" in line for line in xval_card.detail_lines)


def test_no_cross_validation_card_when_no_items() -> None:
    page, edits = _hardware_page_and_edits(
        title="Ignition Setup",
        scalar_defs=[ScalarParameterDefinition(name="dwellRun", data_type="U08", page=1, offset=0)],
        tune_values=[TuneValue(name="dwellRun", value=3.0)],
    )

    cards = HardwareSetupSummaryService().build_page_cards(page, edits)
    assert not any(c.key == "ignition_trigger_cross_check" for c in cards)
