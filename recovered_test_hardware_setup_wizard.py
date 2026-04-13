from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from tuner.domain.ecu_definition import (
    EcuDefinition,
    FieldOptionDefinition,
    ReferenceTableDefinition,
    ReferenceTableSolution,
    ScalarParameterDefinition,
    TableDefinition,
    TableEditorDefinition,
)
from tuner.domain.generator_context import ForcedInductionTopology, SuperchargerType
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.required_fuel_calculator_service import RequiredFuelCalculatorService
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter
from tuner.ui.hardware_setup_wizard import HardwareSetupWizard


def test_knock_visibility_hides_and_reveals_complete_form_rows() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="knock_mode", value=0.0),
            ]
        )
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _assert_row_hidden(wizard._knock_form, wizard._knock_digital_pin_combo)
    _assert_row_hidden(wizard._knock_form, wizard._knock_analog_pin_combo)
    _assert_row_hidden(wizard._knock_form, wizard._knock_threshold_spin)
    _assert_row_hidden(wizard._knock_form, wizard._knock_max_retard_spin)

    wizard._knock_mode_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._knock_form, wizard._knock_digital_pin_combo)
    _assert_row_hidden(wizard._knock_form, wizard._knock_analog_pin_combo)
    _assert_row_hidden(wizard._knock_form, wizard._knock_threshold_spin)
    _assert_row_visible(wizard._knock_form, wizard._knock_max_retard_spin)

    wizard._knock_mode_combo.setCurrentIndex(2)
    app.processEvents()

    _assert_row_hidden(wizard._knock_form, wizard._knock_digital_pin_combo)
    _assert_row_visible(wizard._knock_form, wizard._knock_analog_pin_combo)
    _assert_row_visible(wizard._knock_form, wizard._knock_threshold_spin)
    _assert_row_visible(wizard._knock_form, wizard._knock_max_retard_spin)


def test_knock_pin_selected_in_wizard_bootstraps_missing_tune_value() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="knock_mode",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Digital"),
                ),
            ),
            ScalarParameterDefinition(
                name="knock_digital_pin",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("30", "30"),
                    FieldOptionDefinition("34", "34"),
                ),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="knock_mode", value=0.0)]),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    wizard._knock_mode_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._knock_digital_pin_combo.setCurrentIndex(2)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    staged = wizard._presenter.local_tune_edit_service.get_value("knock_digital_pin")
    assert staged is not None
    assert staged.value == 34.0


def test_oil_pressure_visibility_hides_and_reveals_complete_form_rows() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[TuneValue(name="oilPressureEnable", value=0.0)]))

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _assert_row_hidden(wizard._oil_form, wizard._oil_pin_combo)
    _assert_row_hidden(wizard._oil_form, wizard._oil_min_spin)
    _assert_row_hidden(wizard._oil_form, wizard._oil_max_spin)

    wizard._oil_pressure_enable_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._oil_form, wizard._oil_pin_combo)
    _assert_row_visible(wizard._oil_form, wizard._oil_min_spin)
    _assert_row_visible(wizard._oil_form, wizard._oil_max_spin)


def test_external_baro_visibility_hides_and_reveals_complete_form_rows() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[TuneValue(name="useExtBaro", value=0.0)]))

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _assert_row_hidden(wizard._baro_form, wizard._baro_pin_combo)
    _assert_row_hidden(wizard._baro_form, wizard._baro_min_spin)
    _assert_row_hidden(wizard._baro_form, wizard._baro_max_spin)

    wizard._baro_enable_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._baro_form, wizard._baro_pin_combo)
    _assert_row_visible(wizard._baro_form, wizard._baro_min_spin)
    _assert_row_visible(wizard._baro_form, wizard._baro_max_spin)


def test_definition_backed_sensor_enable_combos_stage_sparse_values() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="flexEnabled",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("4", "Enabled"),
                ),
            ),
            ScalarParameterDefinition(name="flexFreqLow", data_type="F32"),
            ScalarParameterDefinition(name="flexFreqHigh", data_type="F32"),
            ScalarParameterDefinition(
                name="oilPressureEnable",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("3", "Enabled"),
                ),
            ),
            ScalarParameterDefinition(
                name="useExtBaro",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "No"),
                    FieldOptionDefinition("2", "Yes"),
                ),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="flexEnabled", value=0.0),
                TuneValue(name="oilPressureEnable", value=0.0),
                TuneValue(name="useExtBaro", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    wizard._flex_enable_combo.setCurrentIndex(1)
    wizard._oil_pressure_enable_combo.setCurrentIndex(1)
    wizard._baro_enable_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    flex_enabled = wizard._presenter.local_tune_edit_service.get_value("flexEnabled")
    oil_enabled = wizard._presenter.local_tune_edit_service.get_value("oilPressureEnable")
    baro_enabled = wizard._presenter.local_tune_edit_service.get_value("useExtBaro")
    assert flex_enabled is not None
    assert oil_enabled is not None
    assert baro_enabled is not None
    assert flex_enabled.value == 4.0
    assert oil_enabled.value == 3.0
    assert baro_enabled.value == 2.0


def test_sparse_definition_values_drive_sensor_visibility_and_risks() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("5", "Wide Band"),
                ),
            ),
            ScalarParameterDefinition(
                name="knock_mode",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("8", "Analog"),
                ),
            ),
            ScalarParameterDefinition(
                name="knock_analog_pin",
                data_type="U08",
                options=(FieldOptionDefinition("48", "ADC48"),),
            ),
            ScalarParameterDefinition(
                name="engineProtectType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("7", "Fuel Only"),
                ),
            ),
            ScalarParameterDefinition(
                name="afrProtectEnabled",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("6", "Table mode"),
                ),
            ),
            ScalarParameterDefinition(
                name="useExtBaro",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "No"),
                    FieldOptionDefinition("2", "Yes"),
                ),
            ),
            ScalarParameterDefinition(name="baroMin", data_type="F32"),
            ScalarParameterDefinition(name="baroMax", data_type="F32"),
            ScalarParameterDefinition(name="afrProtectCutTime", data_type="F32"),
            ScalarParameterDefinition(name="engineProtectMaxRPM", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="egoType", value=5.0),
                TuneValue(name="knock_mode", value=8.0),
                TuneValue(name="engineProtectType", value=7.0),
                TuneValue(name="afrProtectEnabled", value=6.0),
                TuneValue(name="useExtBaro", value=2.0),
                TuneValue(name="baroMin", value=120.0),
                TuneValue(name="baroMax", value=80.0),
                TuneValue(name="afrProtectCutTime", value=0.0),
                TuneValue(name="engineProtectMaxRPM", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _assert_row_visible(wizard._knock_form, wizard._knock_analog_pin_combo)
    _assert_row_visible(wizard._baro_form, wizard._baro_pin_combo)
    _assert_row_visible(wizard._afr_protect_form, wizard._afr_protect_map_spin)
    assert "Analog knock mode is enabled but no valid analog input pin is selected." not in wizard._sensor_risk_label.text()
    assert "External-baro 5 V calibration must be greater" in wizard._sensor_risk_label.text()
    assert "Set AFR protection RPM limit" in wizard._sensor_checklist_label.text()


def test_flex_fuel_visibility_hides_and_reveals_complete_form_rows() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[TuneValue(name="flexEnabled", value=0.0)]))

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _assert_row_hidden(wizard._flex_form, wizard._flex_freq_low_spin)
    _assert_row_hidden(wizard._flex_form, wizard._flex_freq_high_spin)

    wizard._flex_enable_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    _assert_row_visible(wizard._flex_form, wizard._flex_freq_low_spin)
    _assert_row_visible(wizard._flex_form, wizard._flex_freq_high_spin)


def test_flex_enable_applies_standard_sensor_defaults_when_missing() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="flexEnabled", data_type="U08"),
            ScalarParameterDefinition(name="flexFreqLow", data_type="F32"),
            ScalarParameterDefinition(name="flexFreqHigh", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="flexEnabled", value=0.0)]),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    wizard._flex_enable_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    low = wizard._presenter.local_tune_edit_service.get_value("flexFreqLow")
    high = wizard._presenter.local_tune_edit_service.get_value("flexFreqHigh")
    assert low is not None
    assert high is not None
    assert low.value == 50.0
    assert high.value == 150.0


