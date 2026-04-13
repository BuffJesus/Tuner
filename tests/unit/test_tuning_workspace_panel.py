from __future__ import annotations

from datetime import UTC, datetime
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

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
from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.evidence_replay_service import EvidenceReplayChannel, EvidenceReplaySnapshot
from tuner.services.hardware_setup_summary_service import HardwareSetupCardSnapshot
from tuner.services.tuning_workspace_presenter import CatalogSnapshot
from tuner.ui.tuning_workspace import TuningWorkspacePanel
from tuner.comms.mock_controller_client import MockControllerClient
from tuner.domain.session import SessionState
from datetime import UTC, datetime


def test_table_panel_x_axis_click_selects_column() -> None:
    panel = _panel_with_ve_page()

    panel.map_table.setCurrentIndex(panel.map_table_model.index(1, 0))
    panel._on_x_axis_cell_clicked(0, 1)

    assert panel._active_display_cell == (1, 1)
    assert panel._selected_table_range().left == 1
    assert panel._selected_table_range().right == 1


def test_table_panel_y_axis_click_selects_row() -> None:
    panel = _panel_with_ve_page()

    panel.map_table.setCurrentIndex(panel.map_table_model.index(0, 1))
    panel._on_y_axis_cell_clicked(1, 0)

    assert panel._active_display_cell == (1, 1)
    assert panel._selected_table_range().top == 0
    assert panel._selected_table_range().bottom == 0


def test_table_panel_selected_range_maps_display_row_back_to_model_row() -> None:
    panel = _panel_with_ve_page()

    panel.map_table.setCurrentIndex(panel.map_table_model.index(0, 0))

    selection = panel._selected_table_range()

    assert selection is not None
    assert selection.top == 1
    assert selection.bottom == 1
    assert selection.left == 0
    assert selection.right == 0


def test_table_panel_footer_stays_visible_and_attached() -> None:
    panel = _panel_with_ve_page()

    assert panel.table_footer_panel.isVisible()
    assert panel.table_footer_panel.property("tableAttached") is True
    assert panel.table_grid_panel.property("tableAttachedFooter") is True


def test_table_panel_select_all_covers_full_table() -> None:
    panel = _panel_with_ve_page()

    panel._on_select_all_table()

    selection = panel._selected_table_range()
    assert selection is not None
    assert selection.top == 0
    assert selection.bottom == 1
    assert selection.left == 0
    assert selection.right == 1


def test_table_panel_ctrl_a_shortcut_selects_full_table() -> None:
    panel = _panel_with_ve_page()
    app = QApplication.instance() or QApplication([])

    panel.map_table.setFocus()
    QTest.keyClick(panel.map_table, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()

    selection = panel._selected_table_range()
    assert selection is not None
    assert selection.top == 0
    assert selection.bottom == 1
    assert selection.left == 0
    assert selection.right == 1


def test_table_panel_bulk_edit_commits_to_selected_region() -> None:
    panel = _panel_with_ve_page()
    app = QApplication.instance() or QApplication([])

    panel.map_table.setCurrentIndex(panel.map_table_model.index(0, 0))
    panel._on_select_all_table()

    assert panel.map_table_model.setData(panel.map_table.currentIndex(), "55", Qt.ItemDataRole.EditRole) is True
    app.processEvents()

    assert panel.map_table_model.index(0, 0).data() == "55.0"
    assert panel.map_table_model.index(0, 1).data() == "55.0"
    assert panel.map_table_model.index(1, 0).data() == "55.0"
    assert panel.map_table_model.index(1, 1).data() == "55.0"


def test_table_panel_empty_area_click_clears_selection() -> None:
    panel = _panel_with_ve_page()
    app = QApplication.instance() or QApplication([])

    panel.map_table.setFixedSize(320, 220)
    panel.map_table.setColumnWidth(0, 48)
    panel.map_table.setColumnWidth(1, 48)
    panel.map_table.setRowHeight(0, 24)
    panel.map_table.setRowHeight(1, 24)
    panel._on_select_all_table()
    app.processEvents()
    assert panel._selected_table_range() is not None

    viewport = panel.map_table.viewport()
    empty_point = QPoint(viewport.width() + 20, viewport.height() + 20)
    assert not panel.map_table.indexAt(empty_point).isValid()

    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, empty_point)
    app.processEvents()

    assert not panel.map_table.selectedIndexes()
    assert not panel.map_table.currentIndex().isValid()
    assert panel._selected_table_range() is None
    assert panel._active_display_cell is None


