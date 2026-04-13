from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition, ScalarParameterDefinition, TableDefinition, TableEditorDefinition
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.tuning_page_diff_service import TuningPageDiffService
from tuner.services.tuning_page_service import TuningPageService


def test_build_page_diff_lists_scalar_and_table_before_after_values() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
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
            TuneValue(name="reqFuel", value=8.5, units="ms"),
            TuneValue(name="veTable", value=[10.0, 20.0, 30.0, 40.0], rows=2, cols=2, units="%"),
            TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
            TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    edit_service.stage_scalar_value("reqFuel", "9.1")
    edit_service.stage_list_cell("veTable", 1, "55.0")

    groups = TuningPageService().build_pages(definition)
    settings_page = groups[1].pages[0]
    table_page = groups[0].pages[0]

    settings_diff = TuningPageDiffService().build_page_diff(settings_page, edit_service)
    table_diff = TuningPageDiffService().build_page_diff(table_page, edit_service)

    assert settings_diff.summary == "1 staged change on this page."
    assert settings_diff.detail_text == "reqFuel: 8.5 -> 9.1"
    assert table_diff.summary == "1 staged change on this page."
    assert "veTable: 10.0, 20.0, 30.0, 40.0 -> 10.0, 55.0, 30.0, 40.0" in table_diff.detail_text