def test_dropbear_sensor_pins_default_to_shipped_board_profile_when_absent() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(
        TuneFile(
            firmware_info="Speeduino DropBear v2.0.1",
            constants=[
                TuneValue(name="oilPressureEnable", value=1.0),
                TuneValue(name="useExtBaro", value=1.0),
            ],
        ),
        definition=EcuDefinition(
            name="Speeduino",
            firmware_signature="speeduino 202501-T41",
            scalars=[
                ScalarParameterDefinition(name="oilPressureEnable", data_type="U08"),
                ScalarParameterDefinition(name="oilPressurePin", data_type="U08"),
                ScalarParameterDefinition(name="useExtBaro", data_type="U08"),
                ScalarParameterDefinition(name="baroPin", data_type="U08"),
            ],
        ),
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    assert wizard._oil_pin_combo.currentData() == "15"
    assert wizard._baro_pin_combo.currentData() == "12"


def test_dropbear_sensor_pin_defaults_are_retained_when_feature_is_enabled() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(
        TuneFile(firmware_info="Speeduino DropBear v2.0.1", constants=[]),
        definition=EcuDefinition(
            name="Speeduino",
            firmware_signature="speeduino 202501-T41",
            scalars=[
                ScalarParameterDefinition(name="oilPressureEnable", data_type="U08"),
                ScalarParameterDefinition(name="oilPressurePin", data_type="U08"),
                ScalarParameterDefinition(name="useExtBaro", data_type="U08"),
                ScalarParameterDefinition(name="baroPin", data_type="U08"),
            ],
        ),
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    wizard._oil_pressure_enable_combo.setCurrentIndex(1)
    wizard._baro_enable_combo.setCurrentIndex(1)
    app.processEvents()

    assert wizard._oil_pin_combo.currentData() == "15"
    assert wizard._baro_pin_combo.currentData() == "12"


def test_sensor_pin_combos_honor_definition_options_and_stage_selected_values() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="oilPressureEnable", value=1.0),
                TuneValue(name="useExtBaro", value=1.0),
            ]
        ),
        definition=EcuDefinition(
            name="Speeduino",
            scalars=[
                ScalarParameterDefinition(name="oilPressureEnable", data_type="U08"),
                ScalarParameterDefinition(
                    name="oilPressurePin",
                    data_type="U08",
                    options=(
                        FieldOptionDefinition("3", "EXT_OIL"),
                        FieldOptionDefinition("7", "SPARE_ADC7"),
                    ),
                ),
                ScalarParameterDefinition(name="useExtBaro", data_type="U08"),
                ScalarParameterDefinition(
                    name="baroPin",
                    data_type="U08",
                    options=(
                        FieldOptionDefinition("8", "EXT_BARO"),
                        FieldOptionDefinition("12", "AUX_BARO"),
                    ),
                ),
            ],
        ),
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    assert wizard._oil_pin_combo.itemText(0) == "EXT_OIL"
    assert wizard._baro_pin_combo.itemText(0) == "EXT_BARO"

    wizard._oil_pin_combo.setCurrentIndex(1)
    wizard._baro_pin_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    oil_pin = wizard._presenter.local_tune_edit_service.get_value("oilPressurePin")
    baro_pin = wizard._presenter.local_tune_edit_service.get_value("baroPin")
    assert oil_pin is not None
    assert baro_pin is not None
    assert oil_pin.value == 7.0
    assert baro_pin.value == 12.0


def test_cam_input_visibility_follows_sequential_spark_mode_and_stages_value() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="sparkMode",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Wasted Spark"),
                    FieldOptionDefinition("3", "Sequential"),
                ),
            ),
            ScalarParameterDefinition(
                name="camInput",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Hall Input"),
                ),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="sparkMode", value=0.0),
                TuneValue(name="camInput", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    _assert_row_hidden(wizard._ign_form, wizard._cam_input_combo)

    wizard._spark_mode_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._ign_form, wizard._cam_input_combo)
    wizard._cam_input_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    staged = wizard._presenter.local_tune_edit_service.get_value("camInput")
    assert staged is not None
    assert staged.value == 1.0


def test_cam_input_visibility_follows_decoder_that_requires_secondary_trigger() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="TrigPattern",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Missing Tooth"),
                    FieldOptionDefinition("1", "Dual Wheel with Cam"),
                ),
            ),
            ScalarParameterDefinition(
                name="sparkMode",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Wasted Spark"),),
            ),
            ScalarParameterDefinition(
                name="camInput",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Hall Input"),
                ),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="sparkMode", value=0.0),
                TuneValue(name="camInput", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    _assert_row_hidden(wizard._ign_form, wizard._cam_input_combo)

    wizard._trig_pattern_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._ign_form, wizard._cam_input_combo)


def test_cam_input_visibility_supports_speeduino_secondary_trigger_pattern() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="sparkMode",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Wasted Spark"),
                    FieldOptionDefinition("3", "Sequential"),
                ),
            ),
            ScalarParameterDefinition(
                name="trigPatternSec",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Single tooth cam"),
                    FieldOptionDefinition("1", "4-1 cam"),
                ),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="sparkMode", value=0.0),
                TuneValue(name="trigPatternSec", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    _assert_row_hidden(wizard._ign_form, wizard._cam_input_combo)

    wizard._spark_mode_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._ign_form, wizard._cam_input_combo)
    wizard._cam_input_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    staged = wizard._presenter.local_tune_edit_service.get_value("trigPatternSec")
    assert staged is not None
    assert staged.value == 1.0


