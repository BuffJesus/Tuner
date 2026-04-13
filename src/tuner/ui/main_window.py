from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
import os
import time
from typing import Callable

from PySide6.QtCore import QSettings, QThread, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QMenu,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tuner.app.paths import bundled_tools_root
from tuner.domain.connection import ConnectionConfig, ProtocolType, TransportType
from tuner.domain.ecu_definition import EcuDefinition, SettingGroupDefinition
from tuner.domain.firmware import BoardFamily, FirmwareFlashRequest, FlashPreflightReport
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.domain.project import ConnectionProfile, Project
from tuner.domain.session import SessionInfo, SessionState
from tuner.domain.tune import TuneFile
from tuner.services.board_detection_service import BoardDetectionService
from tuner.domain.datalog_profile import DatalogProfile
from tuner.services.datalog_import_service import DatalogImportService, DatalogImportSnapshot
from tuner.services.datalog_profile_service import DatalogProfileService
from tuner.services.datalog_replay_service import DatalogReplayService, DatalogReplaySelectionSnapshot
from tuner.services.datalog_review_service import DatalogReviewService
from tuner.services.live_capture_session_service import LiveCaptureSessionService
from tuner.services.definition_service import DefinitionService
from tuner.services.evidence_replay_service import EvidenceReplayService, EvidenceReplaySnapshot
from tuner.services.evidence_replay_formatter_service import EvidenceReplayFormatterService
from tuner.services.firmware_catalog_service import FirmwareCatalogEntry, FirmwareCatalogService
from tuner.services.firmware_flash_service import FirmwareFlashService
from tuner.services.flash_preflight_service import FlashPreflightService
from tuner.services.flash_target_detection_service import FlashTargetDetectionService
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService
from tuner.services.parameter_catalog_service import ParameterCatalogService
from tuner.services.project_service import ProjectService
from tuner.services.session_service import SessionService
from tuner.services.surface_evidence_service import SurfaceEvidenceService, SurfaceEvidenceSnapshot
from tuner.services.speeduino_runtime_telemetry_service import SpeeduinoRuntimeTelemetryService
from tuner.services.staged_change_service import StagedChangeService
from tuner.services.table_view_service import TableViewService
from tuner.services.tuning_page_service import TuningPageService
from tuner.services.tune_file_service import TuneFileService
from tuner.services.trigger_log_analysis_service import TriggerLogAnalysisService
from tuner.services.trigger_log_visualization_service import TriggerLogVisualizationService
from tuner.services.live_data_http_server import LiveDataHttpServer
from tuner.services.live_trigger_logger_service import LiveTriggerLoggerService
from tuner.ui.hardware_test_panel import HardwareTestPanel
from tuner.ui.wideband_calibration_panel import WidebandCalibrationPanel
from tuner.parsers.ini_parser import IniParser
from tuner.simulator.protocol_simulator import ProtocolSimulatorServer
from tuner.simulator.xcp_simulator import XcpSimulatorServer
from tuner.transports.serial_ports import available_serial_ports
from tuner.transports.transport_factory import TransportFactory
from tuner.ui.dashboard_panel import DashboardPanel
from tuner.ui.engine_setup_panel import EngineSetupPanel
from tuner.ui.logging_panel import LoggingPanel
from tuner.ui.tuning_workspace import (
    TuningWorkspacePanel,
    WorkspaceActionEntry,
    WorkspacePageEntry,
    WorkspaceUiState,
    emit_table_debug_log,
)


class FlashWorker(QThread):
    progress_changed = Signal(int)
    status_changed = Signal(str)
    finished_result = Signal(int, str)
    failed = Signal(str)

    def __init__(self, service: FirmwareFlashService, request: FirmwareFlashRequest) -> None:
        super().__init__()
        self.service = service
        self.request = request
        self._last_status_message: str | None = None

    def run(self) -> None:
        try:
            result = self.service.flash(self.request, progress_callback=self._on_progress)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_result.emit(result.exit_code, result.output)

    def _on_progress(self, progress: object) -> None:
        if getattr(progress, "percent", None) is not None:
            self.progress_changed.emit(int(progress.percent))
        message = str(getattr(progress, "message", ""))
        if message and message != self._last_status_message:
            self.status_changed.emit(message)
            self._last_status_message = message


class ConnectionTestWorker(QThread):
    status_changed = Signal(str)
    succeeded = Signal(str, str, int)
    failed = Signal(str)

    def __init__(self, config: ConnectionConfig, definition: EcuDefinition | None) -> None:
        super().__init__()
        self.config = config
        self.definition = definition
        self._last_probe_attempts: list[str] = []

    def run(self) -> None:
        try:
            result = probe_connection_config(
                self.config,
                self.definition,
                TransportFactory(),
                status_callback=self.status_changed.emit,
            )
        except Exception as exc:
            diagnostic = self._format_probe_attempts(self._last_probe_attempts)
            if diagnostic:
                self.failed.emit(f"Connection failed: {exc}\n{diagnostic}")
            else:
                self.failed.emit(f"Connection failed: {exc}")
            return
        self._last_probe_attempts = result.attempts
        controller_name = result.controller_name or "controller responded"
        self.succeeded.emit(
            controller_name,
            result.config.serial_port or "",
            result.config.baud_rate,
        )

    @staticmethod
    def _status_message(port: str | None, baud_rate: int) -> str:
        if port:
            return f"Testing {port} @ {baud_rate}..."
        return f"Testing serial connection @ {baud_rate}..."

    @staticmethod
    def _format_probe_attempts(attempts: list[str]) -> str:
        if not attempts:
            return ""
        return "Tried:\n" + "\n".join(attempts[:8])


@dataclass(slots=True)
class ConnectionProbeResult:
    config: ConnectionConfig
    controller_name: str | None = None
    attempts: list[str] | None = None


class TriggerCaptureWorker(QThread):
    """Background thread that runs a live trigger logger capture."""
    succeeded = Signal(object)   # TriggerLogCapture
    failed = Signal(str)

    def __init__(self, client: object, logger_def: object, service: LiveTriggerLoggerService) -> None:
        super().__init__()
        self._client = client
        self._logger_def = logger_def
        self._service = service

    def run(self) -> None:
        try:
            raw = self._client.fetch_logger_data(self._logger_def)
            capture = self._service.decode(self._logger_def, raw)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(capture)


class ProjectAutoConnectWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        config: ConnectionConfig,
        definition: EcuDefinition | None,
        expected_project_path: Path | None,
    ) -> None:
        super().__init__()
        self.config = config
        self.definition = definition
        self.expected_project_path = expected_project_path

    def run(self) -> None:
        try:
            result = probe_connection_config(self.config, self.definition, TransportFactory())
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


def probe_connection_config(
    config: ConnectionConfig,
    definition: EcuDefinition | None,
    transport_factory: TransportFactory,
    *,
    status_callback: Callable[[str], None] | None = None,
    serial_port_supplier: Callable[[], list[str]] = available_serial_ports,
) -> ConnectionProbeResult:
    session_service = SessionService(transport_factory=transport_factory)
    if definition is not None:
        session_service.set_definition(definition)
    attempts: list[str] = []
    try:
        _emit_probe_status(config, status_callback)
        try:
            info = session_service.connect(config)
            return ConnectionProbeResult(
                config=config,
                controller_name=info.controller_name,
                attempts=attempts,
            )
        except Exception as exc:
            if config.transport != TransportType.SERIAL or config.protocol != ProtocolType.SPEEDUINO:
                raise
            attempts.append(f"{config.serial_port} @ {config.baud_rate}: {exc}")
        for candidate in _iter_speeduino_probe_candidates(config, serial_port_supplier):
            if candidate == config:
                continue
            _emit_probe_status(candidate, status_callback)
            try:
                info = session_service.connect(candidate)
                attempts.append(f"{candidate.serial_port} @ {candidate.baud_rate}: connected")
                return ConnectionProbeResult(
                    config=candidate,
                    controller_name=info.controller_name,
                    attempts=attempts,
                )
            except Exception as exc:
                attempts.append(f"{candidate.serial_port} @ {candidate.baud_rate}: {exc}")
                continue
    finally:
        session_service.disconnect()
    raise RuntimeError("No controller responded to the saved connection profile.")


def _iter_speeduino_probe_candidates(
    base_config: ConnectionConfig,
    serial_port_supplier: Callable[[], list[str]] = available_serial_ports,
) -> tuple[ConnectionConfig, ...]:
    ports = [port for port in serial_port_supplier() if port]
    candidate_ports = [base_config.serial_port] if base_config.serial_port else []
    candidate_ports.extend(port for port in ports if port != base_config.serial_port)
    candidate_bauds: list[int] = []
    for baud in (base_config.baud_rate, 115200, 230400, 57600, 9600):
        if baud > 0 and baud not in candidate_bauds:
            candidate_bauds.append(baud)
    candidates: list[ConnectionConfig] = []
    for baud in candidate_bauds:
        for port in candidate_ports:
            candidates.append(
                ConnectionConfig(
                    transport=TransportType.SERIAL,
                    protocol=ProtocolType.SPEEDUINO,
                    serial_port=port,
                    baud_rate=baud,
                    host=base_config.host,
                    port=base_config.port,
                )
            )
    return tuple(candidates)


def _emit_probe_status(
    config: ConnectionConfig,
    status_callback: Callable[[str], None] | None,
) -> None:
    if status_callback is None:
        return
    if config.transport == TransportType.SERIAL:
        if config.serial_port:
            status_callback(f"Testing {config.serial_port} @ {config.baud_rate}...")
        else:
            status_callback(f"Testing serial connection @ {config.baud_rate}...")
        return
    status_callback(f"Testing {config.display_name()}...")


@dataclass(slots=True, frozen=True)
class ShellStatusAction:
    action_id: str
    label: str
    enabled: bool


@dataclass(slots=True, frozen=True)
class ShellStatusSnapshot:
    project_text: str
    session_text: str
    source_text: str
    signature_text: str
    staged_text: str
    hardware_text: str
    project_severity: str
    session_severity: str
    source_severity: str
    signature_severity: str
    staged_severity: str
    hardware_severity: str
    next_steps_text: str
    actions: tuple[ShellStatusAction, ...]
    primary_action_id: str | None


@dataclass(slots=True, frozen=True)
class SurfaceModeSnapshot:
    mode_label: str
    title: str
    description: str
    emphasis: str


def build_shell_status_snapshot(
    *,
    project: Project | None,
    definition: EcuDefinition | None,
    tune_file: TuneFile | None,
    session_info: SessionInfo,
    workspace_snapshot,
) -> ShellStatusSnapshot:
    sync_state = workspace_snapshot.sync_state if workspace_snapshot is not None else None
    staged_count = len(workspace_snapshot.workspace_review.entries) if workspace_snapshot is not None else 0
    hardware_count = len(workspace_snapshot.hardware_issues) if workspace_snapshot is not None else 0
    mismatch_count = len(sync_state.mismatches) if sync_state is not None else 0
    connected = session_info.state == SessionState.CONNECTED
    has_project = project is not None
    has_definition = definition is not None
    has_tune = tune_file is not None

    project_text = f"Project  {project.name}" if has_project else "Project  none"
    project_severity = "info" if has_project else "warning"

    session_text = f"Session  {session_info.state.value if session_info.state else 'unknown'}"
    session_severity = "accent" if connected else "info"

    if connected and sync_state is not None and sync_state.has_ecu_ram:
        source_text = "Source  ECU RAM"
        source_severity = "accent"
    elif staged_count:
        source_text = "Source  Staged Tune"
        source_severity = "accent"
    elif has_tune:
        source_text = "Source  Project Tune"
        source_severity = "ok"
    elif has_definition:
        source_text = "Source  Definition Only"
        source_severity = "warning"
    else:
        source_text = "Source  No Context"
        source_severity = "warning"

    signature_mismatch = any(
        mismatch.kind.value == "signature_mismatch"
        for mismatch in (sync_state.mismatches if sync_state is not None else ())
    )
    page_mismatch = any(
        mismatch.kind.value == "page_size_mismatch"
        for mismatch in (sync_state.mismatches if sync_state is not None else ())
    )
    if signature_mismatch:
        signature_text = "Signatures  mismatch"
        signature_severity = "warning"
    elif page_mismatch:
        signature_text = "Signatures  page mismatch"
        signature_severity = "warning"
    elif has_definition and has_tune and definition.firmware_signature and tune_file.signature:
        signature_text = "Signatures  match"
        signature_severity = "ok"
    else:
        signature_text = "Signatures  unknown"
        signature_severity = "info"

    staged_text = f"Staged  {staged_count}"
    staged_severity = "accent" if staged_count else "ok"
    hardware_text = f"Hardware  {hardware_count}"
    hardware_severity = "warning" if hardware_count else "ok"

    if mismatch_count:
        next_steps_text = f"{mismatch_count} mismatch(s) need review before trusting writes or burns."
    elif hardware_count:
        next_steps_text = f"{hardware_count} hardware issue(s) should be reviewed before applying tune changes."
    elif workspace_snapshot is not None and workspace_snapshot.post_burn_verification_text:
        next_steps_text = workspace_snapshot.post_burn_verification_text
    elif staged_count and connected:
        next_steps_text = "Staged changes are ready to review and write to ECU RAM."
    elif staged_count:
        next_steps_text = "Staged changes are local only. Connect when ready to write or stay offline to keep editing."
    elif connected and sync_state is not None and sync_state.has_ecu_ram:
        next_steps_text = "Connected to the controller. Refresh from ECU or continue editing with ECU RAM as the active source."
    elif has_project and has_definition:
        next_steps_text = "Project loaded offline. Connect to the controller or continue editing the project tune."
    elif has_definition:
        next_steps_text = "Definition loaded. Open a tune or read from ECU to start a real editing session."
    else:
        next_steps_text = "Open a project, definition, or tune to begin."

    actions = (
        ShellStatusAction("session.toggle", "Disconnect" if connected else "Connect", has_definition or connected),
        ShellStatusAction("session.refresh", "Refresh ECU", connected),
        ShellStatusAction("workspace.review", "Review Changes", staged_count > 0),
    )
    if mismatch_count or hardware_count or staged_count:
        primary_action_id = "workspace.review"
    elif connected:
        primary_action_id = "session.refresh"
    elif has_definition or has_project:
        primary_action_id = "session.toggle"
    else:
        primary_action_id = None
    return ShellStatusSnapshot(
        project_text=project_text,
        session_text=session_text,
        source_text=source_text,
        signature_text=signature_text,
        staged_text=staged_text,
        hardware_text=hardware_text,
        project_severity=project_severity,
        session_severity=session_severity,
        source_severity=source_severity,
        signature_severity=signature_severity,
        staged_severity=staged_severity,
        hardware_severity=hardware_severity,
        next_steps_text=next_steps_text,
        actions=actions,
        primary_action_id=primary_action_id,
    )


def build_surface_mode_snapshot(tab_text: str) -> SurfaceModeSnapshot:
    normalized = tab_text.strip().lower()
    if normalized == "overview":
        return SurfaceModeSnapshot(
            mode_label="Overview",
            title="Session Overview",
            description="Review project context, loaded assets, and workspace-wide staged changes before diving into a specific editing surface.",
            emphasis="secondary",
        )
    if normalized == "tuning":
        return SurfaceModeSnapshot(
            mode_label="Tuning",
            title="Calibration Editing",
            description="Edit tables and scalar pages, review staged diffs, and manage write or burn decisions from the main tuning workspace.",
            emphasis="primary",
        )
    if normalized == "engine setup":
        return SurfaceModeSnapshot(
            mode_label="Engine Setup",
            title="Guided Hardware Configuration",
            description="Work through setup-driven ignition, fueling, and sensor dependencies with guided checks instead of hunting through raw pages.",
            emphasis="primary",
        )
    if normalized in {"flash", "tools / flash"}:
        return SurfaceModeSnapshot(
            mode_label="Tools / Flash",
            title="Firmware Tools And Recovery",
            description="Handle board detection, target selection, firmware preflight, and recovery workflows without mixing them into live tuning.",
            emphasis="warning",
        )
    if normalized == "dashboard":
        return SurfaceModeSnapshot(
            mode_label="Dashboard",
            title="Live Gauge Cluster",
            description="Monitor live runtime channels on a configurable gauge cluster. Layout is saved alongside the project and updates on every runtime poll.",
            emphasis="accent",
        )
    if normalized in {"trigger logs", "trigger log"}:
        return SurfaceModeSnapshot(
            mode_label="Trigger Logs",
            title="Trigger Troubleshooting",
            description="Import tooth, composite, or trigger logs and compare them against the loaded Speeduino decoder context before trusting sync or timing behavior.",
            emphasis="accent",
        )
    return SurfaceModeSnapshot(
        mode_label="Runtime",
        title="Connection And Live Runtime",
        description="Manage connection state, simulator control, and live channels while keeping runtime operations separate from tune editing.",
        emphasis="accent",
    )


def build_surface_evidence_snapshot(
    *,
    session_info: SessionInfo,
    workspace_snapshot,
    runtime_snapshot: OutputChannelSnapshot | None,
) -> SurfaceEvidenceSnapshot:
    return SurfaceEvidenceService().build(
        session_info=session_info,
        workspace_snapshot=workspace_snapshot,
        runtime_snapshot=runtime_snapshot,
    )


