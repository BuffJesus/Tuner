from __future__ import annotations

from tuner.domain.ecu_definition import (
    DialogDefinition,
    DialogFieldDefinition,
    DialogPanelReference,
    EcuDefinition,
    MenuDefinition,
    MenuItemDefinition,
    ScalarParameterDefinition,
    TableDefinition,
    TableEditorDefinition,
)
from tuner.domain.tuning_pages import TuningPageKind
from tuner.services.tuning_page_service import TuningPageService


def test_build_pages_groups_table_editors_and_adds_settings_fallback() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms"),
        ],
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=2, page=1, offset=16, units="rpm"),
            TableDefinition(name="loadBins", rows=2, columns=1, page=1, offset=20, units="kPa"),
            TableDefinition(name="sparkTable", rows=2, columns=2, page=2, offset=0, units="deg"),
            TableDefinition(name="sparkRpmBins", rows=1, columns=2, page=2, offset=16, units="rpm"),
            TableDefinition(name="sparkLoadBins", rows=2, columns=1, page=2, offset=20, units="kPa"),
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
            ),
            TableEditorDefinition(
                table_id="spark",
                map_id="sparkMap",
                title="Ignition Advance",
                page=2,
                x_bins="sparkRpmBins",
                y_bins="sparkLoadBins",
                z_bins="sparkTable",
            ),
        ],
    )

    groups = TuningPageService().build_pages(definition)

    assert [group.title for group in groups] == ["Fuel", "Ignition", "Settings"]
    assert groups[0].pages[0].kind == TuningPageKind.TABLE
    assert groups[0].pages[0].parameter_names == ("veTable", "rpmBins", "loadBins")
    assert groups[2].pages[0].title == "Page 1 Settings"
    assert groups[2].pages[0].parameter_names == ("reqFuel",)


def test_build_pages_falls_back_when_table_editor_map_definition_is_missing() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="rpmBins", rows=1, columns=2, page=4, offset=0, units="rpm"),
            TableDefinition(name="loadBins", rows=2, columns=1, page=4, offset=4, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="afr",
                map_id="afrMap",
                title="AFR Targets",
                page=4,
                x_bins="rpmBins",
                y_bins="loadBins",
                z_bins="afrTable",
            ),
        ],
    )

    groups = TuningPageService().build_pages(definition)
    page = groups[0].pages[0]

    assert groups[0].title == "AFR / Lambda"
    assert page.kind == TuningPageKind.PARAMETER_LIST
    assert page.table_name == "afrTable"
    assert [parameter.name for parameter in page.parameters] == ["rpmBins", "loadBins"]
    assert "raw fallback" in page.summary


def test_build_pages_keeps_loose_definition_content_available() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="baroCorrection", data_type="U08", units="%", offset=4)],
        tables=[TableDefinition(name="trimTable", rows=2, columns=2, page=7, offset=0, units="%")],
    )

    groups = TuningPageService().build_pages(definition)

    assert [group.title for group in groups] == ["Settings"]
    assert groups[0].pages[0].title == "Page 7 Settings"
    assert groups[0].pages[0].parameter_names == ("trimTable",)


def test_build_pages_names_fallback_from_explicit_menu_page_labels() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=3, offset=0),
            ScalarParameterDefinition(name="boostEnabled", data_type="U08", page=3, offset=1),
        ],
        menus=[
            MenuDefinition(
                title="&Tuning",
                items=[
                    MenuItemDefinition(target="egoControl", label="AFR/O2", page=3),
                    MenuItemDefinition(target="boostSettings", label="Boost Control", page=3),
                ],
            )
        ],
    )

    groups = TuningPageService().build_pages(definition)

    assert groups[0].pages[0].title == "AFR/O2 / Boost Control Settings"


def test_build_pages_names_fallback_from_dialog_overlap_when_menu_has_no_page_number() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=1),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="engine_constants",
                title="Engine Constants",
                fields=[
                    DialogFieldDefinition(label="Required Fuel", parameter_name="reqFuel"),
                    DialogFieldDefinition(label="Number of cylinders", parameter_name="nCylinders"),
                ],
            )
        ],
        menus=[MenuDefinition(title="Settings", items=[MenuItemDefinition(target="engine_constants", label="Engine Constants")])],
    )

    groups = TuningPageService().build_pages(definition)

    assert groups[0].pages[0].title == "Engine Constants"


def test_build_pages_uses_constant_page_titles_when_menu_inference_is_missing() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="boostControlEnable", data_type="U08", page=15, offset=80)],
        page_titles={15: "Boost Duty Lookup"},
    )

    groups = TuningPageService().build_pages(definition)

    assert groups[0].pages[0].title == "Boost Duty Lookup"