def test_cam_input_visibility_follows_sequential_injection_layout() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="injLayout",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Paired"),
                    FieldOptionDefinition("1", "Semi-Sequential"),
                    FieldOptionDefinition("3", "Sequential"),
                ),
            ),
            ScalarParameterDefinition(
                name="sparkMode",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Wasted Spark"),),
            ),
            ScalarParameterDefinition(
                name="camInput",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Hall Input"),
                ),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="injLayout", value=0.0),
                TuneValue(name="sparkMode", value=0.0),
                TuneValue(name="camInput", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    _assert_row_hidden(wizard._ign_form, wizard._cam_input_combo)

    wizard._injlayout_combo.setCurrentIndex(2)
    app.processEvents()

    _assert_row_visible(wizard._ign_form, wizard._cam_input_combo)
    assert "sequential fuel mode" in wizard._trigger_topology_label.text().lower()
    assert "sequential fuel mode is selected" in wizard._trigger_risk_label.text().lower()


def test_fuel_trim_guidance_follows_sequential_fuel_availability() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="injLayout",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Paired"),
                    FieldOptionDefinition("3", "Sequential"),
                ),
            ),
            ScalarParameterDefinition(name="nCylinders", data_type="U08"),
            ScalarParameterDefinition(name="nFuelChannels", data_type="U08"),
            ScalarParameterDefinition(name="fuelTrimEnabled", data_type="U08"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="injLayout", value=0.0),
                TuneValue(name="nCylinders", value=4.0),
                TuneValue(name="nFuelChannels", value=4.0),
                TuneValue(name="fuelTrimEnabled", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    assert "true sequential" in wizard._fuel_trim_summary_label.text().lower()

    wizard._injlayout_combo.setCurrentIndex(1)
    app.processEvents()

    assert "currently disabled" in wizard._fuel_trim_summary_label.text().lower()
    wizard._fuel_trim_enabled_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    staged = wizard._presenter.local_tune_edit_service.get_value("fuelTrimEnabled")
    assert staged is not None
    assert staged.value == 1.0


def test_definition_backed_engine_and_trim_combos_stage_sparse_enum_values() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="twoStroke", data_type="U08"),
            ScalarParameterDefinition(
                name="injLayout",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Paired"),
                    FieldOptionDefinition("4", "Semi-Sequential"),
                    FieldOptionDefinition("9", "Sequential"),
                ),
            ),
            ScalarParameterDefinition(
                name="boostEnabled",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("6", "On"),
                ),
            ),
            ScalarParameterDefinition(name="nCylinders", data_type="U08"),
            ScalarParameterDefinition(name="nFuelChannels", data_type="U08"),
            ScalarParameterDefinition(
                name="fuelTrimEnabled",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("5", "Enabled"),
                ),
            ),
            ScalarParameterDefinition(
                name="sparkMode",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Wasted Spark"),),
            ),
            ScalarParameterDefinition(
                name="camInput",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Off"),),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="twoStroke", value=0.0),
                TuneValue(name="injLayout", value=0.0),
                TuneValue(name="boostEnabled", value=0.0),
                TuneValue(name="nCylinders", value=4.0),
                TuneValue(name="nFuelChannels", value=4.0),
                TuneValue(name="fuelTrimEnabled", value=0.0),
                TuneValue(name="sparkMode", value=0.0),
                TuneValue(name="camInput", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(1)
    app.processEvents()

    wizard._stroke_combo.setCurrentIndex(1)
    wizard._injlayout_combo.setCurrentIndex(2)
    wizard._boost_enabled_combo.setCurrentIndex(1)
    app.processEvents()

    assert wizard._fuel_trim_enabled_combo.itemText(1) == "Enabled"
    wizard._fuel_trim_enabled_combo.setCurrentIndex(1)
    app.processEvents()

    wizard._apply_button.click()
    app.processEvents()

    two_stroke = wizard._presenter.local_tune_edit_service.get_value("twoStroke")
    inj_layout = wizard._presenter.local_tune_edit_service.get_value("injLayout")
    boost_enabled = wizard._presenter.local_tune_edit_service.get_value("boostEnabled")
    fuel_trim = wizard._presenter.local_tune_edit_service.get_value("fuelTrimEnabled")
    assert two_stroke is not None
    assert inj_layout is not None
    assert boost_enabled is not None
    assert fuel_trim is not None
    assert two_stroke.value == 1.0
    assert inj_layout.value == 9.0
    assert boost_enabled.value == 6.0
    assert fuel_trim.value == 5.0


def test_injector_preset_loads_wizard_draft_before_apply() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injOpen", data_type="F32"),
            ScalarParameterDefinition(name="injflow", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    _select_combo_item_by_text(wizard._injector_preset_combo, "Injector Dynamics ID1050x / XDS")
    wizard._injector_preset_btn.click()
    app.processEvents()

    assert wizard._inj_open_spin.value() == pytest.approx(0.925, abs=0.001)
    assert "1065" in wizard._injector_preset_note.text()
    assert wizard._presenter.local_tune_edit_service.get_value("injOpen") is None
    assert wizard._presenter.local_tune_edit_service.get_value("injflow") is None

    wizard._apply_button.click()
    app.processEvents()

    inj_open = wizard._presenter.local_tune_edit_service.get_value("injOpen")
    inj_flow = wizard._presenter.local_tune_edit_service.get_value("injflow")
    context = wizard._presenter.operator_engine_context_service.get()
    assert inj_open is not None
    assert inj_flow is not None
    assert inj_open.value == pytest.approx(0.925, abs=0.001)
    assert inj_flow.value == pytest.approx(1065.0, abs=0.01)
    assert context.injector_preset_key == "id1050x_xds"
    assert context.base_fuel_pressure_psi == pytest.approx(43.5, abs=0.01)


def test_injector_preset_scales_flow_for_base_pressure() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injOpen", data_type="F32"),
            ScalarParameterDefinition(name="injflow", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    wizard._injector_base_pressure_spin.setValue(58.0)
    _select_combo_item_by_text(wizard._injector_preset_combo, "Injector Dynamics ID1050x / XDS")
    wizard._injector_preset_btn.click()
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    inj_flow = wizard._presenter.local_tune_edit_service.get_value("injflow")
    context = wizard._presenter.operator_engine_context_service.get()
    assert inj_flow is not None
    assert inj_flow.value == pytest.approx(1229.756, abs=0.01)
    assert "58.0 psi" in wizard._injector_preset_note.text()
    assert context.base_fuel_pressure_psi == pytest.approx(58.0, abs=0.01)


def test_injector_preset_combo_includes_bosch_ev14_52lb_entry() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile())

    wizard.show()
    app.processEvents()

    labels = {
        wizard._injector_preset_combo.itemText(index)
        for index in range(wizard._injector_preset_combo.count())
    }

    assert "Bosch EV14 52 lb/hr (0280158117)" in labels


def test_bosch_ev14_0280158117_preset_uses_pressure_compensated_dead_time() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injOpen", data_type="F32"),
            ScalarParameterDefinition(name="injflow", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(), definition=definition)

    wizard.show()
    app.processEvents()

    _select_combo_item_by_text(wizard._injector_preset_combo, "Bosch EV14 52 lb/hr (0280158117)")
    wizard._injector_preset_btn.click()
    app.processEvents()

    assert wizard._inj_open_spin.value() == pytest.approx(0.893, abs=0.002)
    assert "pressure-compensated dead time" in wizard._injector_preset_note.text()


def test_bosch_ev14_0280158117_preset_stages_speeduino_voltage_curve_when_available() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injOpen", data_type="F32"),
            ScalarParameterDefinition(name="injflow", data_type="F32"),
        ],
    )
    tune = TuneFile(
        constants=[
            TuneValue(name="injOpen", value=0.9, units="ms"),
            TuneValue(name="injflow", value=500.0, units="cc/min"),
            TuneValue(name="brvBins", value=[8.0, 10.0, 12.0, 13.0, 14.0, 15.0], units="V"),
            TuneValue(name="injBatRates", value=[100.0, 100.0, 100.0, 100.0, 100.0, 100.0], units="%"),
        ]
    )
    wizard = _wizard_with_tune(tune, definition=definition)

    wizard.show()
    app.processEvents()

    _select_combo_item_by_text(wizard._injector_preset_combo, "Bosch EV14 52 lb/hr (0280158117)")
    wizard._injector_preset_btn.click()
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    correction = wizard._presenter.local_tune_edit_service.get_value("injBatRates")
    assert correction is not None
    assert correction.value == pytest.approx([276.806, 181.876, 131.939, 114.956, 100.0, 88.593], abs=0.01)


def test_ignition_preset_loads_wizard_draft_before_apply() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="dwellrun", data_type="F32"),
            ScalarParameterDefinition(name="dwellcrank", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    _select_combo_item_by_text(wizard._ignition_preset_combo, "GM LS Coil PN 19005218")
    wizard._ignition_preset_btn.click()
    app.processEvents()

    assert wizard._dwell_run_spin.value() == pytest.approx(4.5, abs=0.01)
    assert wizard._dwell_crank_spin.value() == pytest.approx(4.5, abs=0.01)
    assert "19005218" in wizard._ignition_preset_note.text()
    assert wizard._presenter.local_tune_edit_service.get_value("dwellrun") is None
    assert wizard._presenter.local_tune_edit_service.get_value("dwellcrank") is None

    wizard._apply_button.click()
    app.processEvents()

    dwell_run = wizard._presenter.local_tune_edit_service.get_value("dwellrun")
    dwell_crank = wizard._presenter.local_tune_edit_service.get_value("dwellcrank")
    context = wizard._presenter.operator_engine_context_service.get()
    assert dwell_run is not None
    assert dwell_crank is not None
    assert dwell_run.value == pytest.approx(4.5, abs=0.01)
    assert dwell_crank.value == pytest.approx(4.5, abs=0.01)
    assert context.ignition_preset_key == "gm_ls_19005218"
    assert "[Official]" in wizard._ignition_preset_summary.text()


def test_wideband_calibration_visibility_follows_ego_type_and_stages_value() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("2", "Wide Band"),
                ),
            ),
            ScalarParameterDefinition(name="afrCal", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="egoType", value=0.0),
                TuneValue(name="afrCal", value=14.7),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _assert_row_hidden(wizard._o2_form, wizard._wideband_cal_spin)

    wizard._ego_type_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._o2_form, wizard._wideband_cal_spin)
    wizard._wideband_cal_spin.setValue(13.2)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    staged = wizard._presenter.local_tune_edit_service.get_value("afrCal")
    assert staged is not None
    assert staged.value == 13.2


def test_wideband_without_calibration_parameter_shows_guidance_note() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("2", "Wide Band"),
                ),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="egoType", value=0.0)]),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _assert_row_hidden(wizard._o2_form, wizard._wideband_cal_note)

    wizard._ego_type_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._o2_form, wizard._wideband_cal_note)


def test_wideband_reference_table_visibility_replaces_missing_scalar_warning() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("2", "Wide Band"),
                ),
            ),
        ],
        reference_tables=[
            ReferenceTableDefinition(
                table_id="std_ms2geno2",
                label="Calibrate AFR Table...",
                solutions=[
                    ReferenceTableSolution(label="AEM Linear AEM-30-42xx", expression="{ 9.72 + (adcValue * 0.0096665) }"),
                    ReferenceTableSolution(label="Innovate LC-1 / LC-2 Default", expression="{ 7.35 + (adcValue * 0.01470186 ) }"),
                ],
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="egoType", value=0.0)]),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    wizard._ego_type_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._o2_form, wizard._wideband_ref_group)
    assert wizard._wideband_ref_combo.count() == 2
    assert "Calibrate AFR Table" in wizard._wideband_ref_note.text()
    assert "no calibration parameter or AFR calibration table" not in wizard._sensor_risk_label.text()


def test_wideband_controller_preset_matches_definition_reference_table() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("2", "Wide Band"),
                ),
            ),
        ],
        reference_tables=[
            ReferenceTableDefinition(
                table_id="std_ms2geno2",
                label="Calibrate AFR Table...",
                solutions=[
                    ReferenceTableSolution(label="14point7 Spartan 2", expression="{ 10 + (adcValue * 0.009765625 * 2) }"),
                    ReferenceTableSolution(label="AEM Linear AEM-30-42xx", expression="{ 9.72 + (adcValue * 0.0096665) }"),
                    ReferenceTableSolution(label="Innovate LC-1 / LC-2 Default", expression="{ 7.35 + (adcValue * 0.01470186 ) }"),
                ],
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="egoType", value=0.0)]),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    wizard._ego_type_combo.setCurrentIndex(1)
    _select_combo_item_by_text(wizard._wideband_preset_combo, "AEM UEGO X-Series")
    app.processEvents()

    assert wizard._wideband_ref_combo.currentText() == "AEM Linear AEM-30-42xx"
    assert "matches AEM UEGO X-Series" in wizard._wideband_ref_note.text()

    wizard._apply_button.click()
    app.processEvents()

    context = wizard._presenter.operator_engine_context_service.get()
    assert context.wideband_preset_key == "aem_x_series"
    assert context.wideband_reference_table_label == "AEM Linear AEM-30-42xx"