class StartProjectDialog(QDialog):
    def __init__(
        self,
        recent_projects: tuple[RecentProjectSummary, ...] = (),
        suggested_project: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.selection = "continue"
        self.selected_project_path: Path | None = None
        self.setWindowTitle("Start")
        self.setModal(True)
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        title = QLabel("Project Workflow")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        body = QLabel(
            "Choose how to start. Projects let the app reopen the ECU definition and tune together, closer to the TunerStudio workflow."
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        recent_label = QLabel("Recent Projects")
        recent_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(recent_label)

        self.recent_projects_list = QListWidget()
        self.recent_projects_list.itemActivated.connect(self._choose_recent)
        for project in recent_projects:
            item = QListWidgetItem(project.name)
            item.setData(Qt.ItemDataRole.UserRole, str(project.path))
            item.setToolTip(str(project.path))
            self.recent_projects_list.addItem(item)
        self.recent_projects_list.currentItemChanged.connect(self._update_recent_preview)
        self.recent_projects_list.setEnabled(self.recent_projects_list.count() > 0)
        layout.addWidget(self.recent_projects_list, 1)

        self._recent_projects_by_path = {str(project.path): project for project in recent_projects}
        self.recent_project_preview = QTextEdit()
        self.recent_project_preview.setReadOnly(True)
        self.recent_project_preview.setMaximumHeight(110)
        layout.addWidget(self.recent_project_preview)
        if self.recent_projects_list.count():
            self.recent_projects_list.setCurrentRow(0)
        else:
            self.recent_project_preview.setPlainText("No recent projects saved.")

        button_row = QHBoxLayout()
        reopen_button = QPushButton("Reopen Last Project")
        reopen_button.setEnabled(suggested_project is not None)
        reopen_button.clicked.connect(lambda: self._choose_suggested(suggested_project))
        button_row.addWidget(reopen_button)

        new_button = QPushButton("New Project")
        new_button.clicked.connect(self._choose_new)
        button_row.addWidget(new_button)

        open_button = QPushButton("Browse Project")
        open_button.clicked.connect(self._choose_open)
        button_row.addWidget(open_button)

        continue_button = QPushButton("Continue Without Project")
        continue_button.clicked.connect(self.accept)
        button_row.addWidget(continue_button)
        layout.addLayout(button_row)

    def _choose_new(self) -> None:
        self.selection = "new"
        self.accept()

    def _choose_open(self) -> None:
        self.selection = "open"
        self.accept()

    def _choose_recent(self, item: QListWidgetItem) -> None:
        raw_path = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw_path, str):
            return
        self.selection = "recent"
        self.selected_project_path = Path(raw_path)
        self.accept()

    def _choose_suggested(self, path: Path | None) -> None:
        if path is None:
            return
        self.selection = "recent"
        self.selected_project_path = path
        self.accept()

    def _update_recent_preview(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if current is None:
            self.recent_project_preview.clear()
            return
        raw_path = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw_path, str):
            self.recent_project_preview.clear()
            return
        project = self._recent_projects_by_path.get(raw_path)
        if project is None:
            self.recent_project_preview.setPlainText(raw_path)
            return
        lines = [
            f"Project: {project.name}",
            f"Path: {project.path}",
            f"ECU Definition: {project.ecu_definition_path if project.ecu_definition_path else 'n/a'}",
            f"Tune File: {project.tune_file_path if project.tune_file_path else 'n/a'}",
        ]
        self.recent_project_preview.setPlainText("\n".join(lines))


class CreateProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Project")
        self.setModal(True)
        self.resize(620, 360)
        self._detected_signature: str | None = None
        self._last_probe_attempts: list[str] = []
        self.connection_test_worker: ConnectionTestWorker | None = None

        layout = QVBoxLayout(self)
        self.step_indicator = QLabel("")
        self.step_indicator.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self.step_indicator)
        self.step_stack = QStackedWidget()
        layout.addWidget(self.step_stack)

        details_page = QWidget()
        details_form = QFormLayout(details_page)

        self.project_name_edit = QLineEdit("MyCar")
        details_form.addRow("Project Name", self.project_name_edit)

        directory_row = QWidget()
        directory_layout = QHBoxLayout(directory_row)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        self.project_dir_edit = QLineEdit()
        directory_layout.addWidget(self.project_dir_edit, 1)
        browse_dir_button = QPushButton("Browse")
        browse_dir_button.clicked.connect(self._browse_project_dir)
        directory_layout.addWidget(browse_dir_button)
        details_form.addRow("Project Directory", directory_row)
        self.project_name_edit.textChanged.connect(self._sync_project_directory_hint)

        definition_row = QWidget()
        definition_layout = QHBoxLayout(definition_row)
        definition_layout.setContentsMargins(0, 0, 0, 0)
        self.definition_edit = QLineEdit()
        definition_layout.addWidget(self.definition_edit, 1)
        browse_definition_button = QPushButton("Browse")
        browse_definition_button.clicked.connect(self._browse_definition)
        definition_layout.addWidget(browse_definition_button)
        detect_definition_button = QPushButton("Detect")
        detect_definition_button.clicked.connect(self._detect_definition)
        definition_layout.addWidget(detect_definition_button)
        details_form.addRow("ECU Definition", definition_row)

        self.firmware_signature_label = QLabel("Firmware Signature: not detected")
        self.firmware_signature_label.setWordWrap(True)
        details_form.addRow("", self.firmware_signature_label)

        tune_row = QWidget()
        tune_layout = QHBoxLayout(tune_row)
        tune_layout.setContentsMargins(0, 0, 0, 0)
        self.tune_edit = QLineEdit()
        tune_layout.addWidget(self.tune_edit, 1)
        browse_tune_button = QPushButton("Browse")
        browse_tune_button.clicked.connect(self._browse_tune)
        tune_layout.addWidget(browse_tune_button)
        details_form.addRow("Tune File", tune_row)
        self.offline_setup_check = QCheckBox("Offline setup")
        details_form.addRow("", self.offline_setup_check)
        self.step_stack.addWidget(details_page)

        settings_page = QWidget()
        settings_form = QFormLayout(settings_page)
        self.lambda_display_combo = QComboBox()
        self.lambda_display_combo.addItems(["AFR", "Lambda"])
        settings_form.addRow("Lambda Display", self.lambda_display_combo)
        self.temperature_display_combo = QComboBox()
        self.temperature_display_combo.addItems(["Fahrenheit", "Celsius"])
        settings_form.addRow("Temperature", self.temperature_display_combo)
        self.pressure_display_combo = QComboBox()
        self.pressure_display_combo.addItems(["PSI", "kPa", "Bar"])
        settings_form.addRow("Pressure", self.pressure_display_combo)
        self.controller_in_use_combo = QComboBox()
        for board in BoardFamily:
            self.controller_in_use_combo.addItem(board.value, board)
        settings_form.addRow("Controller In Use", self.controller_in_use_combo)
        self.serial_mode_combo = QComboBox()
        self.serial_mode_combo.addItems(["Normal", "Bluetooth", "CAN passthrough"])
        settings_form.addRow("Serial Mode", self.serial_mode_combo)
        self.step_stack.addWidget(settings_page)

        connection_page = QWidget()
        connection_form = QFormLayout(connection_page)
        self.transport_combo = QComboBox()
        for transport in TransportType:
            self.transport_combo.addItem(transport.value.upper(), transport)
        self.transport_combo.currentIndexChanged.connect(self._update_connection_inputs)
        connection_form.addRow("Transport", self.transport_combo)
        self.protocol_combo = QComboBox()
        for protocol in ProtocolType:
            self.protocol_combo.addItem(protocol.value.upper(), protocol)
        self.protocol_combo.currentIndexChanged.connect(self._update_connection_inputs)
        connection_form.addRow("Protocol", self.protocol_combo)
        serial_port_row = QWidget()
        serial_port_layout = QHBoxLayout(serial_port_row)
        serial_port_layout.setContentsMargins(0, 0, 0, 0)
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setEditable(True)
        serial_port_layout.addWidget(self.serial_port_combo, 1)
        refresh_serial_button = QPushButton("Refresh")
        refresh_serial_button.clicked.connect(self._refresh_serial_ports)
        serial_port_layout.addWidget(refresh_serial_button)
        connection_form.addRow("Serial Port", serial_port_row)
        self.baud_rate_spin = QSpinBox()
        self.baud_rate_spin.setRange(1200, 3000000)
        self.baud_rate_spin.setValue(115200)
        connection_form.addRow("Baud Rate", self.baud_rate_spin)
        self.host_edit = QLineEdit("127.0.0.1")
        connection_form.addRow("Host", self.host_edit)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(29000)
        connection_form.addRow("Port", self.port_spin)
        connection_actions = QWidget()
        connection_actions_layout = QHBoxLayout(connection_actions)
        connection_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.connection_status_label = QLabel("Not tested")
        self.connection_status_label.setWordWrap(True)
        connection_actions_layout.addWidget(self.connection_status_label, 1)
        self.test_connection_button = QPushButton("Test Connection")
        self.test_connection_button.clicked.connect(self._test_connection)
        connection_actions_layout.addWidget(self.test_connection_button)
        connection_form.addRow("", connection_actions)
        self.step_stack.addWidget(connection_page)
        self._update_connection_inputs()

        self.help_label = QLabel("Create a project file that reopens the definition and tune together.")
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)

        actions = QHBoxLayout()
        self.back_button = QPushButton("< Back")
        self.back_button.clicked.connect(self._go_back)
        actions.addWidget(self.back_button)
        self.next_button = QPushButton("Next >")
        self.next_button.clicked.connect(self._go_next)
        actions.addWidget(self.next_button)
        actions.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)
        self.create_button = QPushButton("Create")
        self.create_button.clicked.connect(self._validate_and_accept)
        actions.addWidget(self.create_button)
        layout.addLayout(actions)
        self._refresh_serial_ports()
        self.transport_combo.setCurrentIndex(self.transport_combo.findData(TransportType.SERIAL))
        self.protocol_combo.setCurrentIndex(self.protocol_combo.findData(ProtocolType.SPEEDUINO))
        self._sync_project_directory_hint()
        self._update_step_state()

    def project_payload(self) -> tuple[str, Path, Path | None, Path | None, ConnectionProfile, dict[str, str]]:
        board = self.controller_in_use_combo.currentData()
        board_value = board.value if isinstance(board, BoardFamily) else str(board)
        transport = self.transport_combo.currentData()
        transport_value = transport.value if isinstance(transport, TransportType) else str(transport).lower()
        protocol = self.protocol_combo.currentData()
        protocol_value = protocol.value if isinstance(protocol, ProtocolType) else str(protocol).lower()
        return (
            self.project_name_edit.text().strip(),
            Path(self.project_dir_edit.text().strip()),
            Path(self.definition_edit.text().strip()) if self.definition_edit.text().strip() else None,
            Path(self.tune_edit.text().strip()) if self.tune_edit.text().strip() else None,
            ConnectionProfile(
                name="Default",
                transport=transport_value,
                protocol=protocol_value,
                host=self.host_edit.text().strip() or None,
                port=self.port_spin.value(),
                serial_port=self.serial_port_combo.currentText().strip() or None,
                baud_rate=self.baud_rate_spin.value(),
            ),
            {
                "lambdaDisplay": self.lambda_display_combo.currentText(),
                "temperatureDisplay": self.temperature_display_combo.currentText(),
                "pressureDisplay": self.pressure_display_combo.currentText(),
                "controllerInUse": board_value,
                "serialMode": self.serial_mode_combo.currentText(),
                "offlineSetup": "true" if self.offline_setup_check.isChecked() else "false",
                "firmwareSignature": self._detected_signature or "",
            },
        )

    def _validate_and_accept(self) -> None:
        name, project_dir, definition, tune, _, _ = self.project_payload()
        if not name:
            QMessageBox.warning(self, "Create Project", "Project name is required.")
            return
        if not self.project_dir_edit.text().strip():
            QMessageBox.warning(self, "Create Project", "Project directory is required.")
            return
        if definition is not None and not definition.exists():
            QMessageBox.warning(self, "Create Project", "Selected ECU definition file does not exist.")
            return
        if tune is not None and not tune.exists():
            QMessageBox.warning(self, "Create Project", "Selected tune file does not exist.")
            return
        self.accept()

    def _browse_project_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Project Directory", self.project_dir_edit.text())
        if path:
            self.project_dir_edit.setText(path)

    def _browse_definition(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open ECU Definition",
            "",
            "Definition Files (*.ini *.txt);;All Files (*.*)",
        )
        if path:
            self.definition_edit.setText(path)
            self._detect_definition()

    def _browse_tune(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Tune File",
            "",
            "Tune Files (*.msq);;All Files (*.*)",
        )
        if path:
            self.tune_edit.setText(path)

    def _update_connection_inputs(self) -> None:
        transport = self.transport_combo.currentData()
        protocol = self.protocol_combo.currentData()
        is_serial = transport == TransportType.SERIAL
        is_network = transport in {TransportType.TCP, TransportType.UDP}
        self.serial_port_combo.setEnabled(is_serial)
        self.baud_rate_spin.setEnabled(is_serial)
        self.host_edit.setEnabled(is_network)
        self.port_spin.setEnabled(is_network)
        self.test_connection_button.setEnabled(
            transport == TransportType.MOCK
            or protocol == ProtocolType.SPEEDUINO
            or protocol == ProtocolType.SIM_JSON
            or protocol == ProtocolType.XCP
        )

    def _detect_definition(self) -> None:
        raw_path = self.definition_edit.text().strip()
        if not raw_path:
            self._detected_signature = None
            self.firmware_signature_label.setText("Firmware Signature: not detected")
            return
        path = Path(raw_path)
        if not path.exists():
            self._detected_signature = None
            self.firmware_signature_label.setText("Firmware Signature: definition file not found")
            return
        try:
            definition = IniParser().parse(path)
        except Exception as exc:
            self._detected_signature = None
            self.firmware_signature_label.setText(f"Firmware Signature: detect failed ({exc})")
            return
        self._detected_signature = definition.firmware_signature or definition.name
        self.firmware_signature_label.setText(f"Firmware Signature: {self._detected_signature}")
        signature_lower = (self._detected_signature or "").lower()
        board = None
        if "t41" in signature_lower:
            board = BoardFamily.TEENSY41
        elif "t36" in signature_lower:
            board = BoardFamily.TEENSY36
        elif "t35" in signature_lower:
            board = BoardFamily.TEENSY35
        elif "stm32" in signature_lower or "dfu" in signature_lower:
            board = BoardFamily.STM32F407_DFU
        elif "mega" in signature_lower or "2560" in signature_lower:
            board = BoardFamily.ATMEGA2560
        if board is not None:
            index = self.controller_in_use_combo.findData(board)
            if index >= 0:
                self.controller_in_use_combo.setCurrentIndex(index)

    def _test_connection(self) -> None:
        if self.connection_test_worker is not None and self.connection_test_worker.isRunning():
            return
        config = self._connection_config()
        definition = self._connection_test_definition()
        self._set_connection_test_running(True)
        self.connection_status_label.setText("Testing connection... This can take several seconds.")
        worker = ConnectionTestWorker(config, definition)
        worker.status_changed.connect(self.connection_status_label.setText)
        worker.succeeded.connect(self._handle_connection_test_success)
        worker.failed.connect(self._handle_connection_test_failure)
        worker.finished.connect(self._finish_connection_test)
        self.connection_test_worker = worker
        worker.start()

    def _connection_test_definition(self) -> EcuDefinition | None:
        raw_path = self.definition_edit.text().strip()
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.exists():
            return None
        try:
            return IniParser().parse(path)
        except Exception:
            return None

    def _connection_config(self) -> ConnectionConfig:
        transport = self.transport_combo.currentData()
        protocol = self.protocol_combo.currentData()
        return ConnectionConfig(
            transport=transport if isinstance(transport, TransportType) else TransportType(str(transport)),
            protocol=protocol if isinstance(protocol, ProtocolType) else ProtocolType(str(protocol)),
            serial_port=self.serial_port_combo.currentText().strip(),
            baud_rate=self.baud_rate_spin.value(),
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
        )

    def _refresh_serial_ports(self) -> None:
        current = self.serial_port_combo.currentText().strip()
        ports = available_serial_ports()
        self.serial_port_combo.clear()
        self.serial_port_combo.addItems(ports or [""])
        preferred = current or ("COM3" if "COM3" in ports else "")
        if preferred:
            index = self.serial_port_combo.findText(preferred)
            if index >= 0:
                self.serial_port_combo.setCurrentIndex(index)
            else:
                self.serial_port_combo.setEditText(preferred)

    def _attempt_speeduino_serial_discovery(
        self,
        session_service: SessionService,
        base_config: ConnectionConfig,
    ) -> tuple[object, ConnectionConfig, list[str]] | None:
        ports = [port for port in available_serial_ports() if port]
        candidate_ports = [base_config.serial_port] if base_config.serial_port else []
        candidate_ports.extend(port for port in ports if port != base_config.serial_port)
        candidate_bauds: list[int] = []
        attempts: list[str] = []
        for baud in (base_config.baud_rate, 115200, 230400, 57600, 9600):
            if baud not in candidate_bauds:
                candidate_bauds.append(baud)
        for port in candidate_ports:
            for baud in candidate_bauds:
                candidate = ConnectionConfig(
                    transport=TransportType.SERIAL,
                    protocol=ProtocolType.SPEEDUINO,
                    serial_port=port,
                    baud_rate=baud,
                    host=base_config.host,
                    port=base_config.port,
                )
                try:
                    info = session_service.connect(candidate)
                    self._last_probe_attempts = attempts + [f"{port} @ {baud}: connected"]
                    return info, candidate, self._last_probe_attempts
                except Exception as exc:
                    attempts.append(f"{port} @ {baud}: {exc}")
                    continue
        self._last_probe_attempts = attempts
        return None

    def _format_probe_attempts(self, attempts: list[str]) -> str:
        if not attempts:
            return ""
        return "Tried:\n" + "\n".join(attempts[:8])

    def _handle_connection_test_success(self, controller_name: str, port: str, baud_rate: int) -> None:
        if port:
            port_index = self.serial_port_combo.findText(port)
            if port_index >= 0:
                self.serial_port_combo.setCurrentIndex(port_index)
            else:
                self.serial_port_combo.setEditText(port)
        if baud_rate > 0:
            self.baud_rate_spin.setValue(baud_rate)
        if port:
            self.connection_status_label.setText(f"Connected: {controller_name} on {port} @ {baud_rate}")
            return
        self.connection_status_label.setText(f"Connected: {controller_name}")

    def _handle_connection_test_failure(self, message: str) -> None:
        self.connection_status_label.setText(message)

    def _finish_connection_test(self) -> None:
        self._set_connection_test_running(False)
        self.connection_test_worker = None

    def _set_connection_test_running(self, running: bool) -> None:
        self.test_connection_button.setEnabled(not running)
        self.back_button.setEnabled(not running and self.step_stack.currentIndex() > 0)
        self.next_button.setEnabled(not running and self.step_stack.currentIndex() < self.step_stack.count() - 1)
        self.create_button.setEnabled(not running and self.step_stack.currentIndex() == self.step_stack.count() - 1)
        self.cancel_button.setEnabled(not running)

    def _sync_project_directory_hint(self) -> None:
        if self.project_dir_edit.text().strip():
            return
        base = Path.home() / "TunerProjects" / (self.project_name_edit.text().strip() or "MyCar")
        self.project_dir_edit.setText(str(base))

    def _go_back(self) -> None:
        current = self.step_stack.currentIndex()
        if current > 0:
            self.step_stack.setCurrentIndex(current - 1)
            self._update_step_state()

    def _go_next(self) -> None:
        current = self.step_stack.currentIndex()
        if current == 0:
            name, project_dir, definition, tune, _, _ = self.project_payload()
            if not name or not self.project_dir_edit.text().strip():
                QMessageBox.warning(self, "Create Project", "Project name and directory are required.")
                return
            if definition is not None and not definition.exists():
                QMessageBox.warning(self, "Create Project", "Selected ECU definition file does not exist.")
                return
            if tune is not None and not tune.exists():
                QMessageBox.warning(self, "Create Project", "Selected tune file does not exist.")
                return
        if current < self.step_stack.count() - 1:
            self.step_stack.setCurrentIndex(current + 1)
            self._update_step_state()

    def _update_step_state(self) -> None:
        current = self.step_stack.currentIndex()
        titles = ["1. Project", "2. Settings", "3. Connection"]
        help_texts = [
            "Choose the project name, folder, firmware definition, and optional tune baseline.",
            "Set display units and controller defaults for this project.",
            "Set the default connection profile that should be restored with the project.",
        ]
        self.step_indicator.setText(titles[current])
        self.help_label.setText(help_texts[current])
        self.back_button.setEnabled(current > 0)
        self.next_button.setVisible(current < self.step_stack.count() - 1)
        self.create_button.setVisible(current == self.step_stack.count() - 1)