def test_build_pages_uses_definition_layout_for_dialog_backed_table_pages() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="multiplyMAP", data_type="U08", page=2, offset=24)],
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=2, offset=0, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=2, page=2, offset=16, units="rpm"),
            TableDefinition(name="fuelLoadBins", rows=2, columns=1, page=2, offset=20, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="veTable1Tbl",
                map_id="veTable1Map",
                title="VE Table",
                page=2,
                x_bins="rpmBins",
                y_bins="fuelLoadBins",
                z_bins="veTable",
            ),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="veTableDialog_north",
                title="",
                panels=[DialogPanelReference(target="veTable1Tbl", position="North")],
            ),
            DialogDefinition(
                dialog_id="veTableDialog_south",
                title="Legacy Options",
                fields=[DialogFieldDefinition(label="Multiply VE by MAP ratio", parameter_name="multiplyMAP")],
            ),
            DialogDefinition(
                dialog_id="veTableDialog",
                title="VE Table",
                panels=[
                    DialogPanelReference(target="veTableDialog_north", position="North"),
                    DialogPanelReference(target="veTableDialog_south", position="South"),
                ],
            ),
        ],
        menus=[MenuDefinition(title="&Fuel", items=[MenuItemDefinition(target="veTableDialog", label="VE Table", page=2)])],
    )

    groups = TuningPageService().build_pages(definition)

    assert [group.title for group in groups] == ["Fuel"]
    page = groups[0].pages[0]
    assert page.kind == TuningPageKind.TABLE
    assert page.title == "VE Table"
    assert page.parameter_names == ("veTable", "rpmBins", "fuelLoadBins", "multiplyMAP")
    assert page.sections[1].title == "Legacy Options"


def test_hardware_setup_group_captures_injector_dialog() -> None:
    """Injector config dialog in an unrecognised menu routes to Hardware Setup."""
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
            ScalarParameterDefinition(name="deadTime", data_type="U16", page=1, offset=2, units="ms"),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="injectorConfig",
                title="Injector Configuration",
                fields=[
                    DialogFieldDefinition(label="Injector Flow Rate", parameter_name="injectorFlow"),
                    DialogFieldDefinition(label="Dead Time", parameter_name="deadTime"),
                ],
            )
        ],
        menus=[MenuDefinition(title="Setup", items=[MenuItemDefinition(target="injectorConfig", label="Injector Config")])],
    )

    groups = TuningPageService().build_pages(definition)

    group_titles = [g.title for g in groups]
    assert "Hardware Setup" in group_titles
    hw_group = next(g for g in groups if g.title == "Hardware Setup")
    page_titles = [p.title for p in hw_group.pages]
    assert any("injector" in t.lower() for t in page_titles)


def test_hardware_setup_group_captures_trigger_dialog() -> None:
    """Trigger config dialog routes to Hardware Setup regardless of menu name."""
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="triggerType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="toothCount", data_type="U08", page=1, offset=1),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="triggerConfig",
                title="Trigger Setup",
                fields=[
                    DialogFieldDefinition(label="Trigger Type", parameter_name="triggerType"),
                    DialogFieldDefinition(label="Tooth Count", parameter_name="toothCount"),
                ],
            )
        ],
        menus=[MenuDefinition(title="Engine", items=[MenuItemDefinition(target="triggerConfig", label="Trigger Setup")])],
    )

    groups = TuningPageService().build_pages(definition)

    group_titles = [g.title for g in groups]
    assert "Hardware Setup" in group_titles


def test_hardware_setup_group_comes_before_fuel_and_ignition() -> None:
    """Hardware Setup group should be the first group when present."""
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="triggerType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=4, units="ms"),
        ],
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=8, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=2, page=1, offset=24, units="rpm"),
            TableDefinition(name="loadBins", rows=2, columns=1, page=1, offset=28, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(table_id="ve", map_id="veMap", title="VE Table", page=1,
                                  x_bins="rpmBins", y_bins="loadBins", z_bins="veTable"),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="triggerConfig",
                title="Trigger Setup",
                fields=[DialogFieldDefinition(label="Trigger Type", parameter_name="triggerType")],
            )
        ],
        menus=[MenuDefinition(title="Engine", items=[
            MenuItemDefinition(target="triggerConfig", label="Trigger Setup"),
        ])],
    )

    groups = TuningPageService().build_pages(definition)

    assert groups[0].title == "Hardware Setup"
    assert "Fuel" in [g.title for g in groups]


def test_known_fuel_menu_preserves_fuel_group() -> None:
    """A menu explicitly titled 'Fuel' keeps its group identity unchanged."""
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, units="ms")],
        dialogs=[
            DialogDefinition(
                dialog_id="fuelSettings",
                title="Fuel Settings",
                fields=[DialogFieldDefinition(label="Required Fuel", parameter_name="reqFuel")],
            )
        ],
        menus=[MenuDefinition(title="&Fuel", items=[MenuItemDefinition(target="fuelSettings", label="Fuel Settings")])],
    )

    groups = TuningPageService().build_pages(definition)

    assert groups[0].title == "Fuel"
    assert "Hardware Setup" not in [g.title for g in groups]