def test_table_panel_workspace_ui_state_round_trips() -> None:
    panel = _panel_with_ve_page()

    panel.catalog_search_edit.setText("ve")
    panel.catalog_kind_combo.setCurrentText("Tables / Maps")
    panel.workspace_details_tabs.setCurrentIndex(1)
    panel.main_splitter.setSizes([260, 780, 300])
    panel.workspace_splitter.setSizes([700, 180])
    state = panel.capture_ui_state()

    panel.catalog_search_edit.setText("")
    panel.catalog_kind_combo.setCurrentText("All")
    panel.workspace_details_tabs.setCurrentIndex(0)
    panel.main_splitter.setSizes([200, 900, 200])
    panel.workspace_splitter.setSizes([900, 60])

    panel.restore_ui_state(state)

    assert panel.catalog_search_edit.text() == "ve"
    assert panel.catalog_kind_combo.currentText() == "Tables / Maps"
    assert panel.presenter.catalog_query == "ve"
    assert panel.presenter.catalog_kind == "Tables / Maps"
    assert panel.workspace_details_tabs.currentIndex() == 1
    assert panel.presenter.active_page_id == state.active_page_id
    assert len(panel.main_splitter.sizes()) == len(state.main_splitter_sizes)
    assert len(panel.workspace_splitter.sizes()) == len(state.workspace_splitter_sizes)


def test_table_panel_quick_open_entries_and_open_page() -> None:
    panel = _panel_with_ve_page()

    entries = panel.quick_open_entries()

    assert entries
    assert entries[0].page_id == "table-editor:ve"
    assert entries[0].title == "VE Table"

    panel.open_page("table-editor:ve")

    assert panel.presenter.active_page_id == "table-editor:ve"


def test_open_page_emits_workspace_changed() -> None:
    panel = _panel_with_ve_page()
    seen: list[bool] = []
    panel.workspace_changed.connect(lambda: seen.append(True))

    panel.open_page("table-editor:ve")

    assert seen


def test_table_page_renders_latest_evidence_review_note() -> None:
    panel = _panel_with_ve_page()
    panel.set_evidence_replay_snapshot(_evidence_snapshot())

    assert panel.table_evidence_label.isVisible() is True
    assert "Relevant channels: rpm=950.0 rpm | map=42.0 kPa" in panel.table_evidence_label.text()


def test_parameter_page_renders_latest_evidence_review_note() -> None:
    panel = _panel_with_hardware_pages()
    panel.set_evidence_replay_snapshot(_evidence_snapshot())

    assert panel.parameter_evidence_label.isHidden() is False
    assert "Latest write: 11:59:58  written  reqFuel = 9.2" in panel.parameter_evidence_label.text()


def test_table_page_renders_comparison_against_latest_evidence_when_review_is_pinned() -> None:
    panel = _panel_with_ve_page()
    review_snapshot = _evidence_snapshot()
    latest_snapshot = _evidence_snapshot(rpm=1100.0, map_kpa=48.0)

    panel.set_evidence_review_snapshots(review_snapshot, latest_snapshot=latest_snapshot)

    assert "Comparison vs latest capture" in panel.table_evidence_label.text()
    assert "rpm +150.0 rpm" in panel.table_evidence_label.text()
    assert "map +6.0 kPa" in panel.table_evidence_label.text()


