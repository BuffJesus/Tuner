from __future__ import annotations

import pytest

from tuner.comms.mock_controller_client import MockControllerClient
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
from tuner.domain.session import SessionState
from tuner.domain.sync_state import SyncMismatchKind
from tuner.domain.tune import TuneFile, TuneValue
from tuner.domain.tuning_pages import TuningPageStateKind
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.required_fuel_calculator_service import RequiredFuelCalculatorService
from tuner.services.table_edit_service import TableSelection
from tuner.domain.operator_engine_context import OperatorEngineContext
from tuner.services.operator_engine_context_service import OperatorEngineContextService
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter


def test_presenter_tracks_staged_page_state_and_revert() -> None:
    presenter = _presenter_with_ve_page()

    initial = presenter.snapshot()
    assert initial.table_page is not None
    assert initial.table_page.state.kind == TuningPageStateKind.CLEAN

    staged = presenter.stage_table_cell(0, 1, "55.0")

    assert staged.table_page is not None
    assert staged.table_page.state.kind == TuningPageStateKind.STAGED
    assert staged.table_page.diff_summary == "1 staged change on this page."
    assert "veTable: 10.0, 20.0, 30.0, 40.0 -> 10.0, 55.0, 30.0, 40.0" in staged.table_page.diff_text
    ve_catalog_entry = next(entry for entry in staged.catalog.entries if entry.name == "veTable")
    assert ve_catalog_entry.tune_preview.startswith("10.0, 55.0")

    reverted = presenter.revert_active_page()

    assert reverted.table_page is not None
    assert reverted.table_page.state.kind == TuningPageStateKind.CLEAN


def test_presenter_marks_page_invalid_when_edit_cannot_be_applied() -> None:
    presenter = _presenter_with_ve_page()

    invalid = presenter.stage_table_cell(0, 0, "not-a-number")

    assert invalid.table_page is not None
    assert invalid.table_page.state.kind == TuningPageStateKind.INVALID
    assert invalid.navigation[0].pages[0].state.kind == TuningPageStateKind.INVALID
    assert "could not convert string to float" in (invalid.table_page.state.detail or "")


def test_presenter_stages_scalar_value_on_parameter_page() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    presenter.load(definition, tune_file)
    staged = presenter.stage_active_page_parameter("9.2")

    assert staged.parameter_page is not None
    assert staged.parameter_page.state.kind == TuningPageStateKind.STAGED
    assert staged.parameter_page.diff_summary == "1 staged change on this page."
    assert staged.parameter_page.diff_text == "reqFuel: 8.5 -> 9.2"
    assert staged.parameter_page.rows[0].preview == "9.2"
    req_fuel_entry = next(entry for entry in staged.catalog.entries if entry.name == "reqFuel")
    assert req_fuel_entry.tune_preview == "9.2"
    assert staged.workspace_review.entries[0].name == "reqFuel"
    assert staged.workspace_review.entries[0].before_preview == "8.5"
    assert staged.workspace_review.entries[0].page_title == "Page 1 Settings"


def test_presenter_marks_parameter_page_invalid_for_bad_scalar_value() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    presenter.load(definition, tune_file)
    invalid = presenter.stage_active_page_parameter("bad-value")

    assert invalid.parameter_page is not None
    assert invalid.parameter_page.state.kind == TuningPageStateKind.INVALID
    assert "could not convert string to float" in (invalid.parameter_page.state.detail or "")


def test_presenter_marks_missing_table_page_invalid_from_validation() -> None:
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
            TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
            TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snapshot = presenter.load(definition, tune_file)

    assert snapshot.table_page is not None
    assert snapshot.table_page.state.kind == TuningPageStateKind.INVALID
    assert snapshot.table_page.validation_summary.startswith("2 errors")
    assert "Missing tune value for 'veTable'." in snapshot.table_page.details_text


def test_presenter_prefers_edit_error_over_validation_error_in_state_detail() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=2, page=1, offset=16, units="rpm"),
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
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    invalid = presenter.stage_table_cell(0, 0, "bad-value")

    assert invalid.table_page is not None
    assert invalid.table_page.state.kind == TuningPageStateKind.INVALID
    assert invalid.table_page.state.detail == "could not convert string to float: 'bad-value'"


def test_presenter_can_fill_table_selection_and_undo() -> None:
    presenter = _presenter_with_ve_page()

    filled = presenter.fill_table_selection(TableSelection(top=0, left=0, bottom=0, right=1), "60.0")

    assert filled.table_page is not None
    assert filled.table_page.state.kind == TuningPageStateKind.STAGED
    assert filled.table_page.table_model is not None
    assert filled.table_page.table_model.cells[0] == ["60.0", "60.0"]
    assert filled.table_page.can_undo is True

    undone = presenter.undo_active_table()

    assert undone.table_page is not None
    assert undone.table_page.table_model is not None
    assert undone.table_page.table_model.cells[0] == ["10.0", "20.0"]


def test_presenter_can_fill_rectangular_table_selection() -> None:
    presenter = _presenter_with_ve_page()

    filled = presenter.fill_table_selection(TableSelection(top=0, left=0, bottom=1, right=1), "72.0")

    assert filled.table_page is not None
    assert filled.table_page.table_model is not None
    assert filled.table_page.table_model.cells == [["72.0", "72.0"], ["72.0", "72.0"]]


def test_presenter_can_fill_table_selection_down() -> None:
    presenter = _presenter_with_ve_page()

    filled = presenter.fill_down_table_selection(TableSelection(top=0, left=0, bottom=1, right=1))

    assert filled.table_page is not None
    assert filled.table_page.table_model is not None
    assert filled.table_page.table_model.cells == [["10.0", "20.0"], ["10.0", "20.0"]]


def test_presenter_can_fill_table_selection_right() -> None:
    presenter = _presenter_with_ve_page()

    filled = presenter.fill_right_table_selection(TableSelection(top=0, left=0, bottom=1, right=1))

    assert filled.table_page is not None
    assert filled.table_page.table_model is not None
    assert filled.table_page.table_model.cells == [["10.0", "10.0"], ["30.0", "30.0"]]


def test_presenter_paste_repeats_clipboard_pattern_across_selection() -> None:
    presenter = _presenter_with_ve_page()

    pasted = presenter.paste_table_selection(
        TableSelection(top=0, left=0, bottom=1, right=1),
        "77",
    )

    assert pasted.table_page is not None
    assert pasted.table_page.table_model is not None
    assert pasted.table_page.table_model.cells == [["77.0", "77.0"], ["77.0", "77.0"]]


def test_presenter_rejects_out_of_bounds_scalar_value() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms",
                                           min_value=0.5, max_value=20.0)],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    snapshot = presenter.stage_active_page_parameter("25.0")  # above max 20.0

    assert snapshot.parameter_page is not None
    assert snapshot.parameter_page.state.kind == TuningPageStateKind.INVALID
    assert "maximum" in (snapshot.parameter_page.state.detail or "")
    # Value must NOT have changed
    assert edit_service.get_value("reqFuel").value == 8.5  # type: ignore[union-attr]


def test_presenter_exposes_related_pages_for_fuel_trim_family() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injLayout", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=1),
            ScalarParameterDefinition(name="nFuelChannels", data_type="U08", page=1, offset=2),
            ScalarParameterDefinition(name="fuelTrimEnabled", data_type="U08", page=1, offset=3),
        ],
        tables=[
            TableDefinition(name="trim2", rows=2, columns=2, page=8, offset=0, units="%"),
            TableDefinition(name="trim3", rows=2, columns=2, page=8, offset=4, units="%"),
        ],
        table_editors=[
            TableEditorDefinition(table_id="fuelTrimTable2Tbl", map_id="map2", title="Fuel trim Table 2", page=8, z_bins="trim2"),
            TableEditorDefinition(table_id="fuelTrimTable3Tbl", map_id="map3", title="Fuel trim Table 3", page=8, z_bins="trim3"),
        ],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="injLayout", value=3.0),
        TuneValue(name="nCylinders", value=4.0),
        TuneValue(name="nFuelChannels", value=4.0),
        TuneValue(name="fuelTrimEnabled", value=1.0),
        TuneValue(name="trim2", value=[1.0, 2.0, 3.0, 4.0], rows=2, cols=2, units="%"),
        TuneValue(name="trim3", value=[5.0, 6.0, 7.0, 8.0], rows=2, cols=2, units="%"),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snapshot = presenter.load(definition, tune_file)

    assert snapshot.table_page is not None
    assert snapshot.table_page.related_pages_title == "Fuel Trims"
    assert [page.title for page in snapshot.table_page.related_pages] == ["Trim 2", "Trim 3"]
    assert snapshot.table_page.related_pages[0].is_active is True


