from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tuner.domain.ecu_definition import (
    DialogDefinition,
    DialogFieldDefinition,
    EcuDefinition,
    MenuDefinition,
    MenuItemDefinition,
    ScalarParameterDefinition,
)
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.scalar_page_editor_service import ScalarFieldEditorSnapshot, ScalarPageEditorService
from tuner.services.tuning_page_service import TuningPageService
from tuner.ui.tuning_workspace import TuningWorkspacePanel


def test_scalar_page_editor_service_hides_field_when_visibility_expression_false() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="fuelAlgorithm", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(
                name="injTiming",
                data_type="U08",
                page=1,
                offset=1,
                visibility_expression="{fuelAlgorithm == 1}",
            ),
        ],
        dialogs=[],
    )
    page = TuningPageService().build_pages(definition)[0].pages[0]
    tune_file = TuneFile(
        constants=[
            TuneValue(name="fuelAlgorithm", value=0.0),
            TuneValue(name="injTiming", value=5.0),
        ]
    )
    edits = LocalTuneEditService()
    edits.set_tune_file(tune_file)

    sections = ScalarPageEditorService().build_sections(page, edits)

    field_names = [f.name for f in sections[0].fields]
    assert "fuelAlgorithm" in field_names
    assert "injTiming" not in field_names


def test_scalar_page_editor_service_shows_field_when_visibility_expression_true() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="fuelAlgorithm", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(
                name="injTiming",
                data_type="U08",
                page=1,
                offset=1,
                visibility_expression="{fuelAlgorithm == 1}",
            ),
        ],
        dialogs=[],
    )
    page = TuningPageService().build_pages(definition)[0].pages[0]
    tune_file = TuneFile(
        constants=[
            TuneValue(name="fuelAlgorithm", value=1.0),
            TuneValue(name="injTiming", value=5.0),
        ]
    )
    edits = LocalTuneEditService()
    edits.set_tune_file(tune_file)

    sections = ScalarPageEditorService().build_sections(page, edits)

    field_names = [f.name for f in sections[0].fields]
    assert "injTiming" in field_names


def _knock_definition() -> EcuDefinition:
    """Minimal definition that mirrors the Speeduino knock dialog pattern.

    Dialog field:
        field = "Knock Mode",          knock_mode
        field = "Knock Digital Pin",   knock_digital_pin, { knock_mode == 1 }
        field = "Knock Analog Pin",    knock_analog_pin,  { knock_mode == 2 }
    """
    dialog = DialogDefinition(dialog_id="knock_setup", title="Knock Setup")
    dialog.fields.append(DialogFieldDefinition(label="Knock Mode", parameter_name="knock_mode"))
    dialog.fields.append(
        DialogFieldDefinition(
            label="Knock Digital Pin",
            parameter_name="knock_digital_pin",
            visibility_expression="{knock_mode == 1}",
        )
    )
    dialog.fields.append(
        DialogFieldDefinition(
            label="Knock Analog Pin",
            parameter_name="knock_analog_pin",
            visibility_expression="{knock_mode == 2}",
        )
    )

    menu = MenuDefinition(title="Ignition")
    menu.items.append(MenuItemDefinition(target="knock_setup", label="Knock", page=1))

    return EcuDefinition(
        name="Test",
        scalars=[
            ScalarParameterDefinition(name="knock_mode", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="knock_digital_pin", data_type="U08", page=1, offset=1),
            ScalarParameterDefinition(name="knock_analog_pin", data_type="U08", page=1, offset=2),
        ],
        dialogs=[dialog],
        menus=[menu],
    )


def test_dialog_visibility_hides_digital_pin_when_knock_mode_off() -> None:
    """knock_digital_pin must be hidden when knock_mode=0 (off)."""
    definition = _knock_definition()
    pages = TuningPageService().build_pages(definition)
    page = pages[0].pages[0]

    tune = TuneFile(constants=[
        TuneValue(name="knock_mode", value=0.0),
        TuneValue(name="knock_digital_pin", value=30.0),
        TuneValue(name="knock_analog_pin", value=63.0),
    ])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)

    sections = ScalarPageEditorService().build_sections(page, edits)
    names = [f.name for section in sections for f in section.fields]

    assert "knock_mode" in names
    assert "knock_digital_pin" not in names
    assert "knock_analog_pin" not in names