def test_wideband_reference_selection_persists_manual_mismatch_and_surfaces_review_warning() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("2", "Wide Band"),
                ),
            ),
        ],
        reference_tables=[
            ReferenceTableDefinition(
                table_id="std_ms2geno2",
                label="Calibrate AFR Table...",
                solutions=[
                    ReferenceTableSolution(label="14point7 Spartan 2", expression="{ 10 + (adcValue * 0.009765625 * 2) }"),
                    ReferenceTableSolution(label="AEM Linear AEM-30-42xx", expression="{ 9.72 + (adcValue * 0.0096665) }"),
                    ReferenceTableSolution(label="Innovate LC-1 / LC-2 Default", expression="{ 7.35 + (adcValue * 0.01470186 ) }"),
                ],
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="egoType", value=0.0)]),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    wizard._ego_type_combo.setCurrentIndex(1)
    _select_combo_item_by_text(wizard._wideband_preset_combo, "AEM UEGO X-Series")
    _select_combo_item_by_text(wizard._wideband_ref_combo, "Innovate LC-1 / LC-2 Default")
    app.processEvents()

    assert "best matches 'AEM Linear AEM-30-42xx'" in wizard._wideband_ref_note.text()
    assert "AFR ref: Innovate LC-1 / LC-2 Default" in wizard._sensor_summary_label.text()
    assert "suggests 'AEM Linear AEM-30-42xx'" in wizard._sensor_risk_label.text()
    assert "Align AFR calibration preset with controller" in wizard._sensor_checklist_label.text()

    wizard._apply_button.click()
    app.processEvents()

    context = wizard._presenter.operator_engine_context_service.get()
    assert context.wideband_preset_key == "aem_x_series"
    assert context.wideband_reference_table_label == "Innovate LC-1 / LC-2 Default"


def test_map_sensor_preset_loads_draft_values_before_apply() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="mapMin", data_type="F32"),
            ScalarParameterDefinition(name="mapMax", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _select_combo_item_by_text(wizard._map_preset_combo, "Bosch MAP 20-300 kPa (0261230119)")
    wizard._map_preset_button.click()
    app.processEvents()

    assert wizard._map_min_spin.value() == pytest.approx(20.0, abs=0.01)
    assert wizard._map_max_spin.value() == pytest.approx(300.0, abs=0.01)
    assert wizard._presenter.local_tune_edit_service.get_value("mapMin") is None
    assert wizard._presenter.local_tune_edit_service.get_value("mapMax") is None

    wizard._apply_button.click()
    app.processEvents()

    map_min = wizard._presenter.local_tune_edit_service.get_value("mapMin")
    map_max = wizard._presenter.local_tune_edit_service.get_value("mapMax")
    assert map_min is not None
    assert map_max is not None
    assert map_min.value == pytest.approx(20.0, abs=0.01)
    assert map_max.value == pytest.approx(300.0, abs=0.01)


def test_oil_pressure_preset_enables_sensor_and_loads_defaults() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="oilPressureEnable", data_type="U08"),
            ScalarParameterDefinition(name="oilPressurePin", data_type="U08"),
            ScalarParameterDefinition(name="oilPressureMin", data_type="F32"),
            ScalarParameterDefinition(name="oilPressureMax", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _select_combo_item_by_text(wizard._oil_preset_combo, "Bosch PT Liquid 0-10 bar (0261230340)")
    wizard._oil_preset_button.click()
    app.processEvents()

    assert wizard._oil_pressure_enable_combo.currentIndex() == 1
    assert wizard._oil_min_spin.value() == pytest.approx(0.0, abs=0.01)
    assert wizard._oil_max_spin.value() == pytest.approx(10.0, abs=0.01)

    wizard._apply_button.click()
    app.processEvents()

    enabled = wizard._presenter.local_tune_edit_service.get_value("oilPressureEnable")
    oil_min = wizard._presenter.local_tune_edit_service.get_value("oilPressureMin")
    oil_max = wizard._presenter.local_tune_edit_service.get_value("oilPressureMax")
    assert enabled is not None
    assert oil_min is not None
    assert oil_max is not None
    assert enabled.value == 1.0
    assert oil_min.value == pytest.approx(0.0, abs=0.01)
    assert oil_max.value == pytest.approx(10.0, abs=0.01)


def test_baro_pressure_preset_enables_sensor_and_loads_defaults() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="useExtBaro", data_type="U08"),
            ScalarParameterDefinition(name="baroPin", data_type="U08"),
            ScalarParameterDefinition(name="baroMin", data_type="F32"),
            ScalarParameterDefinition(name="baroMax", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _select_combo_item_by_text(wizard._baro_preset_combo, "Bosch MAP 20-300 kPa (0261230119)")
    wizard._baro_preset_button.click()
    app.processEvents()

    assert wizard._baro_enable_combo.currentIndex() == 1
    assert wizard._baro_min_spin.value() == pytest.approx(20.0, abs=0.01)
    assert wizard._baro_max_spin.value() == pytest.approx(300.0, abs=0.01)

    wizard._apply_button.click()
    app.processEvents()

    enabled = wizard._presenter.local_tune_edit_service.get_value("useExtBaro")
    baro_min = wizard._presenter.local_tune_edit_service.get_value("baroMin")
    baro_max = wizard._presenter.local_tune_edit_service.get_value("baroMax")
    assert enabled is not None
    assert baro_min is not None
    assert baro_max is not None
    assert enabled.value == 1.0
    assert baro_min.value == pytest.approx(20.0, abs=0.01)
    assert baro_max.value == pytest.approx(300.0, abs=0.01)


def test_dropbear_map_card_preset_loads_map_sensor_defaults() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="mapMin", data_type="F32"),
            ScalarParameterDefinition(name="mapMax", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _select_combo_item_by_text(wizard._map_preset_combo, "NXP MAP 20-250 kPa (MPXH6250A / DropBear MAP Card)")
    wizard._map_preset_button.click()
    app.processEvents()

    assert wizard._map_min_spin.value() == pytest.approx(20.0, abs=0.01)
    assert wizard._map_max_spin.value() == pytest.approx(250.0, abs=0.01)
    assert "matches NXP MAP 20-250 kPa" in wizard._map_preset_summary.text()


def test_dropbear_baro_preset_loads_external_baro_defaults() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="useExtBaro", data_type="U08"),
            ScalarParameterDefinition(name="baroPin", data_type="U08"),
            ScalarParameterDefinition(name="baroMin", data_type="F32"),
            ScalarParameterDefinition(name="baroMax", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _select_combo_item_by_text(wizard._baro_preset_combo, "NXP Baro 10-121 kPa (MPX4115 / KP234)")
    wizard._baro_preset_button.click()
    app.processEvents()

    assert wizard._baro_enable_combo.currentIndex() == 1
    assert wizard._baro_min_spin.value() == pytest.approx(10.0, abs=0.01)
    assert wizard._baro_max_spin.value() == pytest.approx(121.0, abs=0.01)
    assert "matches NXP Baro 10-121 kPa" in wizard._baro_preset_summary.text()


def test_external_baro_nonstandard_range_surfaces_guidance_and_risk() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="useExtBaro", data_type="U08"),
            ScalarParameterDefinition(name="baroMin", data_type="F32"),
            ScalarParameterDefinition(name="baroMax", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="useExtBaro", value=1.0),
                TuneValue(name="baroMin", value=20.0),
                TuneValue(name="baroMax", value=250.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    assert "matches bmw tmap 20-250 kpa" in wizard._baro_preset_summary.text().lower()
    assert "atmospheric pressure" in wizard._sensor_risk_label.text().lower()


def test_turbo_preset_loads_induction_context_draft_and_applies() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=EcuDefinition(name="Speeduino"))

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    twin_index = next(
        i
        for i in range(wizard._topology_combo.count())
        if wizard._topology_combo.itemData(i) == ForcedInductionTopology.TWIN_TURBO_IDENTICAL
    )
    wizard._topology_combo.setCurrentIndex(twin_index)
    _select_combo_item_by_text(wizard._turbo_preset_combo, "Maxpeedingrods GT2871")
    wizard._turbo_preset_button.click()
    app.processEvents()

    assert wizard._apply_button.isEnabled() is True
    assert "gt2871" in wizard._turbo_preset_note.text().lower()
    assert wizard._induction_form.isRowVisible(wizard._compressor_flow_spin) is True
    assert wizard._compressor_flow_spin.value() == pytest.approx(35.0, abs=0.01)
    assert wizard._compressor_inducer_spin.value() == pytest.approx(49.2, abs=0.01)
    assert wizard._compressor_exducer_spin.value() == pytest.approx(71.0, abs=0.01)
    assert wizard._compressor_ar_spin.value() == pytest.approx(0.64, abs=0.01)

    wizard._apply_button.click()
    app.processEvents()

    ctx = wizard._presenter.operator_engine_context_service.get()
    assert ctx.forced_induction_topology == ForcedInductionTopology.TWIN_TURBO_IDENTICAL
    assert ctx.turbo_preset_key == "maxpeedingrods_gt2871"
    assert ctx.compressor_corrected_flow_lbmin == 35.0
    assert ctx.compressor_inducer_mm == 49.2
    assert ctx.compressor_exducer_mm == 71.0
    assert ctx.compressor_ar == 0.64