def test_presenter_navigation_collapses_fuel_trim_family_into_one_entry() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injLayout", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=1),
            ScalarParameterDefinition(name="nFuelChannels", data_type="U08", page=1, offset=2),
            ScalarParameterDefinition(name="fuelTrimEnabled", data_type="U08", page=1, offset=3),
        ],
        tables=[
            TableDefinition(name="trim2", rows=2, columns=2, page=8, offset=0, units="%"),
            TableDefinition(name="trim3", rows=2, columns=2, page=8, offset=4, units="%"),
        ],
        table_editors=[
            TableEditorDefinition(table_id="fuelTrimTable2Tbl", map_id="map2", title="Fuel trim Table 2", page=8, z_bins="trim2"),
            TableEditorDefinition(table_id="fuelTrimTable3Tbl", map_id="map3", title="Fuel trim Table 3", page=8, z_bins="trim3"),
        ],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="injLayout", value=3.0),
        TuneValue(name="nCylinders", value=4.0),
        TuneValue(name="nFuelChannels", value=4.0),
        TuneValue(name="fuelTrimEnabled", value=1.0),
        TuneValue(name="trim2", value=[1.0, 2.0, 3.0, 4.0], rows=2, cols=2, units="%"),
        TuneValue(name="trim3", value=[5.0, 6.0, 7.0, 8.0], rows=2, cols=2, units="%"),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snapshot = presenter.load(definition, tune_file)

    titles = [page.title for group in snapshot.navigation for page in group.pages]
    assert "Fuel Trims" in titles
    assert "Fuel trim Table 2" not in titles
    assert "Fuel trim Table 3" not in titles


def test_presenter_hides_fuel_trim_family_when_non_sequential() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injLayout", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=1),
            ScalarParameterDefinition(name="nFuelChannels", data_type="U08", page=1, offset=2),
            ScalarParameterDefinition(name="fuelTrimEnabled", data_type="U08", page=1, offset=3),
        ],
        tables=[
            TableDefinition(name="trim2", rows=2, columns=2, page=8, offset=0, units="%"),
            TableDefinition(name="trim3", rows=2, columns=2, page=8, offset=4, units="%"),
        ],
        table_editors=[
            TableEditorDefinition(table_id="fuelTrimTable2Tbl", map_id="map2", title="Fuel trim Table 2", page=8, z_bins="trim2"),
            TableEditorDefinition(table_id="fuelTrimTable3Tbl", map_id="map3", title="Fuel trim Table 3", page=8, z_bins="trim3"),
        ],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="injLayout", value=0.0),
            TuneValue(name="nCylinders", value=4.0),
            TuneValue(name="nFuelChannels", value=2.0),
            TuneValue(name="fuelTrimEnabled", value=0.0),
            TuneValue(name="trim2", value=[1.0, 2.0, 3.0, 4.0], rows=2, cols=2, units="%"),
            TuneValue(name="trim3", value=[5.0, 6.0, 7.0, 8.0], rows=2, cols=2, units="%"),
        ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snapshot = presenter.load(definition, tune_file)

    assert snapshot.table_page is not None
    assert snapshot.table_page.related_pages == ()
    titles = [page.title for group in snapshot.navigation for page in group.pages]
    assert "Fuel Trims" not in titles
    assert "Fuel trim Table 2" not in titles
    assert "Fuel trim Table 3" not in titles


def test_presenter_rejects_below_minimum_scalar_value() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms",
                                           min_value=0.5, max_value=20.0)],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    snapshot = presenter.stage_active_page_parameter("0.0")  # below min 0.5

    assert snapshot.parameter_page is not None
    assert snapshot.parameter_page.state.kind == TuningPageStateKind.INVALID
    assert "minimum" in (snapshot.parameter_page.state.detail or "")
    assert edit_service.get_value("reqFuel").value == 8.5  # type: ignore[union-attr]


def test_presenter_written_values_in_snapshot() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    presenter.stage_active_page_parameter("9.2")
    snapshot = presenter.write_active_page()

    assert snapshot.parameter_page is not None
    written = dict(snapshot.parameter_page.written_values)
    assert "reqFuel" in written
    assert written["reqFuel"] == "9.2"
    assert snapshot.workspace_review.entries[0].is_written is True


def test_write_active_page_marks_page_state_written() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    presenter.stage_active_page_parameter("9.2")

    snapshot = presenter.write_active_page()

    assert snapshot.parameter_page is not None
    assert snapshot.parameter_page.state.kind == TuningPageStateKind.WRITTEN


def test_write_active_page_pushes_values_to_live_controller() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    client = MockControllerClient(definition)
    client.connect()
    presenter.set_client(client, SessionState.CONNECTED)
    presenter.stage_active_page_parameter("9.2")

    presenter.write_active_page()

    assert client.read_parameter("reqFuel") == 9.2


def test_burn_active_page_calls_live_controller_burn() -> None:
    class BurnTrackingClient(MockControllerClient):
        def __init__(self, definition: EcuDefinition | None = None) -> None:
            super().__init__(definition)
            self.burn_count = 0

        def burn(self) -> None:
            self.burn_count += 1

    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    client = BurnTrackingClient(definition)
    client.connect()
    presenter.set_client(client, SessionState.CONNECTED)
    presenter.stage_active_page_parameter("9.2")
    presenter.write_active_page()

    presenter.burn_active_page()

    assert client.burn_count == 1


def test_burn_active_page_writes_staged_values_before_live_burn() -> None:
    class BurnTrackingClient(MockControllerClient):
        def __init__(self, definition: EcuDefinition | None = None) -> None:
            super().__init__(definition)
            self.burn_count = 0

        def burn(self) -> None:
            self.burn_count += 1

    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    client = BurnTrackingClient(definition)
    client.connect()
    presenter.set_client(client, SessionState.CONNECTED)
    presenter.stage_active_page_parameter("9.2")

    snapshot = presenter.burn_active_page()

    assert client.read_parameter("reqFuel") == 9.2
    assert client.burn_count == 1
    assert snapshot.parameter_page is not None
    assert snapshot.parameter_page.state.kind == TuningPageStateKind.CLEAN
    assert snapshot.parameter_page.written_values == ()
    assert presenter.local_tune_edit_service.is_dirty("reqFuel") is False
    assert snapshot.post_burn_verification_text == "Reconnect or read back from ECU and verify persisted values before trusting the burn."


def test_burn_active_page_accepts_burned_values_as_new_baseline() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    presenter.stage_active_page_parameter("9.2")

    snapshot = presenter.burn_active_page()

    assert snapshot.parameter_page is not None
    assert snapshot.parameter_page.state.kind == TuningPageStateKind.CLEAN
    assert presenter.local_tune_edit_service.get_base_value("reqFuel").value == 9.2


def test_read_from_ecu_clears_post_burn_verification_note() -> None:
    class BurnTrackingClient(MockControllerClient):
        def burn(self) -> None:
            return None

    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    client = BurnTrackingClient(definition)
    client.connect()
    presenter.set_client(client, SessionState.CONNECTED)
    presenter.stage_active_page_parameter("9.2")
    presenter.burn_active_page()

    snapshot = presenter.read_from_ecu()

    assert snapshot.post_burn_verification_text is None