def test_dialog_visibility_shows_digital_pin_when_knock_mode_digital() -> None:
    """knock_digital_pin must appear when knock_mode=1 (Digital)."""
    definition = _knock_definition()
    pages = TuningPageService().build_pages(definition)
    page = pages[0].pages[0]

    tune = TuneFile(constants=[
        TuneValue(name="knock_mode", value=1.0),
        TuneValue(name="knock_digital_pin", value=30.0),
        TuneValue(name="knock_analog_pin", value=63.0),
    ])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)

    sections = ScalarPageEditorService().build_sections(page, edits)
    names = [f.name for section in sections for f in section.fields]

    assert "knock_mode" in names
    assert "knock_digital_pin" in names
    assert "knock_analog_pin" not in names


def test_dialog_visibility_updates_after_staged_knock_mode_change() -> None:
    """Staging knock_mode=1 must make knock_digital_pin visible immediately."""
    definition = _knock_definition()
    pages = TuningPageService().build_pages(definition)
    page = pages[0].pages[0]

    tune = TuneFile(constants=[
        TuneValue(name="knock_mode", value=0.0),
        TuneValue(name="knock_digital_pin", value=30.0),
        TuneValue(name="knock_analog_pin", value=63.0),
    ])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)

    # Before staging: pin must be hidden
    before = [f.name for section in ScalarPageEditorService().build_sections(page, edits) for f in section.fields]
    assert "knock_digital_pin" not in before

    # Stage knock_mode = 1 (Digital)
    edits.stage_scalar_value("knock_mode", "1")

    after = [f.name for section in ScalarPageEditorService().build_sections(page, edits) for f in section.fields]
    assert "knock_digital_pin" in after
    assert "knock_analog_pin" not in after


def test_dialog_visibility_shows_analog_pin_when_knock_mode_analog() -> None:
    """knock_analog_pin must appear when knock_mode=2, digital pin must stay hidden."""
    definition = _knock_definition()
    pages = TuningPageService().build_pages(definition)
    page = pages[0].pages[0]

    tune = TuneFile(constants=[
        TuneValue(name="knock_mode", value=0.0),
        TuneValue(name="knock_digital_pin", value=30.0),
        TuneValue(name="knock_analog_pin", value=63.0),
    ])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)

    edits.stage_scalar_value("knock_mode", "2")

    sections = ScalarPageEditorService().build_sections(page, edits)
    names = [f.name for section in sections for f in section.fields]

    assert "knock_analog_pin" in names
    assert "knock_digital_pin" not in names


def test_scalar_page_editor_service_groups_sections_and_marks_dirty() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="sparkMode", data_type="U08", page=1, offset=0, help_text="Mode", requires_power_cycle=True),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
        ],
        dialogs=[],
    )
    page = TuningPageService().build_pages(definition)[0].pages[0]
    tune_file = TuneFile(constants=[TuneValue(name="sparkMode", value=0.0), TuneValue(name="sparkDur", value=1.0, units="ms")])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune_file)
    edits.stage_scalar_value("sparkDur", "1.5")

    sections = ScalarPageEditorService().build_sections(page, edits)

    assert sections[0].fields[0].name == "sparkMode"
    assert sections[0].fields[1].name == "sparkDur"
    assert sections[0].fields[1].is_dirty is True


def test_workspace_scalar_combo_filters_invalid_options_and_selects_by_value() -> None:
    app = QApplication.instance() or QApplication([])
    field = ScalarFieldEditorSnapshot(
        name="knock_digital_pin",
        label="Knock Digital Pin",
        value_text="31",
        base_value_text="31",
        units=None,
        help_text=None,
        min_value=None,
        max_value=None,
        digits=None,
        options=("INVALID", "PT4", "PT5", "INVALID"),
        option_values=("0", "30", "31", "255"),
        is_dirty=False,
        requires_power_cycle=False,
        visibility_expression=None,
    )
    panel = TuningWorkspacePanel(local_tune_edit_service=LocalTuneEditService())

    combo = panel._field_editor(field)  # noqa: SLF001

    assert combo.count() == 2
    assert combo.itemText(0) == "PT4"
    assert combo.itemText(1) == "PT5"
    assert combo.currentText() == "PT5"
    assert combo.currentData() == "31"