def test_thermistor_preset_groups_include_ms4x_sensor_options() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    clt_combo = wizard._clt_cal_widgets["preset_combo"]
    iat_combo = wizard._iat_cal_widgets["preset_combo"]

    clt_labels = {clt_combo.itemText(i) for i in range(clt_combo.count())}
    iat_labels = {iat_combo.itemText(i) for i in range(iat_combo.count())}

    assert "BMW M52 / M52TU / M54 CLT" in clt_labels
    assert "BMW M52 / M52TU / M54 CLT" not in iat_labels
    assert "BMW M52 / M52TU / M54 IAT" in iat_labels
    assert "BMW M52 / M52TU / M54 IAT" not in clt_labels
    assert "Bosch 4 Bar TMAP IAT" in iat_labels
    assert "Bosch 4 Bar TMAP IAT" not in clt_labels

    _select_combo_item_by_text(clt_combo, "BMW M52 / M52TU / M54 CLT")
    app.processEvents()
    assert "MS4X" in wizard._clt_cal_widgets["source_label"].text()

    _select_combo_item_by_text(iat_combo, "Bosch 4 Bar TMAP IAT")
    app.processEvents()
    assert "[Trusted Secondary]" in wizard._iat_cal_widgets["source_label"].text()
    assert "MS4X" in wizard._iat_cal_widgets["source_label"].text()

    _select_combo_item_by_text(iat_combo, "Custom")
    app.processEvents()
    assert "Custom curve" in wizard._iat_cal_widgets["source_label"].text()


def test_afr_protection_visibility_follows_wideband_and_mode() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("2", "Wide Band"),
                ),
            ),
            ScalarParameterDefinition(
                name="engineProtectType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Spark Only"),
                    FieldOptionDefinition("2", "Fuel Only"),
                    FieldOptionDefinition("3", "Both"),
                ),
            ),
            ScalarParameterDefinition(
                name="afrProtectEnabled",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Fixed mode"),
                    FieldOptionDefinition("2", "Table mode"),
                ),
            ),
            ScalarParameterDefinition(name="engineProtectMaxRPM", data_type="F32"),
            ScalarParameterDefinition(name="afrProtectMAP", data_type="F32"),
            ScalarParameterDefinition(name="afrProtectRPM", data_type="F32"),
            ScalarParameterDefinition(name="afrProtectTPS", data_type="F32"),
            ScalarParameterDefinition(name="afrProtectDeviation", data_type="F32"),
            ScalarParameterDefinition(name="afrProtectCutTime", data_type="F32"),
            ScalarParameterDefinition(name="afrProtectReactivationTPS", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="egoType", value=0.0), TuneValue(name="afrProtectEnabled", value=0.0)]),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    _assert_row_hidden(wizard._afr_protect_form, wizard._afr_protect_mode_combo)
    _assert_row_hidden(wizard._afr_protect_form, wizard._afr_protect_map_spin)

    wizard._ego_type_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._afr_protect_form, wizard._afr_protect_mode_combo)
    _assert_row_hidden(wizard._afr_protect_form, wizard._afr_protect_map_spin)

    wizard._afr_protect_mode_combo.setCurrentIndex(1)
    app.processEvents()

    _assert_row_visible(wizard._afr_protect_form, wizard._afr_protect_map_spin)
    _assert_row_visible(wizard._afr_protect_form, wizard._afr_protect_cut_time_spin)