class QuickOpenDialog(QDialog):
    def __init__(self, entries: tuple[WorkspacePageEntry, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries = entries
        self.selected_page_id: str | None = None
        self.setWindowTitle("Quick Open")
        self.setModal(True)
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter pages by title, group, state, or summary")
        self.search_edit.textChanged.connect(self._populate_results)
        layout.addWidget(self.search_edit)

        self.results_list = QListWidget()
        self.results_list.itemActivated.connect(self._accept_item)
        layout.addWidget(self.results_list, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        open_button = QPushButton("Open")
        open_button.clicked.connect(self._accept_current)
        button_row.addWidget(open_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        self._populate_results("")
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _populate_results(self, query: str) -> None:
        terms = [term for term in query.lower().split() if term]
        self.results_list.clear()
        for entry in self._entries:
            haystack = " ".join((entry.title, entry.group_title, entry.state_label, entry.summary, entry.kind)).lower()
            if any(term not in haystack for term in terms):
                continue
            item = QListWidgetItem(f"{entry.title}  [{entry.group_title}]  {entry.state_label}")
            item.setData(Qt.ItemDataRole.UserRole, entry.page_id)
            item.setToolTip(entry.summary)
            self.results_list.addItem(item)
        if self.results_list.count():
            self.results_list.setCurrentRow(0)

    def _accept_current(self) -> None:
        item = self.results_list.currentItem()
        if item is None:
            return
        self._accept_item(item)

    def _accept_item(self, item: QListWidgetItem) -> None:
        page_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(page_id, str):
            self.selected_page_id = page_id
            self.accept()


@dataclass(slots=True, frozen=True)
class CommandPaletteEntry:
    entry_id: str
    title: str
    category: str
    summary: str
    target: str


def build_command_palette_entries(
    page_entries: tuple[WorkspacePageEntry, ...],
    action_entries: tuple[WorkspaceActionEntry, ...],
    global_entries: tuple[CommandPaletteEntry, ...] = (),
) -> tuple[CommandPaletteEntry, ...]:
    entries: list[CommandPaletteEntry] = list(global_entries)
    for entry in action_entries:
        entries.append(
            CommandPaletteEntry(
                entry_id=entry.action_id,
                title=entry.title,
                category="Action",
                summary=entry.summary,
                target="action",
            )
        )
    for entry in page_entries:
        entries.append(
            CommandPaletteEntry(
                entry_id=entry.page_id,
                title=entry.title,
                category=entry.group_title,
                summary=entry.summary,
                target="page",
            )
        )
    return tuple(entries)


def serialize_workspace_project_state(tab_index: int, workspace_state: WorkspaceUiState | None) -> dict[str, str]:
    metadata: dict[str, str] = {"ui.activeTab": str(tab_index)}
    if workspace_state is None:
        return metadata
    if workspace_state.active_page_id:
        metadata["ui.workspace.activePageId"] = workspace_state.active_page_id
    metadata["ui.workspace.catalogQuery"] = workspace_state.catalog_query
    metadata["ui.workspace.catalogKind"] = workspace_state.catalog_kind
    metadata["ui.workspace.detailsTabIndex"] = str(workspace_state.details_tab_index)
    if workspace_state.main_splitter_sizes:
        metadata["ui.workspace.mainSplitter"] = ",".join(str(size) for size in workspace_state.main_splitter_sizes)
    if workspace_state.workspace_splitter_sizes:
        metadata["ui.workspace.workspaceSplitter"] = ",".join(
            str(size) for size in workspace_state.workspace_splitter_sizes
        )
    return metadata


def deserialize_workspace_project_state(metadata: dict[str, str]) -> tuple[int, WorkspaceUiState | None]:
    tab_index = _safe_int(metadata.get("ui.activeTab"), 1)
    workspace_state = WorkspaceUiState(
        active_page_id=metadata.get("ui.workspace.activePageId"),
        main_splitter_sizes=_parse_size_list(metadata.get("ui.workspace.mainSplitter")),
        workspace_splitter_sizes=_parse_size_list(metadata.get("ui.workspace.workspaceSplitter")),
        details_tab_index=_safe_int(metadata.get("ui.workspace.detailsTabIndex"), 0),
        catalog_query=metadata.get("ui.workspace.catalogQuery", ""),
        catalog_kind=metadata.get("ui.workspace.catalogKind", "All"),
    )
    has_workspace_values = any(
        (
            workspace_state.active_page_id,
            workspace_state.main_splitter_sizes,
            workspace_state.workspace_splitter_sizes,
            workspace_state.catalog_query,
            workspace_state.catalog_kind != "All",
            workspace_state.details_tab_index != 0,
        )
    )
    return tab_index, workspace_state if has_workspace_values else None


def _safe_int(raw_value: str | None, default: int) -> int:
    try:
        return int(raw_value) if raw_value is not None else default
    except ValueError:
        return default


def _parse_size_list(raw_value: str | None) -> tuple[int, ...]:
    if not raw_value:
        return ()
    sizes: list[int] = []
    for token in raw_value.split(","):
        try:
            size = int(token.strip())
        except ValueError:
            continue
        if size > 0:
            sizes.append(size)
    return tuple(sizes)


def update_recent_project_paths(
    existing_paths: tuple[str, ...],
    project_path: str,
    *,
    max_entries: int = 8,
) -> tuple[str, ...]:
    normalized = str(Path(project_path).resolve())
    items = [normalized]
    seen = {normalized}
    for raw_path in existing_paths:
        candidate = str(Path(raw_path).resolve())
        if candidate not in seen:
            items.append(candidate)
            seen.add(candidate)
        if len(items) >= max_entries:
            break
    return tuple(items)


def choose_start_project_path(
    recent_paths: tuple[Path, ...],
    last_project_path: Path | None,
) -> Path | None:
    if last_project_path is not None and last_project_path.exists():
        return last_project_path
    return recent_paths[0] if recent_paths else None


@dataclass(slots=True, frozen=True)
class RecentProjectSummary:
    path: Path
    name: str
    ecu_definition_path: Path | None
    tune_file_path: Path | None


def build_recent_project_summaries(
    recent_paths: tuple[Path, ...],
    project_service: ProjectService | None = None,
) -> tuple[RecentProjectSummary, ...]:
    service = project_service or ProjectService()
    summaries: list[RecentProjectSummary] = []
    for path in recent_paths:
        try:
            project = service.open_project(path)
        except Exception:
            summaries.append(
                RecentProjectSummary(
                    path=path,
                    name=path.stem,
                    ecu_definition_path=None,
                    tune_file_path=None,
                )
            )
            continue
        summaries.append(
            RecentProjectSummary(
                path=path,
                name=project.name,
                ecu_definition_path=project.ecu_definition_path,
                tune_file_path=project.tune_file_path,
            )
        )
    return tuple(summaries)


def format_recent_project_menu_label(summary: RecentProjectSummary) -> str:
    return f"{summary.name}  [{summary.path}]"


def controller_signature_matches_definition(
    controller_signature: str | None,
    definition_signature: str | None,
) -> bool:
    if not controller_signature or not definition_signature:
        return True
    normalized_controller = " ".join(controller_signature.lower().split())
    normalized_definition = " ".join(definition_signature.lower().split())
    return normalized_controller == normalized_definition


class CommandPaletteDialog(QDialog):
    def __init__(self, entries: tuple[CommandPaletteEntry, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries = entries
        self.selected_entry: CommandPaletteEntry | None = None
        self.setWindowTitle("Command Palette")
        self.setModal(True)
        self.resize(620, 440)

        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search actions and pages")
        self.search_edit.textChanged.connect(self._populate_results)
        layout.addWidget(self.search_edit)

        self.results_list = QListWidget()
        self.results_list.itemActivated.connect(self._accept_item)
        layout.addWidget(self.results_list, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        run_button = QPushButton("Run")
        run_button.clicked.connect(self._accept_current)
        button_row.addWidget(run_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        self._populate_results("")
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _populate_results(self, query: str) -> None:
        terms = [term for term in query.lower().split() if term]
        self.results_list.clear()
        for entry in self._entries:
            haystack = " ".join((entry.title, entry.category, entry.summary, entry.target)).lower()
            if any(term not in haystack for term in terms):
                continue
            item = QListWidgetItem(f"{entry.title}  [{entry.category}]")
            item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, entry.target)
            item.setToolTip(entry.summary)
            self.results_list.addItem(item)
        if self.results_list.count():
            self.results_list.setCurrentRow(0)

    def _accept_current(self) -> None:
        item = self.results_list.currentItem()
        if item is None:
            return
        self._accept_item(item)

    def _accept_item(self, item: QListWidgetItem) -> None:
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        target = item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(entry_id, str) or not isinstance(target, str):
            return
        for entry in self._entries:
            if entry.entry_id == entry_id and entry.target == target:
                self.selected_entry = entry
                self.accept()
                return


class EvidenceReplayDialog(QDialog):
    def __init__(self, snapshots: list[EvidenceReplaySnapshot], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshots = list(reversed(snapshots))
        self._formatter = EvidenceReplayFormatterService()
        self.selected_snapshot: EvidenceReplaySnapshot | None = None
        self.setWindowTitle("Evidence History")
        self.setModal(True)
        self.resize(860, 560)

        layout = QVBoxLayout(self)
        note = QLabel(
            "Review recent captured evidence bundles from Runtime and Flash surfaces before copying or exporting."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        body = QHBoxLayout()
        self.history_list = QListWidget()
        self.history_list.currentRowChanged.connect(self._refresh_preview)
        body.addWidget(self.history_list, 1)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        body.addWidget(self.preview_text, 2)
        layout.addLayout(body, 1)

        button_row = QHBoxLayout()
        self.use_button = QPushButton("Use In Workspace")
        self.use_button.clicked.connect(self._use_selected)
        button_row.addWidget(self.use_button)
        self.copy_button = QPushButton("Copy Selected")
        self.copy_button.clicked.connect(self._copy_selected)
        button_row.addWidget(self.copy_button)
        self.export_button = QPushButton("Export Selected")
        self.export_button.clicked.connect(self._export_selected)
        button_row.addWidget(self.export_button)
        button_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._populate_history()

    def _populate_history(self) -> None:
        self.history_list.clear()
        for snapshot in self._snapshots:
            label = (
                f"{snapshot.captured_at.strftime('%H:%M:%S')} | {snapshot.session_state} | "
                f"{snapshot.source_text.replace('Source  ', '')} | {snapshot.runtime_summary_text}"
            )
            self.history_list.addItem(label)
        has_items = bool(self._snapshots)
        self.use_button.setEnabled(has_items)
        self.copy_button.setEnabled(has_items)
        self.export_button.setEnabled(has_items)
        if has_items:
            self.history_list.setCurrentRow(0)
        else:
            self.preview_text.setPlainText("No evidence history captured yet.")

    def _selected_snapshot(self) -> EvidenceReplaySnapshot | None:
        row = self.history_list.currentRow()
        if row < 0 or row >= len(self._snapshots):
            return None
        return self._snapshots[row]

    def _refresh_preview(self, _row: int) -> None:
        snapshot = self._selected_snapshot()
        if snapshot is None:
            self.preview_text.setPlainText("No evidence history captured yet.")
            return
        self.preview_text.setPlainText(self._formatter.to_text(snapshot))

    def _copy_selected(self) -> None:
        snapshot = self._selected_snapshot()
        if snapshot is None:
            return
        QApplication.clipboard().setText(self._formatter.to_text(snapshot))

    def _export_selected(self) -> None:
        snapshot = self._selected_snapshot()
        if snapshot is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Evidence Snapshot",
            "evidence_snapshot.txt",
            "Text Files (*.txt);;JSON Files (*.json)",
        )
        if not path:
            return
        payload = self._formatter.to_json(snapshot) if path.lower().endswith(".json") else self._formatter.to_text(snapshot)
        Path(path).write_text(payload, encoding="utf-8")

    def _use_selected(self) -> None:
        snapshot = self._selected_snapshot()
        if snapshot is None:
            return
        self.selected_snapshot = snapshot
        self.accept()


class DefinitionSettingsDialog(QDialog):
    """Toggle INI [SettingGroups] flags and multi-option selectors for the loaded definition."""

    def __init__(
        self,
        setting_groups,  # list[SettingGroupDefinition]
        active_settings: frozenset[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Definition Settings")
        self.setMinimumWidth(440)
        self._groups = setting_groups
        self._result: frozenset[str] = active_settings
        self._checks: dict[str, QCheckBox] = {}
        self._combos: dict[str, QComboBox] = {}
        self._active = set(active_settings)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        if not self._groups:
            root.addWidget(QLabel("No setting groups are defined in the loaded ECU definition."))
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            content = QWidget()
            form = QFormLayout(content)
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(8)

            for group in self._groups:
                if not group.options:
                    # Boolean flag
                    cb = QCheckBox()
                    cb.setChecked(group.symbol in self._active)
                    cb.toggled.connect(lambda checked, sym=group.symbol: self._on_flag_toggled(sym, checked))
                    form.addRow(group.label, cb)
                    self._checks[group.symbol] = cb
                else:
                    # Multi-option selector
                    combo = QComboBox()
                    active_opt = None
                    for opt in group.options:
                        combo.addItem(opt.label, opt.symbol)
                        if opt.symbol in self._active:
                            active_opt = opt.symbol
                    # If active option is the group symbol itself (bare flag), pre-select
                    if active_opt is None and group.symbol in self._active:
                        active_opt = group.symbol
                    if active_opt:
                        idx = combo.findData(active_opt)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                    combo.currentIndexChanged.connect(
                        lambda _i, sym=group.symbol, c=combo: self._on_combo_changed(sym, c)
                    )
                    form.addRow(group.label, combo)
                    self._combos[group.symbol] = combo

            scroll.setWidget(content)
            root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_flag_toggled(self, symbol: str, checked: bool) -> None:
        if checked:
            self._active.add(symbol)
        else:
            self._active.discard(symbol)

    def _on_combo_changed(self, group_symbol: str, combo: QComboBox) -> None:
        # Remove all options for this group from active, then add selected
        group = next((g for g in self._groups if g.symbol == group_symbol), None)
        if group:
            for opt in group.options:
                self._active.discard(opt.symbol)
            self._active.discard(group_symbol)
        selected = combo.currentData()
        if selected and selected != "DEFAULT":
            self._active.add(selected)

    def _on_accept(self) -> None:
        self._result = frozenset(self._active)
        self.accept()

    def result_active_settings(self) -> frozenset[str]:
        return self._result


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project_service = ProjectService()
        self.definition_service = DefinitionService()
        self.tune_file_service = TuneFileService()
        self.board_detection_service = BoardDetectionService()
        self.firmware_catalog_service = FirmwareCatalogService()
        self.flash_service = FirmwareFlashService()
        self.flash_preflight_service = FlashPreflightService(self.firmware_catalog_service)
        self.flash_target_detection_service = FlashTargetDetectionService()
        self.local_tune_edit_service = LocalTuneEditService()
        self.msq_write_service = MsqWriteService()
        self.parameter_catalog_service = ParameterCatalogService()
        self.table_view_service = TableViewService()
        self.tuning_page_service = TuningPageService()
        self.staged_change_service = StagedChangeService()
        self.session_service = SessionService(transport_factory=TransportFactory())
        self.speeduino_runtime_telemetry_service = SpeeduinoRuntimeTelemetryService()
        self.datalog_import_service = DatalogImportService()
        self.datalog_profile_service = DatalogProfileService()
        self.datalog_replay_service = DatalogReplayService()
        self.datalog_review_service = DatalogReviewService()
        self.live_capture_service = LiveCaptureSessionService(self.datalog_profile_service)
        self.trigger_log_analysis_service = TriggerLogAnalysisService()
        self.trigger_log_visualization_service = TriggerLogVisualizationService()
        self.live_data_server = LiveDataHttpServer(port=8080)
        self.live_trigger_logger_service = LiveTriggerLoggerService()
        self.settings = QSettings("tuner-py", "tuner-py")
        self.simulator_server: ProtocolSimulatorServer | XcpSimulatorServer | None = None
        self._last_speeduino_probe_attempts: list[str] = []
        self.flash_worker: FlashWorker | None = None
        self.project_auto_connect_worker: ProjectAutoConnectWorker | None = None
        self._pending_auto_connect_project_path: Path | None = None
        self._last_runtime_snapshot: OutputChannelSnapshot | None = None
        self._last_evidence_replay_snapshot: EvidenceReplaySnapshot | None = None
        self._workspace_evidence_replay_snapshot: EvidenceReplaySnapshot | None = None
        self._evidence_replay_history: list[EvidenceReplaySnapshot] = []
        self._loaded_datalog: DatalogImportSnapshot | None = None
        self._selected_datalog_replay: DatalogReplaySelectionSnapshot | None = None
        self._last_trigger_log_path: Path | None = None
        self._trigger_capture_worker: TriggerCaptureWorker | None = None
        self.project: Project | None = None
        self.definition: EcuDefinition | None = None
        self.tune_file: TuneFile | None = None
        self.tune_file_path: Path | None = None
        self._workspace_ui_state: WorkspaceUiState | None = None
        self._pending_project_tab_index = 1
        self._suspend_project_state_persist = False
        self._table_debug_enabled = os.environ.get("TUNER_TABLE_DEBUG", "").lower() in {"1", "true", "yes", "on"}
        self._project_state_save_timer = QTimer(self)
        self._project_state_save_timer.setSingleShot(True)
        self._project_state_save_timer.setInterval(250)
        self._project_state_save_timer.timeout.connect(self._persist_project_ui_state)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll_runtime)

        self._build_ui()
        QTimer.singleShot(0, self._maybe_show_start_dialog)

    def _build_ui(self) -> None:
        self.setWindowTitle("tuner-py")
        self.resize(1280, 820)

        toolbar = QToolBar("Main")
        toolbar.setProperty("mainToolbar", True)
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            """
            QToolBar[mainToolbar="true"] {
                spacing: 6px;
                border: none;
            }
            QToolBar[mainToolbar="true"] QPushButton,
            QToolBar[mainToolbar="true"] QToolButton {
                background: palette(button);
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 6px 10px;
            }
            QToolBar[mainToolbar="true"] QPushButton[toolbarRole="primary"],
            QToolBar[mainToolbar="true"] QToolButton[toolbarRole="primary"] {
                background: #1a2d42;
                border-color: #40617f;
                color: #d7e8f7;
                font-weight: 600;
            }
            QToolBar[mainToolbar="true"] QPushButton[toolbarRole="secondary"],
            QToolBar[mainToolbar="true"] QToolButton[toolbarRole="secondary"] {
                background: palette(button);
            }
            QToolBar[mainToolbar="true"] QPushButton[toolbarRole="utility"],
            QToolBar[mainToolbar="true"] QToolButton[toolbarRole="utility"] {
                color: #a7b2c2;
            }
            """
        )
        self.addToolBar(toolbar)

        open_project_button = QPushButton("Open Project")
        open_project_button.setProperty("toolbarRole", "primary")
        open_project_button.clicked.connect(self.open_project)
        toolbar.addWidget(open_project_button)

        self.recent_projects_button = QToolButton()
        self.recent_projects_button.setText("Recent Projects")
        self.recent_projects_button.setProperty("toolbarRole", "secondary")
        self.recent_projects_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recent_projects_menu = QMenu(self.recent_projects_button)
        self.recent_projects_button.setMenu(self.recent_projects_menu)
        toolbar.addWidget(self.recent_projects_button)
        self._refresh_recent_projects_menu()

        new_project_button = QPushButton("New Project")
        new_project_button.setProperty("toolbarRole", "secondary")
        new_project_button.clicked.connect(self.create_project)
        toolbar.addWidget(new_project_button)

        open_definition_button = QPushButton("Open ECU Definition")
        open_definition_button.setProperty("toolbarRole", "secondary")
        open_definition_button.clicked.connect(self.open_definition)
        toolbar.addWidget(open_definition_button)

        definition_settings_button = QPushButton("Definition Settings")
        definition_settings_button.setProperty("toolbarRole", "utility")
        definition_settings_button.clicked.connect(self._open_definition_settings_dialog)
        toolbar.addWidget(definition_settings_button)

        open_tune_button = QPushButton("Open Tune")
        open_tune_button.setProperty("toolbarRole", "secondary")
        open_tune_button.clicked.connect(self.open_tune)
        toolbar.addWidget(open_tune_button)

        save_button = QPushButton("Save")
        save_button.setProperty("toolbarRole", "primary")
        save_button.setToolTip("Save tune in-place (Ctrl+S)")
        save_button.clicked.connect(self.save)
        toolbar.addWidget(save_button)

        save_tune_button = QPushButton("Save Tune As")
        save_tune_button.setProperty("toolbarRole", "secondary")
        save_tune_button.clicked.connect(self.save_tune)
        toolbar.addWidget(save_tune_button)

        start_mock_button = QPushButton("Start Mock Session")
        start_mock_button.setProperty("toolbarRole", "utility")
        start_mock_button.clicked.connect(self.start_mock_session)
        toolbar.addWidget(start_mock_button)

        refresh_ports_button = QPushButton("Refresh Ports")
        refresh_ports_button.setProperty("toolbarRole", "utility")
        refresh_ports_button.clicked.connect(self._refresh_serial_ports)
        toolbar.addWidget(refresh_ports_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.shell_status_strip = QFrame()
        self.shell_status_strip.setProperty("shellStatus", True)
        shell_layout = QVBoxLayout(self.shell_status_strip)
        shell_layout.setContentsMargins(10, 8, 10, 8)
        shell_layout.setSpacing(6)

        shell_chip_row = QHBoxLayout()
        shell_chip_row.setContentsMargins(0, 0, 0, 0)
        shell_chip_row.setSpacing(8)
        self.project_chip = QLabel()
        self.session_chip = QLabel()
        self.source_chip = QLabel()
        self.signature_chip = QLabel()
        self.shell_staged_chip = QLabel()
        self.shell_hardware_chip = QLabel()
        for chip in (
            self.project_chip,
            self.session_chip,
            self.source_chip,
            self.signature_chip,
            self.shell_staged_chip,
            self.shell_hardware_chip,
        ):
            chip.setProperty("chip", True)
            shell_chip_row.addWidget(chip)
        shell_chip_row.addStretch(1)
        shell_layout.addLayout(shell_chip_row)

        shell_action_row = QHBoxLayout()
        shell_action_row.setContentsMargins(0, 0, 0, 0)
        shell_action_row.setSpacing(8)
        self.shell_next_steps_label = QLabel()
        self.shell_next_steps_label.setWordWrap(True)
        self.shell_next_steps_label.setProperty("shellStatusNote", True)
        shell_action_row.addWidget(self.shell_next_steps_label, 1)

        self.shell_connect_button = QPushButton()
        self.shell_connect_button.clicked.connect(lambda: self._execute_shell_action("session.toggle"))
        shell_action_row.addWidget(self.shell_connect_button)

        self.shell_refresh_button = QPushButton()
        self.shell_refresh_button.clicked.connect(lambda: self._execute_shell_action("session.refresh"))
        shell_action_row.addWidget(self.shell_refresh_button)

        self.shell_review_button = QPushButton()
        self.shell_review_button.clicked.connect(lambda: self._execute_shell_action("workspace.review"))
        shell_action_row.addWidget(self.shell_review_button)
        shell_layout.addLayout(shell_action_row)

        self.shell_status_strip.setStyleSheet(
            """
            QFrame[shellStatus="true"] {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 10px;
            }
            QLabel[chip="true"] {
                background: palette(button);
                border: 1px solid palette(mid);
                border-radius: 16px;
                padding: 6px 10px;
                font-weight: 600;
            }
            QLabel[chip="true"][severity="ok"] {
                background: #163226;
                border-color: #2d6a4f;
                color: #d7f5df;
            }
            QLabel[chip="true"][severity="warning"] {
                background: #3a2616;
                border-color: #8a5a35;
                color: #f6d6b8;
            }
            QLabel[chip="true"][severity="accent"] {
                background: #1a2d42;
                border-color: #40617f;
                color: #d7e8f7;
            }
            QLabel[chip="true"][severity="info"] {
                background: #2a223b;
                border-color: #66558a;
                color: #e4dcfa;
            }
            QLabel[shellStatusNote="true"] {
                color: palette(text);
            }
            QPushButton[shellActionRole="primary"] {
                background: #1a2d42;
                border: 1px solid #40617f;
                border-radius: 8px;
                color: #d7e8f7;
                font-weight: 600;
                padding: 6px 12px;
            }
            QPushButton[shellActionRole="secondary"] {
                background: palette(button);
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 6px 12px;
            }
            QPushButton[shellActionRole="secondary"]:disabled,
            QPushButton[shellActionRole="primary"]:disabled {
                color: #7f8793;
            }
            """
        )
        layout.addWidget(self.shell_status_strip)

        self.summary_label = QLabel("No project or ECU definition loaded.")
        self.summary_label.setProperty("shellSummaryMeta", True)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            """
            QLabel[shellSummaryMeta="true"] {
                color: #9aa3ad;
                padding: 2px 2px 0 2px;
            }
            """
        )
        layout.addWidget(self.summary_label)

        self.surface_mode_strip = QFrame()
        self.surface_mode_strip.setProperty("surfaceMode", True)
        self.surface_mode_strip.setStyleSheet(
            """
            QFrame[surfaceMode="true"] {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
            QLabel[modeBadge="true"] {
                background: palette(button);
                border: 1px solid palette(mid);
                border-radius: 12px;
                padding: 4px 8px;
                font-weight: 600;
            }
            QLabel[modeBadge="true"][emphasis="primary"] {
                background: #1a2d42;
                border-color: #40617f;
                color: #d7e8f7;
            }
            QLabel[modeBadge="true"][emphasis="accent"] {
                background: #2a223b;
                border-color: #66558a;
                color: #e4dcfa;
            }
            QLabel[modeBadge="true"][emphasis="warning"] {
                background: #3a2616;
                border-color: #8a5a35;
                color: #f6d6b8;
            }
            QLabel[surfaceModeTitle="true"] {
                font-size: 15px;
                font-weight: 600;
                color: palette(text);
            }
            QLabel[surfaceModeDescription="true"] {
                color: #9aa3ad;
            }
            """
        )
        surface_mode_layout = QHBoxLayout(self.surface_mode_strip)
        surface_mode_layout.setContentsMargins(10, 8, 10, 8)
        surface_mode_layout.setSpacing(10)
        self.surface_mode_badge = QLabel()
        self.surface_mode_badge.setProperty("modeBadge", True)
        surface_mode_layout.addWidget(self.surface_mode_badge, 0, Qt.AlignmentFlag.AlignTop)
        surface_mode_text_layout = QVBoxLayout()
        surface_mode_text_layout.setContentsMargins(0, 0, 0, 0)
        surface_mode_text_layout.setSpacing(2)
        self.surface_mode_title = QLabel()
        self.surface_mode_title.setProperty("surfaceModeTitle", True)
        surface_mode_text_layout.addWidget(self.surface_mode_title)
        self.surface_mode_description = QLabel()
        self.surface_mode_description.setProperty("surfaceModeDescription", True)
        self.surface_mode_description.setWordWrap(True)
        surface_mode_text_layout.addWidget(self.surface_mode_description)
        surface_mode_layout.addLayout(surface_mode_text_layout, 1)
        layout.addWidget(self.surface_mode_strip)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid palette(mid);
                border-radius: 8px;
                top: -1px;
                background: palette(base);
            }
            QTabBar::tab {
                background: palette(button);
                border: 1px solid palette(mid);
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 8px 14px;
                margin-right: 4px;
                color: palette(button-text);
            }
            QTabBar::tab:selected {
                background: palette(base);
                color: palette(text);
            }
            QTabBar::tab:hover:!selected {
                background: #343840;
            }
            """
        )
        self.tab_widget.currentChanged.connect(self._schedule_project_ui_state_persist)
        self.tab_widget.currentChanged.connect(self._render_surface_mode)
        layout.addWidget(self.tab_widget)

        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        overview_layout.addWidget(self.summary_text)

        self.staged_changes_text = QTextEdit()
        self.staged_changes_text.setReadOnly(True)
        overview_layout.addWidget(self.staged_changes_text)
        self.tab_widget.addTab(overview_tab, "Overview")

        tuning_tab = QWidget()
        tuning_layout = QVBoxLayout(tuning_tab)
        self.tuning_workspace = TuningWorkspacePanel(
            local_tune_edit_service=self.local_tune_edit_service,
            tuning_page_service=self.tuning_page_service,
            parameter_catalog_service=self.parameter_catalog_service,
            table_view_service=self.table_view_service,
        )
        self.tuning_workspace.workspace_changed.connect(self._refresh_summary)
        self.tuning_workspace.status_message.connect(self.statusBar().showMessage)
        self.tuning_workspace.ui_state_changed.connect(self._schedule_project_ui_state_persist)
        self.tuning_workspace.power_cycle_requested.connect(self.power_cycle_controller)
        tuning_layout.addWidget(self.tuning_workspace)
        self.tab_widget.addTab(tuning_tab, "Tuning")
        self._render_shell_status()
        QShortcut("Ctrl+P", self, activated=self._open_quick_open)
        QShortcut("Ctrl+K", self, activated=self._open_command_palette)
        QShortcut("Ctrl+S", self, activated=self.save)

        engine_setup_tab = QWidget()
        engine_setup_layout = QVBoxLayout(engine_setup_tab)
        engine_setup_layout.setContentsMargins(0, 0, 0, 0)
        self.engine_setup_panel = EngineSetupPanel()
        self.engine_setup_panel.status_message.connect(self.statusBar().showMessage)
        self.tuning_workspace.workspace_changed.connect(self.engine_setup_panel.refresh)
        self.engine_setup_panel.workspace_state_changed.connect(
            lambda: self.tuning_workspace.refresh_from_presenter(notify_workspace=True)
        )
        engine_setup_layout.addWidget(self.engine_setup_panel)
        self.tab_widget.addTab(engine_setup_tab, "Engine Setup")

        runtime_tab = QWidget()
        runtime_layout = QVBoxLayout(runtime_tab)
        runtime_layout.setContentsMargins(10, 10, 10, 10)
        runtime_layout.setSpacing(8)
        runtime_panel = QFrame()
        runtime_panel.setProperty("surfacePanel", "runtime")
        surface_panel_styles = """
            QFrame[surfacePanel="runtime"], QFrame[surfacePanel="flash"] {
                background: #26292e;
                border: 1px solid #585f69;
                border-radius: 10px;
            }
            QLabel[surfacePanelTitle="true"] {
                color: #c9d2dd;
                font-size: 13px;
                font-weight: 600;
                padding: 0 2px;
            }
            QLabel[surfacePanelNote="true"] {
                color: #9aa3ad;
                padding: 0 2px;
            }
            QLabel[surfaceChip="true"] {
                background: #31353b;
                border: 1px solid #585f69;
                border-radius: 14px;
                color: #d7dde6;
                font-weight: 600;
                padding: 4px 8px;
            }
            QLabel[surfaceChip="true"][severity="ok"] {
                background: #163226;
                border-color: #2d6a4f;
                color: #d7f5df;
            }
            QLabel[surfaceChip="true"][severity="warning"] {
                background: #3a2616;
                border-color: #8a5a35;
                color: #f6d6b8;
            }
            QLabel[surfaceChip="true"][severity="accent"] {
                background: #1a2d42;
                border-color: #40617f;
                color: #d7e8f7;
            }
            QLabel[surfaceChip="true"][severity="info"] {
                background: #2a223b;
                border-color: #66558a;
                color: #e4dcfa;
            }
            QFrame[surfacePanel="runtime"] QLineEdit,
            QFrame[surfacePanel="runtime"] QComboBox,
            QFrame[surfacePanel="runtime"] QSpinBox,
            QFrame[surfacePanel="flash"] QLineEdit,
            QFrame[surfacePanel="flash"] QComboBox,
            QFrame[surfacePanel="flash"] QSpinBox {
                background: #202328;
                border: 1px solid #505761;
                border-radius: 7px;
                color: #e5e7eb;
                padding: 4px 6px;
            }
            QFrame[surfacePanel="runtime"] QPushButton[surfaceActionRole="primary"],
            QFrame[surfacePanel="flash"] QPushButton[surfaceActionRole="primary"] {
                background: #1a2d42;
                border: 1px solid #40617f;
                border-radius: 8px;
                color: #d7e8f7;
                font-weight: 600;
                padding: 6px 10px;
            }
            QFrame[surfacePanel="runtime"] QPushButton[surfaceActionRole="secondary"],
            QFrame[surfacePanel="flash"] QPushButton[surfaceActionRole="secondary"] {
                background: #31353b;
                border: 1px solid #585f69;
                border-radius: 8px;
                color: #d7dde6;
                padding: 6px 10px;
            }
            QFrame[surfacePanel="runtime"] QTableWidget[surfaceTable="true"],
            QFrame[surfacePanel="flash"] QTextEdit[surfaceLog="true"] {
                background: #202328;
                border: 1px solid #505761;
                border-radius: 8px;
                color: #d7dde6;
            }
            QFrame[surfacePanel="runtime"] QHeaderView::section {
                background: #343841;
                color: #e5e7eb;
                border: 1px solid #6b7280;
                padding: 3px 4px;
            }
            QFrame[surfacePanel="flash"] QProgressBar {
                background: #202328;
                border: 1px solid #505761;
                border-radius: 7px;
                color: #d7dde6;
                text-align: center;
            }
            QFrame[surfacePanel="flash"] QProgressBar::chunk {
                background: #1a2d42;
                border-radius: 6px;
            }
            """
        runtime_panel.setStyleSheet(
            surface_panel_styles
        )
        runtime_panel_layout = QVBoxLayout(runtime_panel)
        runtime_panel_layout.setContentsMargins(10, 10, 10, 10)
        runtime_panel_layout.setSpacing(8)
        runtime_title = QLabel("Connection And Runtime")
        runtime_title.setProperty("surfacePanelTitle", True)
        runtime_panel_layout.addWidget(runtime_title)
        runtime_evidence_row = QHBoxLayout()
        runtime_evidence_row.setContentsMargins(0, 0, 0, 0)
        runtime_evidence_row.setSpacing(6)
        self.runtime_connection_chip = QLabel()
        self.runtime_source_chip = QLabel()
        self.runtime_sync_chip = QLabel()
        self.runtime_changes_chip = QLabel()
        self.runtime_ops_chip = QLabel()
        self.runtime_samples_chip = QLabel()
        for chip in (
            self.runtime_connection_chip,
            self.runtime_source_chip,
            self.runtime_sync_chip,
            self.runtime_changes_chip,
            self.runtime_ops_chip,
            self.runtime_samples_chip,
        ):
            chip.setProperty("surfaceChip", True)
            runtime_evidence_row.addWidget(chip)
        runtime_evidence_row.addStretch(1)
        runtime_panel_layout.addLayout(runtime_evidence_row)
        runtime_evidence_actions = QHBoxLayout()
        runtime_evidence_actions.setContentsMargins(0, 0, 0, 0)
        runtime_evidence_actions.setSpacing(8)
        self.runtime_evidence_label = QLabel("")
        self.runtime_evidence_label.setProperty("surfacePanelNote", True)
        self.runtime_evidence_label.setWordWrap(True)
        runtime_evidence_actions.addWidget(self.runtime_evidence_label, 1)
        self.runtime_sync_button = QPushButton("Open Sync State")
        self.runtime_sync_button.setProperty("surfaceActionRole", "secondary")
        self.runtime_sync_button.clicked.connect(lambda: self._open_workspace_context_tab(1))
        runtime_evidence_actions.addWidget(self.runtime_sync_button)
        self.runtime_review_button = QPushButton("Open Review")
        self.runtime_review_button.setProperty("surfaceActionRole", "secondary")
        self.runtime_review_button.clicked.connect(lambda: self._open_workspace_context_tab(2))
        runtime_evidence_actions.addWidget(self.runtime_review_button)
        self.runtime_history_button = QPushButton("Evidence History")
        self.runtime_history_button.setProperty("surfaceActionRole", "secondary")
        self.runtime_history_button.clicked.connect(self._open_evidence_history_dialog)
        runtime_evidence_actions.addWidget(self.runtime_history_button)
        self.runtime_copy_evidence_button = QPushButton("Copy Evidence")
        self.runtime_copy_evidence_button.setProperty("surfaceActionRole", "secondary")
        self.runtime_copy_evidence_button.clicked.connect(self._copy_latest_evidence_replay)
        runtime_evidence_actions.addWidget(self.runtime_copy_evidence_button)
        self.runtime_export_evidence_button = QPushButton("Export Evidence")
        self.runtime_export_evidence_button.setProperty("surfaceActionRole", "secondary")
        self.runtime_export_evidence_button.clicked.connect(self._export_latest_evidence_replay)
        runtime_evidence_actions.addWidget(self.runtime_export_evidence_button)
        runtime_panel_layout.addLayout(runtime_evidence_actions)
        connection_row = QWidget()
        connection_layout = QHBoxLayout(connection_row)
        connection_layout.setContentsMargins(0, 0, 0, 0)
        connection_form = QFormLayout()
        connection_form.setHorizontalSpacing(12)
        connection_form.setVerticalSpacing(8)
        self.transport_combo = QComboBox()
        for transport in TransportType:
            self.transport_combo.addItem(transport.value.upper(), transport)
        self.transport_combo.currentIndexChanged.connect(self._update_connection_inputs)
        connection_form.addRow("Transport", self.transport_combo)

        self.protocol_combo = QComboBox()
        for protocol in ProtocolType:
            self.protocol_combo.addItem(protocol.value.upper(), protocol)
        self.protocol_combo.currentIndexChanged.connect(self._update_connection_inputs)
        connection_form.addRow("Protocol", self.protocol_combo)

        self.serial_combo = QComboBox()
        connection_form.addRow("Serial Port", self.serial_combo)

        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 3000000)
        self.baud_spin.setValue(115200)
        connection_form.addRow("Baud Rate", self.baud_spin)

        self.host_edit = QLineEdit("127.0.0.1")
        connection_form.addRow("Host", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(29000)
        connection_form.addRow("Port", self.port_spin)

        connection_layout.addLayout(connection_form, 1)

        button_column = QVBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.setProperty("surfaceActionRole", "primary")
        self.connect_button.clicked.connect(self.connect_session)
        button_column.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setProperty("surfaceActionRole", "secondary")
        self.disconnect_button.clicked.connect(self.disconnect_session)
        button_column.addWidget(self.disconnect_button)

        self.wifi_connect_button = QPushButton("Connect via WiFi")
        self.wifi_connect_button.setProperty("surfaceActionRole", "secondary")
        self.wifi_connect_button.setToolTip(
            "Connect to the Airbear ESP32-C3 WiFi bridge (speeduino.local:2000).\n"
            "Requires the Airbear firmware v0.2.0+ running in TunerStudio TCP "
            "bridge or DASH_ECHO dual mode.\n"
            "Enabled automatically when boardCap_wifiTransport is detected."
        )
        self.wifi_connect_button.clicked.connect(self._connect_via_wifi)
        button_column.addWidget(self.wifi_connect_button)

        self.live_data_server_button = QPushButton("Start Live Data API")
        self.live_data_server_button.setProperty("surfaceActionRole", "secondary")
        self.live_data_server_button.setToolTip(
            "Start an HTTP server on port 8080 that exposes live channel data as JSON.\n"
            "Endpoints: /api/channels  /api/channels/{name}  /api/status\n"
            "Any browser, phone, or Raspberry Pi on the local network can consume it."
        )
        self.live_data_server_button.clicked.connect(self._toggle_live_data_server)
        button_column.addWidget(self.live_data_server_button)

        self.start_simulator_button = QPushButton("Start Simulator")
        self.start_simulator_button.setProperty("surfaceActionRole", "secondary")
        self.start_simulator_button.clicked.connect(self.start_simulator)
        button_column.addWidget(self.start_simulator_button)

        self.stop_simulator_button = QPushButton("Stop Simulator")
        self.stop_simulator_button.setProperty("surfaceActionRole", "secondary")
        self.stop_simulator_button.clicked.connect(self.stop_simulator)
        button_column.addWidget(self.stop_simulator_button)

        button_column.addStretch(1)
        connection_layout.addLayout(button_column)

        runtime_panel_layout.addWidget(connection_row)
        self.connection_hint_label = QLabel("")
        self.connection_hint_label.setWordWrap(True)
        self.connection_hint_label.setProperty("surfacePanelNote", True)
        runtime_panel_layout.addWidget(self.connection_hint_label)

        self.runtime_capability_label = QLabel(
            "Telemetry: connect to a Speeduino controller to review board capabilities, SPI flash health, and tune-learning state."
        )
        self.runtime_capability_label.setWordWrap(True)
        self.runtime_capability_label.setProperty("surfacePanelNote", True)
        runtime_panel_layout.addWidget(self.runtime_capability_label)

        self.channels_table = QTableWidget(0, 2)
        self.channels_table.setProperty("surfaceTable", True)
        self.channels_table.setHorizontalHeaderLabels(["Channel", "Value"])
        self.channels_table.horizontalHeader().setStretchLastSection(True)
        runtime_panel_layout.addWidget(self.channels_table, 1)
        runtime_layout.addWidget(runtime_panel, 1)

        # Hardware Test panel (right column) ---------------------------------
        hw_test_outer = QFrame()
        hw_test_outer.setProperty("surfacePanel", "runtime")
        hw_test_outer.setStyleSheet(surface_panel_styles)
        hw_test_outer_layout = QVBoxLayout(hw_test_outer)
        hw_test_outer_layout.setContentsMargins(10, 10, 10, 10)
        hw_test_outer_layout.setSpacing(6)
        hw_test_title = QLabel("Hardware Test")
        hw_test_title.setProperty("surfacePanelTitle", True)
        hw_test_outer_layout.addWidget(hw_test_title)
        self.hardware_test_panel = HardwareTestPanel(
            send_command=self._send_controller_command,
        )
        hw_test_outer_layout.addWidget(self.hardware_test_panel, 1)

        # Wideband O2 calibration — symmetric to the existing thermistor flow.
        # The panel only knows how to *generate* the 64-byte payload; the
        # host routes it through the controller client's calibration write.
        wideband_title = QLabel("Wideband Calibration")
        wideband_title.setProperty("surfacePanelTitle", True)
        hw_test_outer_layout.addWidget(wideband_title)
        self.wideband_calibration_panel = WidebandCalibrationPanel(
            send_calibration=self._send_wideband_calibration,
        )
        hw_test_outer_layout.addWidget(self.wideband_calibration_panel)

        runtime_layout.addWidget(hw_test_outer)

        self.tab_widget.addTab(runtime_tab, "Runtime")

        # Logging tab (index 4) -------------------------------------------
        logging_tab = QWidget()
        logging_tab_layout = QVBoxLayout(logging_tab)
        logging_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.logging_panel = LoggingPanel(self.datalog_profile_service)
        self.logging_panel.capture_start_requested.connect(self._on_start_capture)
        self.logging_panel.capture_stop_requested.connect(self._on_stop_capture)
        self.logging_panel.capture_clear_requested.connect(self._on_clear_capture)
        self.logging_panel.capture_save_requested.connect(self._on_save_capture)
        self.logging_panel.poll_interval_changed.connect(self._on_poll_interval_changed)
        self.logging_panel.browse_datalog_requested.connect(self.browse_datalog)
        self.logging_panel.load_datalog_requested.connect(self._load_datalog_csv)
        self.logging_panel.select_replay_row_requested.connect(self._select_datalog_row)
        self.logging_panel.use_replay_row_requested.connect(self._use_selected_datalog_replay)
        logging_tab_layout.addWidget(self.logging_panel)
        self.tab_widget.addTab(logging_tab, "Logging")

        dashboard_tab = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_tab)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        self.dashboard_panel = DashboardPanel()
        self.dashboard_panel.navigate_to_page_requested.connect(self._navigate_dashboard_to_tuning_page)
        dashboard_layout.addWidget(self.dashboard_panel)
        self.tab_widget.addTab(dashboard_tab, "Dashboard")

        trigger_logs_tab = QWidget()
        trigger_logs_layout = QVBoxLayout(trigger_logs_tab)
        trigger_logs_layout.setContentsMargins(10, 10, 10, 10)
        trigger_logs_layout.setSpacing(8)
        trigger_logs_panel = QFrame()
        trigger_logs_panel.setProperty("surfacePanel", "flash")
        trigger_logs_panel.setStyleSheet(surface_panel_styles)
        trigger_logs_panel_layout = QVBoxLayout(trigger_logs_panel)
        trigger_logs_panel_layout.setContentsMargins(10, 10, 10, 10)
        trigger_logs_panel_layout.setSpacing(8)
        trigger_logs_title = QLabel("Trigger Troubleshooting")
        trigger_logs_title.setProperty("surfacePanelTitle", True)
        trigger_logs_panel_layout.addWidget(trigger_logs_title)
        self.trigger_log_summary_label = QLabel(
            "Import a tooth, composite, or trigger CSV to compare the capture against the loaded decoder context."
        )
        self.trigger_log_summary_label.setProperty("surfacePanelNote", True)
        self.trigger_log_summary_label.setWordWrap(True)
        trigger_logs_panel_layout.addWidget(self.trigger_log_summary_label)
        trigger_log_form = QFormLayout()
        trigger_log_form.setHorizontalSpacing(12)
        trigger_log_form.setVerticalSpacing(8)
        self.trigger_log_path_edit = QLineEdit()
        trigger_log_form.addRow("CSV Path", self.trigger_log_path_edit)
        browse_trigger_log_button = QPushButton("Browse CSV")
        browse_trigger_log_button.setProperty("surfaceActionRole", "secondary")
        browse_trigger_log_button.clicked.connect(self.browse_trigger_log)
        trigger_log_form.addRow("", browse_trigger_log_button)
        self.trigger_log_analyze_button = QPushButton("Analyze Trigger Log")
        self.trigger_log_analyze_button.setProperty("surfaceActionRole", "primary")
        self.trigger_log_analyze_button.clicked.connect(self._analyze_trigger_log)
        trigger_log_form.addRow("", self.trigger_log_analyze_button)
        trigger_logs_panel_layout.addLayout(trigger_log_form)
        # --- Live capture section ---
        live_capture_sep = QLabel("Live Capture (requires active connection)")
        live_capture_sep.setProperty("surfacePanelTitle", True)
        trigger_logs_panel_layout.addWidget(live_capture_sep)
        live_capture_form = QFormLayout()
        live_capture_form.setHorizontalSpacing(12)
        live_capture_form.setVerticalSpacing(8)
        self.trigger_logger_combo = QComboBox()
        self.trigger_logger_combo.setToolTip(
            "Select the logger type to capture from the connected ECU.\n"
            "Tooth logger captures inter-tooth timing; composite loggers capture level + timing."
        )
        live_capture_form.addRow("Logger", self.trigger_logger_combo)
        self.trigger_capture_button = QPushButton("Capture Live Log")
        self.trigger_capture_button.setProperty("surfaceActionRole", "primary")
        self.trigger_capture_button.setEnabled(False)
        self.trigger_capture_button.setToolTip(
            "Send the start command to the ECU, wait for the buffer to fill, "
            "read the binary log data, then analyse it automatically."
        )
        self.trigger_capture_button.clicked.connect(self._capture_live_trigger_log)
        live_capture_form.addRow("", self.trigger_capture_button)
        trigger_logs_panel_layout.addLayout(live_capture_form)
        self.trigger_log_decoder_label = QLabel("Decoder Context: load a tune or connect to compare against the active decoder.")
        self.trigger_log_decoder_label.setProperty("surfacePanelNote", True)
        self.trigger_log_decoder_label.setWordWrap(True)
        trigger_logs_panel_layout.addWidget(self.trigger_log_decoder_label)
        self.trigger_log_findings_label = QLabel("Findings: no trigger log analyzed yet.")
        self.trigger_log_findings_label.setProperty("surfacePanelNote", True)
        self.trigger_log_findings_label.setWordWrap(True)
        trigger_logs_panel_layout.addWidget(self.trigger_log_findings_label)
        self.trigger_log_visual_label = QLabel("Visualization: no trigger log loaded.")
        self.trigger_log_visual_label.setProperty("surfacePanelNote", True)
        self.trigger_log_visual_label.setWordWrap(True)
        trigger_logs_panel_layout.addWidget(self.trigger_log_visual_label)
        self._trigger_log_plot_widget = None
        try:
            import pyqtgraph as pg

            self._trigger_log_plot_widget = pg.PlotWidget()
            self._trigger_log_plot_widget.setBackground("#202328")
            self._trigger_log_plot_widget.showGrid(x=True, y=True, alpha=0.18)
            self._trigger_log_plot_widget.setMinimumHeight(220)
            self._trigger_log_plot_widget.addLegend(offset=(8, 8))
            trigger_logs_panel_layout.addWidget(self._trigger_log_plot_widget)
        except Exception:
            self._trigger_log_plot_widget = None
        self.trigger_log_preview = QTextEdit()
        self.trigger_log_preview.setReadOnly(True)
        self.trigger_log_preview.setProperty("surfaceLog", True)
        self.trigger_log_preview.setMaximumHeight(180)
        self.trigger_log_preview.setPlainText("Preview: no trigger log loaded.")
        trigger_logs_panel_layout.addWidget(self.trigger_log_preview)
        trigger_logs_layout.addWidget(trigger_logs_panel)
        trigger_logs_layout.addStretch(1)
        self.tab_widget.addTab(trigger_logs_tab, "Trigger Logs")

        flash_tab = QWidget()
        flash_tab_layout = QVBoxLayout(flash_tab)
        flash_tab_layout.setContentsMargins(10, 10, 10, 10)
        flash_tab_layout.setSpacing(8)
        flasher_group = QFrame()
        flasher_group.setProperty("surfacePanel", "flash")
        flasher_group.setStyleSheet(surface_panel_styles)
        flasher_layout = QVBoxLayout(flasher_group)
        flasher_layout.setContentsMargins(10, 10, 10, 10)
        flasher_layout.setSpacing(8)
        flash_title = QLabel("Firmware Flasher")
        flash_title.setProperty("surfacePanelTitle", True)
        flasher_layout.addWidget(flash_title)
        flash_evidence_row = QHBoxLayout()
        flash_evidence_row.setContentsMargins(0, 0, 0, 0)
        flash_evidence_row.setSpacing(6)
        self.flash_connection_chip = QLabel()
        self.flash_source_chip = QLabel()
        self.flash_sync_chip = QLabel()
        self.flash_changes_chip = QLabel()
        self.flash_ops_chip = QLabel()
        for chip in (
            self.flash_connection_chip,
            self.flash_source_chip,
            self.flash_sync_chip,
            self.flash_changes_chip,
            self.flash_ops_chip,
        ):
            chip.setProperty("surfaceChip", True)
            flash_evidence_row.addWidget(chip)
        flash_evidence_row.addStretch(1)
        flasher_layout.addLayout(flash_evidence_row)
        flash_evidence_actions = QHBoxLayout()
        flash_evidence_actions.setContentsMargins(0, 0, 0, 0)
        flash_evidence_actions.setSpacing(8)
        self.flash_evidence_label = QLabel("")
        self.flash_evidence_label.setProperty("surfacePanelNote", True)
        self.flash_evidence_label.setWordWrap(True)
        flash_evidence_actions.addWidget(self.flash_evidence_label, 1)
        self.flash_sync_button = QPushButton("Open Sync State")
        self.flash_sync_button.setProperty("surfaceActionRole", "secondary")
        self.flash_sync_button.clicked.connect(lambda: self._open_workspace_context_tab(1))
        flash_evidence_actions.addWidget(self.flash_sync_button)
        self.flash_review_button = QPushButton("Open Review")
        self.flash_review_button.setProperty("surfaceActionRole", "secondary")
        self.flash_review_button.clicked.connect(lambda: self._open_workspace_context_tab(2))
        flash_evidence_actions.addWidget(self.flash_review_button)
        self.flash_history_button = QPushButton("Evidence History")
        self.flash_history_button.setProperty("surfaceActionRole", "secondary")
        self.flash_history_button.clicked.connect(self._open_evidence_history_dialog)
        flash_evidence_actions.addWidget(self.flash_history_button)
        self.flash_copy_evidence_button = QPushButton("Copy Evidence")
        self.flash_copy_evidence_button.setProperty("surfaceActionRole", "secondary")
        self.flash_copy_evidence_button.clicked.connect(self._copy_latest_evidence_replay)
        flash_evidence_actions.addWidget(self.flash_copy_evidence_button)
        self.flash_export_evidence_button = QPushButton("Export Evidence")
        self.flash_export_evidence_button.setProperty("surfaceActionRole", "secondary")
        self.flash_export_evidence_button.clicked.connect(self._export_latest_evidence_replay)
        flash_evidence_actions.addWidget(self.flash_export_evidence_button)
        flasher_layout.addLayout(flash_evidence_actions)

        flasher_form = QFormLayout()
        flasher_form.setHorizontalSpacing(12)
        flasher_form.setVerticalSpacing(8)
        self.flash_tool_root_edit = QLineEdit(str(self._default_tool_root()))
        flasher_form.addRow("Tool Root", self.flash_tool_root_edit)

        browse_tool_root_button = QPushButton("Browse Tool Root")
        browse_tool_root_button.setProperty("surfaceActionRole", "secondary")
        browse_tool_root_button.clicked.connect(self.browse_tool_root)
        flasher_form.addRow("", browse_tool_root_button)

        self.release_root_edit = QLineEdit(str(self._default_release_root()))
        self.release_root_edit.textChanged.connect(lambda _text: self._refresh_flash_bundle_summary())
        self.release_root_edit.textChanged.connect(lambda _text: self._refresh_flash_guidance())
        flasher_form.addRow("Release Folder", self.release_root_edit)

        browse_release_root_button = QPushButton("Browse Release Folder")
        browse_release_root_button.setProperty("surfaceActionRole", "secondary")
        browse_release_root_button.clicked.connect(self.browse_release_root)
        flasher_form.addRow("", browse_release_root_button)

        self.flash_firmware_edit = QLineEdit()
        self.flash_firmware_edit.textChanged.connect(lambda _text: self._refresh_flash_preflight())
        self.flash_firmware_edit.textChanged.connect(lambda _text: self._refresh_flash_bundle_summary())
        self.flash_firmware_edit.textChanged.connect(lambda _text: self._refresh_flash_guidance())
        flasher_form.addRow("Firmware", self.flash_firmware_edit)

        browse_firmware_button = QPushButton("Browse Firmware")
        browse_firmware_button.setProperty("surfaceActionRole", "secondary")
        browse_firmware_button.clicked.connect(self.browse_firmware)
        flasher_form.addRow("", browse_firmware_button)

        self.suggest_firmware_button = QPushButton("Auto Select Firmware")
        self.suggest_firmware_button.setProperty("surfaceActionRole", "secondary")
        self.suggest_firmware_button.clicked.connect(self.suggest_firmware)
        flasher_form.addRow("", self.suggest_firmware_button)

        self.flash_board_combo = QComboBox()
        for board_family in BoardFamily:
            self.flash_board_combo.addItem(board_family.value, board_family)
        self.flash_board_combo.currentIndexChanged.connect(self._update_flash_inputs)
        self.flash_board_combo.currentIndexChanged.connect(lambda: self._refresh_flash_preflight())
        self.flash_board_combo.currentIndexChanged.connect(lambda: self._refresh_flash_guidance())
        flasher_form.addRow("Board", self.flash_board_combo)

        self.detect_board_button = QPushButton("Detect Board")
        self.detect_board_button.setProperty("surfaceActionRole", "secondary")
        self.detect_board_button.clicked.connect(self.detect_board)
        flasher_form.addRow("", self.detect_board_button)

        self.detect_target_button = QPushButton("Detect Target")
        self.detect_target_button.setProperty("surfaceActionRole", "secondary")
        self.detect_target_button.clicked.connect(self.detect_flash_target)
        flasher_form.addRow("", self.detect_target_button)

        self.flash_port_edit = QLineEdit()
        flasher_form.addRow("Flash Port", self.flash_port_edit)

        self.flash_vid_edit = QLineEdit("0483")
        flasher_form.addRow("USB VID", self.flash_vid_edit)

        self.flash_pid_edit = QLineEdit("DF11")
        flasher_form.addRow("USB PID", self.flash_pid_edit)

        flasher_layout.addLayout(flasher_form)

        flash_button_row = QHBoxLayout()
        self.flash_button = QPushButton("Flash Firmware")
        self.flash_button.setProperty("surfaceActionRole", "primary")
        self.flash_button.clicked.connect(self.flash_firmware)
        flash_button_row.addWidget(self.flash_button)
        flash_button_row.addStretch(1)
        flasher_layout.addLayout(flash_button_row)

        self.flash_progress = QProgressBar()
        self.flash_progress.setRange(0, 100)
        self.flash_progress.setValue(0)
        flasher_layout.addWidget(self.flash_progress)

        self.flash_preflight_label = QLabel("Preflight: not checked")
        self.flash_preflight_label.setProperty("surfacePanelNote", True)
        flasher_layout.addWidget(self.flash_preflight_label)

        self.flash_guidance_label = QLabel(
            "Bench Guidance: select a board and firmware to see the recommended Speeduino flash and reconnect sequence."
        )
        self.flash_guidance_label.setProperty("surfacePanelNote", True)
        self.flash_guidance_label.setWordWrap(True)
        flasher_layout.addWidget(self.flash_guidance_label)

        self.flash_runtime_label = QLabel(
            "Runtime Evidence: reconnect after flashing to verify board capabilities, SPI flash health, and tune-learning status."
        )
        self.flash_runtime_label.setProperty("surfacePanelNote", True)
        self.flash_runtime_label.setWordWrap(True)
        flasher_layout.addWidget(self.flash_runtime_label)

        self.flash_bundle_label = QLabel(
            "Bundle: select a firmware from a Speeduino release folder to review paired artifacts."
        )
        self.flash_bundle_label.setProperty("surfacePanelNote", True)
        self.flash_bundle_label.setWordWrap(True)
        flasher_layout.addWidget(self.flash_bundle_label)

        flash_bundle_actions = QHBoxLayout()
        flash_bundle_actions.setContentsMargins(0, 0, 0, 0)
        flash_bundle_actions.setSpacing(8)
        self.flash_load_definition_button = QPushButton("Load Paired INI")
        self.flash_load_definition_button.setProperty("surfaceActionRole", "secondary")
        self.flash_load_definition_button.clicked.connect(self._load_paired_flash_definition)
        flash_bundle_actions.addWidget(self.flash_load_definition_button)
        self.flash_load_tune_button = QPushButton("Load Paired Tune")
        self.flash_load_tune_button.setProperty("surfaceActionRole", "secondary")
        self.flash_load_tune_button.clicked.connect(self._load_paired_flash_tune)
        flash_bundle_actions.addWidget(self.flash_load_tune_button)
        flash_bundle_actions.addStretch(1)
        flasher_layout.addLayout(flash_bundle_actions)

        self.flash_log = QTextEdit()
        self.flash_log.setReadOnly(True)
        self.flash_log.setProperty("surfaceLog", True)
        self.flash_log.setMaximumHeight(140)
        flasher_layout.addWidget(self.flash_log)
        flash_tab_layout.addWidget(flasher_group)
        flash_tab_layout.addStretch(1)
        self.tab_widget.addTab(flash_tab, "Tools / Flash")

        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")
        self._refresh_serial_ports()
        self._update_connection_inputs()
        self._update_flash_inputs()
        self._refresh_flash_preflight()
        self._refresh_flash_guidance()
        self._render_runtime_telemetry()
        self._render_surface_mode(self.tab_widget.currentIndex())
        self._reload_tuning_workspace()
        self._refresh_summary()

    def closeEvent(self, event) -> None:
        self._persist_project_ui_state()
        super().closeEvent(event)

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "Project Files (*.properties *.project *.txt);;All Files (*.*)",
        )
        if not path:
            return
        self._open_project_path(Path(path))

    def create_project(self) -> None:
        dialog = CreateProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, project_dir, definition_path, tune_path, connection_profile, metadata = dialog.project_payload()
        try:
            project = self.project_service.create_project(
                name=name,
                project_directory=project_dir,
                ecu_definition_path=definition_path,
                tune_file_path=tune_path,
                connection_profile=connection_profile,
                metadata=metadata,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Create Project Failed", str(exc))
            return
        self._load_project(project)
        if project.project_path is not None:
            self._remember_project_path(project.project_path)
        self.statusBar().showMessage(f"Created project: {project.name}")
        self.tab_widget.setCurrentIndex(2)
        QTimer.singleShot(0, self.engine_setup_panel.open_hardware_setup_wizard)
        if connection_profile.transport == TransportType.SERIAL.value and connection_profile.protocol == ProtocolType.SPEEDUINO.value:
            self.connect_session()

    def _open_definition_settings_dialog(self) -> None:
        setting_groups = self.definition.setting_groups if self.definition is not None else []
        active = self.project.active_settings if self.project is not None else frozenset()
        dialog = DefinitionSettingsDialog(setting_groups, active, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_active = dialog.result_active_settings()
        if self.project is not None:
            self.project.active_settings = new_active
            self._persist_project_ui_state()
        if self.definition is not None and self.project is not None and self.project.ecu_definition_path:
            self.definition = self.definition_service.open_definition(
                self.project.ecu_definition_path,
                active_settings=new_active,
            )
            self.session_service.set_definition(self.definition)
            self._reload_tuning_workspace()
            self._refresh_summary()
            self.statusBar().showMessage("Definition settings updated — definition reloaded.", 3000)

    def open_definition(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open ECU Definition",
            "",
            "Definition Files (*.ini *.txt);;All Files (*.*)",
        )
        if not path:
            return
        self._load_definition_path(Path(path))

    def open_tune(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Tune File",
            "",
            "Tune Files (*.msq);;All Files (*.*)",
        )
        if not path:
            return
        self._load_tune_path(Path(path))

    def save(self) -> None:
        """Save tune in-place (no dialog).  Falls back to Save As when no path is known."""
        if self.tune_file_path is None:
            self.save_tune()
            return
        try:
            self.msq_write_service.save(self.tune_file_path, self.tune_file_path, self.local_tune_edit_service)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return
        # Reload the in-memory tune from the freshly written file so edit-service
        # state stays consistent with what is on disk.
        self.tune_file = self.tune_file_service.open_tune(self.tune_file_path)
        self.local_tune_edit_service.set_tune_file(self.tune_file)
        self._persist_project_ui_state()
        self._refresh_summary()
        self.statusBar().showMessage(f"Saved: {self.tune_file_path.name}")

    def save_tune(self) -> None:
        """Save tune to a user-chosen path (Save As dialog)."""
        if self.tune_file_path is None:
            QMessageBox.information(self, "Save Tune", "Load a tune file before saving.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Tune File",
            str(self.tune_file_path),
            "Tune Files (*.msq);;All Files (*.*)",
        )
        if not path:
            return
        try:
            self.msq_write_service.save(self.tune_file_path, Path(path), self.local_tune_edit_service)
        except Exception as exc:
            QMessageBox.critical(self, "Save Tune Failed", str(exc))
            return
        self.tune_file = self.tune_file_service.open_tune(Path(path))
        self.tune_file_path = Path(path)
        self.local_tune_edit_service.set_tune_file(self.tune_file)
        # Update project's tune_file_path reference when user saves to a new location.
        if self.project is not None:
            self.project.tune_file_path = self.tune_file_path
            self._persist_project_ui_state()
        self._reload_tuning_workspace()
        self._refresh_summary()
        self.statusBar().showMessage(f"Saved tune: {Path(path).name}")

    def _open_project_path(self, path: Path, *, show_errors: bool = True) -> bool:
        try:
            project = self.project_service.open_project(path)
        except Exception as exc:
            if show_errors:
                QMessageBox.critical(self, "Open Project Failed", str(exc))
            return False
        self._load_project(project)
        self._remember_project_path(path)
        self.statusBar().showMessage(f"Loaded project: {project.name}")
        return True

    def _load_project(self, project: Project) -> None:
        self._suspend_project_state_persist = True
        self.project = project
        if project.ecu_definition_path is not None and project.ecu_definition_path.exists():
            self.definition = self.definition_service.open_definition(
                project.ecu_definition_path,
                active_settings=project.active_settings,
            )
            self.session_service.set_definition(self.definition)
        else:
            self.definition = None
            self.session_service.set_definition(None)
        if project.tune_file_path is not None and project.tune_file_path.exists():
            self.tune_file = self.tune_file_service.open_tune(project.tune_file_path)
            self.tune_file_path = project.tune_file_path
            self.local_tune_edit_service.set_tune_file(self.tune_file)
        else:
            self.tune_file = None
            self.tune_file_path = None
            self.local_tune_edit_service.set_tune_file(None)
        self._apply_project_settings(project)
        self._pending_project_tab_index, self._workspace_ui_state = deserialize_workspace_project_state(project.metadata)
        self.detect_board()
        self.detect_flash_target()
        self.suggest_firmware()
        self._refresh_flash_preflight()
        if project.project_path is not None:
            self.tuning_workspace.presenter.set_context_sidecar_path(
                project.project_path.with_suffix(".engine-context.json")
            )
            self.dashboard_panel.set_layout_path(
                project.project_path.with_suffix(".dashboard.json")
            )
            self.logging_panel.set_project(project)
        else:
            self.tuning_workspace.presenter.set_context_sidecar_path(None)
        self._reload_tuning_workspace()
        if 0 <= self._pending_project_tab_index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(self._pending_project_tab_index)
        self._refresh_summary()
        self._suspend_project_state_persist = False
        self._auto_connect_project(project)

    def _apply_project_settings(self, project: Project) -> None:
        profile = project.connection_profiles[0] if project.connection_profiles else None
        if profile is not None:
            transport_map = {item.value: item for item in TransportType}
            transport = transport_map.get(profile.transport.lower())
            if transport is not None:
                index = self.transport_combo.findData(transport)
                if index >= 0:
                    self.transport_combo.setCurrentIndex(index)
            if profile.protocol:
                protocol_map = {item.value: item for item in ProtocolType}
                protocol = protocol_map.get(profile.protocol.lower())
                if protocol is not None:
                    index = self.protocol_combo.findData(protocol)
                    if index >= 0:
                        self.protocol_combo.setCurrentIndex(index)
            if profile.serial_port:
                idx = self.serial_combo.findText(profile.serial_port)
                if idx >= 0:
                    self.serial_combo.setCurrentIndex(idx)
                else:
                    self.serial_combo.setEditText(profile.serial_port) if self.serial_combo.isEditable() else None
            if profile.baud_rate is not None:
                self.baud_spin.setValue(profile.baud_rate)
            if profile.host:
                self.host_edit.setText(profile.host)
            if profile.port is not None:
                self.port_spin.setValue(profile.port)
        board_name = project.metadata.get("controllerInUse")
        if board_name:
            board_map = {item.value: item for item in BoardFamily}
            board = board_map.get(board_name)
            if board is not None:
                index = self.flash_board_combo.findData(board)
                if index >= 0:
                    self.flash_board_combo.setCurrentIndex(index)

    def start_mock_session(self) -> None:
        self.transport_combo.setCurrentIndex(self.transport_combo.findData(TransportType.MOCK))
        self.protocol_combo.setCurrentIndex(self.protocol_combo.findData(ProtocolType.SIM_JSON))
        self.connect_session()

    def _maybe_show_start_dialog(self) -> None:
        if self.project is not None or self.definition is not None or self.tune_file is not None:
            return
        last_project = self._last_project_path()
        if last_project is not None and self._open_project_path(last_project, show_errors=False):
            return
        recent_projects = self._recent_project_paths()
        dialog = StartProjectDialog(
            build_recent_project_summaries(recent_projects, self.project_service),
            choose_start_project_path(recent_projects, last_project),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.selection == "new":
            self.create_project()
        elif dialog.selection == "open":
            self.open_project()
        elif dialog.selection == "recent" and dialog.selected_project_path is not None:
            self._open_project_path(dialog.selected_project_path)

    def browse_tool_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select SpeedyLoader Root", self.flash_tool_root_edit.text())
        if path:
            self.flash_tool_root_edit.setText(path)

    def browse_firmware(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Firmware File",
            "",
            "Firmware Files (*.hex *.bin);;All Files (*.*)",
        )
        if path:
            self.flash_firmware_edit.setText(path)
            self._refresh_flash_preflight()

    def browse_release_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Speeduino Release Folder", self.release_root_edit.text())
        if path:
            self.release_root_edit.setText(path)
            self.suggest_firmware()

    # ------------------------------------------------------------------
    # Live capture
    # ------------------------------------------------------------------

    def _on_start_capture(self, profile, poll_ms: int, output_path) -> None:  # noqa: ANN001
        if self._last_runtime_snapshot is None:
            self.statusBar().showMessage("Connect to a controller before starting capture.", 3000)
            return
        available = {v.name for v in self._last_runtime_snapshot.values}
        missing = self.datalog_profile_service.unavailable_channels(profile, available)
        if missing:
            warning = (
                f"Warning: {len(missing)} channel(s) not in current snapshot: "
                + ", ".join(missing[:5])
                + ("…" if len(missing) > 5 else "")
            )
            self.logging_panel.set_capture_channel_warning(warning)
        else:
            self.logging_panel.set_capture_channel_warning("")
        self.live_capture_service.start(profile, output_path=output_path)
        if poll_ms != self.timer.interval():
            self.timer.setInterval(poll_ms)
        self.logging_panel.set_recording(True)
        self.logging_panel.set_capture_has_data(False)
        self.logging_panel.update_capture_status(self.live_capture_service.status().status_text)
        self.statusBar().showMessage(f"Capture started — profile: {profile.name}")

    def _on_stop_capture(self) -> None:
        self.live_capture_service.stop()
        self.logging_panel.set_recording(False)
        self.logging_panel.set_capture_has_data(self.live_capture_service.has_data)
        self.logging_panel.update_capture_status(self.live_capture_service.status().status_text)
        self.statusBar().showMessage(
            f"Capture stopped — {self.live_capture_service.row_count} rows."
        )

    def _on_clear_capture(self) -> None:
        self.live_capture_service.reset()
        self.logging_panel.set_recording(False)
        self.logging_panel.set_capture_has_data(False)
        self.logging_panel.update_capture_status("Ready")
        self.statusBar().showMessage("Capture cleared.")

    def _on_save_capture(self) -> None:
        if not self.live_capture_service.has_data:
            return
        default_name = self.live_capture_service.to_log().name + ".csv"
        start_dir = str(self.project.project_path.parent) if self.project and self.project.project_path else ""
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Capture Log", str(Path(start_dir) / default_name), "CSV (*.csv)"
        )
        if path_str:
            path = Path(path_str)
            if not path.suffix:
                path = path.with_suffix(".csv")
            self.live_capture_service.save_csv(path)
            self.statusBar().showMessage(f"Log saved: {path.name}")

    def _on_poll_interval_changed(self, poll_ms: int) -> None:
        if not self.live_capture_service.is_recording:
            self.timer.setInterval(poll_ms)

    def browse_datalog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Datalog CSV",
            self.logging_panel.datalog_path,
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if path:
            self.logging_panel.set_datalog_path(path)
            self._load_datalog_csv(path)

    def _load_datalog_csv(self, raw_path: str = "") -> None:
        if not raw_path:
            raw_path = self.logging_panel.datalog_path
        if not raw_path:
            self._loaded_datalog = None
            self._selected_datalog_replay = None
            self.tuning_workspace.set_replay_datalog_log(None)
            self.logging_panel.clear_datalog()
            return
        path = Path(raw_path).expanduser().resolve()
        try:
            imported = self.datalog_import_service.load_csv(path)
        except Exception as exc:
            self._loaded_datalog = None
            self._selected_datalog_replay = None
            self.tuning_workspace.set_replay_datalog_log(None)
            self.logging_panel.update_datalog_loaded(1, f"Datalog import failed: {exc}", "Preview: no datalog loaded.")
            self.logging_panel.render_review(None)
            return
        self._loaded_datalog = imported
        self.tuning_workspace.set_replay_datalog_log(imported.log)
        self.logging_panel.update_datalog_loaded(
            row_count=imported.row_count,
            summary_text=imported.summary_text,
            preview_text=imported.preview_text,
        )
        self._select_datalog_row(1)

    def _select_datalog_row(self, row_number: int) -> None:
        if self._loaded_datalog is None:
            self._selected_datalog_replay = None
            self.logging_panel.update_datalog_row("", "Chart review: no datalog loaded.", "")
            self.logging_panel.render_review(None)
            return
        selection = self.datalog_replay_service.select_row(
            log=self._loaded_datalog.log,
            index=max(0, row_number - 1),
            workspace_snapshot=self.tuning_workspace.presenter.snapshot(),
        )
        self._selected_datalog_replay = selection
        review = self.datalog_review_service.build(
            log=self._loaded_datalog.log,
            selected_index=selection.selected_index,
            profile=self.logging_panel.get_active_profile(),
        )
        self.logging_panel.update_datalog_row(
            summary_text=selection.summary_text,
            preview_text=(
                f"{selection.summary_text}\n"
                f"Channels: {selection.preview_text}\n"
                f"Evidence source: {selection.evidence_snapshot.source_text}"
            ),
            chart_text=review.summary_text,
        )
        self.logging_panel.render_review(review)

    def _use_selected_datalog_replay(self) -> None:
        if self._selected_datalog_replay is None:
            self.statusBar().showMessage("Load a datalog and select a replay row first.", 3000)
            return
        self._workspace_evidence_replay_snapshot = self._selected_datalog_replay.evidence_snapshot
        self.tuning_workspace.set_evidence_review_snapshots(
            self._selected_datalog_replay.evidence_snapshot,
            latest_snapshot=self._last_evidence_replay_snapshot,
        )
        self.statusBar().showMessage("Selected datalog replay row pinned to workspace review.", 3000)

    def _send_controller_command(self, payload: bytes) -> None:
        """Dispatch a raw controller command to the connected ECU."""
        if self.session_service.client is None:
            self.statusBar().showMessage("No active connection.", 3000)
            return
        try:
            self.session_service.client.send_controller_command(payload)
            self.statusBar().showMessage(
                f"Controller command sent: {payload.hex(' ').upper()}", 3000
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Controller command failed: {exc}", 5000)

    def _send_wideband_calibration(self, page, payload: bytes) -> None:
        """Dispatch a wideband O2 calibration table to the connected ECU.

        Routes the 64-byte payload from ``WidebandCalibrationPanel``
        through the existing ``write_calibration_table()`` comms path,
        which targets calibration page ``int(page)`` (= 2 for O2).
        """
        client = self.session_service.client
        if client is None:
            self.statusBar().showMessage("No active connection.", 3000)
            return
        write_fn = getattr(client, "write_calibration_table", None)
        if write_fn is None:
            self.statusBar().showMessage(
                "Active controller does not support calibration writes.", 5000,
            )
            return
        try:
            write_fn(int(page), payload)
            self.statusBar().showMessage(
                f"Wideband calibration written to page {int(page)} ({len(payload)} bytes).",
                4000,
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Wideband calibration failed: {exc}", 5000)

    def _refresh_trigger_logger_combo(self) -> None:
        """Populate the logger-type dropdown from the loaded definition."""
        self.trigger_logger_combo.clear()
        if self.definition is None:
            self.trigger_capture_button.setEnabled(False)
            return
        for logger_def in self.definition.logger_definitions:
            self.trigger_logger_combo.addItem(logger_def.display_name, userData=logger_def)
        connected = (
            self.session_service.client is not None
            and len(self.definition.logger_definitions) > 0
        )
        self.trigger_capture_button.setEnabled(connected)

    def _capture_live_trigger_log(self) -> None:
        """Start a live trigger log capture in a background thread."""
        if self.session_service.client is None:
            self.statusBar().showMessage("No active connection — connect to ECU first.", 4000)
            return
        if self._trigger_capture_worker is not None and self._trigger_capture_worker.isRunning():
            self.statusBar().showMessage("Capture already in progress.", 3000)
            return
        logger_def = self.trigger_logger_combo.currentData()
        if logger_def is None:
            self.statusBar().showMessage("No logger selected.", 3000)
            return
        self.trigger_capture_button.setEnabled(False)
        self.trigger_capture_button.setText("Capturing…")
        self.statusBar().showMessage(
            f"Capturing {logger_def.display_name} — waiting for ECU buffer to fill…"
        )
        worker = TriggerCaptureWorker(
            self.session_service.client,
            logger_def,
            self.live_trigger_logger_service,
        )
        worker.succeeded.connect(self._on_trigger_capture_done)
        worker.failed.connect(self._on_trigger_capture_failed)
        self._trigger_capture_worker = worker
        worker.start()

    def _on_trigger_capture_done(self, capture: object) -> None:
        self.trigger_capture_button.setText("Capture Live Log")
        self.trigger_capture_button.setEnabled(True)
        from tuner.services.live_trigger_logger_service import TriggerLogCapture
        if not isinstance(capture, TriggerLogCapture):
            return
        if capture.record_count == 0:
            self.statusBar().showMessage(
                f"{capture.display_name}: captured 0 records — check ECU connection and logger type.", 5000
            )
            return
        csv_path = capture.to_csv_path()
        self.trigger_log_path_edit.setText(str(csv_path))
        self._last_trigger_log_path = csv_path
        self.statusBar().showMessage(
            f"{capture.display_name}: {capture.record_count} records captured — analysing…", 4000
        )
        self._analyze_trigger_log()

    def _on_trigger_capture_failed(self, error: str) -> None:
        self.trigger_capture_button.setText("Capture Live Log")
        self.trigger_capture_button.setEnabled(True)
        self.statusBar().showMessage(f"Trigger capture failed: {error}", 6000)
        self.trigger_log_summary_label.setText(f"Live capture failed: {error}")

    def browse_trigger_log(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Trigger Log CSV",
            self.trigger_log_path_edit.text(),
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if path:
            self.trigger_log_path_edit.setText(path)
            self._analyze_trigger_log()

    def _analyze_trigger_log(self) -> None:
        raw_path = self.trigger_log_path_edit.text().strip()
        if not raw_path:
            self.trigger_log_summary_label.setText("Import a tooth, composite, or trigger CSV to compare the capture against the loaded decoder context.")
            self.trigger_log_decoder_label.setText("Decoder Context: load a tune or connect to compare against the active decoder.")
            self.trigger_log_findings_label.setText("Findings: no trigger log analyzed yet.")
            self.trigger_log_visual_label.setText("Visualization: no trigger log loaded.")
            self._render_trigger_log_visualization(None)
            self.trigger_log_preview.setPlainText("Preview: no trigger log loaded.")
            self._last_trigger_log_path = None
            return
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            self.trigger_log_summary_label.setText("Trigger log import failed: the selected CSV path does not exist.")
            self.trigger_log_findings_label.setText("Findings: pick a valid tooth, composite, or trigger CSV file.")
            self.trigger_log_visual_label.setText("Visualization: no trigger log loaded.")
            self._render_trigger_log_visualization(None)
            self.trigger_log_preview.setPlainText("Preview: no trigger log loaded.")
            self._last_trigger_log_path = None
            return
        try:
            summary = self.trigger_log_analysis_service.analyze_csv(
                path,
                edits=self.local_tune_edit_service,
                definition=self.definition,
                runtime_snapshot=self._last_runtime_snapshot,
            )
            visualization = self.trigger_log_visualization_service.build_from_csv(path)
        except Exception as exc:
            self.trigger_log_summary_label.setText(f"Trigger log import failed: {exc}")
            self.trigger_log_findings_label.setText("Findings: review the CSV format and try again.")
            self.trigger_log_visual_label.setText("Visualization: no trigger log loaded.")
            self._render_trigger_log_visualization(None)
            self.trigger_log_preview.setPlainText("Preview: no trigger log loaded.")
            self._last_trigger_log_path = None
            return
        self._last_trigger_log_path = path
        self.trigger_log_summary_label.setText(
            f"{summary.capture_summary_text} Operator summary: {summary.operator_summary_text}"
        )
        self.trigger_log_decoder_label.setText(summary.decoder_summary_text)
        self.trigger_log_findings_label.setText("Findings: " + " ".join(summary.findings))
        self.trigger_log_visual_label.setText(visualization.summary_text)
        self._render_trigger_log_visualization(visualization)
        self.trigger_log_preview.setPlainText(summary.preview_text)

    def _render_trigger_log_visualization(self, visualization) -> None:
        if self._trigger_log_plot_widget is None:
            return
        import pyqtgraph as pg

        self._trigger_log_plot_widget.clear()
        if visualization is None:
            return
        colors = ("#4fc3f7", "#ffb74d", "#81c784", "#f06292", "#ba68c8", "#ffd54f")
        for index, trace in enumerate(visualization.traces):
            pen = colors[index % len(colors)]
            step_mode = "left" if trace.is_digital else None
            self._trigger_log_plot_widget.plot(
                list(trace.x_values),
                list(trace.y_values),
                pen=pen,
                name=trace.name,
                stepMode=step_mode,
            )
        for annotation in visualization.annotations:
            color = "#f6d6b8" if annotation.severity == "warning" else "#c9d2dd"
            line_pen = pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine)
            line = pg.InfiniteLine(pos=annotation.time_ms, angle=90, pen=line_pen)
            self._trigger_log_plot_widget.addItem(line)
            label = pg.TextItem(
                text=annotation.label,
                color=color,
                anchor=(0, 1),
                border=None,
                fill=None,
            )
            label.setPos(annotation.time_ms, max((trace.offset for trace in visualization.traces), default=0.0) + 1.0)
            self._trigger_log_plot_widget.addItem(label)

    def detect_board(self) -> None:
        detected = self.board_detection_service.detect(
            definition=self.definition,
            tune_file=self.tune_file,
            session_info=self.session_service.info,
        )
        if detected is None:
            self.statusBar().showMessage("Board autodetect could not determine a board family")
            return
        index = self.flash_board_combo.findData(detected)
        if index >= 0:
            self.flash_board_combo.setCurrentIndex(index)
        self.statusBar().showMessage(f"Detected board family: {detected.value}")

    def detect_flash_target(self) -> None:
        target = self.flash_target_detection_service.detect_preferred_target(self._selected_board_family())
        if target is None:
            self.statusBar().showMessage("No flash target detected")
            self._refresh_flash_guidance()
            return
        board_index = self.flash_board_combo.findData(target.board_family)
        if board_index >= 0:
            self.flash_board_combo.setCurrentIndex(board_index)
        if target.serial_port:
            self.flash_port_edit.setText(target.serial_port)
        if target.usb_vid:
            self.flash_vid_edit.setText(target.usb_vid)
        if target.usb_pid:
            self.flash_pid_edit.setText(target.usb_pid)
        self.statusBar().showMessage(f"Detected flash target: {target.description}")
        self._refresh_flash_preflight()
        self._refresh_flash_guidance()

    def suggest_firmware(self) -> None:
        try:
            suggestion = self.firmware_catalog_service.suggest_firmware(
                Path(self.release_root_edit.text().strip()),
                preferred_board=self._selected_board_family(),
                definition=self.definition,
                tune_file=self.tune_file,
            )
        except Exception as exc:
            self.statusBar().showMessage(str(exc))
            return
        if suggestion is None:
            self.statusBar().showMessage("No matching firmware file found")
            return
        self.flash_firmware_edit.setText(str(suggestion.path))
        self.statusBar().showMessage(f"Selected firmware: {suggestion.path.name}")
        self._refresh_flash_preflight()
        self._refresh_flash_bundle_summary()
        self._refresh_flash_guidance()

    def flash_firmware(self) -> None:
        if self.flash_worker is not None and self.flash_worker.isRunning():
            self.statusBar().showMessage("Firmware flashing is already running")
            return
        report = self._refresh_flash_preflight()
        if not report.ok:
            QMessageBox.critical(self, "Flash Preflight Failed", "\n".join(report.errors))
            return
        if report.warnings:
            choice = QMessageBox.warning(
                self,
                "Flash Preflight Warning",
                "\n".join(report.warnings) + "\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        try:
            request = self._flash_request()
            command_preview = self.flash_service.build_command(request)
        except Exception as exc:
            QMessageBox.critical(self, "Flash Setup Failed", str(exc))
            return

        self.flash_log.clear()
        self.flash_log.append(command_preview.display_command())
        self.flash_progress.setValue(0)
        self.flash_button.setEnabled(False)
        self.flash_worker = FlashWorker(self.flash_service, request)
        self.flash_worker.progress_changed.connect(self.flash_progress.setValue)
        self.flash_worker.status_changed.connect(self._append_flash_status)
        self.flash_worker.finished_result.connect(self._flash_finished)
        self.flash_worker.failed.connect(self._flash_failed)
        self.flash_worker.start()
        self.statusBar().showMessage("Firmware flashing started")

    def connect_session(self) -> None:
        self._connect_session_with_config(self._connection_config(), show_failures=True)

    def _toggle_live_data_server(self) -> None:
        if self.live_data_server.is_running:
            self.live_data_server.stop()
            self.live_data_server_button.setText("Start Live Data API")
            self.statusBar().showMessage("Live data API stopped.", 3000)
        else:
            try:
                self.live_data_server.start()
                self.live_data_server_button.setText("Stop Live Data API  :8080")
                self.statusBar().showMessage(
                    "Live data API running on http://localhost:8080/api/channels", 5000
                )
            except OSError as exc:
                self.statusBar().showMessage(f"Live data API failed to start: {exc}", 5000)

    def _connect_via_wifi(self) -> None:
        """Connect to the Airbear ESP32-C3 WiFi bridge at speeduino.local:2000."""
        config = ConnectionConfig(
            transport=TransportType.TCP,
            protocol=ProtocolType.SPEEDUINO,
            host="speeduino.local",
            port=2000,
        )
        # Update the UI fields so the saved project reflects the WiFi config.
        idx = self.transport_combo.findData(TransportType.TCP)
        if idx >= 0:
            self.transport_combo.setCurrentIndex(idx)
        idx = self.protocol_combo.findData(ProtocolType.SPEEDUINO)
        if idx >= 0:
            self.protocol_combo.setCurrentIndex(idx)
        self.host_edit.setText("speeduino.local")
        self.port_spin.setValue(2000)
        self.statusBar().showMessage("Connecting to speeduino.local:2000 (Airbear WiFi bridge)…")
        self._connect_session_with_config(config, show_failures=True)

    def _connect_session_with_config(self, config: ConnectionConfig, *, show_failures: bool) -> bool:
        # Capture any previously connected signature before connect() calls disconnect().
        prior_signature = self.session_service.info.firmware_signature
        try:
            info = self.session_service.connect(config)
        except Exception as exc:
            if config.transport == TransportType.SERIAL and config.protocol == ProtocolType.SPEEDUINO:
                discovered = self._attempt_speeduino_serial_discovery(config)
                if discovered is not None:
                    info, discovered_config, _attempt_log = discovered
                    port_index = self.serial_combo.findText(discovered_config.serial_port)
                    if port_index >= 0:
                        self.serial_combo.setCurrentIndex(port_index)
                    self.baud_spin.setValue(discovered_config.baud_rate)
                    self.timer.start()
                    self.tuning_workspace.set_session_client(self.session_service.client, SessionState.CONNECTED)
                    self.statusBar().showMessage(
                        f"Connected via {info.transport_name} after probing serial ports"
                    )
                    self.detect_board()
                    self.detect_flash_target()
                    self._refresh_flash_preflight()
                    self._refresh_summary()
                    return True
                diagnostic = self._format_probe_attempts(self._last_speeduino_probe_attempts)
                if diagnostic:
                    exc = RuntimeError(f"{exc}\n\nProbe attempts:\n{diagnostic}")
            self.timer.stop()
            if show_failures:
                QMessageBox.critical(self, "Connection Failed", str(exc))
                self.statusBar().showMessage("Connection failed")
            else:
                self.statusBar().showMessage("Project opened offline; no controller responded.")
            return False
        self.timer.start()
        self.tuning_workspace.set_session_client(self.session_service.client, SessionState.CONNECTED)
        new_signature = info.firmware_signature
        if (
            prior_signature is not None
            and new_signature is not None
            and not controller_signature_matches_definition(new_signature, prior_signature)
        ):
            self.statusBar().showMessage(
                f"Warning: firmware signature changed since last session "
                f"({prior_signature!r} → {new_signature!r}). "
                "Verify your definition and tune still match this firmware."
            )
            QMessageBox.warning(
                self,
                "Firmware Signature Changed",
                f"The connected controller is reporting a different firmware signature than the previous session.\n\n"
                f"Previous: {prior_signature}\n"
                f"Current:  {new_signature}\n\n"
                "If you recently flashed new firmware, ensure the loaded ECU definition and tune file "
                "still match the running firmware before writing or burning any values.",
            )
        else:
            self.statusBar().showMessage(f"Connected via {info.transport_name}")
        self.detect_board()
        self.detect_flash_target()
        self._refresh_flash_preflight()
        self._refresh_summary()
        self.live_data_server.update_status(connected=True, sync_state="connected")
        self._refresh_trigger_logger_combo()
        self.hardware_test_panel.set_connected(True)
        self.wideband_calibration_panel.set_connected(True)
        return True

    def disconnect_session(self) -> None:
        self.timer.stop()
        self.session_service.disconnect()
        self._last_runtime_snapshot = None
        self.tuning_workspace.presenter.set_runtime_snapshot(None)
        self.dashboard_panel.set_runtime_snapshot(None)
        self.tuning_workspace.go_offline()
        self._render_runtime_telemetry()
        if self._last_trigger_log_path is not None:
            self._analyze_trigger_log()
        self.statusBar().showMessage("Disconnected")
        self._refresh_summary()
        self.live_data_server.update_status(connected=False, sync_state="offline")
        self._refresh_trigger_logger_combo()
        self.hardware_test_panel.set_connected(False)
        self.wideband_calibration_panel.set_connected(False)

    def power_cycle_controller(self) -> None:
        if self.session_service.client is None or self.session_service.info.state != SessionState.CONNECTED:
            self.statusBar().showMessage("No connected controller to power cycle.")
            return
        config = self._connection_config()
        self.disconnect_session()
        if self._connect_session_with_config(config, show_failures=True):
            self.tuning_workspace.sync_from_ecu()
            self._refresh_summary()
            self.statusBar().showMessage(
                "Controller session reconnected. If the board resets on reconnect, restart-required settings should now be active."
            )

    def _auto_connect_project(self, project: Project) -> None:
        if self.session_service.client is not None or not project.connection_profiles:
            return
        profile = project.connection_profiles[0]
        if not profile.transport:
            return
        if self.project_auto_connect_worker is not None and self.project_auto_connect_worker.isRunning():
            return
        config = self._connection_config()
        self._pending_auto_connect_project_path = project.project_path
        self.project_auto_connect_worker = ProjectAutoConnectWorker(config, self.definition, project.project_path)
        self.project_auto_connect_worker.succeeded.connect(self._finish_project_auto_connect)
        self.project_auto_connect_worker.failed.connect(self._fail_project_auto_connect)
        self.project_auto_connect_worker.finished.connect(self._clear_project_auto_connect_worker)
        self.project_auto_connect_worker.start()
        self.statusBar().showMessage("Opening project offline first while checking for the configured controller...")

    def _finish_project_auto_connect(self, result: ConnectionProbeResult) -> None:
        current_path = self.project.project_path if self.project is not None else None
        if self.session_service.client is not None or current_path != self._pending_auto_connect_project_path:
            return
        if not self._connect_session_with_config(result.config, show_failures=False):
            return
        controller_signature = getattr(self.session_service.client, "firmware_signature", None)
        definition_signature = self.definition.firmware_signature if self.definition is not None else None
        if controller_signature_matches_definition(controller_signature, definition_signature):
            self.tuning_workspace.sync_from_ecu()
            self._refresh_summary()
        else:
            self.statusBar().showMessage(
                "Connected controller signature does not match the loaded definition; skipped automatic ECU sync."
            )

    def _fail_project_auto_connect(self, _message: str) -> None:
        current_path = self.project.project_path if self.project is not None else None
        if current_path != self._pending_auto_connect_project_path:
            return
        self.statusBar().showMessage("Project opened offline; no controller responded.")

    def _clear_project_auto_connect_worker(self) -> None:
        self.project_auto_connect_worker = None
        self._pending_auto_connect_project_path = None

    def start_simulator(self) -> None:
        if self.simulator_server is not None:
            self.statusBar().showMessage("Simulator already running")
            return
        protocol = self._selected_protocol()
        if protocol == ProtocolType.XCP:
            self.simulator_server = XcpSimulatorServer()
        else:
            self.simulator_server = ProtocolSimulatorServer()
        self.simulator_server.start()
        host, port = self.simulator_server.address
        self.transport_combo.setCurrentIndex(self.transport_combo.findData(TransportType.TCP))
        self.host_edit.setText(host)
        self.port_spin.setValue(port)
        self.statusBar().showMessage(f"{protocol.value} simulator listening on {host}:{port}")

    def stop_simulator(self) -> None:
        if self.simulator_server is None:
            return
        self.simulator_server.stop()
        self.simulator_server = None
        self.statusBar().showMessage("Simulator stopped")

    def _poll_runtime(self) -> None:
        try:
            snapshot = self.session_service.poll_runtime()
        except Exception as exc:
            self.timer.stop()
            self.statusBar().showMessage(str(exc))
            return
        self._last_runtime_snapshot = snapshot
        self.tuning_workspace.presenter.set_runtime_snapshot(snapshot)
        self.dashboard_panel.set_runtime_snapshot(snapshot)
        if self.live_data_server.is_running:
            self.live_data_server.update_snapshot(snapshot)
        if self.live_capture_service.is_recording:
            self.live_capture_service.append(snapshot)
            self.logging_panel.update_capture_status(self.live_capture_service.status().status_text)
        capabilities = self.session_service.info.firmware_capabilities
        uncertain_groups = capabilities.uncertain_channel_groups() if capabilities is not None else frozenset()
        self.channels_table.setRowCount(len(snapshot.values))
        for row, channel in enumerate(snapshot.values):
            name_item = QTableWidgetItem(channel.name)
            value_item = QTableWidgetItem(str(channel.value))
            if channel.name in uncertain_groups:
                dim = QColor("#888888")
                name_item.setForeground(dim)
                value_item.setForeground(dim)
                tip = f"{channel.name}: this channel was not advertised by the firmware capabilities handshake — value may be unreliable."
                name_item.setToolTip(tip)
                value_item.setToolTip(tip)
            self.channels_table.setItem(row, 0, name_item)
            self.channels_table.setItem(row, 1, value_item)
        self._render_runtime_telemetry()
        if self._last_trigger_log_path is not None:
            self._analyze_trigger_log()
        self._render_surface_evidence()

    def _set_shell_chip_state(self, chip: QLabel, text: str, severity: str) -> None:
        chip.setText(text)
        chip.setProperty("severity", severity)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def _set_shell_action_role(self, button: QPushButton, role: str) -> None:
        button.setProperty("shellActionRole", role)
        button.style().unpolish(button)
        button.style().polish(button)

    def _set_surface_chip_state(self, chip: QLabel, text: str, severity: str) -> None:
        chip.setText(text)
        chip.setProperty("severity", severity)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def _render_surface_mode(self, index: int) -> None:
        if not hasattr(self, "tab_widget") or index < 0 or index >= self.tab_widget.count():
            return
        snapshot = build_surface_mode_snapshot(self.tab_widget.tabText(index))
        self.surface_mode_badge.setText(snapshot.mode_label)
        self.surface_mode_badge.setProperty("emphasis", snapshot.emphasis)
        self.surface_mode_badge.style().unpolish(self.surface_mode_badge)
        self.surface_mode_badge.style().polish(self.surface_mode_badge)
        self.surface_mode_title.setText(snapshot.title)
        self.surface_mode_description.setText(snapshot.description)

    def _open_workspace_context_tab(self, index: int) -> None:
        self.tab_widget.setCurrentIndex(1)
        self.tuning_workspace.workspace_details_tabs.setCurrentIndex(index)

    def _render_surface_evidence(self) -> None:
        workspace_snapshot = self.tuning_workspace.presenter.snapshot()
        self._last_evidence_replay_snapshot = EvidenceReplayService().build(
            session_info=self.session_service.info,
            workspace_snapshot=workspace_snapshot,
            runtime_snapshot=self._last_runtime_snapshot,
        )
        self._remember_evidence_replay_snapshot(self._last_evidence_replay_snapshot)
        review_snapshot = self._workspace_evidence_replay_snapshot or self._last_evidence_replay_snapshot
        self.tuning_workspace.set_evidence_review_snapshots(
            review_snapshot,
            latest_snapshot=self._last_evidence_replay_snapshot,
        )
        snapshot = build_surface_evidence_snapshot(
            session_info=self.session_service.info,
            workspace_snapshot=workspace_snapshot,
            runtime_snapshot=self._last_runtime_snapshot,
        )
        for chip, text, severity in (
            (self.runtime_connection_chip, snapshot.connection_text, snapshot.connection_severity),
            (self.runtime_source_chip, snapshot.source_text, snapshot.source_severity),
            (self.runtime_sync_chip, snapshot.sync_text, snapshot.sync_severity),
            (self.runtime_changes_chip, snapshot.changes_text, snapshot.changes_severity),
            (self.runtime_ops_chip, snapshot.log_text, snapshot.log_severity),
            (self.runtime_samples_chip, snapshot.runtime_text, snapshot.runtime_severity),
            (self.flash_connection_chip, snapshot.connection_text, snapshot.connection_severity),
            (self.flash_source_chip, snapshot.source_text, snapshot.source_severity),
            (self.flash_sync_chip, snapshot.sync_text, snapshot.sync_severity),
            (self.flash_changes_chip, snapshot.changes_text, snapshot.changes_severity),
            (self.flash_ops_chip, snapshot.log_text, snapshot.log_severity),
        ):
            self._set_surface_chip_state(chip, text, severity)
        self.runtime_evidence_label.setText(snapshot.summary_text)
        self.flash_evidence_label.setText(snapshot.summary_text)
        has_sync = workspace_snapshot.sync_state is not None
        has_review = len(workspace_snapshot.workspace_review.entries) > 0
        self.runtime_sync_button.setEnabled(has_sync)
        self.flash_sync_button.setEnabled(has_sync)
        self.runtime_review_button.setEnabled(has_review)
        self.flash_review_button.setEnabled(has_review)
        has_evidence = self._last_evidence_replay_snapshot is not None
        has_evidence_history = bool(self._evidence_replay_history)
        self.runtime_history_button.setEnabled(has_evidence_history)
        self.flash_history_button.setEnabled(has_evidence_history)
        self.runtime_copy_evidence_button.setEnabled(has_evidence)
        self.runtime_export_evidence_button.setEnabled(has_evidence)
        self.flash_copy_evidence_button.setEnabled(has_evidence)
        self.flash_export_evidence_button.setEnabled(has_evidence)

    def _render_runtime_telemetry(self) -> None:
        summary = self.speeduino_runtime_telemetry_service.decode(self._last_runtime_snapshot)
        capabilities = self.session_service.info.firmware_capabilities
        capability_prefix = ""
        if capabilities is not None:
            details: list[str] = [f"Capability source: {capabilities.source}"]
            if capabilities.serial_protocol_version is not None:
                details.append(f"serial protocol v{capabilities.serial_protocol_version}")
            if capabilities.blocking_factor is not None and capabilities.table_blocking_factor is not None:
                details.append(
                    f"blocking {capabilities.blocking_factor}/{capabilities.table_blocking_factor}"
                )
            if capabilities.live_data_size is not None:
                details.append(f"live data size {capabilities.live_data_size} bytes")
            capability_prefix = ", ".join(details) + ".\n"
        self.runtime_capability_label.setText(
            f"{capability_prefix}{summary.capability_summary_text}\n{summary.operator_summary_text}\n{summary.setup_guidance_text}\n{summary.persistence_summary_text}"
        )
        self.flash_runtime_label.setText(
            f"Runtime Evidence: {capability_prefix}{summary.capability_summary_text} {summary.runtime_summary_text} {summary.setup_guidance_text} {summary.persistence_summary_text}"
        )
        self._update_connection_inputs()

    def _base_connection_hint_text(self) -> str:
        transport = self._selected_transport()
        protocol = self._selected_protocol()
        if transport == TransportType.MOCK:
            return "Mock transport is fully supported for offline and simulator-driven workflows."
        if transport in {TransportType.TCP, TransportType.UDP} and protocol == ProtocolType.SIM_JSON:
            return "TCP/UDP with SIM_JSON is intended for the built-in simulator and compatible JSON-line controller endpoints."
        if transport == TransportType.SERIAL and protocol == ProtocolType.SPEEDUINO:
            return "Native Speeduino serial is available. Use the controller serial port, matching INI, and baud rate expected by the firmware."
        if protocol == ProtocolType.XCP:
            return "XCP connections currently support connect plus runtime/status reads. Parameter read/write and burn are still pending."
        if transport == TransportType.SERIAL:
            return "Serial transport is available, but the selected protocol has partial support."
        return "Selected connection mode has partial support."

    def _render_shell_status(self) -> None:
        workspace_snapshot = self.tuning_workspace.presenter.snapshot()
        snapshot = build_shell_status_snapshot(
            project=self.project,
            definition=self.definition,
            tune_file=self.tune_file,
            session_info=self.session_service.info,
            workspace_snapshot=workspace_snapshot,
        )
        self._set_shell_chip_state(self.project_chip, snapshot.project_text, snapshot.project_severity)
        self._set_shell_chip_state(self.session_chip, snapshot.session_text, snapshot.session_severity)
        self._set_shell_chip_state(self.source_chip, snapshot.source_text, snapshot.source_severity)
        self._set_shell_chip_state(self.signature_chip, snapshot.signature_text, snapshot.signature_severity)
        self._set_shell_chip_state(self.shell_staged_chip, snapshot.staged_text, snapshot.staged_severity)
        self._set_shell_chip_state(self.shell_hardware_chip, snapshot.hardware_text, snapshot.hardware_severity)
        shell_next_steps = snapshot.next_steps_text
        if workspace_snapshot.post_burn_verification_text:
            shell_next_steps = self._build_post_burn_shell_text(shell_next_steps)
        self.shell_next_steps_label.setText(shell_next_steps)
        actions = {action.action_id: action for action in snapshot.actions}
        session_action = actions.get("session.toggle")
        refresh_action = actions.get("session.refresh")
        review_action = actions.get("workspace.review")
        if session_action is not None:
            self.shell_connect_button.setText(session_action.label)
            self.shell_connect_button.setEnabled(session_action.enabled)
        if refresh_action is not None:
            self.shell_refresh_button.setText(refresh_action.label)
            self.shell_refresh_button.setEnabled(refresh_action.enabled)
        if review_action is not None:
            self.shell_review_button.setText(review_action.label)
            self.shell_review_button.setEnabled(review_action.enabled)
        primary_action_id = snapshot.primary_action_id
        self._set_shell_action_role(
            self.shell_connect_button,
            "primary" if primary_action_id == "session.toggle" else "secondary",
        )
        self._set_shell_action_role(
            self.shell_refresh_button,
            "primary" if primary_action_id == "session.refresh" else "secondary",
        )
        self._set_shell_action_role(
            self.shell_review_button,
            "primary" if primary_action_id == "workspace.review" else "secondary",
        )

    def _build_post_burn_shell_text(self, base_text: str) -> str:
        lines = [base_text]
        controller_signature = getattr(self.session_service.client, "firmware_signature", None)
        definition_signature = self.definition.firmware_signature if self.definition is not None else None
        if controller_signature and definition_signature:
            if controller_signature_matches_definition(controller_signature, definition_signature):
                lines.append("Connected controller signature matches the loaded definition.")
            else:
                lines.append("Connected controller signature does not match the loaded definition.")
        runtime_summary = self.speeduino_runtime_telemetry_service.decode(self._last_runtime_snapshot)
        if runtime_summary.board_capabilities.raw_value is not None or runtime_summary.spi_flash_health is not None:
            lines.append(runtime_summary.persistence_summary_text)
        return "\n".join(lines)

    def _execute_shell_action(self, action_id: str) -> None:
        if action_id == "session.toggle":
            if self.session_service.info.state == SessionState.CONNECTED:
                self.disconnect_session()
            else:
                self.connect_session()
            return
        if action_id == "session.refresh":
            self.tab_widget.setCurrentIndex(1)
            self.tuning_workspace.sync_from_ecu()
            self._refresh_summary()
            return
        if action_id == "workspace.review":
            self.tab_widget.setCurrentIndex(1)
            self.tuning_workspace.workspace_details_tabs.setCurrentIndex(2)
            self._refresh_summary()

    def _refresh_summary(self) -> None:
        started = time.perf_counter() if self._table_debug_enabled else None
        project_lines = self._project_summary_lines()
        definition_lines = self._definition_summary_lines()
        tune_lines = self._tune_summary_lines()
        self.summary_text.setPlainText("\n".join(project_lines + [""] + definition_lines + [""] + tune_lines).strip())
        staged_entries = self.staged_change_service.summarize(self.local_tune_edit_service)
        if staged_entries:
            staged_lines = ["Staged Changes:"]
            staged_lines.extend(f"{entry.name}: {entry.preview}" for entry in staged_entries)
            self.staged_changes_text.setPlainText("\n".join(staged_lines))
        else:
            self.staged_changes_text.setPlainText("Staged Changes: none")
        self.summary_label.setText(
            f"Project: {self.project.name if self.project else 'none'} | "
            f"ECU: {self.definition.name if self.definition else 'none'} | "
            f"Session: {self.session_service.info.state.value}"
        )
        self._render_shell_status()
        self._render_surface_evidence()
        if self._table_debug_enabled and started is not None:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            emit_table_debug_log(f"[TUNER_TABLE_DEBUG] main_window_refresh_summary:end elapsed_ms={elapsed_ms:.2f}")

    def _reload_tuning_workspace(self) -> None:
        if self._workspace_ui_state is None:
            self._workspace_ui_state = self.tuning_workspace.capture_ui_state()
        self.tuning_workspace.set_context(self.definition, self.tune_file)
        if self.session_service.client is not None and self.session_service.info.state == SessionState.CONNECTED:
            self.tuning_workspace.set_session_client(self.session_service.client, SessionState.CONNECTED)
        else:
            self.tuning_workspace.go_offline()
        self.tuning_workspace.restore_ui_state(self._workspace_ui_state)
        self._workspace_ui_state = self.tuning_workspace.capture_ui_state()
        self.engine_setup_panel.set_presenter(self.tuning_workspace.presenter)
        self.dashboard_panel.set_available_pages(
            [(e.page_id, e.title) for e in self.tuning_workspace.quick_open_entries()]
        )
        if self.definition is not None:
            self.dashboard_panel.set_available_channels(
                list(self.definition.output_channel_definitions)
            )
            self.dashboard_panel.set_front_page_data(
                gauge_configurations=list(self.definition.gauge_configurations),
                front_page_gauges=list(self.definition.front_page_gauges),
                front_page_indicators=list(self.definition.front_page_indicators),
            )
            self.logging_panel.set_channel_defs(list(self.definition.output_channel_definitions))
        self._refresh_trigger_logger_combo()
        self.hardware_test_panel.set_definition(self.definition)

    def _open_quick_open(self) -> None:
        if self.tab_widget.currentWidget() is not self.tab_widget.widget(1):
            self.tab_widget.setCurrentIndex(1)
        entries = self.tuning_workspace.quick_open_entries()
        if not entries:
            self.statusBar().showMessage("No tuning pages available to open.", 3000)
            return
        dialog = QuickOpenDialog(entries, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_page_id is None:
            return
        self.tuning_workspace.open_page(dialog.selected_page_id)

    def _open_command_palette(self) -> None:
        entries = build_command_palette_entries(
            self.tuning_workspace.quick_open_entries(),
            self.tuning_workspace.command_actions(),
            self._global_command_palette_entries(),
        )
        if not entries:
            self.statusBar().showMessage("No commands available.", 3000)
            return
        dialog = CommandPaletteDialog(entries, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_entry is None:
            return
        entry = dialog.selected_entry
        if entry.target == "page":
            if self.tab_widget.currentWidget() is not self.tab_widget.widget(1):
                self.tab_widget.setCurrentIndex(1)
            self.tuning_workspace.open_page(entry.entry_id)
            return
        if entry.target == "action":
            if self.tab_widget.currentWidget() is not self.tab_widget.widget(1):
                self.tab_widget.setCurrentIndex(1)
            self.tuning_workspace.execute_action(entry.entry_id)
            return
        self._execute_global_command(entry.entry_id)

    def _global_command_palette_entries(self) -> tuple[CommandPaletteEntry, ...]:
        return (
            CommandPaletteEntry("surface.overview", "Go To Overview", "Surface", "Switch to the overview summary tab.", "global"),
            CommandPaletteEntry("surface.tuning", "Go To Tuning", "Surface", "Switch to the tuning workspace tab.", "global"),
            CommandPaletteEntry("surface.engine_setup", "Go To Engine Setup", "Surface", "Switch to the Engine Setup wizard tab.", "global"),
            CommandPaletteEntry("surface.runtime", "Go To Runtime", "Surface", "Switch to the runtime/session tab.", "global"),
            CommandPaletteEntry("surface.logging", "Go To Logging", "Surface", "Switch to the graphing and logging tab.", "global"),
            CommandPaletteEntry("surface.dashboard", "Go To Dashboard", "Surface", "Switch to the live gauge cluster dashboard.", "global"),
            CommandPaletteEntry("surface.trigger_logs", "Go To Trigger Logs", "Surface", "Switch to the trigger troubleshooting tab.", "global"),
            CommandPaletteEntry("surface.flash", "Go To Flash", "Surface", "Switch to the firmware flasher tab.", "global"),
            CommandPaletteEntry("evidence.history", "Open Evidence History", "Evidence", "Review recent captured evidence bundles.", "global"),
            CommandPaletteEntry("evidence.use_latest", "Use Latest Evidence For Review", "Evidence", "Clear any pinned historical evidence and return workspace review to the latest capture.", "global"),
            CommandPaletteEntry("evidence.copy", "Copy Evidence Snapshot", "Evidence", "Copy the latest captured evidence bundle to the clipboard.", "global"),
            CommandPaletteEntry("evidence.export", "Export Evidence Snapshot", "Evidence", "Export the latest captured evidence bundle as text or JSON.", "global"),
            CommandPaletteEntry("session.connect", "Connect Session", "Session", "Connect to the configured controller session.", "global"),
            CommandPaletteEntry("session.disconnect", "Disconnect Session", "Session", "Disconnect the active controller session.", "global"),
            CommandPaletteEntry("session.start_simulator", "Start Simulator", "Session", "Start the local protocol simulator.", "global"),
            CommandPaletteEntry("session.stop_simulator", "Stop Simulator", "Session", "Stop the local protocol simulator.", "global"),
        )

    def _execute_global_command(self, entry_id: str) -> None:
        if entry_id == "surface.overview":
            self.tab_widget.setCurrentIndex(0)
        elif entry_id == "surface.tuning":
            self.tab_widget.setCurrentIndex(1)
        elif entry_id == "surface.engine_setup":
            self.tab_widget.setCurrentIndex(2)
        elif entry_id == "surface.runtime":
            self.tab_widget.setCurrentIndex(3)
        elif entry_id == "surface.logging":
            self.tab_widget.setCurrentIndex(4)
        elif entry_id == "surface.dashboard":
            self.tab_widget.setCurrentIndex(5)
        elif entry_id == "surface.trigger_logs":
            self.tab_widget.setCurrentIndex(6)
        elif entry_id == "surface.flash":
            self.tab_widget.setCurrentIndex(7)
        elif entry_id == "evidence.history":
            self._open_evidence_history_dialog()
        elif entry_id == "evidence.use_latest":
            self._use_latest_evidence_for_workspace()
        elif entry_id == "evidence.copy":
            self._copy_latest_evidence_replay()
        elif entry_id == "evidence.export":
            self._export_latest_evidence_replay()
        elif entry_id == "session.connect":
            self.connect_session()
        elif entry_id == "session.disconnect":
            self.disconnect_session()
        elif entry_id == "session.start_simulator":
            self.start_simulator()
        elif entry_id == "session.stop_simulator":
            self.stop_simulator()

    @staticmethod
    def _evidence_replay_signature(snapshot: EvidenceReplaySnapshot) -> tuple:
        return (
            snapshot.session_state,
            snapshot.connection_text,
            snapshot.source_text,
            snapshot.sync_summary_text,
            snapshot.staged_summary_text,
            snapshot.operation_summary_text,
            snapshot.runtime_summary_text,
            tuple((item.name, item.value, item.units) for item in snapshot.runtime_channels),
        )

    def _remember_evidence_replay_snapshot(self, snapshot: EvidenceReplaySnapshot) -> None:
        if self._evidence_replay_history:
            if self._evidence_replay_signature(self._evidence_replay_history[-1]) == self._evidence_replay_signature(snapshot):
                self._evidence_replay_history[-1] = snapshot
                return
        self._evidence_replay_history.append(snapshot)
        if len(self._evidence_replay_history) > 12:
            del self._evidence_replay_history[:-12]

    def _copy_latest_evidence_replay(self) -> None:
        snapshot = self._last_evidence_replay_snapshot
        if snapshot is None:
            self.statusBar().showMessage("No evidence snapshot available yet.", 3000)
            return
        text = EvidenceReplayFormatterService().to_text(snapshot)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Evidence snapshot copied to clipboard.", 3000)

    def _export_latest_evidence_replay(self) -> None:
        snapshot = self._last_evidence_replay_snapshot
        if snapshot is None:
            self.statusBar().showMessage("No evidence snapshot available yet.", 3000)
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Evidence Snapshot",
            "evidence_snapshot.txt",
            "Text Files (*.txt);;JSON Files (*.json)",
        )
        if not path:
            return
        formatter = EvidenceReplayFormatterService()
        payload = formatter.to_json(snapshot) if path.lower().endswith(".json") else formatter.to_text(snapshot)
        Path(path).write_text(payload, encoding="utf-8")
        self.statusBar().showMessage(f"Evidence snapshot exported to {path}", 3000)

    def _open_evidence_history_dialog(self) -> None:
        if not self._evidence_replay_history:
            self.statusBar().showMessage("No evidence history captured yet.", 3000)
            return
        dialog = EvidenceReplayDialog(self._evidence_replay_history, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_snapshot is not None:
            self._workspace_evidence_replay_snapshot = dialog.selected_snapshot
            self.tuning_workspace.set_evidence_review_snapshots(
                dialog.selected_snapshot,
                latest_snapshot=self._last_evidence_replay_snapshot,
            )
            self.statusBar().showMessage("Historical evidence snapshot pinned to workspace review.", 3000)

    def _use_latest_evidence_for_workspace(self) -> None:
        self._workspace_evidence_replay_snapshot = None
        if self._last_evidence_replay_snapshot is None:
            self.statusBar().showMessage("No live evidence snapshot available yet.", 3000)
            return
        self.tuning_workspace.set_evidence_review_snapshots(
            self._last_evidence_replay_snapshot,
            latest_snapshot=self._last_evidence_replay_snapshot,
        )
        self.statusBar().showMessage("Workspace review returned to the latest evidence snapshot.", 3000)

    def _schedule_project_ui_state_persist(self, *_args) -> None:
        if self._suspend_project_state_persist or self.project is None or self.project.project_path is None:
            return
        self._project_state_save_timer.start()

    def _persist_project_ui_state(self) -> None:
        if self._suspend_project_state_persist or self.project is None or self.project.project_path is None:
            return
        workspace_state = self.tuning_workspace.capture_ui_state()
        self._workspace_ui_state = workspace_state
        ui_metadata = serialize_workspace_project_state(self.tab_widget.currentIndex(), workspace_state)
        self.project.metadata.update(ui_metadata)
        try:
            self.project_service.save_project(self.project)
        except Exception:
            pass

    def _recent_project_paths(self) -> tuple[Path, ...]:
        raw_value = self.settings.value("recentProjects", [], type=list)
        if not isinstance(raw_value, list):
            return ()
        paths: list[Path] = []
        for raw_path in raw_value:
            try:
                path = Path(str(raw_path))
            except Exception:
                continue
            if path.exists():
                paths.append(path)
        return tuple(paths)

    def _last_project_path(self) -> Path | None:
        raw_value = self.settings.value("lastProjectPath", "", type=str)
        if not raw_value:
            return None
        path = Path(raw_value)
        return path if path.exists() else None

    def _remember_project_path(self, path: Path) -> None:
        updated = update_recent_project_paths(
            tuple(str(item) for item in self._recent_project_paths()),
            str(path),
        )
        self.settings.setValue("recentProjects", list(updated))
        self.settings.setValue("lastProjectPath", str(Path(path).resolve()))
        self._refresh_recent_projects_menu()

    def _refresh_recent_projects_menu(self) -> None:
        if not hasattr(self, "recent_projects_menu"):
            return
        menu = self.recent_projects_menu
        menu.clear()
        summaries = build_recent_project_summaries(self._recent_project_paths(), self.project_service)
        if not summaries:
            action = menu.addAction("No recent projects")
            action.setEnabled(False)
        else:
            for summary in summaries:
                action = menu.addAction(format_recent_project_menu_label(summary))
                action.setToolTip(str(summary.path))
                action.triggered.connect(
                    lambda checked=False, path=summary.path: self._open_project_path(path)
                )
        menu.addSeparator()
        browse_action = menu.addAction("Browse...")
        browse_action.triggered.connect(self.open_project)

    def _project_summary_lines(self) -> list[str]:
        if self.project is None:
            return ["Project: not loaded"]
        return [
            f"Project: {self.project.name}",
            f"Project Path: {self.project.project_path}",
            f"ECU Definition Path: {self.project.ecu_definition_path}",
            f"Tune File Path: {self.project.tune_file_path}",
            f"Dashboards: {', '.join(self.project.dashboards) if self.project.dashboards else 'none'}",
            f"Metadata Keys: {len(self.project.metadata)}",
        ]

    def _definition_summary_lines(self) -> list[str]:
        if self.definition is None:
            return ["ECU Definition: not loaded"]
        return [
            f"ECU Definition: {self.definition.name}",
            f"Firmware Signature: {self.definition.firmware_signature or 'n/a'}",
            f"Transport Hint: {self.definition.transport_hint or 'n/a'}",
            f"Query Command: {self.definition.query_command or 'n/a'}",
            f"Endianness: {self.definition.endianness or 'n/a'}",
            f"Pages: {len(self.definition.page_sizes) if self.definition.page_sizes else 'n/a'}",
            f"Output Channels: {', '.join(self.definition.output_channels[:12]) if self.definition.output_channels else 'none'}",
            f"Scalars: {len(self.definition.scalars)}",
            f"Tables: {len(self.definition.tables)}",
            f"Metadata Keys: {len(self.definition.metadata)}",
            f"Detected Board: {self._detected_board_label()}",
        ]

    def _tune_summary_lines(self) -> list[str]:
        if self.tune_file is None:
            return ["Tune File: not loaded"]
        return [
            f"Tune File Signature: {self.tune_file.signature or 'n/a'}",
            f"Tune Firmware: {self.tune_file.firmware_info or 'n/a'}",
            f"Tune Format: {self.tune_file.file_format or 'n/a'}",
            f"Tune Pages: {self.tune_file.page_count if self.tune_file.page_count is not None else 'n/a'}",
            f"Tune Constants: {len(self.tune_file.constants)}",
            f"Tune PC Variables: {len(self.tune_file.pc_variables)}",
        ]

    def _connection_config(self) -> ConnectionConfig:
        transport = self._selected_transport()
        return ConnectionConfig(
            transport=transport,
            protocol=self._selected_protocol(),
            serial_port=self.serial_combo.currentText(),
            baud_rate=self.baud_spin.value(),
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
        )

    def _attempt_speeduino_serial_discovery(
        self,
        base_config: ConnectionConfig,
    ) -> tuple[object, ConnectionConfig, list[str]] | None:
        attempts: list[str] = []
        for candidate in _iter_speeduino_probe_candidates(base_config):
            try:
                info = self.session_service.connect(candidate)
                self._last_speeduino_probe_attempts = (
                    attempts + [f"{candidate.serial_port} @ {candidate.baud_rate}: connected"]
                )
                return info, candidate, self._last_speeduino_probe_attempts
            except Exception as exc:
                attempts.append(f"{candidate.serial_port} @ {candidate.baud_rate}: {exc}")
                continue
        self._last_speeduino_probe_attempts = attempts
        return None

    def _format_probe_attempts(self, attempts: list[str]) -> str:
        if not attempts:
            return ""
        return "\n".join(f"- {attempt}" for attempt in attempts[:12])

    def _refresh_serial_ports(self) -> None:
        current = self.serial_combo.currentText()
        ports = available_serial_ports()
        self.serial_combo.clear()
        self.serial_combo.addItems(ports or [""])
        if not self.flash_port_edit.text() and ports:
            self.flash_port_edit.setText(ports[0])
        if current:
            idx = self.serial_combo.findText(current)
            if idx >= 0:
                self.serial_combo.setCurrentIndex(idx)
        self.detect_flash_target()

    def _update_connection_inputs(self) -> None:
        transport = self._selected_transport()
        protocol = self._selected_protocol()
        is_serial = transport == TransportType.SERIAL
        is_network = transport in {TransportType.TCP, TransportType.UDP}
        self.serial_combo.setEnabled(is_serial)
        self.baud_spin.setEnabled(is_serial)
        self.host_edit.setEnabled(is_network)
        self.port_spin.setEnabled(is_network)
        hint = self._base_connection_hint_text()
        telemetry = self.speeduino_runtime_telemetry_service.decode(self._last_runtime_snapshot)
        if transport == TransportType.SERIAL and protocol == ProtocolType.SPEEDUINO and self.session_service.is_connected():
            hint = f"{hint}\n{telemetry.setup_guidance_text}"
        # WiFi button: enabled when firmware has reported WiFi transport capability,
        # or always visible as a shortcut even before first connect.
        wifi_capable = telemetry.board_capabilities.wifi_transport
        self.wifi_connect_button.setEnabled(not self.session_service.is_connected())
        if wifi_capable:
            self.wifi_connect_button.setText("Connect via WiFi ✓")
        else:
            self.wifi_connect_button.setText("Connect via WiFi")
        self.connection_hint_label.setText(hint)

    def _update_flash_inputs(self) -> None:
        board = self._selected_board_family()
        is_avr = board == BoardFamily.ATMEGA2560
        is_teensy = board in {BoardFamily.TEENSY35, BoardFamily.TEENSY36, BoardFamily.TEENSY41}
        is_stm32 = board == BoardFamily.STM32F407_DFU
        self.flash_port_edit.setEnabled(is_avr or is_teensy)
        self.flash_vid_edit.setEnabled(is_stm32)
        self.flash_pid_edit.setEnabled(is_stm32)

    def _selected_transport(self) -> TransportType:
        value = self.transport_combo.currentData()
        if isinstance(value, TransportType):
            return value
        return TransportType(str(value).lower())

    def _selected_protocol(self) -> ProtocolType:
        value = self.protocol_combo.currentData()
        if isinstance(value, ProtocolType):
            return value
        return ProtocolType(str(value).lower())

    def _selected_board_family(self) -> BoardFamily:
        value = self.flash_board_combo.currentData()
        if isinstance(value, BoardFamily):
            return value
        return BoardFamily(str(value))

    def _detected_board_label(self) -> str:
        detected = self.board_detection_service.detect(
            definition=self.definition,
            tune_file=self.tune_file,
            session_info=self.session_service.info,
        )
        return detected.value if detected is not None else "n/a"

    def _flash_request(self) -> FirmwareFlashRequest:
        return FirmwareFlashRequest(
            firmware_path=Path(self.flash_firmware_edit.text().strip()),
            board_family=self._selected_board_family(),
            tool_root=Path(self.flash_tool_root_edit.text().strip()),
            serial_port=self.flash_port_edit.text().strip() or None,
            usb_vid=self.flash_vid_edit.text().strip() or None,
            usb_pid=self.flash_pid_edit.text().strip() or None,
        )

    def _refresh_flash_preflight(self) -> FlashPreflightReport:
        _session = self.session_service.info
        report = self.flash_preflight_service.validate(
            firmware_path=Path(self.flash_firmware_edit.text().strip()),
            selected_board=self._selected_board_family(),
            detected_board=self.board_detection_service.detect(
                definition=self.definition,
                tune_file=self.tune_file,
                session_info=_session,
            ),
            definition=self.definition,
            tune_file=self.tune_file,
            firmware_capabilities=_session.firmware_capabilities,
            connected_firmware_signature=_session.firmware_signature,
        )
        if report.errors:
            self.flash_preflight_label.setText(f"Preflight: blocked - {report.errors[0]}")
        elif report.warnings:
            self.flash_preflight_label.setText(f"Preflight: warning - {report.warnings[0]}")
        else:
            self.flash_preflight_label.setText("Preflight: OK")
        return report

    def _navigate_dashboard_to_tuning_page(self, page_id: str) -> None:
        self.tab_widget.setCurrentIndex(1)  # Tuning tab (index unchanged)
        self.tuning_workspace.open_page(page_id)

    def _refresh_flash_guidance(self) -> None:
        entry = self._selected_flash_firmware_entry()
        selected_board = self._selected_board_family()
        detected_board = self.board_detection_service.detect(
            definition=self.definition,
            tune_file=self.tune_file,
            session_info=self.session_service.info,
        )
        target = self.flash_target_detection_service.detect_preferred_target(selected_board)

        board_text = detected_board.value if detected_board is not None else selected_board.value
        artifact_text = "experimental" if entry is not None and entry.is_experimental else "production"
        if entry is not None and entry.artifact_kind.value != "standard":
            artifact_text = f"{artifact_text}, {entry.artifact_kind.value}"

        lines = [
            f"Bench Guidance: {board_text} / {artifact_text}",
            self._flash_target_guidance_text(selected_board, target),
        ]
        if entry is not None and entry.is_experimental:
            lines.append("Use bench power, flash the selected artifact, then force a full power cycle before reconnecting the controller port.")
        else:
            lines.append("Flash the selected artifact, reconnect on the controller serial port, and verify the reported signature before writing tune data.")

        if self.definition is not None and self.tune_file is not None:
            lines.append("Loaded INI and tune are present. Verify they still match the flashed signature family before burning changes.")
        elif self.definition is not None:
            lines.append("Load a paired base tune after reconnect so the flashed firmware, INI, and tune stay aligned.")
        else:
            lines.append("Load the paired INI and base tune for this firmware before tuning; avoid mixing loose files unless you are intentionally testing.")

        runtime_summary = self.speeduino_runtime_telemetry_service.decode(self._last_runtime_snapshot)
        if runtime_summary.board_capabilities.raw_value is not None or runtime_summary.spi_flash_health is not None:
            lines.append(runtime_summary.persistence_summary_text)

        lines.append("Recovery: if reconnect fails, detect the flash target again, confirm the board family, and re-open the matched INI before retrying the controller serial port.")
        self.flash_guidance_label.setText("\n".join(lines))

    def _refresh_flash_bundle_summary(self) -> None:
        entry = self._selected_flash_firmware_entry()
        if entry is None:
            self.flash_bundle_label.setText(
                "Bundle: no release metadata for the selected firmware. Pairing falls back to filename and signature heuristics."
            )
            self.flash_load_definition_button.setEnabled(False)
            self.flash_load_tune_button.setEnabled(False)
            return

        definition_available = entry.definition_path is not None and entry.definition_path.is_file()
        tune_available = entry.tune_path is not None and entry.tune_path.is_file()
        artifact_label = "experimental" if entry.is_experimental else "production"
        if getattr(entry, "artifact_kind", None) is not None and entry.artifact_kind.value != "standard":
            artifact_label = f"{artifact_label}, {entry.artifact_kind.value}"

        lines = [
            f"Bundle: {entry.version_label or entry.path.name} [{artifact_label}]",
            f"Firmware: {entry.path.name}",
            f"Paired INI: {entry.definition_path.name if definition_available and entry.definition_path else 'not provided'}",
            f"Paired Tune: {entry.tune_path.name if tune_available and entry.tune_path else 'not provided'}",
        ]
        if entry.preferred:
            lines.append("Release note: this artifact is marked preferred for its bundle.")
        if entry.is_experimental:
            lines.append("Bench sequence: flash, power-cycle, reconnect, verify signature/pages, then review or burn the paired base tune.")
        else:
            lines.append("Bench sequence: flash, reconnect, verify signature/pages, then confirm the paired base tune before burning changes.")
        self.flash_bundle_label.setText("\n".join(lines))
        self.flash_load_definition_button.setEnabled(definition_available)
        self.flash_load_tune_button.setEnabled(tune_available)

    def _selected_flash_firmware_entry(self) -> FirmwareCatalogEntry | None:
        firmware_text = self.flash_firmware_edit.text().strip()
        if not firmware_text:
            return None
        firmware_path = Path(firmware_text).expanduser().resolve()
        if not firmware_path.is_file():
            return None
        try:
            return self.firmware_catalog_service.entry_for_firmware(firmware_path)
        except Exception:
            return None

    @staticmethod
    def _flash_target_guidance_text(
        selected_board: BoardFamily,
        target,
    ) -> str:
        if selected_board == BoardFamily.TEENSY41:
            if target is not None and target.source == "usb":
                return "Target: bootloader USB target is present. Flash first, then reconnect to the normal controller serial port after the board re-enumerates."
            if target is not None and target.serial_port:
                return f"Target: controller serial port {target.serial_port} is visible. Teensy flashing may still require the board to enter bootloader mode during the flash step."
            return "Target: no Teensy flash target detected yet. Put the board on bench power and use Detect Target before flashing."
        if selected_board == BoardFamily.STM32F407_DFU:
            if target is not None and target.source == "usb":
                return "Target: STM32 DFU device detected. Flash in DFU mode, then power-cycle back into normal serial mode before reconnecting."
            return "Target: place the STM32 board into DFU mode before flashing, then return it to normal serial mode for tuning."
        if selected_board == BoardFamily.ATMEGA2560:
            if target is not None and target.serial_port:
                return f"Target: flash over serial on {target.serial_port}. Keep the correct COM port selected and avoid burning tune changes until the reconnect signature is verified."
            return "Target: select the Arduino Mega serial port before flashing and verify the reconnect signature afterward."
        return "Target: verify the flash target and reconnect path before proceeding."

    def _load_paired_flash_definition(self) -> None:
        entry = self._selected_flash_firmware_entry()
        if entry is None or entry.definition_path is None or not entry.definition_path.is_file():
            QMessageBox.information(self, "Paired INI", "No paired ECU definition is available for this firmware.")
            return
        self._load_definition_path(entry.definition_path)

    def _load_paired_flash_tune(self) -> None:
        entry = self._selected_flash_firmware_entry()
        if entry is None or entry.tune_path is None or not entry.tune_path.is_file():
            QMessageBox.information(self, "Paired Tune", "No paired base tune is available for this firmware.")
            return
        self._load_tune_path(entry.tune_path)

    def _load_definition_path(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        active = self.project.active_settings if self.project is not None else frozenset()
        self.definition = self.definition_service.open_definition(resolved, active_settings=active)
        self.session_service.set_definition(self.definition)
        self.statusBar().showMessage(f"Loaded ECU definition: {self.definition.name}")
        self.detect_board()
        self.detect_flash_target()
        self.suggest_firmware()
        self._refresh_flash_preflight()
        self._refresh_flash_bundle_summary()
        self._reload_tuning_workspace()
        if self._last_trigger_log_path is not None:
            self._analyze_trigger_log()
        self._refresh_summary()

    def _load_tune_path(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        self.tune_file = self.tune_file_service.open_tune(resolved)
        self.tune_file_path = resolved
        self.local_tune_edit_service.set_tune_file(self.tune_file)
        self.statusBar().showMessage(f"Loaded tune file: {resolved.name}")
        self.detect_board()
        self.detect_flash_target()
        self.suggest_firmware()
        self._refresh_flash_preflight()
        self._refresh_flash_bundle_summary()
        self._reload_tuning_workspace()
        if self._last_trigger_log_path is not None:
            self._analyze_trigger_log()
        self._refresh_summary()

    def _append_flash_status(self, message: str) -> None:
        if message:
            self.flash_log.append(message)
            self.statusBar().showMessage(message)

    def _flash_finished(self, exit_code: int, output: str) -> None:
        self.flash_button.setEnabled(True)
        self.flash_worker = None
        self.flash_log.append("")
        self.flash_log.append(output.strip() or "No process output.")
        if exit_code == 0:
            self.flash_progress.setValue(100)
            self.statusBar().showMessage("Firmware flash completed")
        else:
            QMessageBox.critical(self, "Firmware Flash Failed", f"Flash process exited with code {exit_code}.")
            self.statusBar().showMessage("Firmware flash failed")

    def _flash_failed(self, message: str) -> None:
        self.flash_button.setEnabled(True)
        self.flash_worker = None
        self.flash_log.append(message)
        QMessageBox.critical(self, "Firmware Flash Failed", message)
        self.statusBar().showMessage("Firmware flash failed")

    @staticmethod
    def _default_tool_root() -> Path:
        bundled = bundled_tools_root()
        if bundled.exists():
            return bundled
        candidate = Path(r"C:\Users\Cornelio\Desktop\SpeedyLoader-1.7.0")
        if candidate.exists():
            return candidate
        return Path.cwd()

    @staticmethod
    def _default_release_root() -> Path:
        candidate = Path(r"C:\Users\Cornelio\Desktop\speeduino-202501.6\release")
        if candidate.exists():
            return candidate
        return Path.cwd()


def launch_app() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