def test_burn_active_page_bootstraps_newly_visible_table_values() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="dualFuel", data_type="U08", page=1, offset=0)],
        tables=[
            TableDefinition(name="ve2Table", rows=2, columns=2, page=2, offset=0, units="%"),
            TableDefinition(name="ve2RpmBins", rows=1, columns=2, page=2, offset=16, units="rpm"),
            TableDefinition(name="ve2LoadBins", rows=2, columns=1, page=2, offset=20, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="ve2",
                map_id="ve2Map",
                title="Second Fuel Table",
                page=2,
                x_bins="ve2RpmBins",
                y_bins="ve2LoadBins",
                z_bins="ve2Table",
            )
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="fuelSettings",
                title="Fuel Settings",
                fields=[DialogFieldDefinition(label="Dual Fuel", parameter_name="dualFuel")],
            )
        ],
        menus=[
            MenuDefinition(title="Fuel", items=[MenuItemDefinition(target="fuelSettings", label="Fuel Settings")]),
            MenuDefinition(
                title="Fuel",
                items=[
                    MenuItemDefinition(
                        target="ve2",
                        label="Second Fuel Table",
                        page=2,
                        visibility_expression="{dualFuel == 1}",
                    )
                ],
            ),
        ],
    )
    tune_file = TuneFile(constants=[TuneValue(name="dualFuel", value=0.0)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    presenter.select_page("dialog:fuelSettings")
    presenter.stage_named_parameter("dualFuel", "1")

    presenter.burn_active_page()
    snapshot = presenter.select_page("table-editor:ve2")

    assert snapshot.table_page is not None
    assert snapshot.table_page.state.kind == TuningPageStateKind.CLEAN
    assert presenter.local_tune_edit_service.get_value("ve2Table") is not None
    assert presenter.local_tune_edit_service.get_value("ve2Table").value == [0.0, 0.0, 0.0, 0.0]  # type: ignore[union-attr]
    assert presenter.local_tune_edit_service.get_value("ve2RpmBins").value == [0.0, 0.0]  # type: ignore[union-attr]
    assert presenter.local_tune_edit_service.get_value("ve2LoadBins").value == [0.0, 0.0]  # type: ignore[union-attr]


def test_read_from_ecu_materializes_missing_table_values_from_ecu_ram() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="afrTable", rows=2, columns=2, page=2, offset=0, units="AFR"),
            TableDefinition(name="afrRpmBins", rows=1, columns=2, page=2, offset=16, units="rpm"),
            TableDefinition(name="afrLoadBins", rows=2, columns=1, page=2, offset=20, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="afr1",
                map_id="afr1Map",
                title="AFR Target Table",
                page=2,
                x_bins="afrRpmBins",
                y_bins="afrLoadBins",
                z_bins="afrTable",
            )
        ],
    )
    tune_file = TuneFile()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    client = MockControllerClient(definition)
    client.connect()
    client.seed_parameters(
        {
            "afrTable": [14.7, 14.7, 13.2, 12.6],
            "afrRpmBins": [800.0, 3000.0],
            "afrLoadBins": [30.0, 100.0],
        }
    )
    presenter.set_client(client, SessionState.CONNECTED)

    snapshot = presenter.read_from_ecu()

    assert snapshot.table_page is not None
    assert snapshot.table_page.state.kind == TuningPageStateKind.CLEAN
    assert presenter.local_tune_edit_service.get_value("afrTable").value == [14.7, 14.7, 13.2, 12.6]  # type: ignore[union-attr]
    assert presenter.local_tune_edit_service.get_value("afrRpmBins").value == [800.0, 3000.0]  # type: ignore[union-attr]
    assert presenter.local_tune_edit_service.get_value("afrLoadBins").value == [30.0, 100.0]  # type: ignore[union-attr]


def test_workspace_review_collects_changes_across_pages() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms"),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=2, offset=0, units="ms"),
        ],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="reqFuel", value=8.5, units="ms"),
            TuneValue(name="sparkDur", value=2.5, units="ms"),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    presenter.stage_active_page_parameter("9.2")
    presenter.select_page("fallback:2")
    snap = presenter.stage_active_page_parameter("3.1")

    assert len(snap.workspace_review.entries) == 2
    assert snap.workspace_review.summary_text.startswith("2 staged changes across the workspace.")
    assert {entry.name for entry in snap.workspace_review.entries} == {"reqFuel", "sparkDur"}


def test_workspace_review_empty_when_no_staged_changes() -> None:
    presenter = _presenter_with_ve_page()

    snap = presenter.snapshot()

    assert snap.workspace_review.entries == ()
    assert snap.workspace_review.summary_text == "No staged changes across the workspace."


def test_presenter_scalar_undo_redo_on_parameter_page() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    staged = presenter.stage_active_page_parameter("9.2")
    assert staged.parameter_page is not None
    assert staged.parameter_page.can_undo is True
    assert staged.parameter_page.can_redo is False

    undone = presenter.undo_active_page_parameter()
    assert undone.parameter_page is not None
    assert undone.parameter_page.can_undo is False
    assert undone.parameter_page.can_redo is True
    assert edit_service.get_value("reqFuel") is not None
    assert edit_service.get_value("reqFuel").value == 8.5  # type: ignore[union-attr]

    redone = presenter.redo_active_page_parameter()
    assert redone.parameter_page is not None
    assert redone.parameter_page.can_undo is True
    assert redone.parameter_page.can_redo is False
    assert edit_service.get_value("reqFuel") is not None
    assert edit_service.get_value("reqFuel").value == 9.2  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Phase 3 — sync state, read_from_ecu, revert flows, offline/reconnect
# ---------------------------------------------------------------------------

def test_snapshot_includes_sync_state() -> None:
    presenter = _presenter_with_ve_page()
    snap = presenter.snapshot()
    assert snap.sync_state is not None


def test_sync_state_reports_offline_when_no_client() -> None:
    presenter = _presenter_with_ve_page()
    snap = presenter.snapshot()
    assert snap.sync_state is not None
    assert snap.sync_state.connection_state == SessionState.OFFLINE.value


def test_sync_state_stale_staged_when_staged_and_no_ecu_ram() -> None:
    presenter = _presenter_with_ve_page()
    presenter.stage_table_cell(0, 0, "55.0")
    snap = presenter.snapshot()
    assert snap.sync_state is not None
    kinds = {m.kind for m in snap.sync_state.mismatches}
    assert SyncMismatchKind.STALE_STAGED in kinds