def test_definition_backed_sensor_combos_stage_stored_enum_values() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("5", "Wide Band"),
                ),
            ),
            ScalarParameterDefinition(
                name="engineProtectType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("4", "Spark Only"),
                    FieldOptionDefinition("7", "Fuel Only"),
                ),
            ),
            ScalarParameterDefinition(
                name="afrProtectEnabled",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("3", "Fixed mode"),
                    FieldOptionDefinition("6", "Table mode"),
                ),
            ),
            ScalarParameterDefinition(
                name="mapSample",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Instantaneous"),
                    FieldOptionDefinition("4", "Cycle Average"),
                    FieldOptionDefinition("9", "Event Average"),
                ),
            ),
            ScalarParameterDefinition(
                name="knock_mode",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("5", "Digital"),
                    FieldOptionDefinition("8", "Analog"),
                ),
            ),
            ScalarParameterDefinition(
                name="knock_digital_pin",
                data_type="U08",
                options=(FieldOptionDefinition("34", "GPIO34"),),
            ),
            ScalarParameterDefinition(
                name="knock_analog_pin",
                data_type="U08",
                options=(FieldOptionDefinition("48", "ADC48"),),
            ),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="egoType", value=0.0),
                TuneValue(name="engineProtectType", value=0.0),
                TuneValue(name="afrProtectEnabled", value=0.0),
                TuneValue(name="mapSample", value=0.0),
                TuneValue(name="knock_mode", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    wizard._ego_type_combo.setCurrentIndex(1)
    wizard._engine_protect_type_combo.setCurrentIndex(2)
    wizard._afr_protect_mode_combo.setCurrentIndex(1)
    wizard._map_sample_combo.setCurrentIndex(2)
    wizard._knock_mode_combo.setCurrentIndex(2)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    engine_protect = wizard._presenter.local_tune_edit_service.get_value("engineProtectType")
    afr_protect = wizard._presenter.local_tune_edit_service.get_value("afrProtectEnabled")
    map_sample = wizard._presenter.local_tune_edit_service.get_value("mapSample")
    knock_mode = wizard._presenter.local_tune_edit_service.get_value("knock_mode")
    assert engine_protect is not None
    assert afr_protect is not None
    assert map_sample is not None
    assert knock_mode is not None
    assert engine_protect.value == 7.0
    assert afr_protect.value == 3.0
    assert map_sample.value == 9.0
    assert knock_mode.value == 8.0


def test_sensor_tab_surfaces_afr_protection_risks_and_checklist() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("2", "Wide Band"),
                ),
            ),
            ScalarParameterDefinition(
                name="engineProtectType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Spark Only"),
                ),
            ),
            ScalarParameterDefinition(
                name="afrProtectEnabled",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Fixed mode"),
                ),
            ),
            ScalarParameterDefinition(name="engineProtectMaxRPM", data_type="F32"),
            ScalarParameterDefinition(name="afrProtectCutTime", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="egoType", value=2.0),
                TuneValue(name="engineProtectType", value=0.0),
                TuneValue(name="afrProtectEnabled", value=1.0),
                TuneValue(name="engineProtectMaxRPM", value=0.0),
                TuneValue(name="afrProtectCutTime", value=0.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    summary = wizard._sensor_summary_label.text()
    risks = wizard._sensor_risk_label.text()
    checklist = wizard._sensor_checklist_label.text()

    assert "AFR protection: Fixed mode" in summary
    assert "engine protection cut is still off" in risks
    assert "protection RPM limit" in risks
    assert "Enable engine protection cut for AFR protection" in checklist


def test_sensor_tab_shows_summary_and_known_risks() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("2", "Wide Band"),
                ),
            ),
            ScalarParameterDefinition(name="stoich", data_type="F32"),
            ScalarParameterDefinition(name="tpsMin", data_type="U16"),
            ScalarParameterDefinition(name="tpsMax", data_type="U16"),
            ScalarParameterDefinition(name="mapMin", data_type="F32"),
            ScalarParameterDefinition(name="mapMax", data_type="F32"),
            ScalarParameterDefinition(name="flexEnabled", data_type="U08"),
            ScalarParameterDefinition(name="flexFreqLow", data_type="F32"),
            ScalarParameterDefinition(name="flexFreqHigh", data_type="F32"),
            ScalarParameterDefinition(
                name="knock_mode",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Digital"),
                ),
            ),
            ScalarParameterDefinition(name="knock_digital_pin", data_type="U08"),
            ScalarParameterDefinition(name="oilPressureEnable", data_type="U08"),
            ScalarParameterDefinition(name="oilPressureMin", data_type="F32"),
            ScalarParameterDefinition(name="oilPressureMax", data_type="F32"),
            ScalarParameterDefinition(name="useExtBaro", data_type="U08"),
            ScalarParameterDefinition(name="baroMin", data_type="F32"),
            ScalarParameterDefinition(name="baroMax", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="egoType", value=2.0),
                TuneValue(name="stoich", value=14.7),
                TuneValue(name="tpsMin", value=300.0),
                TuneValue(name="tpsMax", value=200.0),
                TuneValue(name="mapMin", value=250.0),
                TuneValue(name="mapMax", value=100.0),
                TuneValue(name="flexEnabled", value=1.0),
                TuneValue(name="flexFreqLow", value=150.0),
                TuneValue(name="flexFreqHigh", value=50.0),
                TuneValue(name="knock_mode", value=1.0),
                TuneValue(name="knock_digital_pin", value=0.0),
                TuneValue(name="oilPressureEnable", value=1.0),
                TuneValue(name="oilPressureMin", value=5.0),
                TuneValue(name="oilPressureMax", value=2.0),
                TuneValue(name="useExtBaro", value=1.0),
                TuneValue(name="baroMin", value=120.0),
                TuneValue(name="baroMax", value=80.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    summary = wizard._sensor_summary_label.text()
    risks = wizard._sensor_risk_label.text()
    assert "O2: Wide Band" in summary
    assert "MAP range: 250-100 kPa" in summary
    assert "Flex fuel: enabled" in summary
    assert "Known risks:" in risks
    assert "Wideband is enabled but no calibration parameter or AFR calibration table is exposed" in risks
    assert "Flex fuel high frequency must be greater" in risks
    assert "TPS max must be greater than TPS min" in risks
    assert "MAP 5 V pressure must be greater" in risks
    assert "Oil-pressure 5 V calibration must be greater" in risks
    assert "External-baro 5 V calibration must be greater" in risks
    checklist = wizard._sensor_checklist_label.text()
    assert "Wideband calibration parameter not in definition" in checklist
    assert "Flex sensor calibration invalid" in checklist


def test_sensor_tab_shows_clear_safe_message_when_config_is_plausible() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Disabled"),),
            ),
            ScalarParameterDefinition(name="stoich", data_type="F32"),
            ScalarParameterDefinition(name="tpsMin", data_type="U16"),
            ScalarParameterDefinition(name="tpsMax", data_type="U16"),
            ScalarParameterDefinition(name="mapMin", data_type="F32"),
            ScalarParameterDefinition(name="mapMax", data_type="F32"),
            ScalarParameterDefinition(name="flexEnabled", data_type="U08"),
            ScalarParameterDefinition(name="flexFreqLow", data_type="F32"),
            ScalarParameterDefinition(name="flexFreqHigh", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="egoType", value=0.0),
                TuneValue(name="stoich", value=14.7),
                TuneValue(name="tpsMin", value=100.0),
                TuneValue(name="tpsMax", value=900.0),
                TuneValue(name="mapMin", value=20.0),
                TuneValue(name="mapMax", value=300.0),
                TuneValue(name="flexEnabled", value=1.0),
                TuneValue(name="flexFreqLow", value=50.0),
                TuneValue(name="flexFreqHigh", value=150.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    assert "No immediate sensor-configuration risks detected." in wizard._sensor_risk_label.text()
    checklist = wizard._sensor_checklist_label.text()
    assert "Flex fuel: enabled" in wizard._sensor_summary_label.text()
    assert "Flex sensor calibration OK" in checklist


def test_engine_tab_updates_operator_context_fields() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="nCylinders", value=4.0)]),
        definition=EcuDefinition(
            name="Speeduino",
            scalars=[ScalarParameterDefinition(name="nCylinders", data_type="U08")],
        ),
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(1)
    app.processEvents()

    wizard._displacement_edit.setValue(1998.0)
    wizard._compression_edit.setValue(9.5)
    wizard._cam_duration_spin.setValue(228.0)
    wizard._intent_combo.setCurrentIndex(1)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    context = wizard._presenter.operator_engine_context_service.get()
    assert context.displacement_cc == 1998.0
    assert context.compression_ratio == 9.5
    assert context.cam_duration_deg == 228.0
    assert context.calibration_intent == "drivable_base"


def test_engine_tab_hides_advanced_cam_duration_until_enabled() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(1)
    app.processEvents()

    _assert_row_hidden(wizard._engine_form, wizard._cam_duration_spin)
    _assert_row_hidden(wizard._engine_form, wizard._head_flow_combo)
    _assert_row_hidden(wizard._engine_form, wizard._manifold_style_combo)

    wizard._engine_advanced_check.setChecked(True)
    app.processEvents()

    _assert_row_visible(wizard._engine_form, wizard._cam_duration_spin)
    _assert_row_visible(wizard._engine_form, wizard._head_flow_combo)
    _assert_row_visible(wizard._engine_form, wizard._manifold_style_combo)


def test_injector_tab_shows_pressure_model_and_hides_pressure_until_needed() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    assert wizard._injector_pressure_row.isVisible() is False
    assert wizard._injector_pressure_model_row.isVisible() is True
    assert wizard._injector_characterization_row.isVisible() is False

    wizard._injector_advanced_check.setChecked(True)
    app.processEvents()

    assert wizard._injector_pressure_model_row.isVisible() is True
    assert wizard._injector_characterization_row.isVisible() is True

    wizard._injector_pressure_model_combo.setCurrentIndex(
        wizard._injector_pressure_model_combo.findData("vacuum_referenced")
    )
    app.processEvents()

    assert wizard._injector_pressure_row.isVisible() is True


def test_engine_tab_applies_additional_tier2_context_fields() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(1)
    app.processEvents()

    wizard._engine_advanced_check.setChecked(True)
    app.processEvents()

    wizard._head_flow_combo.setCurrentIndex(wizard._head_flow_combo.findData("mild_ported"))
    wizard._manifold_style_combo.setCurrentIndex(wizard._manifold_style_combo.findData("itb"))
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    context = wizard._presenter.operator_engine_context_service.get()
    assert context.head_flow_class == "mild_ported"
    assert context.intake_manifold_style == "itb"


def test_injector_tab_applies_injector_characterization_context_field() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    wizard._injector_advanced_check.setChecked(True)
    app.processEvents()

    wizard._injector_characterization_combo.setCurrentIndex(
        wizard._injector_characterization_combo.findData("full_characterization")
    )
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    context = wizard._presenter.operator_engine_context_service.get()
    assert context.injector_characterization == "full_characterization"


def test_injector_tab_applies_pressure_model_context_fields() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    wizard._injector_advanced_check.setChecked(True)
    app.processEvents()

    wizard._injector_pressure_model_combo.setCurrentIndex(
        wizard._injector_pressure_model_combo.findData("vacuum_referenced")
    )
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    context = wizard._presenter.operator_engine_context_service.get()
    assert context.injector_pressure_model == "vacuum_referenced"


def test_induction_tab_applies_supercharger_type_for_supported_topologies() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    wizard._topology_combo.setCurrentIndex(
        wizard._topology_combo.findData(ForcedInductionTopology.SINGLE_SUPERCHARGER)
    )
    wizard._supercharger_type_combo.setCurrentIndex(
        wizard._supercharger_type_combo.findData(SuperchargerType.CENTRIFUGAL)
    )
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    context = wizard._presenter.operator_engine_context_service.get()
    assert context.supercharger_type == SuperchargerType.CENTRIFUGAL


def test_injector_preset_surfaces_characterization_readiness_note() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    _select_combo_item_by_text(wizard._injector_preset_combo, "Bosch EV14 52 lb/hr (0280158117)")
    wizard._refresh_injector_characterization_note()
    app.processEvents()

    assert wizard._injector_characterization_note.isVisible() is True
    assert "full_characterization" in wizard._injector_characterization_note.text()


def test_req_fuel_guidance_mentions_pressure_model_and_secondary_pressure_gap() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="nCylinders", data_type="U08"),
            ScalarParameterDefinition(name="stagedInjSizePri", data_type="F32"),
            ScalarParameterDefinition(name="stagedInjSizeSec", data_type="F32"),
            ScalarParameterDefinition(name="reqFuel", data_type="U08"),
            ScalarParameterDefinition(name="stoich", data_type="F32"),
        ],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="nCylinders", value=6.0),
            TuneValue(name="stagedInjSizePri", value=250.0),
            TuneValue(name="stagedInjSizeSec", value=300.0),
            TuneValue(name="reqFuel", value=0.0),
            TuneValue(name="stoich", value=14.7),
        ]
    )
    wizard = _wizard_with_tune(tune_file, definition=definition)
    wizard._presenter.update_operator_engine_context(
        displacement_cc=2000.0,
        injector_pressure_model="operator_specified",
    )
    wizard.refresh()
    wizard._refresh_req_fuel_guidance()

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    assert "operator-specified pressure" in wizard._req_fuel_result_label.text().lower()
    assert "secondary injectors are configured" in wizard._req_fuel_result_label.text().lower()