def test_table_page_renders_replay_position_context() -> None:
    panel = _panel_with_ve_page()
    panel.set_evidence_replay_snapshot(_evidence_snapshot(rpm=1125.0, map_kpa=52.0))

    assert "Replay position is nearest row" in panel.table_evidence_label.text()
    assert "Table cell value:" in panel.table_evidence_label.text()



def test_refresh_from_presenter_updates_navigation_after_external_change() -> None:
    app = QApplication.instance() or QApplication([])
    panel = _panel_with_hardware_pages()
    seen: list[bool] = []
    panel.workspace_changed.connect(lambda: seen.append(True))

    panel.presenter.stage_named_parameter("sparkDur", "4.0")
    panel.refresh_from_presenter(notify_workspace=True)
    app.processEvents()

    group_item = panel.navigator_tree.topLevelItem(0)
    page_item = group_item.child(0)

    assert page_item.text(1) == "Staged"
    assert seen


def test_hardware_cards_group_into_operator_sections() -> None:
    grouped = TuningWorkspacePanel._group_hardware_cards(
        (
            HardwareSetupCardSnapshot(key="ignition", title="Ignition Setup", summary="", detail_lines=()),
            HardwareSetupCardSnapshot(key="ignition_checklist", title="Ignition Checklist", summary="", detail_lines=()),
            HardwareSetupCardSnapshot(key="ignition_gated_followups", title="Hidden Follow-Ups", summary="", detail_lines=()),
            HardwareSetupCardSnapshot(key="safety", title="Change Safety", summary="", detail_lines=(), severity="warning"),
        )
    )

    assert [title for title, _cards in grouped] == [
        "Configured Now",
        "Required Next Checks",
        "Hidden Follow-Ups",
        "Apply / Restart Implications",
    ]


def test_hardware_card_link_button_opens_related_page() -> None:
    app = QApplication.instance() or QApplication([])
    panel = _panel_with_hardware_pages()

    primary = next(card for card in panel.presenter.snapshot().parameter_page.hardware_cards if card.key == "ignition")
    card_widget = panel._hardware_card_widget(primary)
    button = next(
        widget
        for widget in card_widget.findChildren(QPushButton)
        if widget.text() == "Open Knock Input"
    )

    button.click()
    app.processEvents()

    assert panel.presenter.active_page_id == "dialog:knockPins"
    assert panel.presenter.active_page_parameter_name == "knockPin"


def test_catalog_selection_emits_workspace_changed() -> None:
    app = QApplication.instance() or QApplication([])
    panel = _panel_with_ve_page()
    seen: list[bool] = []
    panel.workspace_changed.connect(lambda: seen.append(True))

    assert panel.catalog_table.rowCount() > 1
    panel.catalog_table.selectRow(1)
    app.processEvents()

    assert seen


def test_open_page_with_parameter_target_selects_destination_parameter() -> None:
    panel = _panel_with_hardware_pages()

    panel.open_page("dialog:knockPins#knockPin")

    assert panel.presenter.active_page_id == "dialog:knockPins"
    assert panel.presenter.active_page_parameter_name == "knockPin"


def test_staged_navigation_page_uses_highlighted_row_colors() -> None:
    panel = _panel_with_ve_page()
    app = QApplication.instance() or QApplication([])

    panel.presenter.select_page("table-editor:ve")
    snapshot = panel.presenter.stage_table_cell(0, 0, "55")
    panel._render_and_emit(snapshot, notify_workspace=True)
    app.processEvents()

    group_item = panel.navigator_tree.topLevelItem(0)
    page_item = group_item.child(0)
    background = page_item.background(0).color().name()
    foreground = page_item.foreground(0).color().name()

    assert page_item.text(1) == "Staged"
    assert background == "#5a3e12"
    assert foreground == "#f8e7bf"