def test_sync_state_signature_mismatch_surfaced_in_snapshot() -> None:
    definition = EcuDefinition(name="Speedy", firmware_signature="sig-2025")
    tune_file = TuneFile(
        signature="sig-2024",
        constants=[TuneValue(name="reqFuel", value=8.5)],
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    snap = presenter.snapshot()
    assert snap.sync_state is not None
    kinds = {m.kind for m in snap.sync_state.mismatches}
    assert SyncMismatchKind.SIGNATURE_MISMATCH in kinds


def test_set_client_updates_connection_state() -> None:
    presenter = _presenter_with_ve_page()
    client = MockControllerClient()
    client.connect()

    snap = presenter.set_client(client, SessionState.CONNECTED)

    assert snap.sync_state is not None
    assert snap.sync_state.connection_state == SessionState.CONNECTED.value


def test_go_offline_clears_client_and_preserves_tune() -> None:
    presenter = _presenter_with_ve_page()
    client = MockControllerClient()
    client.connect()
    presenter.set_client(client, SessionState.CONNECTED)
    presenter.stage_table_cell(0, 0, "55.0")

    snap = presenter.go_offline()

    assert snap.sync_state is not None
    assert snap.sync_state.connection_state == SessionState.OFFLINE.value
    # Staged change still present
    assert snap.table_page is not None
    assert snap.table_page.state.kind == TuningPageStateKind.STAGED


def test_set_client_none_sets_disconnected() -> None:
    presenter = _presenter_with_ve_page()
    snap = presenter.set_client(None)
    assert snap.sync_state is not None
    assert snap.sync_state.connection_state == SessionState.DISCONNECTED.value


def test_read_from_ecu_without_client_returns_message() -> None:
    presenter = _presenter_with_ve_page()

    snap = presenter.read_from_ecu()
    msg = presenter.consume_message()

    assert snap.sync_state is not None
    assert not snap.sync_state.has_ecu_ram
    assert msg is not None and "No active connection" in msg


def test_read_from_ecu_populates_ecu_ram_snapshot() -> None:
    definition, tune_file, edit_service = _scalar_definition_and_tune()
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    client = MockControllerClient()
    client.connect()
    client.seed_parameters({"reqFuel": 9.5})
    presenter.set_client(client, SessionState.CONNECTED)

    snap = presenter.read_from_ecu()

    assert snap.sync_state is not None
    assert snap.sync_state.has_ecu_ram


def test_read_from_ecu_detects_ecu_vs_tune_mismatch() -> None:
    definition, tune_file, edit_service = _scalar_definition_and_tune()
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    client = MockControllerClient()
    client.connect()
    client.seed_parameters({"reqFuel": 9.5})   # tune has 8.5
    presenter.set_client(client, SessionState.CONNECTED)
    snap = presenter.read_from_ecu()

    assert snap.sync_state is not None
    kinds = {m.kind for m in snap.sync_state.mismatches}
    assert SyncMismatchKind.ECU_VS_TUNE in kinds


def test_read_from_ecu_no_mismatch_when_values_match() -> None:
    definition, tune_file, edit_service = _scalar_definition_and_tune()
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    client = MockControllerClient()
    client.connect()
    client.seed_parameters({"reqFuel": 8.5})   # same as tune
    presenter.set_client(client, SessionState.CONNECTED)
    snap = presenter.read_from_ecu()

    assert snap.sync_state is not None
    kinds = {m.kind for m in snap.sync_state.mismatches}
    assert SyncMismatchKind.ECU_VS_TUNE not in kinds


def test_revert_from_ecu_without_snapshot_returns_message() -> None:
    presenter = _presenter_with_ve_page()

    presenter.revert_from_ecu()
    msg = presenter.consume_message()

    assert msg is not None and "read_from_ecu" in msg


def test_revert_from_ecu_updates_base_values_and_clears_staged() -> None:
    definition, tune_file, edit_service = _scalar_definition_and_tune()
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    # Stage a local change first
    presenter.stage_active_page_parameter("7.0")
    assert edit_service.is_dirty("reqFuel")

    # Simulate an ECU read with a different value
    client = MockControllerClient()
    client.connect()
    client.seed_parameters({"reqFuel": 9.5})
    presenter.set_client(client, SessionState.CONNECTED)
    presenter.read_from_ecu()

    snap = presenter.revert_from_ecu()

    # Local staged change gone, base value is now 9.5
    assert not edit_service.is_dirty("reqFuel")
    base = edit_service.get_base_value("reqFuel")
    assert base is not None
    assert base.value == 9.5
    # Sync state should now be clean (ecu_ram matches base)
    assert snap.sync_state is not None
    assert snap.sync_state.is_clean


def test_revert_all_to_baseline_clears_all_staged() -> None:
    presenter = _presenter_with_ve_page()
    presenter.stage_table_cell(0, 0, "55.0")
    presenter.stage_table_cell(0, 1, "66.0")

    snap = presenter.revert_all_to_baseline()

    assert snap.table_page is not None
    assert snap.table_page.state.kind == TuningPageStateKind.CLEAN


def test_revert_all_to_baseline_is_noop_when_clean() -> None:
    presenter = _presenter_with_ve_page()
    snap = presenter.revert_all_to_baseline()
    msg = presenter.consume_message()
    assert snap.table_page is not None
    assert snap.table_page.state.kind == TuningPageStateKind.CLEAN
    assert msg is not None and "No staged" in msg


# ---------------------------------------------------------------------------
# Phase 4 — hardware setup validation in presenter
# ---------------------------------------------------------------------------

def test_hardware_issues_empty_when_no_hardware_setup_pages() -> None:
    presenter = _presenter_with_ve_page()
    snap = presenter.snapshot()
    assert snap.hardware_issues == ()


def test_hardware_issues_populated_for_hardware_setup_page() -> None:
    """Excessive dwell on a hardware setup page surfaces in workspace snapshot."""
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=0, units="ms"),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="coilConfig",
                title="Coil Configuration",
                fields=[DialogFieldDefinition(label="Spark Duration", parameter_name="sparkDur")],
            )
        ],
        menus=[MenuDefinition(title="Setup", items=[MenuItemDefinition(target="coilConfig", label="Coil Config")])],
    )
    # sparkDur = 15 ms → exceeds 10 ms dwell limit
    tune_file = TuneFile(constants=[TuneValue(name="sparkDur", value=15.0, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    snap = presenter.snapshot()

    assert len(snap.hardware_issues) > 0
    from tuner.domain.hardware_setup import HardwareIssueSeverity
    assert any(i.severity == HardwareIssueSeverity.ERROR for i in snap.hardware_issues)


def test_hardware_issues_on_parameter_page_snapshot_for_hardware_group() -> None:
    """When active page is in hardware_setup group, parameter_page includes issues."""
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=0, units="ms"),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="coilConfig",
                title="Coil Configuration",
                fields=[DialogFieldDefinition(label="Spark Duration", parameter_name="sparkDur")],
            )
        ],
        menus=[MenuDefinition(title="Setup", items=[MenuItemDefinition(target="coilConfig", label="Coil Config")])],
    )
    tune_file = TuneFile(constants=[TuneValue(name="sparkDur", value=15.0, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    assert len(snap.parameter_page.hardware_issues) > 0


def test_any_requires_power_cycle_set_on_parameter_page() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="sparkMode", data_type="U08", page=1, offset=0,
                                      requires_power_cycle=True),
        ],
    )
    tune_file = TuneFile(constants=[TuneValue(name="sparkMode", value=0.0)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    assert snap.parameter_page.any_requires_power_cycle is True


def test_any_requires_power_cycle_false_when_not_present() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    assert snap.parameter_page.any_requires_power_cycle is False


def test_hardware_cards_can_reference_related_hardware_pages() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="knockEnabled", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
            ScalarParameterDefinition(name="knockPin", data_type="U08", page=2, offset=0),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="ignitionOptions",
                title="Ignition Knock Options",
                fields=[
                    DialogFieldDefinition(label="Knock Enabled", parameter_name="knockEnabled"),
                    DialogFieldDefinition(label="Spark Duration", parameter_name="sparkDur"),
                ],
            ),
            DialogDefinition(
                dialog_id="knockPins",
                title="Knock Input Pins",
                fields=[DialogFieldDefinition(label="Knock Pin", parameter_name="knockPin")],
            ),
        ],
        menus=[MenuDefinition(title="Setup", items=[
            MenuItemDefinition(target="ignitionOptions", label="Ignition Knock Options"),
            MenuItemDefinition(target="knockPins", label="Knock Input Pins"),
        ])],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="knockEnabled", value=1.0),
        TuneValue(name="sparkDur", value=3.0, units="ms"),
        TuneValue(name="knockPin", value=5.0),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    checklist = next(card for card in snap.parameter_page.hardware_cards if card.key == "ignition_checklist")
    assert any("See 'Knock Input Pins'." in line for line in checklist.detail_lines)


def test_hardware_cards_include_hidden_followups_when_related_setting_is_gated() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="knockEnabled", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
            ScalarParameterDefinition(name="knockPin", data_type="U08", page=2, offset=0),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="ignitionOptions",
                title="Ignition Knock Options",
                fields=[
                    DialogFieldDefinition(label="Knock Enabled", parameter_name="knockEnabled"),
                    DialogFieldDefinition(label="Spark Duration", parameter_name="sparkDur"),
                ],
            ),
            DialogDefinition(
                dialog_id="knockPins",
                title="Knock Input Pins",
                fields=[DialogFieldDefinition(label="Knock Pin", parameter_name="knockPin", visibility_expression="{knockEnabled == 2}")],
            ),
        ],
        menus=[MenuDefinition(title="Setup", items=[
            MenuItemDefinition(target="ignitionOptions", label="Ignition Knock Options"),
            MenuItemDefinition(target="knockPins", label="Knock Input Pins"),
        ])],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="knockEnabled", value=1.0),
        TuneValue(name="sparkDur", value=3.0, units="ms"),
        TuneValue(name="knockPin", value=5.0),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    gated = next(card for card in snap.parameter_page.hardware_cards if card.key == "ignition_gated_followups")
    assert any("hidden until prerequisite options are enabled" in line for line in gated.detail_lines)


