import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog

import tuner.ui.main_window as main_window_module
from tuner.ui.main_window import (
    RecentProjectSummary,
    build_recent_project_summaries,
    CommandPaletteEntry,
    build_command_palette_entries,
    build_shell_status_snapshot,
    build_surface_evidence_snapshot,
    build_surface_mode_snapshot,
    choose_start_project_path,
    probe_connection_config,
    controller_signature_matches_definition,
    deserialize_workspace_project_state,
    format_recent_project_menu_label,
    _iter_speeduino_probe_candidates,
    MainWindow,
    serialize_workspace_project_state,
    update_recent_project_paths,
)
from tuner.ui.tuning_workspace import WorkspaceActionEntry, WorkspacePageEntry, WorkspaceUiState
from tuner.domain.connection import ConnectionConfig, ProtocolType, TransportType
from tuner.domain.ecu_definition import EcuDefinition, ScalarParameterDefinition
from tuner.domain.project import ConnectionProfile
from tuner.domain.project import Project
from tuner.domain.firmware_capabilities import FirmwareCapabilities
from tuner.domain.session import SessionInfo, SessionState
from tuner.domain.sync_state import SyncMismatch, SyncMismatchKind, SyncState
from tuner.domain.tune import TuneFile, TuneValue
from tuner.domain.firmware import BoardFamily, DetectedFlashTarget
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.services.project_service import ProjectService
from tuner.services.tuning_workspace_presenter import CatalogSnapshot, OperationLogSnapshot, TuningWorkspaceSnapshot, WorkspaceReviewSnapshot
from tuner.transports.base import Transport
from tuner.transports.transport_factory import TransportFactory


class _ProbeTransport:
    def __init__(self, *, signature: bytes | None = None, fail_open: bool = False) -> None:
        self.signature = signature
        self.fail_open = fail_open
        self._open = False
        self._read_buffer = bytearray()

    def open(self) -> None:
        if self.fail_open:
            raise RuntimeError("port unavailable")
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def read(self, size: int, timeout: float | None = None) -> bytes:
        del timeout
        size = min(size, len(self._read_buffer))
        data = self._read_buffer[:size]
        del self._read_buffer[:size]
        return bytes(data)

    def write(self, data: bytes) -> int:
        if self.signature is not None and data in {b"Q", b"S"}:
            self._read_buffer.extend(self.signature if data == b"Q" else b"Speeduino")
        return len(data)


class _ProbeTransportFactory(TransportFactory):
    def __init__(self, transports_by_port: dict[str, Transport]) -> None:
        self.transports_by_port = transports_by_port

    def create(self, config: ConnectionConfig) -> Transport:
        if config.transport == TransportType.SERIAL:
            return self.transports_by_port[config.serial_port]
        return self.transports_by_port["default"]


def _workspace_snapshot(
    *,
    staged_count: int = 0,
    hardware_count: int = 0,
    sync_state: SyncState | None = None,
    post_burn_verification_text: str | None = None,
) -> TuningWorkspaceSnapshot:
    return TuningWorkspaceSnapshot(
        navigation=(),
        active_page_kind="empty",
        table_page=None,
        parameter_page=None,
        catalog=CatalogSnapshot(entries=(), selected_name=None, details_text=""),
        operation_log=OperationLogSnapshot(summary_text="", entry_count=0, has_unwritten=False),
        workspace_review=WorkspaceReviewSnapshot(
            summary_text="",
            entries=tuple(object() for _ in range(staged_count)),
        ),
        sync_state=sync_state,
        hardware_issues=tuple(object() for _ in range(hardware_count)),
        post_burn_verification_text=post_burn_verification_text,
    )


def test_build_command_palette_entries_combines_actions_and_pages() -> None:
    page_entries = (
        WorkspacePageEntry(
            page_id="table-editor:ve",
            title="VE Table",
            group_title="Fuel",
            kind="table-editor",
            state_label="clean",
            summary="Fuel map",
        ),
    )
    action_entries = (
        WorkspaceActionEntry(
            action_id="workspace.write_page",
            title="Write Active Page",
            summary="Write staged changes to RAM.",
        ),
    )

    entries = build_command_palette_entries(page_entries, action_entries)

    assert len(entries) == 2
    assert entries[0].entry_id == "workspace.write_page"
    assert entries[0].target == "action"
    assert entries[0].category == "Action"
    assert entries[1].entry_id == "table-editor:ve"
    assert entries[1].target == "page"
    assert entries[1].category == "Fuel"