def test_written_navigation_page_uses_distinct_row_colors() -> None:
    panel = _panel_with_ve_page()
    app = QApplication.instance() or QApplication([])

    panel.presenter.select_page("table-editor:ve")
    snapshot = panel.presenter.stage_table_cell(0, 0, "55")
    panel._render_and_emit(snapshot, notify_workspace=True)
    snapshot = panel.presenter.write_active_page()
    panel._render_and_emit(snapshot, notify_workspace=True)
    app.processEvents()

    group_item = panel.navigator_tree.topLevelItem(0)
    page_item = group_item.child(0)
    background = page_item.background(0).color().name()
    foreground = page_item.foreground(0).color().name()

    assert page_item.text(1) == "Written"
    assert background == "#12384f"
    assert foreground == "#d9f1ff"


def test_burned_navigation_page_returns_to_clean_state() -> None:
    panel = _panel_with_ve_page()
    app = QApplication.instance() or QApplication([])

    panel.presenter.select_page("table-editor:ve")
    snapshot = panel.presenter.stage_table_cell(0, 0, "55")
    panel._render_and_emit(snapshot, notify_workspace=True)
    snapshot = panel.presenter.burn_active_page()
    panel._render_and_emit(snapshot, notify_workspace=True)
    app.processEvents()

    group_item = panel.navigator_tree.topLevelItem(0)
    page_item = group_item.child(0)

    assert page_item.text(1) == "Clean"


def test_power_cycle_action_emits_request_signal() -> None:
    panel = _panel_with_ve_page()
    seen: list[bool] = []
    panel.power_cycle_requested.connect(lambda: seen.append(True))

    panel.execute_action("workspace.power_cycle")

    assert seen


def test_sync_from_ecu_preserves_local_staged_changes() -> None:
    panel = _panel_with_scalar_page()
    panel.presenter.stage_active_page_parameter("9.2")
    client = MockControllerClient()
    client.connect()
    client.seed_parameters({"reqFuel": 8.5})
    panel.set_session_client(client, SessionState.CONNECTED)

    panel.sync_from_ecu()

    assert panel.presenter.local_tune_edit_service.is_dirty("reqFuel") is True
    snapshot = panel.presenter.snapshot()
    assert snapshot.parameter_page is not None
    assert snapshot.parameter_page.state.kind.value == "staged"


def test_table_meta_summary_panel_hides_when_all_meta_labels_hidden() -> None:
    panel = _panel_with_ve_page()

    panel.table_page_summary_label.hide()
    panel.table_validation_summary_label.hide()
    panel.table_diff_summary_label.hide()
    panel.table_axis_summary_label.hide()
    panel._refresh_table_header_sections()

    assert panel.table_meta_summary_panel.isHidden()

    panel.table_axis_summary_label.setText("RPM vs Load")
    panel.table_axis_summary_label.show()
    panel._refresh_table_header_sections()

    assert panel.table_meta_summary_panel.isHidden() is False


def test_catalog_details_hide_when_snapshot_has_no_details() -> None:
    panel = _panel_with_ve_page()

    panel._render_catalog(CatalogSnapshot(entries=(), selected_name=None, details_text=""))

    assert panel.catalog_details.isHidden()

    panel._render_catalog(CatalogSnapshot(entries=(), selected_name=None, details_text="Selected parameter details"))

    assert panel.catalog_details.isHidden() is False


def test_workspace_details_panel_wraps_context_tabs() -> None:
    panel = _panel_with_ve_page()

    assert panel.workspace_details_panel.property("workspaceDetailsPanel") is True
    assert panel.workspace_splitter.widget(1) is panel.workspace_details_panel


def test_related_page_tabs_switch_between_fuel_trim_tables() -> None:
    app = QApplication.instance() or QApplication([])
    panel = _panel_with_fuel_trim_pages()

    fuel_group = panel.navigator_tree.topLevelItem(0)
    assert fuel_group.childCount() == 1
    assert fuel_group.child(0).text(0) == "Fuel Trims"

    assert panel.table_related_pages_tabs.count() == 2
    assert panel.table_related_pages_tabs.tabText(0) == "Trim 2"
    assert panel.table_related_pages_tabs.tabText(1) == "Trim 3"

    panel.table_related_pages_tabs.setCurrentIndex(1)
    app.processEvents()

    assert panel.presenter.active_page_id == "table-editor:fuelTrimTable3Tbl"