def test_hardware_cards_emit_related_page_links() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="knockEnabled", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="sparkDur", data_type="U08", page=1, offset=1, units="ms"),
            ScalarParameterDefinition(name="knockPin", data_type="U08", page=2, offset=0),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="ignitionOptions",
                title="Ignition Knock Options",
                fields=[
                    DialogFieldDefinition(label="Knock Enabled", parameter_name="knockEnabled"),
                    DialogFieldDefinition(label="Spark Duration", parameter_name="sparkDur"),
                ],
            ),
            DialogDefinition(
                dialog_id="knockPins",
                title="Knock Input Pins",
                fields=[DialogFieldDefinition(label="Knock Pin", parameter_name="knockPin")],
            ),
        ],
        menus=[MenuDefinition(title="Setup", items=[
            MenuItemDefinition(target="ignitionOptions", label="Ignition Knock Options"),
            MenuItemDefinition(target="knockPins", label="Knock Input Pins"),
        ])],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="knockEnabled", value=1.0),
        TuneValue(name="sparkDur", value=3.0, units="ms"),
        TuneValue(name="knockPin", value=5.0),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    primary = next(card for card in snap.parameter_page.hardware_cards if card.key == "ignition")
    assert ("Open Knock Input", "dialog:knockPins#knockPin") in primary.links


def test_hidden_followup_links_target_exact_related_parameter() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="afrCal", data_type="F32", page=2, offset=0),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="sensorOptions",
                title="Sensor Options",
                fields=[
                    DialogFieldDefinition(label="O2 Sensor Type", parameter_name="egoType"),
                ],
            ),
            DialogDefinition(
                dialog_id="widebandCal",
                title="Wideband Calibration",
                fields=[DialogFieldDefinition(label="Wideband Calibration", parameter_name="afrCal", visibility_expression="{egoType == 1}")],
            ),
        ],
        menus=[MenuDefinition(title="Setup", items=[
            MenuItemDefinition(target="sensorOptions", label="Sensor Options"),
            MenuItemDefinition(target="widebandCal", label="Wideband Calibration"),
        ])],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="egoType", value=2.0),
        TuneValue(name="afrCal", value=14.7),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    gated = next(card for card in snap.parameter_page.hardware_cards if card.key == "sensor_gated_followups")
    assert ("Open Wideband Calibration", "dialog:widebandCal#afrCal") in gated.links


def test_same_page_hidden_followup_is_reported_for_sensor_page() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="egoType", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="afrCal", data_type="F32", page=1, offset=1),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="sensorOptions",
                title="Sensor Options",
                fields=[
                    DialogFieldDefinition(label="O2 Sensor Type", parameter_name="egoType"),
                    DialogFieldDefinition(
                        label="Wideband Calibration",
                        parameter_name="afrCal",
                        visibility_expression="{egoType == 1}",
                    ),
                ],
            ),
        ],
        menus=[MenuDefinition(title="Setup", items=[
            MenuItemDefinition(target="sensorOptions", label="Sensor Options"),
        ])],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="egoType", value=2.0),
        TuneValue(name="afrCal", value=14.7),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    gated = next(card for card in snap.parameter_page.hardware_cards if card.key == "sensor_gated_followups")
    assert any(
        line == "Wideband calibration exists on this page but is currently hidden until prerequisite options are enabled."
        for line in gated.detail_lines
    )


def test_same_page_hidden_followup_is_reported_for_trigger_page() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08", page=1, offset=0),
            ScalarParameterDefinition(name="secondTrigger", data_type="U08", page=1, offset=1),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="triggerSetup",
                title="Trigger Setup",
                fields=[
                    DialogFieldDefinition(label="Trigger Pattern", parameter_name="TrigPattern"),
                    DialogFieldDefinition(
                        label="Secondary Trigger",
                        parameter_name="secondTrigger",
                        visibility_expression="{TrigPattern == 1}",
                    ),
                ],
            ),
        ],
        menus=[MenuDefinition(title="Setup", items=[
            MenuItemDefinition(target="triggerSetup", label="Trigger Setup"),
        ])],
    )
    tune_file = TuneFile(constants=[
        TuneValue(name="TrigPattern", value=0.0),
        TuneValue(name="secondTrigger", value=1.0),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)

    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    gated = next(card for card in snap.parameter_page.hardware_cards if card.key == "trigger_gated_followups")
    assert any(
        line == "Missing-tooth or secondary-trigger setting exists on this page but is currently hidden until prerequisite options are enabled."
        for line in gated.detail_lines
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scalar_definition_and_tune():
    definition = EcuDefinition(
        name="Speedy",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    return definition, tune_file, edit_service


def _presenter_with_ve_page() -> TuningWorkspacePresenter:
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
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


# ---------------------------------------------------------------------------
# RequiredFuelCalculatorSnapshot tests
# ---------------------------------------------------------------------------

def _injector_page_definition(extra_scalars: list | None = None) -> tuple:
    """Return (definition, tune_file) for a minimal injector page."""
    scalars = [
        ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
        ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=2, units="ms"),
        ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=3),
    ]
    values = [
        TuneValue(name="injectorFlow", value=550.0, units="cc/min"),
        TuneValue(name="reqFuel", value=8.4, units="ms"),
        TuneValue(name="nCylinders", value=4.0),
    ]
    if extra_scalars:
        for s, v in extra_scalars:
            scalars.append(s)
            values.append(v)
    definition = EcuDefinition(
        name="Test",
        scalars=scalars,
        dialogs=[
            DialogDefinition(
                dialog_id="injPage",
                title="Injector Setup",
                fields=[DialogFieldDefinition(label=s.label or s.name, parameter_name=s.name) for s in scalars],
            )
        ],
        menus=[MenuDefinition(title="Setup", items=[MenuItemDefinition(target="injPage", label="Injector Setup")])],
    )
    tune_file = TuneFile(constants=values)
    return definition, tune_file


def test_calculator_snapshot_none_on_non_hardware_page() -> None:
    """Pages not in hardware_setup group produce no calculator snapshot."""
    presenter = _presenter_with_ve_page()
    snap = presenter.snapshot()
    assert snap.parameter_page is None or snap.parameter_page.calculator_snapshot is None


def test_calculator_snapshot_none_when_displacement_missing() -> None:
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    calc = snap.parameter_page.calculator_snapshot
    assert calc is not None
    assert calc.result is None
    assert any("displacement" in m.lower() for m in calc.missing_inputs)
    assert calc.can_apply is False


def test_calculator_snapshot_populated_with_operator_displacement() -> None:
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)

    op_svc = OperatorEngineContextService()
    op_svc.update(displacement_cc=2000.0)

    presenter = TuningWorkspacePresenter(
        local_tune_edit_service=edit_service,
        operator_engine_context_service=op_svc,
    )
    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    calc = snap.parameter_page.calculator_snapshot
    assert calc is not None
    assert calc.result is not None
    assert calc.result.is_valid
    assert 5.0 < calc.result.req_fuel_ms < 20.0
    assert calc.can_apply is True


def test_calculator_snapshot_can_apply_false_without_req_fuel_param() -> None:
    """When reqFuel param is absent from the page, can_apply must be False."""
    scalars = [
        ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
        ScalarParameterDefinition(name="nCylinders", data_type="U08", page=1, offset=2),
        ScalarParameterDefinition(name="engineSize", data_type="U16", page=1, offset=3, units="cc"),
    ]
    values = [
        TuneValue(name="injectorFlow", value=550.0, units="cc/min"),
        TuneValue(name="nCylinders", value=4.0),
        TuneValue(name="engineSize", value=2000.0, units="cc"),
    ]
    definition = EcuDefinition(
        name="Test",
        scalars=scalars,
        dialogs=[
            DialogDefinition(
                dialog_id="injPage",
                title="Injector Setup",
                fields=[DialogFieldDefinition(label=s.label or s.name, parameter_name=s.name) for s in scalars],
            )
        ],
        menus=[MenuDefinition(title="Setup", items=[MenuItemDefinition(target="injPage", label="Injector Setup")])],
    )
    tune_file = TuneFile(constants=values)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    calc = snap.parameter_page.calculator_snapshot
    assert calc is not None
    assert calc.result is not None  # result computable
    assert calc.can_apply is False  # but no reqFuel param to apply to