def test_build_command_palette_entries_preserves_global_entries_first() -> None:
    global_entries = (
        CommandPaletteEntry(
            entry_id="surface.tuning",
            title="Go To Tuning",
            category="Surface",
            summary="Switch tabs.",
            target="global",
        ),
    )

    entries = build_command_palette_entries((), (), global_entries=global_entries)

    assert len(entries) == 1
    assert entries[0].entry_id == "surface.tuning"
    assert entries[0].target == "global"


def test_build_surface_mode_snapshot_maps_tuning_surface() -> None:
    snapshot = build_surface_mode_snapshot("Tuning")

    assert snapshot.mode_label == "Tuning"
    assert snapshot.title == "Calibration Editing"
    assert snapshot.emphasis == "primary"


def test_build_surface_mode_snapshot_maps_tools_flash_surface() -> None:
    snapshot = build_surface_mode_snapshot("Tools / Flash")

    assert snapshot.mode_label == "Tools / Flash"
    assert "Firmware" in snapshot.title
    assert snapshot.emphasis == "warning"


def test_build_surface_mode_snapshot_maps_trigger_logs_surface() -> None:
    snapshot = build_surface_mode_snapshot("Trigger Logs")

    assert snapshot.mode_label == "Trigger Logs"
    assert snapshot.title == "Trigger Troubleshooting"
    assert snapshot.emphasis == "accent"


def test_build_surface_evidence_snapshot_marks_runtime_live_when_channels_present() -> None:
    snapshot = build_surface_evidence_snapshot(
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(
            staged_count=1,
            sync_state=SyncState(mismatches=(), has_ecu_ram=True, connection_state=SessionState.CONNECTED.value),
            post_burn_verification_text=None,
        ),
        runtime_snapshot=OutputChannelSnapshot(values=[OutputChannelValue(name="rpm", value=950.0)]),
    )

    assert snapshot.connection_text == "Connection  connected"
    assert snapshot.source_text == "Source  ECU RAM"
    assert snapshot.runtime_text == "Runtime  1 channel(s)"
    assert snapshot.changes_text == "Changes  1 staged"
    assert "staged changes remain pending" in snapshot.summary_text.lower()
    assert "latest runtime sample is" in snapshot.summary_text.lower()


def test_build_surface_evidence_snapshot_warns_on_sync_mismatch() -> None:
    snapshot = build_surface_evidence_snapshot(
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(
            sync_state=SyncState(
                mismatches=(SyncMismatch(SyncMismatchKind.SIGNATURE_MISMATCH, "signature drift"),),
                has_ecu_ram=True,
                connection_state=SessionState.CONNECTED.value,
            ),
        ),
        runtime_snapshot=None,
    )

    assert snapshot.sync_text == "Sync  1 mismatch(s)"
    assert snapshot.sync_severity == "warning"
    assert "sync mismatches" in snapshot.summary_text.lower()


def test_workspace_project_state_serializes_and_round_trips() -> None:
    state = WorkspaceUiState(
        active_page_id="table-editor:ve",
        main_splitter_sizes=(260, 780, 300),
        workspace_splitter_sizes=(700, 180),
        details_tab_index=2,
        catalog_query="ve",
        catalog_kind="Tables / Maps",
    )

    metadata = serialize_workspace_project_state(1, state)
    tab_index, restored = deserialize_workspace_project_state(metadata)

    assert tab_index == 1
    assert restored == state


def test_update_recent_project_paths_dedupes_and_promotes_latest() -> None:
    paths = update_recent_project_paths(
        ("C:/Projects/A.project", "C:/Projects/B.project", "C:/Projects/A.project"),
        "C:/Projects/B.project",
        max_entries=3,
    )

    assert paths[0].endswith("B.project")
    assert len(paths) == 2
    assert any(path.endswith("A.project") for path in paths)


def test_choose_start_project_path_prefers_last_project_when_present(tmp_path) -> None:
    first = tmp_path / "A.project"
    second = tmp_path / "B.project"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")

    chosen = choose_start_project_path((first,), second)

    assert chosen == second


def test_choose_start_project_path_falls_back_to_recent_projects(tmp_path) -> None:
    first = tmp_path / "A.project"
    first.write_text("", encoding="utf-8")

    chosen = choose_start_project_path((first,), None)

    assert chosen == first