def test_req_fuel_guidance_calculates_and_stages_without_active_injector_page() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="nCylinders", data_type="U08"),
            ScalarParameterDefinition(name="injflow", data_type="F32"),
            ScalarParameterDefinition(name="reqFuel", data_type="U08"),
            ScalarParameterDefinition(name="stoich", data_type="F32"),
        ],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="nCylinders", value=6.0),
            TuneValue(name="injflow", value=250.0),
            TuneValue(name="reqFuel", value=0.0),
            TuneValue(name="stoich", value=14.7),
        ]
    )
    wizard = _wizard_with_tune(tune_file, definition=definition)

    wizard.show()
    wizard._tabs.setCurrentIndex(1)
    app.processEvents()
    wizard._displacement_edit.setValue(2000.0)
    app.processEvents()

    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    expected = RequiredFuelCalculatorService().calculate(
        displacement_cc=2000.0,
        cylinder_count=6,
        injector_flow_ccmin=250.0,
        target_afr=14.7,
    )
    assert expected.is_valid is True
    assert wizard._req_fuel_apply_btn.isEnabled() is True
    assert str(expected.req_fuel_stored) in wizard._req_fuel_result_label.text()

    wizard._req_fuel_apply_btn.click()
    app.processEvents()

    staged = wizard._presenter.local_tune_edit_service.get_value("reqFuel")
    assert staged is not None
    assert staged.value == pytest.approx(expected.req_fuel_ms, abs=0.01)


def test_req_fuel_manual_edit_stages_physical_ms_value() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08")],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="reqFuel", value=8.4)]),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    wizard._req_fuel_spin.setValue(10.2)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    staged = wizard._presenter.local_tune_edit_service.get_value("reqFuel")
    assert staged is not None
    assert staged.value == pytest.approx(10.2, abs=0.01)


def test_ve_generator_status_reports_tier1_tier2_and_fallbacks() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=2, page=1, offset=16, units="rpm"),
            TableDefinition(name="loadBins", rows=2, columns=1, page=1, offset=20, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="ve",
                map_id="veMap",
                title="VE Table",
                page=1,
                x_bins="rpmBins",
                y_bins="loadBins",
                z_bins="veTable",
            )
        ],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="veTable", value=[10.0, 20.0, 30.0, 40.0], rows=2, cols=2, units="%"),
            TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
            TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
        ]
    )
    wizard = _wizard_with_tune(tune_file, definition=definition)
    wizard._presenter.update_operator_engine_context(
        displacement_cc=1998.0,
        cylinder_count=4,
        compression_ratio=9.5,
        forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
        boost_target_kpa=180.0,
        cam_duration_deg=228.0,
        compressor_corrected_flow_lbmin=52.0,
        compressor_ar=0.82,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    wizard._on_generate_ve_table()
    app.processEvents()

    status = wizard._ve_status_label.text().lower()
    assert "tier 1" in status
    assert "tier 2" in status
    assert "cam duration" in status
    assert "compressor flow" in status
    assert "conservative fallbacks" in status


def test_startup_generator_status_reports_fallbacks_when_inputs_missing() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="wueBins", rows=1, columns=10, page=1, offset=0),
            TableDefinition(name="wueRates", rows=1, columns=10, page=1, offset=20),
        ],
    )
    wizard = _wizard_with_tune(TuneFile(constants=[]), definition=definition)
    wizard._presenter.update_operator_engine_context(compression_ratio=9.0)

    wizard.show()
    wizard._tabs.setCurrentIndex(3)
    app.processEvents()

    wizard._on_generate_wue()
    app.processEvents()

    status = wizard._wue_status_label.text().lower()
    assert "tier 1 + conservative fallbacks" in status or "conservative defaults" in status
    assert "conservative fallbacks" in status


def test_trigger_tab_surfaces_cross_validation_checklist() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="dwellRun", data_type="F32"),
            ScalarParameterDefinition(name="triggerAngle", data_type="F32"),
            ScalarParameterDefinition(name="numTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="dwellRun", value=0.0),
                TuneValue(name="triggerAngle", value=0.0),
                TuneValue(name="numTeeth", value=12.0),
                TuneValue(name="missingTeeth", value=12.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    checklist = wizard._trigger_checklist_label.text()
    assert "Needed:" in checklist or "needed" in checklist
    assert "Set dwell time" in checklist
    assert "reference angle" in checklist.lower()


def test_trigger_tab_shows_summary_and_known_risks() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="TrigPattern",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Missing Tooth"),),
            ),
            ScalarParameterDefinition(
                name="sparkMode",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Wasted Spark"),
                    FieldOptionDefinition("3", "Sequential"),
                ),
            ),
            ScalarParameterDefinition(
                name="camInput",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Off"),
                    FieldOptionDefinition("1", "Hall Input"),
                ),
            ),
            ScalarParameterDefinition(name="numTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
            ScalarParameterDefinition(name="dwellrun", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="sparkMode", value=3.0),
                TuneValue(name="camInput", value=0.0),
                TuneValue(name="numTeeth", value=12.0),
                TuneValue(name="missingTeeth", value=7.0),
                TuneValue(name="dwellrun", value=7.5),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    summary = wizard._trigger_summary_label.text()
    risks = wizard._trigger_risk_label.text()
    assert "Pattern: Missing Tooth" in summary
    assert "Wheel: 12-7" in summary
    assert "Spark mode: Sequential" in summary
    assert "Fuel mode:" in summary
    assert "Cam sync: Hall Input" in summary or "Cam sync: Off" in summary
    assert "Known risks:" in risks
    assert "Missing-tooth count is unusually large" in risks


def test_trigger_tab_shows_connected_interrupt_capability_warning() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="dwellRun", data_type="F32"),
            ScalarParameterDefinition(name="triggerAngle", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="dwellRun", value=3.0),
                TuneValue(name="triggerAngle", value=20.0),
            ]
        ),
        definition=definition,
    )
    wizard._presenter.set_runtime_snapshot(
        OutputChannelSnapshot(values=[OutputChannelValue(name="boardCapabilities", value=0.0)])
    )
    wizard._refresh_trigger_checklist()

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    checklist = wizard._trigger_checklist_label.text().lower()
    assert "does not advertise unrestricted interrupts" in checklist


def test_trigger_tab_shows_connected_interrupt_capability_ok() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="dwellRun", data_type="F32"),
            ScalarParameterDefinition(name="triggerAngle", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="dwellRun", value=3.0),
                TuneValue(name="triggerAngle", value=20.0),
            ]
        ),
        definition=definition,
    )
    wizard._presenter.set_runtime_snapshot(
        OutputChannelSnapshot(values=[OutputChannelValue(name="boardCapabilities", value=float(1 << 6))])
    )
    wizard._refresh_trigger_checklist()

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    checklist = wizard._trigger_checklist_label.text().lower()
    assert "advertises unrestricted interrupts" in checklist


def test_board_tab_shows_connected_storage_and_transport_capabilities() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))
    wizard._presenter.set_runtime_snapshot(
        OutputChannelSnapshot(
            values=[OutputChannelValue(name="boardCapabilities", value=float((1 << 2) | (1 << 3) | (1 << 7) | (1 << 6))),
                    OutputChannelValue(name="spiFlashHealth", value=1.0)]
        )
    )
    wizard._refresh_board_tab()

    wizard.show()
    wizard._tabs.setCurrentIndex(0)
    app.processEvents()

    note = wizard._board_capability_note.text().lower()
    assert "spi flash healthy" in note
    assert "burned changes should be treated as flash-backed" in note
    assert "native can hardware is available" in note
    assert "wi-fi transport coprocessor" in note
    assert "unrestricted interrupts" in note


def test_board_tab_shows_placeholder_without_connected_runtime() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile(constants=[]))

    wizard.show()
    wizard._tabs.setCurrentIndex(0)
    app.processEvents()

    note = wizard._board_capability_note.text().lower()
    assert "connected board capability data will appear here" in note


def test_sensor_tab_warns_when_can_wideband_selected_without_native_can() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("1", "Narrow Band"),
                    FieldOptionDefinition("2", "Wide Band CAN"),
                ),
            ),
            ScalarParameterDefinition(name="stoich", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="egoType", value=2.0), TuneValue(name="stoich", value=14.7)]),
        definition=definition,
    )
    wizard._presenter.set_runtime_snapshot(
        OutputChannelSnapshot(values=[OutputChannelValue(name="boardCapabilities", value=0.0)])
    )
    wizard._refresh_sensor_tab()

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    assert "does not advertise native can support" in wizard._sensor_risk_label.text().lower()
    assert "does not advertise native can support" in wizard._sensor_checklist_label.text().lower()