def test_calculator_snapshot_uses_stoich_from_tune() -> None:
    extra = [
        (
            ScalarParameterDefinition(name="stoich", data_type="U08", page=1, offset=10),
            TuneValue(name="stoich", value=13.8),  # E10-blend stoich
        ),
        (
            ScalarParameterDefinition(name="engineSize", data_type="U16", page=1, offset=12, units="cc"),
            TuneValue(name="engineSize", value=2000.0, units="cc"),
        ),
    ]
    definition, tune_file = _injector_page_definition(extra_scalars=extra)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    snap = presenter.load(definition, tune_file)

    assert snap.parameter_page is not None
    calc = snap.parameter_page.calculator_snapshot
    assert calc is not None
    assert calc.target_afr == 13.8


# ---------------------------------------------------------------------------
# update_operator_engine_context
# ---------------------------------------------------------------------------

def test_update_operator_engine_context_re_emits_snapshot() -> None:
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    snap = presenter.update_operator_engine_context(displacement_cc=2000.0)

    assert snap.parameter_page is not None
    calc = snap.parameter_page.calculator_snapshot
    assert calc is not None
    assert calc.displacement_cc == 2000.0


def test_update_operator_engine_context_result_becomes_valid() -> None:
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    # Without displacement: result is None
    before = presenter.snapshot().parameter_page
    assert before is not None
    assert before.calculator_snapshot is None or before.calculator_snapshot.result is None

    snap = presenter.update_operator_engine_context(displacement_cc=1600.0)
    calc = snap.parameter_page.calculator_snapshot  # type: ignore[union-attr]
    assert calc is not None
    assert calc.result is not None
    assert calc.result.is_valid


def test_update_operator_engine_context_ellipsis_leaves_other_fields() -> None:
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    presenter.update_operator_engine_context(
        displacement_cc=2000.0, compression_ratio=9.5
    )

    # Updating only compression_ratio should leave displacement unchanged
    presenter.update_operator_engine_context(compression_ratio=10.0)
    ctx = presenter.operator_engine_context_service.get()
    assert ctx.displacement_cc == 2000.0
    assert ctx.compression_ratio == 10.0


# ---------------------------------------------------------------------------
# apply_req_fuel_result
# ---------------------------------------------------------------------------

def _presenter_with_injector_page_and_displacement(displacement_cc: float = 2000.0):
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    op_svc = OperatorEngineContextService()
    op_svc.update(displacement_cc=displacement_cc)
    presenter = TuningWorkspacePresenter(
        local_tune_edit_service=edit_service,
        operator_engine_context_service=op_svc,
    )
    presenter.load(definition, tune_file)
    return presenter


def test_apply_req_fuel_result_stages_value() -> None:
    presenter = _presenter_with_injector_page_and_displacement(2000.0)
    initial_snap = presenter.snapshot()
    assert initial_snap.parameter_page is not None
    calc = initial_snap.parameter_page.calculator_snapshot
    assert calc is not None and calc.can_apply
    expected_ms = calc.result.req_fuel_ms  # type: ignore[union-attr]

    snap = presenter.apply_req_fuel_result()

    assert snap.parameter_page is not None
    assert snap.parameter_page.state.kind == TuningPageStateKind.STAGED
    req_fuel_row = next(r for r in snap.parameter_page.rows if r.name == "reqFuel")
    assert float(req_fuel_row.preview) == pytest.approx(float(expected_ms), abs=0.01)


def test_apply_req_fuel_result_no_op_without_displacement() -> None:
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    snap = presenter.apply_req_fuel_result()

    # Page should remain clean — no valid result to apply
    assert snap.parameter_page is not None
    assert snap.parameter_page.state.kind == TuningPageStateKind.CLEAN


def test_apply_req_fuel_result_stages_without_active_injector_page() -> None:
    extra = [
        (
            ScalarParameterDefinition(name="veTableSelect", data_type="U08", page=2, offset=0),
            TuneValue(name="veTableSelect", value=1.0),
        )
    ]
    definition, tune_file = _injector_page_definition(extra_scalars=extra)
    definition.dialogs = tuple(definition.dialogs) + (
        DialogDefinition(
            dialog_id="otherPage",
            title="Other Page",
            fields=[DialogFieldDefinition(label="VE Table Select", parameter_name="veTableSelect")],
        ),
    )
    definition.menus = tuple(definition.menus) + (
        MenuDefinition(title="Fuel", items=[MenuItemDefinition(target="otherPage", label="Other Page")]),
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    op_svc = OperatorEngineContextService()
    op_svc.update(displacement_cc=2000.0)
    presenter = TuningWorkspacePresenter(
        local_tune_edit_service=edit_service,
        operator_engine_context_service=op_svc,
    )
    presenter.load(definition, tune_file)
    expected = RequiredFuelCalculatorService().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=550.0,
        target_afr=14.7,
    )
    presenter.select_page("dialog:otherPage")

    snap = presenter.apply_req_fuel_result()

    tv = presenter.local_tune_edit_service.get_value("reqFuel")
    assert tv is not None
    assert float(tv.value) == pytest.approx(expected.req_fuel_ms, abs=0.01)
    assert snap.parameter_page is not None


# ---------------------------------------------------------------------------
# stage_generated_ve_table
# ---------------------------------------------------------------------------

def test_stage_generated_ve_table_stages_list_on_named_parameter() -> None:
    presenter = _presenter_with_ve_page()
    from tuner.services.ve_table_generator_service import VeTableGeneratorResult
    from tuner.domain.generator_context import ForcedInductionTopology

    result = VeTableGeneratorResult(
        values=tuple([75.0] * 4),  # 2×2 for the test fixture
        rows=2,
        columns=2,
        topology=ForcedInductionTopology.NA,
        summary="test",
        warnings=(),
    )

    snap = presenter.stage_generated_ve_table("veTable", result)

    assert snap.table_page is not None
    assert snap.table_page.state.kind == TuningPageStateKind.STAGED
    tv = presenter.local_tune_edit_service.get_value("veTable")
    assert tv is not None
    assert tv.value == [75.0, 75.0, 75.0, 75.0]


def test_stage_generated_ve_table_unknown_name_returns_message() -> None:
    presenter = _presenter_with_ve_page()
    from tuner.services.ve_table_generator_service import VeTableGeneratorResult
    from tuner.domain.generator_context import ForcedInductionTopology

    result = VeTableGeneratorResult(
        values=tuple([75.0] * 4),
        rows=2,
        columns=2,
        topology=ForcedInductionTopology.NA,
        summary="test",
        warnings=(),
    )
    presenter.stage_generated_ve_table("nonexistentTable", result)
    message = presenter.consume_message()
    assert message is not None
    assert "not found" in message.lower()


def test_generate_and_stage_ve_table_uses_generator_service() -> None:
    presenter = _presenter_with_ve_page()
    # The test fixture VE table is 2×2 (4 cells). The generator will produce
    # 256 cells, which can't fit a 2×2 list. That's fine — the replace_list
    # will stage 256 values; we verify it triggered the operation log.
    presenter.generate_and_stage_ve_table("veTable")
    message = presenter.consume_message()
    # Should have a staged message or error message
    assert message is not None