def test_build_recent_project_summaries_reads_project_metadata(tmp_path) -> None:
    project_dir = tmp_path / "Car"
    definition = project_dir / "speeduino.ini"
    tune = project_dir / "base.msq"
    definition.parent.mkdir(parents=True, exist_ok=True)
    definition.write_text("signature=Speeduino", encoding="utf-8")
    tune.write_text("<msq/>", encoding="utf-8")
    project = ProjectService().create_project(
        name="Car",
        project_directory=project_dir,
        ecu_definition_path=definition,
        tune_file_path=tune,
    )

    summaries = build_recent_project_summaries((project.project_path,), ProjectService())

    assert len(summaries) == 1
    assert summaries[0].name == "Car"
    assert summaries[0].ecu_definition_path == definition.resolve()
    assert summaries[0].tune_file_path == tune.resolve()


def test_create_project_opens_engine_setup_and_hardware_wizard(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])

    definition = tmp_path / "speeduino.ini"
    tune = tmp_path / "base.msq"
    definition.write_text("signature=Speeduino", encoding="utf-8")
    tune.write_text("<msq/>", encoding="utf-8")

    class _CreateProjectDialog:
        def __init__(self, parent=None) -> None:
            del parent

        def exec(self) -> int:
            return QDialog.DialogCode.Accepted

        def project_payload(self):
            return (
                "New Car",
                tmp_path / "project",
                definition,
                tune,
                ConnectionProfile(
                    name="offline",
                    transport=TransportType.MOCK.value,
                    protocol=ProtocolType.SPEEDUINO.value,
                ),
                {},
            )

    monkeypatch.setattr(main_window_module, "CreateProjectDialog", _CreateProjectDialog)
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)

    window = MainWindow()
    seen: list[bool] = []
    monkeypatch.setattr(window.engine_setup_panel, "open_hardware_setup_wizard", lambda: seen.append(True))
    monkeypatch.setattr(window, "connect_session", lambda: seen.append(False))
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", staticmethod(lambda _ms, fn: fn()))

    window.create_project()
    app.processEvents()

    assert window.tab_widget.currentIndex() == 2
    assert seen == [True]


