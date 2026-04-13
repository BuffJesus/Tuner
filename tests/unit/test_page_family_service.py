from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition, MenuDefinition, MenuItemDefinition, TableDefinition, TableEditorDefinition
from tuner.services.page_family_service import PageFamilyService
from tuner.services.tuning_page_service import TuningPageService


def test_build_index_groups_fuel_trim_pages_into_one_family() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="trim2", rows=2, columns=2, page=8, offset=0, units="%"),
            TableDefinition(name="trim3", rows=2, columns=2, page=8, offset=4, units="%"),
            TableDefinition(name="trim1", rows=2, columns=2, page=9, offset=0, units="%"),
            TableDefinition(name="trim5", rows=2, columns=2, page=9, offset=4, units="%"),
        ],
        table_editors=[
            TableEditorDefinition(table_id="fuelTrimTable2Tbl", map_id="map2", title="Fuel trim Table 2", page=8, z_bins="trim2"),
            TableEditorDefinition(table_id="fuelTrimTable3Tbl", map_id="map3", title="Fuel trim Table 3", page=8, z_bins="trim3"),
            TableEditorDefinition(table_id="fuelTrimTable1Tbl", map_id="map1", title="Sequential fuel trim (1-4)", page=9, z_bins="trim1"),
            TableEditorDefinition(table_id="fuelTrimTable5Tbl", map_id="map5", title="Sequential fuel trim (5-8)", page=9, z_bins="trim5"),
        ],
    )

    pages = TuningPageService().build_pages(definition)
    families = PageFamilyService().build_index(pages)

    family = families["table-editor:fuelTrimTable2Tbl"]
    assert family.title == "Fuel Trims"
    assert [tab.title for tab in family.tabs] == ["Trim 2", "Trim 3", "Seq 1-4", "Seq 5-8"]