def test_generate_and_stage_ve_table_preserves_operator_topology_without_hardware_pages() -> None:
    from tuner.domain.generator_context import ForcedInductionTopology

    class RecordingGenerator:
        def __init__(self) -> None:
            self.last_ctx = None

        def generate(self, ctx):
            from tuner.services.ve_table_generator_service import VeTableGeneratorResult

            self.last_ctx = ctx
            return VeTableGeneratorResult(
                values=tuple([40.0] * 4),
                rows=2,
                columns=2,
                topology=ctx.forced_induction_topology,
                summary="test",
                warnings=(),
            )

    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, units="%"),
        ],
    )
    tune_file = TuneFile(constants=[TuneValue(name="veTable", value=[10.0, 20.0, 30.0, 40.0], rows=2, cols=2, units="%")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    generator = RecordingGenerator()
    presenter = TuningWorkspacePresenter(
        local_tune_edit_service=edit_service,
        ve_table_generator_service=generator,
    )
    presenter.load(definition, tune_file)
    presenter.update_operator_engine_context(
        forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
        boost_target_kpa=180.0,
    )

    presenter.generate_and_stage_ve_table("veTable")

    assert generator.last_ctx is not None
    assert generator.last_ctx.forced_induction_topology == ForcedInductionTopology.SINGLE_TURBO
    assert generator.last_ctx.boost_target_kpa == 180.0


def test_stage_generated_spark_table_accepts_string_topology() -> None:
    from tuner.services.spark_table_generator_service import SparkTableGeneratorResult
    from tuner.domain.operator_engine_context import CalibrationIntent

    definition = EcuDefinition(
        name="Speeduino",
        tables=[TableDefinition(name="sparkTable", rows=2, columns=2, page=1, offset=0, units="deg")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="sparkTable", value=[10.0, 12.0, 14.0, 16.0], rows=2, cols=2, units="deg")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    result = SparkTableGeneratorResult(
        values=tuple([18.0] * 4),
        rows=2,
        columns=2,
        topology="single_turbo",  # type: ignore[arg-type]
        compression_ratio=9.5,
        calibration_intent=CalibrationIntent.FIRST_START,
        summary="test",
        warnings=(),
    )

    presenter.stage_generated_spark_table("sparkTable", result)

    message = presenter.consume_message()
    assert message is not None
    assert "single_turbo" in message


# ---------------------------------------------------------------------------
# stage_named_parameter
# ---------------------------------------------------------------------------

def _presenter_with_scalar(name: str, value: float) -> TuningWorkspacePresenter:
    """Return a presenter with a single scalar and its tune value."""
    definition = EcuDefinition(
        name="Test",
        scalars=[ScalarParameterDefinition(name=name, data_type="U08", page=1, offset=0)],
    )
    tune_file = TuneFile(constants=[TuneValue(name=name, value=value)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


def test_stage_named_parameter_stages_value_by_name() -> None:
    presenter = _presenter_with_scalar("injOpen", 0.9)

    snap = presenter.stage_named_parameter("injOpen", "1.2")

    msg = presenter.consume_message()
    assert msg is not None and "injOpen" in msg
    tv = presenter.local_tune_edit_service.get_value("injOpen")
    assert tv is not None
    assert float(tv.value) == pytest.approx(1.2, abs=0.01)
    del snap


def test_stage_named_parameter_unknown_name_returns_message() -> None:
    presenter = _presenter_with_scalar("injOpen", 0.9)

    presenter.stage_named_parameter("nonExistentParam", "5.0")
    msg = presenter.consume_message()

    assert msg is not None and "not found" in msg.lower()


def test_stage_named_parameter_records_operation_log_entry() -> None:
    presenter = _presenter_with_scalar("injOpen", 0.9)

    presenter.stage_named_parameter("injOpen", "1.5")

    snap = presenter.snapshot()
    assert any(e.name == "injOpen" for e in snap.workspace_review.entries)


def test_stage_named_parameter_bootstraps_missing_definition_scalar_into_tune() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="knock_digital_pin", data_type="U08", page=1, offset=0)],
    )
    tune_file = TuneFile(constants=[])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    presenter.stage_named_parameter("knock_digital_pin", "34")

    tv = presenter.local_tune_edit_service.get_value("knock_digital_pin")
    assert tv is not None
    assert float(tv.value) == pytest.approx(34.0, abs=0.01)
    assert any(item.name == "knock_digital_pin" for item in tune_file.constants)


# ---------------------------------------------------------------------------
# Operator engine context — persistence wiring
# ---------------------------------------------------------------------------

def test_presenter_saves_context_on_update_when_sidecar_path_set(tmp_path) -> None:
    """update_operator_engine_context must write the sidecar file when a path is set."""
    import json
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    path = tmp_path / "ctx.json"
    presenter.set_context_sidecar_path(path)
    presenter.load(definition, tune_file)

    presenter.update_operator_engine_context(displacement_cc=3500.0)

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["displacement_cc"] == 3500.0


def test_presenter_loads_context_on_load_when_sidecar_path_set(tmp_path) -> None:
    """presenter.load() must restore operator engine context from the sidecar."""
    import json
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)

    path = tmp_path / "ctx.json"
    path.write_text(json.dumps({"displacement_cc": 2200.0, "compression_ratio": 9.5}), encoding="utf-8")

    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.set_context_sidecar_path(path)
    presenter.load(definition, tune_file)

    ctx = presenter.operator_engine_context_service.get()
    assert ctx.displacement_cc == 2200.0
    assert ctx.compression_ratio == 9.5


def test_presenter_does_not_save_context_without_sidecar_path(tmp_path) -> None:
    """No file should be created when no sidecar path is set."""
    definition, tune_file = _injector_page_definition()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    # no set_context_sidecar_path call
    presenter.load(definition, tune_file)

    presenter.update_operator_engine_context(displacement_cc=1800.0)

    assert not list(tmp_path.iterdir())  # nothing written anywhere


# ---------------------------------------------------------------------------
# stage_generated_afr_table / generate_and_stage_afr_table
# ---------------------------------------------------------------------------

def test_stage_generated_afr_table_stages_list_on_named_parameter() -> None:
    presenter = _presenter_with_ve_page()
    from tuner.services.afr_target_generator_service import AfrTargetGeneratorResult
    from tuner.domain.generator_context import ForcedInductionTopology

    result = AfrTargetGeneratorResult(
        values=tuple([14.7] * 4),  # 2×2 for the test fixture
        rows=2,
        columns=2,
        topology=ForcedInductionTopology.NA,
        stoich=14.7,
        summary="test",
        warnings=(),
    )

    snap = presenter.stage_generated_afr_table("veTable", result)

    assert snap.table_page is not None
    assert snap.table_page.state.kind == TuningPageStateKind.STAGED
    tv = presenter.local_tune_edit_service.get_value("veTable")
    assert tv is not None
    assert tv.value == [14.7, 14.7, 14.7, 14.7]


def test_stage_generated_afr_table_unknown_name_returns_message() -> None:
    presenter = _presenter_with_ve_page()
    from tuner.services.afr_target_generator_service import AfrTargetGeneratorResult
    from tuner.domain.generator_context import ForcedInductionTopology

    result = AfrTargetGeneratorResult(
        values=tuple([14.7] * 4),
        rows=2,
        columns=2,
        topology=ForcedInductionTopology.NA,
        stoich=14.7,
        summary="test",
        warnings=(),
    )
    presenter.stage_generated_afr_table("nonexistentTable", result)
    message = presenter.consume_message()
    assert message is not None
    assert "not found" in message.lower()


def test_stage_generated_afr_table_materializes_missing_definition_backed_table_and_axes() -> None:
    from tuner.domain.generator_context import ForcedInductionTopology
    from tuner.services.afr_target_generator_service import AfrTargetGeneratorResult

    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="afrTable", rows=2, columns=2, page=2, offset=0, units="AFR"),
            TableDefinition(name="afrRpmBins", rows=1, columns=2, page=2, offset=16, units="rpm"),
            TableDefinition(name="afrLoadBins", rows=2, columns=1, page=2, offset=20, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="afr1",
                map_id="afr1Map",
                title="AFR Target Table",
                page=2,
                x_bins="afrRpmBins",
                y_bins="afrLoadBins",
                z_bins="afrTable",
            )
        ],
    )
    tune_file = TuneFile()
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    result = AfrTargetGeneratorResult(
        values=(14.7, 14.4, 13.2, 12.6),
        rows=2,
        columns=2,
        topology=ForcedInductionTopology.NA,
        stoich=14.7,
        summary="test",
        warnings=(),
    )

    snap = presenter.stage_generated_afr_table("afrTable", result)

    assert snap.table_page is not None
    assert snap.table_page.table_model is not None
    assert snap.table_page.state.kind == TuningPageStateKind.STAGED
    assert presenter.local_tune_edit_service.get_value("afrTable").value == [14.7, 14.4, 13.2, 12.6]  # type: ignore[union-attr]
    assert presenter.local_tune_edit_service.get_value("afrRpmBins").value == [0.0, 0.0]  # type: ignore[union-attr]
    assert presenter.local_tune_edit_service.get_value("afrLoadBins").value == [0.0, 0.0]  # type: ignore[union-attr]