def test_navigator_panel_wraps_tree() -> None:
    panel = _panel_with_ve_page()

    assert panel.navigator_panel.property("navigatorPanel") is True
    assert panel.main_splitter.widget(0) is panel.navigator_panel
    assert panel.navigator_tree.property("navigatorTree") is True


def _panel_with_ve_page() -> TuningWorkspacePanel:
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
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    panel = TuningWorkspacePanel(local_tune_edit_service=edit_service)
    panel.resize(1400, 900)
    panel.show()
    panel.set_context(definition, tune_file)
    app.processEvents()
    return panel


def _panel_with_scalar_page() -> TuningWorkspacePanel:
    app = QApplication.instance() or QApplication([])
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    panel = TuningWorkspacePanel(local_tune_edit_service=edit_service)
    panel.resize(1200, 800)
    panel.show()
    panel.set_context(definition, tune_file)
    app.processEvents()
    return panel


def _panel_with_hardware_pages() -> TuningWorkspacePanel:
    app = QApplication.instance() or QApplication([])
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
    tune_file = TuneFile(
        constants=[
            TuneValue(name="knockEnabled", value=1.0),
            TuneValue(name="sparkDur", value=3.0, units="ms"),
            TuneValue(name="knockPin", value=5.0),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    panel = TuningWorkspacePanel(local_tune_edit_service=edit_service)
    panel.resize(1400, 900)
    panel.show()
    panel.set_context(definition, tune_file)
    app.processEvents()
    return panel


def _panel_with_fuel_trim_pages() -> TuningWorkspacePanel:
    app = QApplication.instance() or QApplication([])
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
    tune_file = TuneFile(
        constants=[
            TuneValue(name="injLayout", value=3.0),
            TuneValue(name="nCylinders", value=4.0),
            TuneValue(name="nFuelChannels", value=4.0),
            TuneValue(name="fuelTrimEnabled", value=1.0),
            TuneValue(name="trim2", value=[1.0, 2.0, 3.0, 4.0], rows=2, cols=2, units="%"),
            TuneValue(name="trim3", value=[5.0, 6.0, 7.0, 8.0], rows=2, cols=2, units="%"),
        ]
    )
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    panel = TuningWorkspacePanel(local_tune_edit_service=edit_service)
    panel.resize(1400, 900)
    panel.show()
    panel.set_context(definition, tune_file)
    app.processEvents()
    return panel


def _evidence_snapshot(*, rpm: float = 950.0, map_kpa: float = 42.0, advance: float = 14.0) -> EvidenceReplaySnapshot:
    return EvidenceReplaySnapshot(
        captured_at=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
        session_state="connected",
        connection_text="Connection  connected",
        source_text="Source  ECU RAM",
        sync_summary_text="Sync  clean",
        sync_mismatch_details=(),
        staged_summary_text="1 staged change across the workspace.",
        operation_summary_text="Evidence summary: latest staged work has been written to RAM but not burned.",
        operation_session_count=1,
        latest_write_text="11:59:58  written  reqFuel = 9.2",
        latest_burn_text=None,
        runtime_summary_text="Runtime  4 channel(s)",
        runtime_channel_count=4,
        runtime_age_seconds=4.0,
        runtime_channels=(
            EvidenceReplayChannel(name="rpm", value=rpm, units="rpm"),
            EvidenceReplayChannel(name="map", value=map_kpa, units="kPa"),
            EvidenceReplayChannel(name="advance", value=advance, units="deg"),
            EvidenceReplayChannel(name="rSA_fullSync", value=1.0),
        ),
        evidence_summary_text="Captured replay bundle.",
    )
