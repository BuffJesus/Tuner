from __future__ import annotations

from tuner.domain.ecu_definition import (
    DialogDefinition,
    DialogFieldDefinition,
    EcuDefinition,
    MenuDefinition,
    MenuItemDefinition,
    ScalarParameterDefinition,
    TableDefinition,
    TableEditorDefinition,
)
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.tuning_page_service import TuningPageService
from tuner.services.tuning_page_validation_service import TuningPageValidationService


def test_validate_table_page_reports_missing_main_table_and_axis_problems() -> None:
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
    tune_file = TuneFile(constants=[TuneValue(name="rpmBins", value=12.0), TuneValue(name="loadBins", value=[])])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    page = TuningPageService().build_pages(definition)[0].pages[0]

    result = TuningPageValidationService().validate_page(page, edit_service)

    assert "Missing tune value for 'veTable'." in result.errors
    assert "Main table 'veTable' is unavailable." in result.errors
    assert "X axis 'rpmBins' is not list-backed." in result.errors
    assert "Y axis 'loadBins' has no labels." in result.warnings


def test_validate_parameter_page_warns_on_out_of_bounds_staged_value() -> None:
    definition = EcuDefinition(
        name="Test",
        scalars=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, min_value=0.5, max_value=20.0),
        ],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.0)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    edit_service.stage_scalar_value("reqFuel", "25.0")  # above max
    page = TuningPageService().build_pages(definition)[0].pages[0]

    result = TuningPageValidationService().validate_page(page, edit_service)

    assert any("reqFuel" in w and "maximum" in w for w in result.warnings)


def test_validate_parameter_page_warns_on_below_minimum_staged_value() -> None:
    definition = EcuDefinition(
        name="Test",
        scalars=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, min_value=0.5, max_value=20.0),
        ],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.0)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    edit_service.stage_scalar_value("reqFuel", "0.1")  # below min
    page = TuningPageService().build_pages(definition)[0].pages[0]

    result = TuningPageValidationService().validate_page(page, edit_service)

    assert any("reqFuel" in w and "minimum" in w for w in result.warnings)


def test_validate_parameter_page_warns_when_only_fallback_tables_exist() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        tables=[TableDefinition(name="trimTable", rows=2, columns=2, page=7, offset=0, units="%")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="trimTable", value=[1.0, 2.0, 3.0, 4.0], rows=2, cols=2)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    page = TuningPageService().build_pages(definition)[0].pages[0]

    result = TuningPageValidationService().validate_page(page, edit_service)

    assert result.errors == ()
    assert result.warnings == ("This fallback page has only table content and no direct scalar edits.",)


def test_validate_parameter_page_ignores_hidden_knock_pin_fields() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="knock_mode", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="knock_digital_pin", data_type="U08", page=1, offset=1),
            ScalarParameterDefinition(name="knock_analog_pin", data_type="U08", page=1, offset=2),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="knock_setup",
                title="Knock Setup",
                fields=[
                    DialogFieldDefinition(label="Knock Mode", parameter_name="knock_mode"),
                    DialogFieldDefinition(
                        label="Knock Digital Pin",
                        parameter_name="knock_digital_pin",
                        visibility_expression="{knock_mode == 1}",
                    ),
                    DialogFieldDefinition(
                        label="Knock Analog Pin",
                        parameter_name="knock_analog_pin",
                        visibility_expression="{knock_mode == 2}",
                    ),
                ],
            )
        ],
        menus=[MenuDefinition(title="Ignition", items=[MenuItemDefinition(target="knock_setup", label="Knock")])],
    )
    tune_file = TuneFile(constants=[TuneValue(name="knock_mode", value=1.0), TuneValue(name="knock_digital_pin", value=34.0)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    page = TuningPageService().build_pages(definition)[0].pages[0]

    result = TuningPageValidationService().validate_page(page, edit_service)

    assert result.errors == ()


def test_validate_page_ignores_missing_unpaged_definition_only_items() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="idleUnits", data_type="U08"),
        ],
        tables=[
            TableDefinition(name="boardHasSD", rows=1, columns=1, data_type="U16"),
        ],
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(TuneFile(constants=[TuneValue(name="reqFuel", value=8.0)]))
    groups = TuningPageService().build_pages(definition)
    page = groups[0].pages[0]

    result = TuningPageValidationService().validate_page(page, edit_service)

    assert page.title == "Page 1 Settings"
    assert result.errors == ()
    assert result.warnings == ()