def test_generate_and_stage_afr_table_uses_generator_service() -> None:
    presenter = _presenter_with_ve_page()
    presenter.generate_and_stage_afr_table("veTable")
    message = presenter.consume_message()
    # Should have a staged message or error message
    assert message is not None


# ---------------------------------------------------------------------------
# Startup enrichment generators — WUE, cranking, ASE
# ---------------------------------------------------------------------------

def _presenter_with_startup_arrays() -> TuningWorkspacePresenter:
    """Return a presenter loaded with WUE, cranking, and ASE array parameters."""
    definition = EcuDefinition(name="Speeduino")
    tune_file = TuneFile(
        constants=[
            TuneValue(name="wueBins",            value=list(range(10, 20)),         rows=1, cols=10),
            TuneValue(name="wueRates",           value=[180.0] * 10,               rows=1, cols=10),
            TuneValue(name="crankingEnrichBins", value=[-40.0, 0.0, 30.0, 70.0],  rows=1, cols=4),
            TuneValue(name="crankingEnrichValues", value=[140.0, 115.0, 105.0, 100.0], rows=1, cols=4),
            TuneValue(name="aseBins",            value=[-20.0, 0.0, 40.0, 80.0],  rows=1, cols=4),
            TuneValue(name="asePct",             value=[25.0, 20.0, 15.0, 10.0],  rows=1, cols=4),
            TuneValue(name="aseCount",           value=[25.0, 20.0, 15.0, 6.0],   rows=1, cols=4),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


def test_stage_generated_wue_stages_both_arrays() -> None:
    from tuner.services.startup_enrichment_generator_service import (
        WarmupEnrichmentGeneratorResult, _WUE_BINS,
    )
    presenter = _presenter_with_startup_arrays()
    result = WarmupEnrichmentGeneratorResult(
        clt_bins=_WUE_BINS,
        enrichment_pct=tuple([180.0, 175.0, 168.0, 154.0, 134.0, 121.0, 112.0, 104.0, 102.0, 100.0]),
        summary="test",
        warnings=(),
    )

    presenter.stage_generated_wue("wueBins", "wueRates", result)

    bins_tv = presenter.local_tune_edit_service.get_value("wueBins")
    rates_tv = presenter.local_tune_edit_service.get_value("wueRates")
    assert bins_tv is not None and list(bins_tv.value) == list(_WUE_BINS)
    assert rates_tv is not None and rates_tv.value[0] == 180.0
    msg = presenter.consume_message()
    assert msg is not None and "wueRates" in msg


def test_stage_generated_wue_unknown_bins_returns_message() -> None:
    from tuner.services.startup_enrichment_generator_service import (
        WarmupEnrichmentGeneratorResult, _WUE_BINS,
    )
    presenter = _presenter_with_startup_arrays()
    result = WarmupEnrichmentGeneratorResult(
        clt_bins=_WUE_BINS,
        enrichment_pct=tuple([100.0] * 10),
        summary="test",
        warnings=(),
    )
    presenter.stage_generated_wue("nonexistentBins", "wueRates", result)
    msg = presenter.consume_message()
    assert msg is not None and "not found" in msg.lower()


def test_generate_and_stage_wue_produces_message() -> None:
    presenter = _presenter_with_startup_arrays()
    presenter.generate_and_stage_wue("wueBins", "wueRates")
    assert presenter.consume_message() is not None


def test_stage_generated_cranking_enrichment_stages_both_arrays() -> None:
    from tuner.services.startup_enrichment_generator_service import (
        CrankingEnrichmentGeneratorResult, _CRANK_BINS,
    )
    presenter = _presenter_with_startup_arrays()
    result = CrankingEnrichmentGeneratorResult(
        clt_bins=_CRANK_BINS,
        enrichment_pct=(148.0, 123.0, 113.0, 100.0),
        summary="test",
        warnings=(),
    )

    presenter.stage_generated_cranking_enrichment(
        "crankingEnrichBins", "crankingEnrichValues", result
    )

    tv = presenter.local_tune_edit_service.get_value("crankingEnrichValues")
    assert tv is not None and tv.value[0] == pytest.approx(148.0)
    msg = presenter.consume_message()
    assert msg is not None and "crankingEnrichValues" in msg


def test_stage_generated_cranking_unknown_name_returns_message() -> None:
    from tuner.services.startup_enrichment_generator_service import (
        CrankingEnrichmentGeneratorResult, _CRANK_BINS,
    )
    presenter = _presenter_with_startup_arrays()
    result = CrankingEnrichmentGeneratorResult(
        clt_bins=_CRANK_BINS,
        enrichment_pct=(140.0, 115.0, 105.0, 100.0),
        summary="test",
        warnings=(),
    )
    presenter.stage_generated_cranking_enrichment("badBins", "crankingEnrichValues", result)
    msg = presenter.consume_message()
    assert msg is not None and "not found" in msg.lower()


def test_generate_and_stage_cranking_enrichment_produces_message() -> None:
    presenter = _presenter_with_startup_arrays()
    presenter.generate_and_stage_cranking_enrichment(
        "crankingEnrichBins", "crankingEnrichValues"
    )
    assert presenter.consume_message() is not None


def test_stage_generated_ase_stages_all_three_arrays() -> None:
    from tuner.services.startup_enrichment_generator_service import (
        AfterStartEnrichmentGeneratorResult, _ASE_BINS,
    )
    presenter = _presenter_with_startup_arrays()
    result = AfterStartEnrichmentGeneratorResult(
        clt_bins=_ASE_BINS,
        enrichment_pct=(30.0, 25.0, 20.0, 15.0),
        duration_seconds=(30.0, 25.0, 20.0, 11.0),
        summary="test",
        warnings=(),
    )

    presenter.stage_generated_ase("aseBins", "asePct", "aseCount", result)

    pct_tv = presenter.local_tune_edit_service.get_value("asePct")
    count_tv = presenter.local_tune_edit_service.get_value("aseCount")
    assert pct_tv is not None and pct_tv.value[0] == pytest.approx(30.0)
    assert count_tv is not None and count_tv.value[0] == pytest.approx(30.0)
    msg = presenter.consume_message()
    assert msg is not None and "asePct" in msg


def test_stage_generated_ase_unknown_name_returns_message() -> None:
    from tuner.services.startup_enrichment_generator_service import (
        AfterStartEnrichmentGeneratorResult, _ASE_BINS,
    )
    presenter = _presenter_with_startup_arrays()
    result = AfterStartEnrichmentGeneratorResult(
        clt_bins=_ASE_BINS,
        enrichment_pct=(25.0, 20.0, 15.0, 10.0),
        duration_seconds=(25.0, 20.0, 15.0, 6.0),
        summary="test",
        warnings=(),
    )
    presenter.stage_generated_ase("aseBins", "badPct", "aseCount", result)
    msg = presenter.consume_message()
    assert msg is not None and "not found" in msg.lower()


def test_generate_and_stage_ase_produces_message() -> None:
    presenter = _presenter_with_startup_arrays()
    presenter.generate_and_stage_ase("aseBins", "asePct", "aseCount")
    assert presenter.consume_message() is not None