def test_sensor_tab_marks_can_wideband_ok_when_native_can_available() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="egoType",
                data_type="U08",
                options=(
                    FieldOptionDefinition("0", "Disabled"),
                    FieldOptionDefinition("1", "Narrow Band"),
                    FieldOptionDefinition("2", "Wide Band CAN"),
                ),
            ),
            ScalarParameterDefinition(name="stoich", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(constants=[TuneValue(name="egoType", value=2.0), TuneValue(name="stoich", value=14.7)]),
        definition=definition,
    )
    wizard._presenter.set_runtime_snapshot(
        OutputChannelSnapshot(values=[OutputChannelValue(name="boardCapabilities", value=float(1 << 2))])
    )
    wizard._refresh_sensor_tab()

    wizard.show()
    wizard._tabs.setCurrentIndex(5)
    app.processEvents()

    assert "native can support" not in wizard._sensor_risk_label.text().lower()
    assert "advertises native can support" in wizard._sensor_checklist_label.text().lower()


def test_trigger_tab_shows_decoder_required_cam_guidance() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="TrigPattern",
                data_type="U08",
                options=(FieldOptionDefinition("1", "Dual Wheel with Cam"),),
            ),
            ScalarParameterDefinition(
                name="sparkMode",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Wasted Spark"),),
            ),
            ScalarParameterDefinition(
                name="camInput",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Off"),),
            ),
            ScalarParameterDefinition(name="numTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=1.0),
                TuneValue(name="sparkMode", value=0.0),
                TuneValue(name="camInput", value=0.0),
                TuneValue(name="numTeeth", value=36.0),
                TuneValue(name="missingTeeth", value=1.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    assert "crank + cam required by the selected decoder" in wizard._trigger_topology_label.text()
    assert "The selected decoder needs a cam/secondary trigger input" in wizard._trigger_risk_label.text()


def test_trigger_tab_shows_clear_safe_message_when_geometry_is_plausible() -> None:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(
                name="TrigPattern",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Missing Tooth"),),
            ),
            ScalarParameterDefinition(
                name="sparkMode",
                data_type="U08",
                options=(FieldOptionDefinition("0", "Wasted Spark"),),
            ),
            ScalarParameterDefinition(name="numTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
            ScalarParameterDefinition(name="dwellrun", data_type="F32"),
        ],
    )
    wizard = _wizard_with_tune(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="sparkMode", value=0.0),
                TuneValue(name="numTeeth", value=36.0),
                TuneValue(name="missingTeeth", value=1.0),
                TuneValue(name="dwellrun", value=3.0),
            ]
        ),
        definition=definition,
    )

    wizard.show()
    wizard._tabs.setCurrentIndex(4)
    app.processEvents()

    assert "No immediate trigger-pattern risks detected." in wizard._trigger_risk_label.text()


def test_induction_tab_hides_boost_and_intercooler_for_na() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile())

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    # NA topology — boost target and intercooler rows should be hidden
    from tuner.domain.generator_context import ForcedInductionTopology
    ctx = wizard._presenter.operator_engine_context_service.get()
    assert ctx.forced_induction_topology == ForcedInductionTopology.NA
    assert wizard._induction_form.isRowVisible(wizard._boost_target_spin) is False
    assert wizard._induction_form.isRowVisible(wizard._intercooler_check) is False


def test_induction_tab_shows_boost_and_intercooler_for_turbo() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile())

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    from tuner.domain.generator_context import ForcedInductionTopology
    # Select single turbo (index 1)
    turbo_index = None
    for i in range(wizard._topology_combo.count()):
        if wizard._topology_combo.itemData(i) == ForcedInductionTopology.SINGLE_TURBO:
            turbo_index = i
            break
    assert turbo_index is not None

    wizard._topology_combo.setCurrentIndex(turbo_index)
    app.processEvents()

    assert wizard._induction_form.isRowVisible(wizard._boost_target_spin) is True
    assert wizard._induction_form.isRowVisible(wizard._intercooler_check) is True


def test_induction_tab_hides_advanced_compressor_fields_until_enabled() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile())

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    assert wizard._induction_form.isRowVisible(wizard._compressor_flow_spin) is False

    turbo_index = next(
        i
        for i in range(wizard._topology_combo.count())
        if wizard._topology_combo.itemData(i) == ForcedInductionTopology.SINGLE_TURBO
    )
    wizard._topology_combo.setCurrentIndex(turbo_index)
    app.processEvents()
    assert wizard._induction_form.isRowVisible(wizard._compressor_flow_spin) is False

    wizard._induction_advanced_check.setChecked(True)
    app.processEvents()

    assert wizard._induction_form.isRowVisible(wizard._compressor_flow_spin) is True
    assert wizard._induction_form.isRowVisible(wizard._compressor_ar_spin) is True


def test_induction_tab_applies_advanced_compressor_context_fields() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile())

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    turbo_index = next(
        i
        for i in range(wizard._topology_combo.count())
        if wizard._topology_combo.itemData(i) == ForcedInductionTopology.SINGLE_TURBO
    )
    wizard._topology_combo.setCurrentIndex(turbo_index)
    wizard._induction_advanced_check.setChecked(True)
    app.processEvents()

    wizard._compressor_flow_spin.setValue(52.0)
    wizard._compressor_pr_spin.setValue(2.2)
    wizard._compressor_inducer_spin.setValue(54.0)
    wizard._compressor_exducer_spin.setValue(71.0)
    wizard._compressor_ar_spin.setValue(0.82)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    ctx = wizard._presenter.operator_engine_context_service.get()
    assert ctx.compressor_corrected_flow_lbmin == 52.0
    assert ctx.compressor_pressure_ratio == 2.2
    assert ctx.compressor_inducer_mm == 54.0
    assert ctx.compressor_exducer_mm == 71.0
    assert ctx.compressor_ar == 0.82


def test_induction_tab_auto_reveals_advanced_compressor_fields_when_context_present() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile())
    wizard._presenter.update_operator_engine_context(
        forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
        compressor_corrected_flow_lbmin=52.0,
        compressor_pressure_ratio=2.2,
    )
    wizard.refresh()

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    assert wizard._induction_advanced_check.isChecked() is True
    assert wizard._induction_form.isRowVisible(wizard._compressor_flow_spin) is True
    assert wizard._compressor_flow_spin.value() == pytest.approx(52.0, abs=0.01)


def test_induction_tab_persists_topology_to_operator_context() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile())

    wizard.show()
    wizard._tabs.setCurrentIndex(2)
    app.processEvents()

    from tuner.domain.generator_context import ForcedInductionTopology
    twin_index = None
    for i in range(wizard._topology_combo.count()):
        if wizard._topology_combo.itemData(i) == ForcedInductionTopology.TWIN_TURBO_IDENTICAL:
            twin_index = i
            break
    assert twin_index is not None

    wizard._topology_combo.setCurrentIndex(twin_index)
    app.processEvents()
    wizard._apply_button.click()
    app.processEvents()

    ctx = wizard._presenter.operator_engine_context_service.get()
    assert ctx.forced_induction_topology == ForcedInductionTopology.TWIN_TURBO_IDENTICAL


def test_wizard_emits_workspace_state_changed_when_applying_pending_changes() -> None:
    app = QApplication.instance() or QApplication([])
    wizard = _wizard_with_tune(TuneFile())
    seen: list[bool] = []
    wizard.workspace_state_changed.connect(lambda: seen.append(True))

    wizard._stage_raw("nCylinders", "4")
    app.processEvents()
    assert not seen
    wizard._apply_button.click()
    app.processEvents()

    assert seen


def _wizard_with_tune(tune_file: TuneFile, *, definition: EcuDefinition | None = None) -> HardwareSetupWizard:
    definition = definition or EcuDefinition(name="Speeduino")
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return HardwareSetupWizard(presenter)


def _select_combo_item_by_text(combo, text: str) -> None:
    for index in range(combo.count()):
        if combo.itemText(index) == text:
            combo.setCurrentIndex(index)
            return
    raise AssertionError(f"Combo item not found: {text}")


def _assert_row_visible(form, field) -> None:
    label = form.labelForField(field)
    assert form.isRowVisible(field) is True
    assert field.isVisible() is True
    if label is not None:
        assert isinstance(label, QLabel)
        assert label.isVisible() is True


def _assert_row_hidden(form, field) -> None:
    label = form.labelForField(field)
    assert form.isRowVisible(field) is False
    assert field.isVisible() is False
    if label is not None:
        assert isinstance(label, QLabel)
        assert label.isVisible() is False
