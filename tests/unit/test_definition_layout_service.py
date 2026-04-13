from __future__ import annotations

from tuner.domain.ecu_definition import (
    DialogDefinition,
    DialogFieldDefinition,
    DialogPanelReference,
    EcuDefinition,
    MenuDefinition,
    MenuItemDefinition,
    TableEditorDefinition,
)
from tuner.services.definition_layout_service import DefinitionLayoutService


def test_compile_pages_resolves_dialog_backed_table_page_with_nested_sections() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        table_editors=[
            TableEditorDefinition(
                table_id="veTable1Tbl",
                map_id="veTable1Map",
                title="VE Table",
                page=2,
                x_bins="rpmBins",
                y_bins="fuelLoadBins",
                z_bins="veTable",
            )
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
        menus=[
            MenuDefinition(
                title="&Fuel",
                items=[MenuItemDefinition(target="veTableDialog", label="VE Table", page=2)],
            )
        ],
    )

    pages = DefinitionLayoutService().compile_pages(definition)

    assert len(pages) == 1
    assert pages[0].title == "VE Table"
    assert pages[0].table_editor_id == "veTable1Tbl"
    assert pages[0].group_title == "Fuel"
    assert pages[0].sections[0].title == "Legacy Options"
    assert pages[0].sections[0].fields[0].parameter_name == "multiplyMAP"