def test_flash_bundle_summary_surfaces_manifest_pairings(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    firmware = tmp_path / "paired.hex"
    definition = tmp_path / "paired.ini"
    tune = tmp_path / "paired.msq"
    firmware.write_text("", encoding="utf-8")
    definition.write_text("signature=Speeduino", encoding="utf-8")
    tune.write_text("<msq/>", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": firmware.name,
                        "board_family": "TEENSY41",
                        "version": "v2.0.1",
                        "is_experimental": True,
                        "preferred": True,
                        "definition_file": definition.name,
                        "tune_file": tune.name,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()

    window.release_root_edit.setText(str(tmp_path))
    window.flash_firmware_edit.setText(str(firmware))
    app.processEvents()

    assert "paired.ini" in window.flash_bundle_label.text()
    assert "paired.msq" in window.flash_bundle_label.text()
    assert "preferred" in window.flash_bundle_label.text().lower()
    assert window.flash_load_definition_button.isEnabled() is True
    assert window.flash_load_tune_button.isEnabled() is True


def test_flash_bundle_buttons_load_paired_artifacts(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    firmware = tmp_path / "paired.hex"
    definition = tmp_path / "paired.ini"
    tune = tmp_path / "paired.msq"
    firmware.write_text("", encoding="utf-8")
    definition.write_text("signature=Speeduino", encoding="utf-8")
    tune.write_text("<msq/>", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": firmware.name,
                        "board_family": "TEENSY41",
                        "definition_file": definition.name,
                        "tune_file": tune.name,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    loaded: list[tuple[str, Path]] = []
    monkeypatch.setattr(window, "_load_definition_path", lambda path: loaded.append(("definition", path)))
    monkeypatch.setattr(window, "_load_tune_path", lambda path: loaded.append(("tune", path)))

    window.release_root_edit.setText(str(tmp_path))
    window.flash_firmware_edit.setText(str(firmware))
    app.processEvents()

    window.flash_load_definition_button.click()
    window.flash_load_tune_button.click()

    assert loaded == [
        ("definition", definition.resolve()),
        ("tune", tune.resolve()),
    ]


def test_flash_guidance_explains_teensy_experimental_reconnect_flow(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    firmware = tmp_path / "paired.hex"
    firmware.write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": firmware.name,
                        "board_family": "TEENSY41",
                        "is_experimental": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    monkeypatch.setattr(
        window.flash_target_detection_service,
        "detect_preferred_target",
        lambda preferred_board=None: DetectedFlashTarget(
            board_family=BoardFamily.TEENSY41,
            source="usb",
            description="Uninitialized Teensy 4.1",
        ),
    )

    window.release_root_edit.setText(str(tmp_path))
    window.flash_board_combo.setCurrentIndex(window.flash_board_combo.findData(BoardFamily.TEENSY41))
    window.flash_firmware_edit.setText(str(firmware))
    app.processEvents()

    guidance = window.flash_guidance_label.text().lower()
    assert "teensy41 / experimental" in guidance
    assert "bootloader usb target is present" in guidance
    assert "force a full power cycle" in guidance
    assert "load the paired ini and base tune" in guidance


def test_flash_guidance_explains_avr_serial_flash_path(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    monkeypatch.setattr(
        window.flash_target_detection_service,
        "detect_preferred_target",
        lambda preferred_board=None: DetectedFlashTarget(
            board_family=BoardFamily.ATMEGA2560,
            source="serial",
            description="COM8 (Arduino Mega)",
            serial_port="COM8",
        ),
    )

    window.flash_board_combo.setCurrentIndex(window.flash_board_combo.findData(BoardFamily.ATMEGA2560))
    window._refresh_flash_guidance()
    app.processEvents()

    guidance = window.flash_guidance_label.text().lower()
    assert "atmega2560 / production" in guidance
    assert "flash over serial on com8" in guidance
    assert "recover" in guidance


def test_flash_guidance_includes_runtime_persistence_warning(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window._last_runtime_snapshot = OutputChannelSnapshot(
        values=[
            OutputChannelValue(name="boardCapabilities", value=float(1 << 3)),
            OutputChannelValue(name="spiFlashHealth", value=0.0),
        ]
    )

    window._refresh_flash_guidance()
    app.processEvents()

    guidance = window.flash_guidance_label.text().lower()
    assert "do not trust burn persistence" in guidance


def test_runtime_telemetry_labels_show_decoded_speeduino_state(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()

    window._last_runtime_snapshot = OutputChannelSnapshot(
        values=[
            OutputChannelValue(name="boardCapabilities", value=float(0b01001000)),
            OutputChannelValue(name="spiFlashHealth", value=1.0),
            OutputChannelValue(name="runtimeStatusA", value=float(0b10010000)),
        ]
    )
    window.session_service.info.firmware_capabilities = FirmwareCapabilities(
        source="serial+definition",
        serial_protocol_version=2,
        blocking_factor=64,
        table_blocking_factor=128,
        live_data_size=148,
    )
    window._render_runtime_telemetry()
    app.processEvents()

    assert "Capability source: serial+definition" in window.runtime_capability_label.text()
    assert "serial protocol v2" in window.runtime_capability_label.text()
    assert "SPI flash healthy" in window.runtime_capability_label.text()
    assert "Tune learning is currently allowed" in window.runtime_capability_label.text()
    assert "burned changes should be treated as flash-backed" in window.runtime_capability_label.text().lower()
    assert "Tune Learn Valid" in window.flash_runtime_label.text()
    assert "burned changes should be treated as flash-backed" in window.flash_runtime_label.text().lower()
    assert "unrestricted interrupts" in window.runtime_capability_label.text().lower()


def test_shell_status_enriches_post_burn_note_with_signature_and_persistence(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window.definition = EcuDefinition(name="Speeduino", firmware_signature="speeduino 202501-T41")
    window.session_service.info.state = SessionState.CONNECTED

    class _Client:
        firmware_signature = "speeduino 202501-T41"

    window.session_service.client = _Client()
    window.tuning_workspace.presenter._post_burn_verification_text = (
        "Reconnect or read back from ECU and verify persisted values before trusting the burn."
    )
    window._last_runtime_snapshot = OutputChannelSnapshot(
        values=[
            OutputChannelValue(name="boardCapabilities", value=float(1 << 3)),
            OutputChannelValue(name="spiFlashHealth", value=1.0),
        ]
    )

    window._render_shell_status()
    app.processEvents()

    text = window.shell_next_steps_label.text().lower()
    assert "verify persisted values before trusting the burn" in text
    assert "signature matches the loaded definition" in text
    assert "flash-backed" in text


def test_trigger_log_surface_analyzes_csv_against_loaded_decoder_context(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window.definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08"),
            ScalarParameterDefinition(name="sparkMode", data_type="U08"),
            ScalarParameterDefinition(name="nTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
        ],
    )
    tune = TuneFile(
        constants=[
            TuneValue(name="TrigPattern", value=0.0),
            TuneValue(name="sparkMode", value=3.0),
            TuneValue(name="nTeeth", value=36.0),
            TuneValue(name="missingTeeth", value=1.0),
        ]
    )
    window.tune_file = tune
    window.local_tune_edit_service.set_tune_file(tune)
    window._last_runtime_snapshot = OutputChannelSnapshot(values=[OutputChannelValue(name="rSA_fullSync", value=0.0)])
    csv_path = tmp_path / "tooth.csv"
    csv_path.write_text(
        "timeMs,tooth\n"
        "0.0,1\n"
        "1.0,1\n"
        "2.0,1\n"
        "3.0,1\n"
        "4.0,1\n"
        "5.0,1\n",
        encoding="utf-8",
    )

    window.trigger_log_path_edit.setText(str(csv_path))
    window._analyze_trigger_log()
    app.processEvents()

    assert "capture: tooth log" in window.trigger_log_summary_label.text().lower()
    assert "missing tooth" in window.trigger_log_decoder_label.text().lower()
    assert "full sync is currently not reported" in window.trigger_log_decoder_label.text().lower()
    assert "missing-tooth gap" in window.trigger_log_findings_label.text().lower()
    assert "visualization:" in window.trigger_log_visual_label.text().lower()
    assert "annotation" in window.trigger_log_visual_label.text().lower()


def test_execute_global_command_opens_trigger_logs_surface(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()

    window._execute_global_command("surface.trigger_logs")
    app.processEvents()

    assert window.tab_widget.tabText(window.tab_widget.currentIndex()) == "Trigger Logs"


def test_global_command_copy_evidence_uses_clipboard(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window._last_runtime_snapshot = OutputChannelSnapshot(
        values=[OutputChannelValue(name="rpm", value=950.0)]
    )
    window._render_surface_evidence()
    app.processEvents()

    copied: list[str] = []

    class _Clipboard:
        def setText(self, text: str) -> None:
            copied.append(text)

    monkeypatch.setattr(main_window_module.QApplication, "clipboard", staticmethod(lambda: _Clipboard()))

    window._execute_global_command("evidence.copy")

    assert copied
    assert "Evidence Summary:" in copied[0]


def test_export_latest_evidence_replay_writes_json_file(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window._last_runtime_snapshot = OutputChannelSnapshot(
        values=[OutputChannelValue(name="rpm", value=950.0)]
    )
    window._render_surface_evidence()
    app.processEvents()

    export_path = tmp_path / "evidence.json"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(export_path), "JSON Files (*.json)")),
    )

    window._export_latest_evidence_replay()

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["runtime_channel_count"] == 1
    assert payload["runtime_channels"][0]["name"] == "rpm"


def test_evidence_history_deduplicates_latest_signature(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window._evidence_replay_history.clear()
    window._last_evidence_replay_snapshot = None
    window._last_runtime_snapshot = OutputChannelSnapshot(
        values=[OutputChannelValue(name="rpm", value=950.0)]
    )

    window._render_surface_evidence()
    first_capture = window._evidence_replay_history[0].captured_at
    app.processEvents()
    window._render_surface_evidence()

    assert len(window._evidence_replay_history) == 1
    assert window._evidence_replay_history[0].captured_at >= first_capture


def test_global_command_opens_evidence_history_dialog(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window._evidence_replay_history.clear()
    window._last_evidence_replay_snapshot = None
    window._last_runtime_snapshot = OutputChannelSnapshot(
        values=[OutputChannelValue(name="rpm", value=950.0)]
    )
    window._render_surface_evidence()
    app.processEvents()

    seen: list[int] = []

    class _Dialog:
        def __init__(self, snapshots, parent=None) -> None:
            del parent
            seen.append(len(snapshots))
            self.selected_snapshot = None

        def exec(self) -> int:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "EvidenceReplayDialog", _Dialog)

    window._execute_global_command("evidence.history")

    assert seen == [1]


def test_evidence_history_can_pin_selected_snapshot_into_workspace(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window._evidence_replay_history.clear()
    window._last_evidence_replay_snapshot = None
    window._workspace_evidence_replay_snapshot = None
    window._last_runtime_snapshot = OutputChannelSnapshot(values=[OutputChannelValue(name="rpm", value=950.0)])
    window._render_surface_evidence()
    app.processEvents()
    selected = window._evidence_replay_history[0]

    class _Dialog:
        def __init__(self, snapshots, parent=None) -> None:
            del snapshots, parent
            self.selected_snapshot = selected

        def exec(self) -> int:
            return QDialog.DialogCode.Accepted

    seen: list[tuple[object, object]] = []
    monkeypatch.setattr(main_window_module, "EvidenceReplayDialog", _Dialog)
    monkeypatch.setattr(
        window.tuning_workspace,
        "set_evidence_review_snapshots",
        lambda snapshot, *, latest_snapshot=None: seen.append((snapshot, latest_snapshot)),
    )

    window._open_evidence_history_dialog()

    assert window._workspace_evidence_replay_snapshot is selected
    assert seen == [(selected, window._last_evidence_replay_snapshot)]


def test_use_latest_evidence_for_workspace_clears_pin(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window._evidence_replay_history.clear()
    window._last_evidence_replay_snapshot = None
    window._last_runtime_snapshot = OutputChannelSnapshot(values=[OutputChannelValue(name="rpm", value=950.0)])
    window._render_surface_evidence()
    app.processEvents()
    window._workspace_evidence_replay_snapshot = object()  # type: ignore[assignment]

    seen: list[tuple[object, object]] = []
    monkeypatch.setattr(
        window.tuning_workspace,
        "set_evidence_review_snapshots",
        lambda snapshot, *, latest_snapshot=None: seen.append((snapshot, latest_snapshot)),
    )

    window._execute_global_command("evidence.use_latest")

    assert window._workspace_evidence_replay_snapshot is None
    assert seen == [(window._last_evidence_replay_snapshot, window._last_evidence_replay_snapshot)]


def test_render_surface_evidence_keeps_pinned_review_but_updates_latest_comparison(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    window._evidence_replay_history.clear()
    window._last_evidence_replay_snapshot = None
    window._last_runtime_snapshot = OutputChannelSnapshot(values=[OutputChannelValue(name="rpm", value=950.0)])
    window._render_surface_evidence()
    app.processEvents()
    pinned = window._last_evidence_replay_snapshot
    window._workspace_evidence_replay_snapshot = pinned
    window._last_runtime_snapshot = OutputChannelSnapshot(values=[OutputChannelValue(name="rpm", value=1050.0)])

    seen: list[tuple[object, object]] = []
    monkeypatch.setattr(
        window.tuning_workspace,
        "set_evidence_review_snapshots",
        lambda snapshot, *, latest_snapshot=None: seen.append((snapshot, latest_snapshot)),
    )

    window._render_surface_evidence()

    assert seen
    assert seen[-1][0] is pinned
    assert seen[-1][1] is window._last_evidence_replay_snapshot


def test_runtime_panel_can_load_datalog_and_pin_replay_row(monkeypatch, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()
    path = tmp_path / "runtime.csv"
    path.write_text(
        "timeMs,rpm,map\n"
        "0,900,40\n"
        "500,1100,48\n",
        encoding="utf-8",
    )
    seen: list[tuple[object, object]] = []
    monkeypatch.setattr(
        window.tuning_workspace,
        "set_evidence_review_snapshots",
        lambda snapshot, *, latest_snapshot=None: seen.append((snapshot, latest_snapshot)),
    )

    window.logging_panel.set_datalog_path(str(path))
    window._load_datalog_csv(str(path))
    window.logging_panel._row_spin.setValue(2)
    app.processEvents()
    window._use_selected_datalog_replay()

    assert "Replay row 2 of 2" in window.logging_panel._datalog_summary_label.text()
    assert "rpm=1100.0" in window.logging_panel._datalog_preview.toPlainText()
    assert "Selected replay row 2" in window.logging_panel._chart_label.text()
    assert window._workspace_evidence_replay_snapshot is not None
    assert window._workspace_evidence_replay_snapshot.source_text == "Source  Datalog Replay"
    assert seen[-1][0] is window._workspace_evidence_replay_snapshot


def test_connected_speeduino_hint_uses_runtime_capability_guidance(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_maybe_show_start_dialog", lambda self: None)
    window = MainWindow()

    window.transport_combo.setCurrentIndex(window.transport_combo.findData(TransportType.SERIAL))
    window.protocol_combo.setCurrentIndex(window.protocol_combo.findData(ProtocolType.SPEEDUINO))
    window.session_service.info.state = SessionState.CONNECTED
    window._last_runtime_snapshot = OutputChannelSnapshot(
        values=[
            OutputChannelValue(name="boardCapabilities", value=float(0b00000100)),
            OutputChannelValue(name="spiFlashHealth", value=0.0),
        ]
    )
    window._update_connection_inputs()
    app.processEvents()

    hint = window.connection_hint_label.text().lower()
    assert "native speeduino serial is available" in hint
    assert "does not advertise unrestricted interrupts" in hint
    assert "spi flash unavailable" in hint


def test_build_recent_project_summaries_falls_back_for_invalid_project(tmp_path) -> None:
    broken = tmp_path / "broken.project"
    broken.write_text("not=a\nvalid=line", encoding="utf-8")

    summaries = build_recent_project_summaries((broken,), ProjectService())

    assert len(summaries) == 1
    assert summaries[0] == RecentProjectSummary(
        path=broken,
        name="broken",
        ecu_definition_path=None,
        tune_file_path=None,
    )


def test_format_recent_project_menu_label_includes_name_and_path(tmp_path) -> None:
    summary = RecentProjectSummary(
        path=tmp_path / "car.project",
        name="Track Car",
        ecu_definition_path=None,
        tune_file_path=None,
    )

    label = format_recent_project_menu_label(summary)

    assert label == f"Track Car  [{summary.path}]"


def test_controller_signature_matches_definition_normalizes_case_and_spacing() -> None:
    assert controller_signature_matches_definition(
        "speeduino   202501-T41-U16P2",
        "Speeduino 202501-T41-U16P2",
    ) is True


def test_controller_signature_matches_definition_detects_mismatch() -> None:
    assert controller_signature_matches_definition(
        "speeduino 202501-T41",
        "speeduino 202501-T41-U16P2",
    ) is False


def test_iter_speeduino_probe_candidates_promotes_selected_port_first() -> None:
    config = ConnectionConfig(
        transport=TransportType.SERIAL,
        protocol=ProtocolType.SPEEDUINO,
        serial_port="COM7",
        baud_rate=230400,
    )

    candidates = _iter_speeduino_probe_candidates(config, serial_port_supplier=lambda: ["COM3", "COM7", "COM9"])

    assert candidates[0].serial_port == "COM7"
    assert candidates[0].baud_rate == 230400
    assert any(candidate.serial_port == "COM3" for candidate in candidates)
    assert any(candidate.serial_port == "COM9" for candidate in candidates)


def test_probe_connection_config_discovers_reachable_speeduino_port() -> None:
    config = ConnectionConfig(
        transport=TransportType.SERIAL,
        protocol=ProtocolType.SPEEDUINO,
        serial_port="COM1",
        baud_rate=115200,
    )
    definition = EcuDefinition(
        name="Speeduino",
        query_command="Q",
        version_info_command="S",
        metadata={"controllerConnectDelay": "0"},
    )
    factory = _ProbeTransportFactory(
        {
            "COM1": _ProbeTransport(fail_open=True),
            "COM9": _ProbeTransport(signature=b"speeduino 202501-T41"),
        }
    )

    result = probe_connection_config(
        config,
        definition,
        factory,
        serial_port_supplier=lambda: ["COM9"],
    )

    assert result.config.serial_port == "COM9"
    assert result.controller_name == "Speeduino"
    assert result.attempts == [
        "COM1 @ 115200: port unavailable",
        "COM9 @ 115200: connected",
    ]


def test_probe_connection_config_raises_for_non_speeduino_failure() -> None:
    config = ConnectionConfig(
        transport=TransportType.TCP,
        protocol=ProtocolType.SIM_JSON,
        host="127.0.0.1",
        port=29000,
    )
    factory = _ProbeTransportFactory({"default": _ProbeTransport(fail_open=True)})

    try:
        probe_connection_config(config, None, factory)
    except RuntimeError as exc:
        assert str(exc) == "port unavailable"
    else:
        raise AssertionError("Expected probe_connection_config() to raise for an unreachable non-serial controller.")


def test_build_shell_status_snapshot_prefers_project_tune_when_offline() -> None:
    snapshot = build_shell_status_snapshot(
        project=Project(name="Track Car"),
        definition=EcuDefinition(name="Speeduino", firmware_signature="sig-a"),
        tune_file=TuneFile(signature="sig-a"),
        session_info=SessionInfo(state=SessionState.DISCONNECTED),
        workspace_snapshot=_workspace_snapshot(),
    )

    assert snapshot.project_text == "Project  Track Car"
    assert snapshot.source_text == "Source  Project Tune"
    assert snapshot.signature_text == "Signatures  match"
    assert snapshot.next_steps_text == "Project loaded offline. Connect to the controller or continue editing the project tune."
    assert snapshot.actions[0].label == "Connect"
    assert snapshot.actions[0].enabled is True
    assert snapshot.actions[1].enabled is False
    assert snapshot.primary_action_id == "session.toggle"


def test_build_shell_status_snapshot_uses_ecu_ram_when_connected() -> None:
    snapshot = build_shell_status_snapshot(
        project=Project(name="Track Car"),
        definition=EcuDefinition(name="Speeduino"),
        tune_file=TuneFile(signature="sig-a"),
        session_info=SessionInfo(state=SessionState.CONNECTED, controller_name="Speeduino"),
        workspace_snapshot=_workspace_snapshot(
            sync_state=SyncState(mismatches=(), has_ecu_ram=True, connection_state=SessionState.CONNECTED.value),
        ),
    )

    assert snapshot.session_text == "Session  connected"
    assert snapshot.source_text == "Source  ECU RAM"
    assert snapshot.next_steps_text == "Connected to the controller. Refresh from ECU or continue editing with ECU RAM as the active source."
    assert snapshot.actions[0].label == "Disconnect"
    assert snapshot.actions[1].enabled is True
    assert snapshot.primary_action_id == "session.refresh"


def test_build_shell_status_snapshot_flags_signature_mismatch() -> None:
    snapshot = build_shell_status_snapshot(
        project=Project(name="Track Car"),
        definition=EcuDefinition(name="Speeduino", firmware_signature="sig-a"),
        tune_file=TuneFile(signature="sig-b"),
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(
            sync_state=SyncState(
                mismatches=(SyncMismatch(SyncMismatchKind.SIGNATURE_MISMATCH, "signature drift"),),
                has_ecu_ram=True,
                connection_state=SessionState.CONNECTED.value,
            ),
        ),
    )

    assert snapshot.signature_text == "Signatures  mismatch"
    assert snapshot.signature_severity == "warning"
    assert snapshot.next_steps_text == "1 mismatch(s) need review before trusting writes or burns."
    assert snapshot.primary_action_id == "workspace.review"


def test_build_shell_status_snapshot_promotes_review_for_staged_changes() -> None:
    snapshot = build_shell_status_snapshot(
        project=Project(name="Track Car"),
        definition=EcuDefinition(name="Speeduino"),
        tune_file=TuneFile(signature="sig-a"),
        session_info=SessionInfo(state=SessionState.DISCONNECTED),
        workspace_snapshot=_workspace_snapshot(staged_count=2, hardware_count=1),
    )

    assert snapshot.source_text == "Source  Staged Tune"
    assert snapshot.staged_text == "Staged  2"
    assert snapshot.hardware_text == "Hardware  1"
    assert snapshot.actions[2].enabled is True
    assert snapshot.next_steps_text == "1 hardware issue(s) should be reviewed before applying tune changes."
    assert snapshot.primary_action_id == "workspace.review"


def test_build_shell_status_snapshot_prefers_post_burn_verification_note() -> None:
    snapshot = build_shell_status_snapshot(
        project=Project(name="Track Car"),
        definition=EcuDefinition(name="Speeduino"),
        tune_file=TuneFile(signature="sig-a"),
        session_info=SessionInfo(state=SessionState.CONNECTED),
        workspace_snapshot=_workspace_snapshot(
            sync_state=SyncState(mismatches=(), has_ecu_ram=True, connection_state=SessionState.CONNECTED.value),
            post_burn_verification_text="Reconnect and verify persisted values before trusting the burn.",
        ),
    )

    assert snapshot.next_steps_text == "Reconnect and verify persisted values before trusting the burn."
