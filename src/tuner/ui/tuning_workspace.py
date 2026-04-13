from __future__ import annotations

from dataclasses import dataclass
from functools import partial
import os
from pathlib import Path
import time


# Phase 5 polish — table cell density bounds. Floor keeps small cells
# legible (44 px ≈ 3 digits + padding); ceiling avoids cells looking
# stranded on ultra-wide displays. The previous 56 px ceiling was set
# for 1080p and started wasting space on 1440p+ panels with smaller
# (≤12-column) tables.
_TABLE_CELL_MIN_WIDTH = 44
_TABLE_CELL_MAX_WIDTH = 80


def compute_table_cell_width(viewport_width: int, columns: int) -> int:
    """Pure helper for table cell width fit logic.

    Distributes the available viewport across the column count, then
    clamps to ``[_TABLE_CELL_MIN_WIDTH, _TABLE_CELL_MAX_WIDTH]``. Pulled
    out of ``TuningWorkspace._fit_table_column_widths`` so it can be
    unit-tested without instantiating Qt widgets.
    """
    if columns <= 0:
        return _TABLE_CELL_MIN_WIDTH
    raw = round(viewport_width / columns) - 4
    return max(_TABLE_CELL_MIN_WIDTH, min(_TABLE_CELL_MAX_WIDTH, raw))

from PySide6.QtCore import QAbstractTableModel, QItemSelection, QItemSelectionModel, QSignalBlocker, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPalette, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.session import SessionState
from tuner.domain.tune import TuneFile
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.evidence_replay_comparison_service import EvidenceReplayComparisonService
from tuner.services.parameter_catalog_service import ParameterCatalogService
from tuner.services.page_evidence_review_service import PageEvidenceReviewService
from tuner.services.table_replay_context_service import TableReplayContextService
from tuner.services.table_replay_hit_service import TableReplayHitService
from tuner.services.table_edit_service import TableSelection
from tuner.services.table_rendering_service import TableCellRender, TableRenderModel, TableRenderingService
from tuner.services.table_view_service import TableViewService
from tuner.services.tuning_page_service import TuningPageService
from tuner.domain.operator_engine_context import CalibrationIntent
from tuner.services.tuning_workspace_presenter import (
    CatalogSnapshot,
    CurvePageSnapshot,
    HardwareSetupCardSnapshot,
    OperationLogSnapshot,
    ParameterPageSnapshot,
    RequiredFuelCalculatorSnapshot,
    TablePageSnapshot,
    TuningWorkspacePresenter,
    TuningWorkspaceSnapshot,
    VeAnalyzeSnapshot,
    WueAnalyzeSnapshot,
    WorkspaceReviewSnapshot,
)


def emit_table_debug_log(message: str) -> None:
    print(message)
    log_path = Path(os.environ.get("TUNER_TABLE_DEBUG_LOG", "tuner_table_debug.log"))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


class TableGridModel(QAbstractTableModel):
    cell_edited = Signal(int, int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._x_labels: tuple[str, ...] = ()
        self._y_labels: tuple[str, ...] = ()
        self._cells: list[list[TableCellRender]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._cells)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid() or not self._cells:
            return 0
        return len(self._cells[0])

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        cell = self._cells[index.row()][index.column()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return cell.text
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.BackgroundRole:
            return QColor(cell.background_hex)
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(cell.foreground_hex)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        labels = self._x_labels if orientation == Qt.Orientation.Horizontal else self._y_labels
        if 0 <= section < len(labels):
            return labels[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        text = "" if value is None else str(value)
        current = self._cells[index.row()][index.column()]
        self._cells[index.row()][index.column()] = TableCellRender(
            text=text,
            background_hex=current.background_hex,
            foreground_hex=current.foreground_hex,
        )
        self.dataChanged.emit(
            index,
            index,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.EditRole,
                Qt.ItemDataRole.BackgroundRole,
                Qt.ItemDataRole.ForegroundRole,
            ],
        )
        self.cell_edited.emit(index.row(), index.column(), text)
        return True

    def set_render_model(self, render_model: TableRenderModel | None) -> None:
        self.beginResetModel()
        if render_model is None:
            self._x_labels = ()
            self._y_labels = ()
            self._cells = []
        else:
            self._x_labels = tuple(render_model.x_labels)
            self._y_labels = tuple(render_model.y_labels)
            self._cells = [list(row) for row in render_model.cells]
        self.endResetModel()

    def update_cell(self, display_row: int, column: int, cell: TableCellRender) -> None:
        if not (0 <= display_row < len(self._cells)):
            return
        if not (0 <= column < len(self._cells[display_row])):
            return
        self._cells[display_row][column] = cell
        index = self.index(display_row, column)
        self.dataChanged.emit(
            index,
            index,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.EditRole,
                Qt.ItemDataRole.BackgroundRole,
                Qt.ItemDataRole.ForegroundRole,
            ],
        )


class MapTableView(QTableView):
    empty_area_clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.indexAt(event.position().toPoint()).isValid():
            selection_model = self.selectionModel()
            if selection_model is not None:
                selection_model.clearSelection()
                selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
            self.empty_area_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2):
            if self.state() != QAbstractItemView.State.EditingState:
                current = self.currentIndex()
                if current.isValid():
                    self.edit(current)
                    event.accept()
                    return
        super().keyPressEvent(event)


@dataclass(slots=True, frozen=True)
class WorkspaceUiState:
    active_page_id: str | None
    main_splitter_sizes: tuple[int, ...]
    workspace_splitter_sizes: tuple[int, ...]
    details_tab_index: int
    catalog_query: str
    catalog_kind: str


@dataclass(slots=True, frozen=True)
class WorkspacePageEntry:
    page_id: str
    title: str
    group_title: str
    kind: str
    state_label: str
    summary: str


@dataclass(slots=True, frozen=True)
class WorkspaceActionEntry:
    action_id: str
    title: str
    summary: str


class TuningWorkspacePanel(QWidget):
    workspace_changed = Signal()
    status_message = Signal(str)
    ui_state_changed = Signal()
    power_cycle_requested = Signal()

    def __init__(
        self,
        local_tune_edit_service: LocalTuneEditService,
        tuning_page_service: TuningPageService | None = None,
        parameter_catalog_service: ParameterCatalogService | None = None,
        table_view_service: TableViewService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.presenter = TuningWorkspacePresenter(
            local_tune_edit_service=local_tune_edit_service,
            tuning_page_service=tuning_page_service,
            parameter_catalog_service=parameter_catalog_service,
            table_view_service=table_view_service,
        )
        self.table_rendering_service = TableRenderingService()
        self._display_to_model_row: list[int] = []
        self._active_display_cell: tuple[int, int] | None = None
        self._command_table_selection: TableSelection | None = None
        self._highlighted_x_axis_columns: set[int] = set()
        self._highlighted_y_axis_rows: set[int] = set()
        self._table_highlight_refresh_pending = False
        self._ui_state_emit_pending = False
        self._last_active_page_kind = "empty"
        self._last_parameter_page_id: str | None = None
        self._last_parameter_section_key: frozenset | None = None
        self._last_workspace_snapshot: TuningWorkspaceSnapshot | None = None
        self._review_evidence_replay_snapshot = None
        self._latest_evidence_replay_snapshot = None
        self._replay_datalog_log = None
        self._last_table_evidence_text = ""
        self._last_table_evidence_visible = False
        self._last_parameter_evidence_text = ""
        self._last_parameter_evidence_visible = False
        self._updating_widgets = False
        self._table_debug_enabled = os.environ.get("TUNER_TABLE_DEBUG", "").lower() in {"1", "true", "yes", "on"}
        self._table_shortcuts: list[QShortcut] = []
        self._page_evidence_review_service = PageEvidenceReviewService()
        self._evidence_replay_comparison_service = EvidenceReplayComparisonService()
        self._table_replay_context_service = TableReplayContextService()
        self._table_replay_hit_service = TableReplayHitService()
        self._build_ui()
        self._apply_theme()
        self._render(self.presenter.snapshot())

    def set_context(self, definition: EcuDefinition | None, tune_file: TuneFile | None) -> None:
        snapshot = self.presenter.load(definition, tune_file)
        self._render_and_emit(snapshot, notify_workspace=True)

    def set_session_client(self, client, state: SessionState) -> None:
        snapshot = self.presenter.set_client(client, state)
        self._render_and_emit(snapshot)

    def go_offline(self) -> None:
        snapshot = self.presenter.go_offline()
        self._render_and_emit(snapshot)

    def refresh_from_presenter(self, *, notify_workspace: bool = False) -> None:
        """Re-render from the current presenter state without changing selection."""
        self._render_and_emit(self.presenter.snapshot(), notify_workspace=notify_workspace)

    def set_evidence_replay_snapshot(self, snapshot) -> None:
        self.set_evidence_review_snapshots(snapshot, latest_snapshot=snapshot)

    @staticmethod
    def _evidence_snapshot_signature(snapshot) -> tuple | None:
        if snapshot is None:
            return None
        return (
            snapshot.session_state,
            snapshot.connection_text,
            snapshot.source_text,
            snapshot.sync_summary_text,
            snapshot.sync_mismatch_details,
            snapshot.staged_summary_text,
            snapshot.operation_summary_text,
            snapshot.operation_session_count,
            snapshot.latest_write_text,
            snapshot.latest_burn_text,
            snapshot.runtime_channel_count,
            tuple((item.name, item.value, item.units) for item in snapshot.runtime_channels),
        )

    def set_evidence_review_snapshots(self, review_snapshot, *, latest_snapshot=None) -> None:
        resolved_latest_snapshot = latest_snapshot if latest_snapshot is not None else review_snapshot
        same_review = (
            self._evidence_snapshot_signature(self._review_evidence_replay_snapshot)
            == self._evidence_snapshot_signature(review_snapshot)
        )
        same_latest = (
            self._evidence_snapshot_signature(self._latest_evidence_replay_snapshot)
            == self._evidence_snapshot_signature(resolved_latest_snapshot)
        )
        self._review_evidence_replay_snapshot = review_snapshot
        self._latest_evidence_replay_snapshot = resolved_latest_snapshot
        if same_review and same_latest:
            return
        if self._last_workspace_snapshot is not None:
            self._refresh_active_page_evidence(self._last_workspace_snapshot)

    def set_replay_datalog_log(self, log) -> None:
        if self._replay_datalog_log is log:
            return
        self._replay_datalog_log = log
        if self._last_workspace_snapshot is not None:
            self._refresh_active_page_evidence(self._last_workspace_snapshot)

    def sync_from_ecu(self) -> None:
        snapshot = self.presenter.read_from_ecu()
        self._render_and_emit(snapshot, notify_workspace=True)

    def capture_ui_state(self) -> WorkspaceUiState:
        return WorkspaceUiState(
            active_page_id=self.presenter.active_page_id,
            main_splitter_sizes=tuple(self.main_splitter.sizes()),
            workspace_splitter_sizes=tuple(self.workspace_splitter.sizes()),
            details_tab_index=self.workspace_details_tabs.currentIndex(),
            catalog_query=self.catalog_search_edit.text(),
            catalog_kind=self.catalog_kind_combo.currentText(),
        )

    def restore_ui_state(self, state: WorkspaceUiState | None) -> None:
        if state is None:
            return
        snapshot = self.presenter.snapshot()
        if state.catalog_kind and state.catalog_kind != self.catalog_kind_combo.currentText():
            index = self.catalog_kind_combo.findText(state.catalog_kind)
            if index >= 0:
                blocker = QSignalBlocker(self.catalog_kind_combo)
                self.catalog_kind_combo.setCurrentIndex(index)
                del blocker
                snapshot = self.presenter.set_catalog_kind(state.catalog_kind)
        if state.catalog_query != self.catalog_search_edit.text():
            blocker = QSignalBlocker(self.catalog_search_edit)
            self.catalog_search_edit.setText(state.catalog_query)
            del blocker
            snapshot = self.presenter.set_catalog_query(state.catalog_query)
        if state.active_page_id and state.active_page_id in self.presenter.pages_by_id:
            snapshot = self.presenter.select_page(state.active_page_id)
        self._render(snapshot)
        if state.main_splitter_sizes:
            self.main_splitter.setSizes(list(state.main_splitter_sizes))
        if state.workspace_splitter_sizes:
            self.workspace_splitter.setSizes(list(state.workspace_splitter_sizes))
        if 0 <= state.details_tab_index < self.workspace_details_tabs.count():
            self.workspace_details_tabs.setCurrentIndex(state.details_tab_index)

    def quick_open_entries(self) -> tuple[WorkspacePageEntry, ...]:
        entries: list[WorkspacePageEntry] = []
        for group in self.presenter.page_groups:
            for page in group.pages:
                state = self.presenter._page_state(page)
                entries.append(
                    WorkspacePageEntry(
                        page_id=page.page_id,
                        title=page.title,
                        group_title=group.title,
                        kind=page.kind.value,
                        state_label=state.label,
                        summary=page.summary,
                    )
                )
        return tuple(entries)

    def open_page(self, page_id: str | None) -> None:
        if not page_id:
            return
        target_page_id, parameter_name = page_id.split("#", 1) if "#" in page_id else (page_id, None)
        snapshot = self.presenter.select_page(target_page_id)
        if parameter_name:
            snapshot = self.presenter.select_active_page_parameter(parameter_name)
        self._render_and_emit(snapshot, notify_workspace=True)
        self._schedule_ui_state_changed()

    def command_actions(self) -> tuple[WorkspaceActionEntry, ...]:
        return (
            WorkspaceActionEntry("workspace.write_page", "Write Active Page", "Write staged changes on the active page to RAM."),
            WorkspaceActionEntry("workspace.burn_page", "Burn Active Page", "Burn already written changes on the active page to flash."),
            WorkspaceActionEntry("workspace.power_cycle", "Power Cycle Controller", "Reconnect the controller session so restart-required settings can take effect."),
            WorkspaceActionEntry("workspace.revert_page", "Revert Active Page", "Discard staged changes on the active page."),
            WorkspaceActionEntry("workspace.undo", "Undo Active Table/Page", "Undo the latest active-page edit."),
            WorkspaceActionEntry("workspace.redo", "Redo Active Table/Page", "Redo the latest active-page edit."),
        )

    def execute_action(self, action_id: str) -> None:
        if action_id == "workspace.write_page":
            self._on_write_page_clicked()
        elif action_id == "workspace.burn_page":
            self._on_burn_page_clicked()
        elif action_id == "workspace.power_cycle":
            self._on_power_cycle_clicked()
        elif action_id == "workspace.revert_page":
            self._on_revert_page_clicked()
        elif action_id == "workspace.undo":
            if self.editor_stack.currentWidget() == self.table_page_widget:
                self._on_undo_table_clicked()
            else:
                self._on_undo_parameter_clicked()
        elif action_id == "workspace.redo":
            if self.editor_stack.currentWidget() == self.table_page_widget:
                self._on_redo_table_clicked()
            else:
                self._on_redo_parameter_clicked()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.workspace_overview = QFrame()
        overview_layout = QHBoxLayout(self.workspace_overview)
        overview_layout.setContentsMargins(8, 4, 8, 4)
        overview_layout.setSpacing(6)
        self.connection_chip = QLabel()
        self.mismatch_chip = QLabel()
        self.staged_chip = QLabel()
        self.hardware_chip = QLabel()
        for chip in (self.connection_chip, self.mismatch_chip, self.staged_chip, self.hardware_chip):
            chip.setProperty("chip", True)
            overview_layout.addWidget(chip)
        overview_layout.addStretch(1)
        layout.addWidget(self.workspace_overview)

        self.workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        self.workspace_splitter.setChildrenCollapsible(False)
        layout.addWidget(self.workspace_splitter, 1)

        self.main_splitter = QSplitter()
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.splitterMoved.connect(lambda _pos, _index: (self._fit_active_editor(), self._schedule_ui_state_changed()))
        self.workspace_splitter.addWidget(self.main_splitter)

        self.navigator_panel = QFrame()
        self.navigator_panel.setProperty("navigatorPanel", True)
        navigator_layout = QVBoxLayout(self.navigator_panel)
        navigator_layout.setContentsMargins(8, 8, 8, 8)
        navigator_layout.setSpacing(6)
        self.navigator_caption = QLabel("Tuning pages")
        self.navigator_caption.setProperty("navigatorCaption", True)
        navigator_layout.addWidget(self.navigator_caption)

        self.navigator_tree = QTreeWidget()
        self.navigator_tree.setProperty("navigatorTree", True)
        self.navigator_tree.setColumnCount(2)
        self.navigator_tree.setHeaderLabels(["Tuning Page", "State"])
        self.navigator_tree.setMinimumWidth(240)
        self.navigator_tree.setUniformRowHeights(True)
        self.navigator_tree.setAlternatingRowColors(True)
        self.navigator_tree.setIndentation(14)
        self.navigator_tree.setRootIsDecorated(True)
        self.navigator_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.navigator_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.navigator_tree.setColumnWidth(0, 170)
        self.navigator_tree.setColumnWidth(1, 58)
        self.navigator_tree.itemSelectionChanged.connect(self._on_navigator_selection_changed)
        navigator_layout.addWidget(self.navigator_tree, 1)
        self.main_splitter.addWidget(self.navigator_panel)

        self.editor_stack = QStackedWidget()
        self.main_splitter.addWidget(self.editor_stack)

        self.empty_page = QLabel("Load an ECU definition to build tuning pages.")
        self.empty_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_page.setProperty("emptyState", True)
        self.editor_stack.addWidget(self.empty_page)

        self.table_page_widget = self._build_table_page_widget()
        self.editor_stack.addWidget(self.table_page_widget)

        self.parameter_page_widget = self._build_parameter_page_widget()
        self.editor_stack.addWidget(self.parameter_page_widget)

        self.curve_page_widget = self._build_curve_page_widget()
        self.editor_stack.addWidget(self.curve_page_widget)

        self.catalog_panel = self._build_catalog_panel()
        self.catalog_panel.setMinimumWidth(260)
        self.main_splitter.addWidget(self.catalog_panel)
        self._rebalance_splitter("empty")

        self.workspace_details_panel = QFrame()
        self.workspace_details_panel.setProperty("workspaceDetailsPanel", True)
        details_panel_layout = QVBoxLayout(self.workspace_details_panel)
        details_panel_layout.setContentsMargins(8, 6, 8, 8)
        details_panel_layout.setSpacing(6)
        self.workspace_details_caption = QLabel("Workspace context")
        self.workspace_details_caption.setProperty("workspaceDetailsCaption", True)
        details_panel_layout.addWidget(self.workspace_details_caption)

        self.workspace_details_tabs = QTabWidget()
        self.workspace_details_tabs.setDocumentMode(True)
        self.workspace_details_tabs.currentChanged.connect(lambda _index: self._schedule_ui_state_changed())

        self.operation_log_group = QWidget()
        log_layout = QVBoxLayout(self.operation_log_group)
        log_layout.setContentsMargins(6, 6, 6, 6)
        self.operation_log_text = QTextEdit()
        self.operation_log_text.setReadOnly(True)
        self.operation_log_text.setPlaceholderText("No operations recorded this session.")
        log_layout.addWidget(self.operation_log_text)
        self.workspace_details_tabs.addTab(self.operation_log_group, "Operations")

        self.sync_state_group = QWidget()
        sync_layout = QVBoxLayout(self.sync_state_group)
        sync_layout.setContentsMargins(6, 6, 6, 6)
        self.sync_state_text = QTextEdit()
        self.sync_state_text.setReadOnly(True)
        sync_layout.addWidget(self.sync_state_text)
        self.workspace_details_tabs.addTab(self.sync_state_group, "Sync State")

        self.workspace_review_group = QWidget()
        review_layout = QVBoxLayout(self.workspace_review_group)
        review_layout.setContentsMargins(6, 6, 6, 6)
        self.workspace_review_table = QTableWidget(0, 4)
        self.workspace_review_table.setHorizontalHeaderLabels(["Page", "Parameter", "Before", "After"])
        self.workspace_review_table.horizontalHeader().setStretchLastSection(True)
        self.workspace_review_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.workspace_review_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.workspace_review_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.workspace_review_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.workspace_review_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        review_layout.addWidget(self.workspace_review_table)
        self.workspace_review_summary = QLabel("No staged changes across the workspace.")
        self.workspace_review_summary.setWordWrap(True)
        review_layout.addWidget(self.workspace_review_summary)
        self.workspace_details_tabs.addTab(self.workspace_review_group, "Workspace Review")

        # VE Analyze tab
        self.ve_analyze_group = QWidget()
        ve_analyze_layout = QVBoxLayout(self.ve_analyze_group)
        ve_analyze_layout.setContentsMargins(6, 6, 6, 6)
        ve_analyze_layout.setSpacing(4)
        self.ve_analyze_status_label = QLabel("Select a table page and click VE Analyze to start.")
        self.ve_analyze_status_label.setWordWrap(True)
        ve_analyze_layout.addWidget(self.ve_analyze_status_label)
        self.ve_analyze_detail_text = QTextEdit()
        self.ve_analyze_detail_text.setReadOnly(True)
        self.ve_analyze_detail_text.setPlaceholderText("No VE Analyze data yet.")
        ve_analyze_layout.addWidget(self.ve_analyze_detail_text, 1)
        self.workspace_details_tabs.addTab(self.ve_analyze_group, "VE Analyze")

        # WUE Analyze tab
        self.wue_analyze_group = QWidget()
        wue_analyze_layout = QVBoxLayout(self.wue_analyze_group)
        wue_analyze_layout.setContentsMargins(6, 6, 6, 6)
        wue_analyze_layout.setSpacing(4)
        self.wue_analyze_status_label = QLabel("Select a warmup table page and click WUE Analyze to start.")
        self.wue_analyze_status_label.setWordWrap(True)
        wue_analyze_layout.addWidget(self.wue_analyze_status_label)
        self.wue_analyze_detail_text = QTextEdit()
        self.wue_analyze_detail_text.setReadOnly(True)
        self.wue_analyze_detail_text.setPlaceholderText("No WUE Analyze data yet.")
        wue_analyze_layout.addWidget(self.wue_analyze_detail_text, 1)
        self.workspace_details_tabs.addTab(self.wue_analyze_group, "WUE Analyze")

        details_panel_layout.addWidget(self.workspace_details_tabs, 1)
        self.workspace_splitter.addWidget(self.workspace_details_panel)
        self.workspace_splitter.setSizes([930, 110])

    def _build_table_page_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.table_header_panel = QFrame()
        self.table_header_panel.setProperty("tableShell", "header")
        header_layout = QVBoxLayout(self.table_header_panel)
        header_layout.setContentsMargins(8, 6, 8, 4)
        header_layout.setSpacing(3)

        self.table_page_header_label = QLabel("Select a tuning page.")
        self.table_page_header_label.setProperty("tablePageTitle", True)
        header_layout.addWidget(self.table_page_header_label)
        self.table_related_pages_label = QLabel("")
        self.table_related_pages_label.setProperty("navigatorCaption", True)
        self.table_related_pages_label.hide()
        header_layout.addWidget(self.table_related_pages_label)
        self.table_related_pages_tabs = QTabBar()
        self.table_related_pages_tabs.setDocumentMode(True)
        self.table_related_pages_tabs.setDrawBase(False)
        self.table_related_pages_tabs.setExpanding(False)
        self.table_related_pages_tabs.currentChanged.connect(self._on_table_related_page_changed)
        self.table_related_pages_tabs.hide()
        header_layout.addWidget(self.table_related_pages_tabs)

        self.table_toolbar = QFrame()
        self.table_toolbar.setProperty("tableToolbar", True)
        table_toolbar_layout = QVBoxLayout(self.table_toolbar)
        table_toolbar_layout.setContentsMargins(6, 5, 6, 5)
        table_toolbar_layout.setSpacing(5)

        self.table_meta_summary_panel = QWidget()
        table_meta_layout = QGridLayout(self.table_meta_summary_panel)
        table_meta_layout.setContentsMargins(0, 0, 0, 0)
        table_meta_layout.setHorizontalSpacing(8)
        table_meta_layout.setVerticalSpacing(3)

        self.table_page_summary_label = QLabel("")
        self.table_page_summary_label.setProperty("tableMeta", "summary")
        self.table_page_summary_label.setWordWrap(True)
        table_meta_layout.addWidget(self.table_page_summary_label, 0, 0)

        self.table_validation_summary_label = QLabel("")
        self.table_validation_summary_label.setProperty("tableMeta", "validation")
        self.table_validation_summary_label.setWordWrap(True)
        table_meta_layout.addWidget(self.table_validation_summary_label, 0, 1)

        self.table_diff_summary_label = QLabel("")
        self.table_diff_summary_label.setProperty("tableMeta", "diff")
        self.table_diff_summary_label.setWordWrap(True)
        table_meta_layout.addWidget(self.table_diff_summary_label, 1, 0)

        self.table_axis_summary_label = QLabel("")
        self.table_axis_summary_label.setProperty("tableMeta", "axis")
        self.table_axis_summary_label.setWordWrap(True)
        table_meta_layout.addWidget(self.table_axis_summary_label, 1, 1)
        table_meta_layout.setColumnStretch(0, 2)
        table_meta_layout.setColumnStretch(1, 1)

        self.table_help_label = QLabel("")
        self.table_help_label.setWordWrap(True)
        self.table_help_label.setStyleSheet("color: #94a3b8; font-style: italic; padding: 0 2px;")
        self.table_help_label.hide()

        self.table_power_cycle_warning = QLabel(
            "\u26a0 One or more parameters on this page require a power cycle after changing."
        )
        self.table_power_cycle_warning.setWordWrap(False)
        self.table_power_cycle_warning.setStyleSheet(
            "background: #5b4615; color: #f6e7b0; padding: 2px 6px; border-radius: 3px; border: 1px solid #8f6a17;"
        )
        self.table_power_cycle_warning.hide()

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(4)
        self.table_page_state_label = QLabel("Page State: clean")
        self.table_page_state_label.setProperty("tableState", True)
        action_row.addWidget(self.table_page_state_label)
        self.table_cell_status_label = QLabel("RPM: n/a | Load: n/a | Selected: n/a")
        self.table_cell_status_label.setProperty("tableStatus", True)
        action_row.addWidget(self.table_cell_status_label)
        action_row.addStretch(1)
        self.table_copy_button = QPushButton("Copy")
        self.table_copy_button.setProperty("tableActionRole", "secondary")
        self.table_copy_button.clicked.connect(self._on_copy_table_clicked)
        action_row.addWidget(self.table_copy_button)
        self.table_paste_button = QPushButton("Paste")
        self.table_paste_button.setProperty("tableActionRole", "secondary")
        self.table_paste_button.clicked.connect(self._on_paste_table_clicked)
        action_row.addWidget(self.table_paste_button)
        self.table_fill_button = QPushButton("Fill")
        self.table_fill_button.setProperty("tableActionRole", "secondary")
        self.table_fill_button.clicked.connect(self._on_fill_table_clicked)
        action_row.addWidget(self.table_fill_button)
        self.table_interpolate_button = QPushButton("Interp")
        self.table_interpolate_button.setToolTip("Interpolate the current selection.")
        self.table_interpolate_button.setProperty("tableActionRole", "secondary")
        self.table_interpolate_button.clicked.connect(self._on_interpolate_table_clicked)
        action_row.addWidget(self.table_interpolate_button)
        self.table_smooth_button = QPushButton("Smooth")
        self.table_smooth_button.setProperty("tableActionRole", "secondary")
        self.table_smooth_button.clicked.connect(self._on_smooth_table_clicked)
        action_row.addWidget(self.table_smooth_button)
        self.table_undo_button = QPushButton("Undo")
        self.table_undo_button.setProperty("tableActionRole", "secondary")
        self.table_undo_button.clicked.connect(self._on_undo_table_clicked)
        action_row.addWidget(self.table_undo_button)
        self.table_redo_button = QPushButton("Redo")
        self.table_redo_button.setProperty("tableActionRole", "secondary")
        self.table_redo_button.clicked.connect(self._on_redo_table_clicked)
        action_row.addWidget(self.table_redo_button)
        self.table_revert_button = QPushButton("Revert")
        self.table_revert_button.setToolTip("Discard staged changes on the active page.")
        self.table_revert_button.setProperty("tableActionRole", "secondary")
        self.table_revert_button.clicked.connect(self._on_revert_page_clicked)
        action_row.addWidget(self.table_revert_button)
        self.table_ve_analyze_start_button = QPushButton("VE Analyze")
        self.table_ve_analyze_start_button.setToolTip("Start live VE Analyze session on this table.")
        self.table_ve_analyze_start_button.setProperty("tableActionRole", "secondary")
        self.table_ve_analyze_start_button.clicked.connect(self._on_ve_analyze_start_clicked)
        action_row.addWidget(self.table_ve_analyze_start_button)
        self.table_ve_analyze_stop_button = QPushButton("Stop VE")
        self.table_ve_analyze_stop_button.setToolTip("Stop feeding samples; keep data for review.")
        self.table_ve_analyze_stop_button.setProperty("tableActionRole", "secondary")
        self.table_ve_analyze_stop_button.clicked.connect(self._on_ve_analyze_stop_clicked)
        self.table_ve_analyze_stop_button.hide()
        action_row.addWidget(self.table_ve_analyze_stop_button)
        self.table_ve_analyze_apply_button = QPushButton("Apply VE")
        self.table_ve_analyze_apply_button.setToolTip("Stage all VE Analyze proposals as edits.")
        self.table_ve_analyze_apply_button.setProperty("tableActionRole", "primary")
        self.table_ve_analyze_apply_button.clicked.connect(self._on_ve_analyze_apply_clicked)
        self.table_ve_analyze_apply_button.hide()
        action_row.addWidget(self.table_ve_analyze_apply_button)
        self.table_ve_analyze_reset_button = QPushButton("Reset VE")
        self.table_ve_analyze_reset_button.setToolTip("Clear all accumulated VE Analyze data.")
        self.table_ve_analyze_reset_button.setProperty("tableActionRole", "secondary")
        self.table_ve_analyze_reset_button.clicked.connect(self._on_ve_analyze_reset_clicked)
        self.table_ve_analyze_reset_button.hide()
        action_row.addWidget(self.table_ve_analyze_reset_button)
        self.table_wue_analyze_start_button = QPushButton("WUE Analyze")
        self.table_wue_analyze_start_button.setToolTip("Start live WUE Analyze session on this warmup table.")
        self.table_wue_analyze_start_button.setProperty("tableActionRole", "secondary")
        self.table_wue_analyze_start_button.clicked.connect(self._on_wue_analyze_start_clicked)
        action_row.addWidget(self.table_wue_analyze_start_button)
        self.table_wue_analyze_stop_button = QPushButton("Stop WUE")
        self.table_wue_analyze_stop_button.setToolTip("Stop feeding samples; keep data for review.")
        self.table_wue_analyze_stop_button.setProperty("tableActionRole", "secondary")
        self.table_wue_analyze_stop_button.clicked.connect(self._on_wue_analyze_stop_clicked)
        self.table_wue_analyze_stop_button.hide()
        action_row.addWidget(self.table_wue_analyze_stop_button)
        self.table_wue_analyze_apply_button = QPushButton("Apply WUE")
        self.table_wue_analyze_apply_button.setToolTip("Stage all WUE Analyze proposals as edits.")
        self.table_wue_analyze_apply_button.setProperty("tableActionRole", "primary")
        self.table_wue_analyze_apply_button.clicked.connect(self._on_wue_analyze_apply_clicked)
        self.table_wue_analyze_apply_button.hide()
        action_row.addWidget(self.table_wue_analyze_apply_button)
        self.table_wue_analyze_reset_button = QPushButton("Reset WUE")
        self.table_wue_analyze_reset_button.setToolTip("Clear all accumulated WUE Analyze data.")
        self.table_wue_analyze_reset_button.setProperty("tableActionRole", "secondary")
        self.table_wue_analyze_reset_button.clicked.connect(self._on_wue_analyze_reset_clicked)
        self.table_wue_analyze_reset_button.hide()
        action_row.addWidget(self.table_wue_analyze_reset_button)
        self.table_write_button = QPushButton("Write RAM")
        self.table_write_button.setProperty("tableActionRole", "primary")
        self.table_write_button.clicked.connect(self._on_write_page_clicked)
        action_row.addWidget(self.table_write_button)
        self.table_burn_button = QPushButton("Burn Flash")
        self.table_burn_button.setProperty("tableActionRole", "warning")
        self.table_burn_button.clicked.connect(self._on_burn_page_clicked)
        action_row.addWidget(self.table_burn_button)
        self.table_power_cycle_button = QPushButton("Power Cycle")
        self.table_power_cycle_button.setProperty("tableActionRole", "secondary")
        self.table_power_cycle_button.clicked.connect(self._on_power_cycle_clicked)
        self.table_power_cycle_button.hide()
        action_row.addWidget(self.table_power_cycle_button)
        table_toolbar_layout.addLayout(action_row)
        table_toolbar_layout.addWidget(self.table_meta_summary_panel)
        header_layout.addWidget(self.table_toolbar)
        header_layout.addWidget(self.table_help_label)
        header_layout.addWidget(self.table_power_cycle_warning)

        self.table_page_details = QTextEdit()
        self.table_page_details.setReadOnly(True)
        self.table_page_details.setMaximumHeight(64)
        self.table_page_details.hide()
        header_layout.addWidget(self.table_page_details)
        self.table_evidence_label = QLabel("")
        self.table_evidence_label.setWordWrap(True)
        self.table_evidence_label.setProperty("surfacePanelNote", True)
        self.table_evidence_label.hide()
        header_layout.addWidget(self.table_evidence_label)

        self.table_diff_group = QGroupBox("Staged Changes")
        table_diff_layout = QVBoxLayout(self.table_diff_group)
        table_diff_layout.setContentsMargins(4, 4, 4, 4)
        self.table_diff_table = QTableWidget(0, 3)
        self.table_diff_table.setHorizontalHeaderLabels(["Parameter", "Before", "After"])
        self.table_diff_table.horizontalHeader().setStretchLastSection(True)
        self.table_diff_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_diff_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_diff_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table_diff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_diff_table.setMaximumHeight(96)
        table_diff_layout.addWidget(self.table_diff_table)
        self.table_diff_group.hide()
        header_layout.addWidget(self.table_diff_group)
        layout.addWidget(self.table_header_panel, 0)

        self.table_grid_panel = QFrame()
        self.table_grid_panel.setProperty("tableShell", "grid")
        self.table_grid_panel.setProperty("tableAttachedFooter", False)
        grid_panel_layout = QVBoxLayout(self.table_grid_panel)
        grid_panel_layout.setContentsMargins(0, 0, 0, 0)
        grid_panel_layout.setSpacing(0)
        self.table_grid = QWidget()
        table_grid_layout = QGridLayout(self.table_grid)
        table_grid_layout.setContentsMargins(0, 0, 0, 0)
        table_grid_layout.setHorizontalSpacing(1)
        table_grid_layout.setVerticalSpacing(0)

        self.y_bins_table = QTableWidget(0, 1)
        self.y_bins_table.setHorizontalHeaderLabels(["Y Bins"])
        self.y_bins_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.y_bins_table.horizontalHeader().setStretchLastSection(True)
        self.y_bins_table.setFrameShape(QFrame.Shape.NoFrame)
        self.y_bins_table.setMinimumWidth(148)
        self.y_bins_table.setMaximumWidth(196)
        self.y_bins_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.y_bins_table.verticalHeader().setDefaultSectionSize(24)
        self.y_bins_table.verticalHeader().setMinimumSectionSize(24)
        self.y_bins_table.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.y_bins_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.SelectedClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.AnyKeyPressed
        )
        self.y_bins_table.itemChanged.connect(self._on_y_bin_item_changed)
        self.y_bins_table.cellClicked.connect(self._on_y_axis_cell_clicked)
        table_grid_layout.addWidget(self.y_bins_table, 0, 0)

        self.map_table_model = TableGridModel(self)
        self.map_table = MapTableView()
        self.map_table.setModel(self.map_table_model)
        self.map_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.map_table.horizontalHeader().sectionResized.connect(self._on_map_header_resized)
        self.map_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.map_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.map_table.setFrameShape(QFrame.Shape.NoFrame)
        self.map_table.setWordWrap(False)
        self.map_table.setShowGrid(True)
        self.map_table.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.map_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.map_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.map_table.verticalHeader().setDefaultSectionSize(24)
        self.map_table.verticalHeader().setMinimumSectionSize(24)
        self.map_table.horizontalHeader().setMinimumSectionSize(40)
        self.map_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        palette = self.map_table.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#2b2b2b"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e5e7eb"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#4b7bd1"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#f8fafc"))
        self.map_table.setPalette(palette)
        self.map_table.setStyleSheet(
            (
                "QTableView { selection-background-color: #4b7bd1; selection-color: #f8fafc; } "
                "QTableView::item:selected { background-color: #4b7bd1; color: #f8fafc; } "
                "QTableView::item:selected:active { background-color: #4b7bd1; color: #f8fafc; }"
            )
        )
        self.map_table_model.cell_edited.connect(self._on_map_cell_edited)
        self.map_table.empty_area_clicked.connect(self._on_map_empty_area_clicked)
        self.map_table.selectionModel().currentChanged.connect(self._on_map_current_index_changed)
        self.map_table.selectionModel().selectionChanged.connect(self._on_map_selection_changed)
        table_grid_layout.addWidget(self.map_table, 0, 1)

        self.axis_corner = QWidget()
        self.axis_corner.setMinimumWidth(148)
        table_grid_layout.addWidget(self.axis_corner, 1, 0)

        self.x_bins_table = QTableWidget(1, 0)
        self.x_bins_table.setVerticalHeaderLabels(["X Bins"])
        self.x_bins_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.x_bins_table.horizontalHeader().setStretchLastSection(True)
        self.x_bins_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.x_bins_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.x_bins_table.setFrameShape(QFrame.Shape.NoFrame)
        self.x_bins_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.x_bins_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.SelectedClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.AnyKeyPressed
        )
        self.x_bins_table.verticalHeader().setDefaultSectionSize(24)
        self.x_bins_table.verticalHeader().setMinimumSectionSize(24)
        self.x_bins_table.horizontalHeader().hide()
        self.x_bins_table.setMaximumHeight(30)
        self.x_bins_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.x_bins_table.itemChanged.connect(self._on_x_bin_item_changed)
        self.x_bins_table.cellClicked.connect(self._on_x_axis_cell_clicked)
        table_grid_layout.addWidget(self.x_bins_table, 1, 1)
        table_grid_layout.setColumnStretch(0, 0)
        table_grid_layout.setColumnStretch(1, 1)
        table_grid_layout.setRowMinimumHeight(1, 28)
        grid_panel_layout.addWidget(self.table_grid, 0)

        self.table_editor_stack = QWidget()
        self.table_editor_stack_layout = QVBoxLayout(self.table_editor_stack)
        self.table_editor_stack_layout.setContentsMargins(0, 0, 0, 0)
        self.table_editor_stack_layout.setSpacing(0)
        self.table_editor_stack_layout.addWidget(self.table_grid_panel, 0)

        self.table_footer_panel = QFrame()
        self.table_footer_panel.setProperty("tableShell", "footer")
        self.table_footer_panel.setProperty("tableAttached", True)
        table_footer_layout = QVBoxLayout(self.table_footer_panel)
        table_footer_layout.setContentsMargins(0, 0, 0, 0)
        table_footer_layout.setSpacing(0)
        self.table_footer_scroll = QScrollArea()
        self.table_footer_scroll.setWidgetResizable(True)
        self.table_footer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.table_footer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_footer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table_footer_content = QWidget()
        self.table_aux_layout = QVBoxLayout(self.table_footer_content)
        self.table_aux_layout.setContentsMargins(8, 6, 8, 8)
        self.table_aux_layout.setSpacing(5)
        self.table_footer_scroll.setWidget(self.table_footer_content)
        table_footer_layout.addWidget(self.table_footer_scroll)
        self.table_footer_hint = QLabel(
            "Enter or F2 edits. Ctrl+A selects all. Ctrl+Enter fills. Ctrl+D fills down. Ctrl+R fills right."
        )
        self.table_footer_hint.setWordWrap(True)
        self.table_footer_hint.setProperty("tableFooterNote", True)
        self.table_aux_layout.addWidget(self.table_footer_hint)
        self.table_footer_panel.setMinimumHeight(116)
        self.table_footer_panel.setMaximumHeight(240)
        self.table_editor_stack_layout.addWidget(self.table_footer_panel, 0)

        self.table_editor_row = QHBoxLayout()
        self.table_editor_row.setContentsMargins(0, 0, 0, 0)
        self.table_editor_row.addStretch(1)
        self.table_editor_row.addWidget(self.table_editor_stack, 0)
        self.table_editor_row.addStretch(1)
        layout.addLayout(self.table_editor_row, 1)

        self._bind_table_shortcut("Ctrl+C", self._on_copy_table_clicked)
        self._bind_table_shortcut("Ctrl+V", self._on_paste_table_clicked)
        self._bind_table_shortcut("Ctrl+Return", self._on_fill_selection_from_active_cell)
        self._bind_table_shortcut("Ctrl+Enter", self._on_fill_selection_from_active_cell)
        self._bind_table_shortcut("Ctrl+D", self._on_fill_down_table_clicked)
        self._bind_table_shortcut("Ctrl+R", self._on_fill_right_table_clicked)
        self._bind_table_shortcut("Shift+Space", self._on_select_active_row)
        self._bind_table_shortcut("Ctrl+Space", self._on_select_active_column)
        self._bind_table_shortcut("Ctrl+A", self._on_select_all_table)
        self._bind_table_shortcut("Ctrl+Z", self._on_undo_table_clicked)
        self._bind_table_shortcut("Ctrl+Y", self._on_redo_table_clicked)
        self._bind_table_shortcut("F2", self._begin_edit_current_table_cell)
        return widget

    # Tab indices for the parameter page sub-tab widget
    _PARAM_TAB_FIELDS = 0
    _PARAM_TAB_HARDWARE = 1
    _PARAM_TAB_SETUP = 2
    _PARAM_TAB_HELP = 3

    def _build_parameter_page_widget(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Compact top strip: title + state + validation + action buttons ---
        top_strip = QFrame()
        top_strip.setProperty("parameterPageHeader", True)
        top_strip_layout = QVBoxLayout(top_strip)
        top_strip_layout.setContentsMargins(8, 6, 8, 4)
        top_strip_layout.setSpacing(3)

        title_row = QHBoxLayout()
        self.parameter_page_header_label = QLabel("Select a tuning page.")
        self.parameter_page_header_label.setProperty("parameterPageTitle", True)
        title_row.addWidget(self.parameter_page_header_label, 1)
        self.parameter_page_state_label = QLabel("Page State: clean")
        title_row.addWidget(self.parameter_page_state_label)
        top_strip_layout.addLayout(title_row)
        self.parameter_related_pages_label = QLabel("")
        self.parameter_related_pages_label.setProperty("navigatorCaption", True)
        self.parameter_related_pages_label.hide()
        top_strip_layout.addWidget(self.parameter_related_pages_label)
        self.parameter_related_pages_tabs = QTabBar()
        self.parameter_related_pages_tabs.setDocumentMode(True)
        self.parameter_related_pages_tabs.setDrawBase(False)
        self.parameter_related_pages_tabs.setExpanding(False)
        self.parameter_related_pages_tabs.currentChanged.connect(self._on_parameter_related_page_changed)
        self.parameter_related_pages_tabs.hide()
        top_strip_layout.addWidget(self.parameter_related_pages_tabs)

        self.parameter_validation_summary_label = QLabel("")
        self.parameter_validation_summary_label.setWordWrap(False)
        top_strip_layout.addWidget(self.parameter_validation_summary_label)

        action_row = QHBoxLayout()
        self.parameter_undo_button = QPushButton("Undo")
        self.parameter_undo_button.clicked.connect(self._on_undo_parameter_clicked)
        action_row.addWidget(self.parameter_undo_button)
        self.parameter_redo_button = QPushButton("Redo")
        self.parameter_redo_button.clicked.connect(self._on_redo_parameter_clicked)
        action_row.addWidget(self.parameter_redo_button)
        self.parameter_revert_button = QPushButton("Revert Page")
        self.parameter_revert_button.clicked.connect(self._on_revert_page_clicked)
        action_row.addWidget(self.parameter_revert_button)
        action_row.addStretch(1)
        self.parameter_write_button = QPushButton("Write to RAM")
        self.parameter_write_button.clicked.connect(self._on_write_page_clicked)
        action_row.addWidget(self.parameter_write_button)
        self.parameter_burn_button = QPushButton("Burn to Flash")
        self.parameter_burn_button.clicked.connect(self._on_burn_page_clicked)
        action_row.addWidget(self.parameter_burn_button)
        self.parameter_power_cycle_button = QPushButton("Power Cycle")
        self.parameter_power_cycle_button.clicked.connect(self._on_power_cycle_clicked)
        self.parameter_power_cycle_button.hide()
        action_row.addWidget(self.parameter_power_cycle_button)
        top_strip_layout.addLayout(action_row)
        outer.addWidget(top_strip)

        # --- Sub-tab widget: each contextual panel gets its own tab ---
        self.parameter_page_tabs = QTabWidget()
        self.parameter_page_tabs.setDocumentMode(True)

        # Tab 0 — Fields: the scalar editor scroll area (always dominant)
        fields_tab = QWidget()
        fields_layout = QVBoxLayout(fields_tab)
        fields_layout.setContentsMargins(0, 4, 0, 0)
        fields_layout.setSpacing(4)

        self.parameter_scroll = QScrollArea()
        self.parameter_scroll.setWidgetResizable(True)
        self.parameter_form_container = QWidget()
        self.parameter_form_layout = QVBoxLayout(self.parameter_form_container)
        self.parameter_form_layout.setContentsMargins(0, 0, 0, 0)
        self.parameter_form_layout.addStretch(1)
        self.parameter_scroll.setWidget(self.parameter_form_container)
        fields_layout.addWidget(self.parameter_scroll, 1)

        self.parameter_diff_group = QGroupBox("Staged Changes")
        self.parameter_diff_group.setProperty("parameterPanelGroup", True)
        param_diff_layout = QVBoxLayout(self.parameter_diff_group)
        param_diff_layout.setContentsMargins(4, 4, 4, 4)
        self.parameter_diff_table = QTableWidget(0, 3)
        self.parameter_diff_table.setHorizontalHeaderLabels(["Parameter", "Before", "After"])
        self.parameter_diff_table.horizontalHeader().setStretchLastSection(True)
        self.parameter_diff_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.parameter_diff_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.parameter_diff_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.parameter_diff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.parameter_diff_table.setMaximumHeight(150)
        param_diff_layout.addWidget(self.parameter_diff_table)
        self.parameter_diff_group.hide()
        fields_layout.addWidget(self.parameter_diff_group)
        self.parameter_page_tabs.addTab(fields_tab, "Fields")

        # Tab 1 — Hardware: readiness cards and issues (full height, no cap)
        hardware_tab = QWidget()
        hardware_tab_layout = QVBoxLayout(hardware_tab)
        hardware_tab_layout.setContentsMargins(0, 4, 0, 0)
        hardware_tab_layout.setSpacing(0)

        self.parameter_hardware_group = QGroupBox("Hardware Summary")
        self.parameter_hardware_group.setProperty("parameterPanelGroup", True)
        hardware_group_layout = QVBoxLayout(self.parameter_hardware_group)
        hardware_group_layout.setContentsMargins(8, 8, 8, 8)
        hardware_group_layout.setSpacing(10)
        self.parameter_hardware_scroll = QScrollArea()
        self.parameter_hardware_scroll.setWidgetResizable(True)
        self.parameter_hardware_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.parameter_hardware_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.parameter_hardware_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.parameter_hardware_cards = QWidget()
        self.parameter_hardware_cards_layout = QVBoxLayout(self.parameter_hardware_cards)
        self.parameter_hardware_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.parameter_hardware_cards_layout.setSpacing(10)
        self.parameter_hardware_scroll.setWidget(self.parameter_hardware_cards)
        hardware_group_layout.addWidget(self.parameter_hardware_scroll, 1)
        self.parameter_hardware_summary = QLabel("")
        self.parameter_hardware_summary.setWordWrap(True)
        hardware_group_layout.addWidget(self.parameter_hardware_summary)
        hardware_tab_layout.addWidget(self.parameter_hardware_group, 1)
        self.parameter_page_tabs.addTab(hardware_tab, "Hardware")

        # Tab 2 — Setup: engine context + req fuel calculator
        setup_tab = QWidget()
        setup_layout = QVBoxLayout(setup_tab)
        setup_layout.setContentsMargins(8, 8, 8, 8)
        setup_layout.setSpacing(8)

        self.operator_context_group = QGroupBox("Engine Context")
        self.operator_context_group.setProperty("parameterPanelGroup", True)
        op_layout = QFormLayout()
        op_layout.setContentsMargins(8, 8, 8, 8)
        self.op_displacement_edit = QLineEdit()
        self.op_displacement_edit.setPlaceholderText("e.g. 2000")
        self.op_displacement_edit.editingFinished.connect(self._on_op_displacement_changed)
        op_layout.addRow("Displacement (cc):", self.op_displacement_edit)
        self.op_compression_edit = QLineEdit()
        self.op_compression_edit.setPlaceholderText("e.g. 9.5")
        self.op_compression_edit.editingFinished.connect(self._on_op_compression_changed)
        op_layout.addRow("Compression ratio:", self.op_compression_edit)
        self.op_cam_duration_edit = QLineEdit()
        self.op_cam_duration_edit.setPlaceholderText("e.g. 240  (degrees @ 0.050)")
        self.op_cam_duration_edit.editingFinished.connect(self._on_op_cam_duration_changed)
        op_layout.addRow("Cam duration (°):", self.op_cam_duration_edit)
        self.op_intent_combo = QComboBox()
        self.op_intent_combo.addItems(["First Start", "Drivable Base"])
        self.op_intent_combo.currentIndexChanged.connect(self._on_op_intent_changed)
        op_layout.addRow("Calibration intent:", self.op_intent_combo)
        self.operator_context_group.setLayout(op_layout)
        setup_layout.addWidget(self.operator_context_group)

        self.req_fuel_group = QGroupBox("Required Fuel Calculator")
        self.req_fuel_group.setProperty("parameterPanelGroup", True)
        req_layout = QVBoxLayout()
        req_layout.setContentsMargins(8, 8, 8, 8)
        self.req_fuel_inputs_label = QLabel("")
        self.req_fuel_inputs_label.setWordWrap(True)
        req_layout.addWidget(self.req_fuel_inputs_label)
        self.req_fuel_result_label = QLabel("")
        self.req_fuel_result_label.setWordWrap(True)
        req_layout.addWidget(self.req_fuel_result_label)
        apply_row = QHBoxLayout()
        self.req_fuel_apply_button = QPushButton("Apply to reqFuel")
        self.req_fuel_apply_button.clicked.connect(self._on_apply_req_fuel_clicked)
        apply_row.addWidget(self.req_fuel_apply_button)
        apply_row.addStretch(1)
        req_layout.addLayout(apply_row)
        self.req_fuel_group.setLayout(req_layout)
        setup_layout.addWidget(self.req_fuel_group)
        setup_layout.addStretch(1)
        self.parameter_page_tabs.addTab(setup_tab, "Setup")

        # Tab 3 — Help: page summary, INI details text, and diff summary
        help_tab = QWidget()
        help_layout = QVBoxLayout(help_tab)
        help_layout.setContentsMargins(8, 6, 8, 6)
        help_layout.setSpacing(4)

        self.parameter_page_summary_label = QLabel("")
        self.parameter_page_summary_label.setWordWrap(True)
        help_layout.addWidget(self.parameter_page_summary_label)

        self.parameter_diff_summary_label = QLabel("")
        self.parameter_diff_summary_label.setWordWrap(True)
        help_layout.addWidget(self.parameter_diff_summary_label)
        self.parameter_evidence_label = QLabel("")
        self.parameter_evidence_label.setWordWrap(True)
        self.parameter_evidence_label.setProperty("surfacePanelNote", True)
        self.parameter_evidence_label.hide()
        help_layout.addWidget(self.parameter_evidence_label)

        self.parameter_page_details = QTextEdit()
        self.parameter_page_details.setReadOnly(True)
        help_layout.addWidget(self.parameter_page_details, 1)
        self.parameter_page_tabs.addTab(help_tab, "Help")

        # Hide Hardware and Setup tabs until content makes them relevant
        self.parameter_page_tabs.setTabVisible(self._PARAM_TAB_HARDWARE, False)
        self.parameter_page_tabs.setTabVisible(self._PARAM_TAB_SETUP, False)

        outer.addWidget(self.parameter_page_tabs, 1)
        return widget

    def _build_curve_page_widget(self) -> QWidget:
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header strip
        top_strip = QFrame()
        top_strip.setProperty("parameterPageHeader", True)
        top_layout = QVBoxLayout(top_strip)
        top_layout.setContentsMargins(8, 6, 8, 4)
        top_layout.setSpacing(3)

        title_row = QHBoxLayout()
        self.curve_page_title_label = QLabel("Curve")
        self.curve_page_title_label.setProperty("parameterPageTitle", True)
        title_row.addWidget(self.curve_page_title_label, 1)
        self.curve_page_state_label = QLabel("")
        title_row.addWidget(self.curve_page_state_label)
        top_layout.addLayout(title_row)

        self.curve_page_summary_label = QLabel("")
        self.curve_page_summary_label.setWordWrap(True)
        top_layout.addWidget(self.curve_page_summary_label)

        self.curve_channel_label = QLabel("")
        self.curve_channel_label.setProperty("navigatorCaption", True)
        top_layout.addWidget(self.curve_channel_label)

        action_row = QHBoxLayout()
        self.curve_undo_button = QPushButton("Undo")
        self.curve_undo_button.clicked.connect(self._on_curve_undo_clicked)
        action_row.addWidget(self.curve_undo_button)
        self.curve_redo_button = QPushButton("Redo")
        self.curve_redo_button.clicked.connect(self._on_curve_redo_clicked)
        action_row.addWidget(self.curve_redo_button)
        self.curve_revert_button = QPushButton("Revert Page")
        self.curve_revert_button.clicked.connect(self._on_revert_page_clicked)
        action_row.addWidget(self.curve_revert_button)
        action_row.addStretch(1)
        self.curve_write_button = QPushButton("Write to RAM")
        self.curve_write_button.clicked.connect(self._on_write_page_clicked)
        action_row.addWidget(self.curve_write_button)
        self.curve_burn_button = QPushButton("Burn to Flash")
        self.curve_burn_button.clicked.connect(self._on_burn_page_clicked)
        action_row.addWidget(self.curve_burn_button)
        top_layout.addLayout(action_row)
        outer.addWidget(top_strip)

        # Curve table
        self._curve_snapshot: CurvePageSnapshot | None = None
        self.curve_table = QTableWidget(0, 1)
        self.curve_table.setAlternatingRowColors(True)
        self.curve_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.curve_table.horizontalHeader().setStretchLastSection(True)
        self.curve_table.verticalHeader().setVisible(False)
        self.curve_table.cellChanged.connect(self._on_curve_cell_changed)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.curve_table)
        outer.addWidget(scroll, 1)
        return widget

    def _build_catalog_panel(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("catalogPanel", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Parameter Catalog")
        title.setProperty("catalogTitle", True)
        layout.addWidget(title)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)
        self.catalog_search_edit = QLineEdit()
        self.catalog_search_edit.setPlaceholderText("Filter by name, type, or units")
        self.catalog_search_edit.setProperty("catalogFilter", True)
        self.catalog_search_edit.textChanged.connect(self._on_catalog_query_changed)
        filter_row.addWidget(self.catalog_search_edit, 1)

        self.catalog_kind_combo = QComboBox()
        self.catalog_kind_combo.setProperty("catalogFilter", True)
        self.catalog_kind_combo.addItems(["All", "Scalars", "Tables / Maps", "Tune Only"])
        self.catalog_kind_combo.currentTextChanged.connect(self._on_catalog_kind_changed)
        filter_row.addWidget(self.catalog_kind_combo)
        layout.addLayout(filter_row)

        self.catalog_table = QTableWidget(0, 8)
        self.catalog_table.setProperty("catalogTable", True)
        self.catalog_table.setHorizontalHeaderLabels(
            ["Name", "Kind", "Page", "Offset", "Units", "Type", "Shape", "Tune Value"]
        )
        self.catalog_table.horizontalHeader().setStretchLastSection(True)
        self.catalog_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.catalog_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.catalog_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.catalog_table.setAlternatingRowColors(True)
        self.catalog_table.setColumnWidth(0, 124)
        self.catalog_table.setColumnWidth(1, 68)
        self.catalog_table.setColumnWidth(2, 44)
        self.catalog_table.setColumnWidth(3, 54)
        self.catalog_table.setColumnWidth(4, 52)
        self.catalog_table.setColumnWidth(5, 60)
        self.catalog_table.setColumnWidth(6, 66)
        self.catalog_table.itemSelectionChanged.connect(self._on_catalog_selection_changed)
        layout.addWidget(self.catalog_table, 1)

        self.catalog_details = QTextEdit()
        self.catalog_details.setReadOnly(True)
        self.catalog_details.setProperty("catalogDetails", True)
        self.catalog_details.setPlaceholderText("Select a parameter to inspect its details.")
        self.catalog_details.setMaximumHeight(132)
        layout.addWidget(self.catalog_details)
        return panel

    def _render_and_emit(self, snapshot: TuningWorkspaceSnapshot, notify_workspace: bool = False) -> None:
        started = self._table_debug_start("render_and_emit", notify_workspace=notify_workspace)
        self._render(snapshot)
        message = self.presenter.consume_message()
        if message:
            self.status_message.emit(message)
        if notify_workspace:
            self.workspace_changed.emit()
        self._table_debug_end(started, "render_and_emit", notify_workspace=notify_workspace)

    def _render(self, snapshot: TuningWorkspaceSnapshot) -> None:
        started = self._table_debug_start("render", active_page_kind=snapshot.active_page_kind)
        self._updating_widgets = True
        try:
            self._last_workspace_snapshot = snapshot
            t = self._table_debug_start("render_overview")
            self._render_overview(snapshot)
            self._table_debug_end(t, "render_overview")
            t = self._table_debug_start("render_navigation")
            self._render_navigation(snapshot)
            self._table_debug_end(t, "render_navigation")
            t = self._table_debug_start("render_active_page")
            self._render_active_page(snapshot)
            self._table_debug_end(t, "render_active_page")
            t = self._table_debug_start("render_catalog", entries=len(snapshot.catalog.entries))
            self._render_catalog(snapshot.catalog)
            self._table_debug_end(t, "render_catalog", entries=len(snapshot.catalog.entries))
            t = self._table_debug_start("render_operation_log")
            self._render_operation_log(snapshot.operation_log)
            self._table_debug_end(t, "render_operation_log")
            t = self._table_debug_start("render_sync_state")
            self._render_sync_state(snapshot)
            self._table_debug_end(t, "render_sync_state")
            t = self._table_debug_start("render_workspace_review")
            self._render_workspace_review(snapshot.workspace_review)
            self._table_debug_end(t, "render_workspace_review")
            self._render_ve_analyze(snapshot.ve_analyze)
            self._render_wue_analyze(snapshot.wue_analyze)
        finally:
            self._updating_widgets = False
        t = self._table_debug_start("fit_active_editor")
        self._fit_active_editor()
        self._table_debug_end(t, "fit_active_editor")
        self._table_debug_end(started, "render", active_page_kind=snapshot.active_page_kind)

    def _render_overview(self, snapshot: TuningWorkspaceSnapshot) -> None:
        sync_state = snapshot.sync_state
        mismatch_count = len(sync_state.mismatches) if sync_state is not None else 0
        staged_count = len(snapshot.workspace_review.entries)
        hardware_count = len(snapshot.hardware_issues)
        connection_text = sync_state.connection_state if sync_state is not None else "unknown"
        self.connection_chip.setText(f"Connection  {connection_text}")
        self.mismatch_chip.setText(f"Mismatches  {mismatch_count}")
        self.staged_chip.setText(f"Staged  {staged_count}")
        self.hardware_chip.setText(f"Hardware  {hardware_count}")
        self.connection_chip.setProperty("severity", "info")
        self.mismatch_chip.setProperty("severity", "warning" if mismatch_count else "ok")
        self.staged_chip.setProperty("severity", "accent" if staged_count else "ok")
        self.hardware_chip.setProperty("severity", "warning" if hardware_count else "ok")
        for chip in (self.connection_chip, self.mismatch_chip, self.staged_chip, self.hardware_chip):
            self._refresh_style(chip)

    def _render_navigation(self, snapshot: TuningWorkspaceSnapshot) -> None:
        blocker = QSignalBlocker(self.navigator_tree)
        self.navigator_tree.setUpdatesEnabled(False)
        try:
            self.navigator_tree.clear()
            active_item: QTreeWidgetItem | None = None
            for group in snapshot.navigation:
                group_item = QTreeWidgetItem([group.title, ""])
                group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.navigator_tree.addTopLevelItem(group_item)
                for page in group.pages:
                    item = QTreeWidgetItem([page.title, page.state.label])
                    item.setData(0, Qt.ItemDataRole.UserRole, page.page_id)
                    item.setToolTip(0, page.summary)
                    self._apply_navigation_item_style(item, page.state.label)
                    if page.is_active:
                        active_item = item
                    group_item.addChild(item)
                group_item.setExpanded(True)
            if active_item is not None:
                self.navigator_tree.setCurrentItem(active_item)
        finally:
            self.navigator_tree.setUpdatesEnabled(True)
            del blocker

    @staticmethod
    def _apply_navigation_item_style(item: QTreeWidgetItem, state_label: str) -> None:
        state = state_label.strip().lower()
        if state == "staged":
            background = QColor("#5a3e12")
            foreground = QColor("#f8e7bf")
            bold = True
        elif state == "written":
            background = QColor("#12384f")
            foreground = QColor("#d9f1ff")
            bold = True
        elif state == "invalid":
            background = QColor("#4b1f24")
            foreground = QColor("#ffd7dc")
            bold = True
        else:
            background = QColor("#24272c")
            foreground = QColor("#d7dde6")
            bold = False
        for column in range(item.columnCount()):
            item.setBackground(column, background)
            item.setForeground(column, foreground)
            font = item.font(column)
            font.setBold(bold)
            item.setFont(column, font)

    def _render_active_page(self, snapshot: TuningWorkspaceSnapshot) -> None:
        self._last_active_page_kind = snapshot.active_page_kind
        self._rebalance_splitter(snapshot.active_page_kind)
        if snapshot.table_page is not None:
            self.editor_stack.setCurrentWidget(self.table_page_widget)
            self._render_table_page(snapshot.table_page)
            return
        if snapshot.curve_page is not None:
            self.editor_stack.setCurrentWidget(self.curve_page_widget)
            self._render_curve_page(snapshot.curve_page)
            return
        if snapshot.parameter_page is not None:
            self.editor_stack.setCurrentWidget(self.parameter_page_widget)
            self._render_parameter_page(snapshot.parameter_page)
            return
        self.editor_stack.setCurrentWidget(self.empty_page)

    def _render_active_page_only(self, snapshot: TuningWorkspaceSnapshot) -> None:
        self._updating_widgets = True
        try:
            self._render_active_page(snapshot)
        finally:
            self._updating_widgets = False
        self._fit_active_editor()

    def _refresh_active_page_evidence(self, snapshot: TuningWorkspaceSnapshot) -> None:
        if snapshot.table_page is not None:
            self._render_table_page_evidence(snapshot.table_page)
            return
        if snapshot.parameter_page is not None:
            self._render_parameter_page_evidence(snapshot.parameter_page)

    def _render_table_page(self, snapshot: TablePageSnapshot, rebuild_grid: bool = True) -> None:
        started = self._table_debug_start(
            "render_table_page",
            page_id=snapshot.page_id,
            rebuild_grid=rebuild_grid,
        )
        self.table_page_header_label.setText(snapshot.title)
        self._render_related_page_tabs(
            self.table_related_pages_label,
            self.table_related_pages_tabs,
            snapshot.related_pages_title,
            snapshot.related_pages,
        )
        self.table_page_summary_label.setText(snapshot.summary)
        self.table_page_summary_label.setVisible(
            bool(snapshot.summary.strip())
            and snapshot.summary.strip() != snapshot.title.strip()
            and snapshot.summary.strip() != snapshot.axis_summary.strip()
        )
        self.table_validation_summary_label.setText(f"Validation: {snapshot.validation_summary}")
        self.table_validation_summary_label.setVisible(self._has_table_validation_details(snapshot.validation_summary))
        self.table_diff_summary_label.setText(f"Diff: {snapshot.diff_summary}")
        self.table_diff_summary_label.setVisible(bool(snapshot.diff_entries))
        self.table_axis_summary_label.setText(snapshot.axis_summary)
        self.table_axis_summary_label.setVisible(
            "n/a" not in snapshot.axis_summary.lower() and snapshot.axis_summary.strip() != snapshot.summary.strip()
        )
        self._refresh_table_header_sections()
        self.table_page_state_label.setText(self._state_text(snapshot.state.kind.value, snapshot.state.detail))
        details_text = snapshot.details_text.strip()
        show_details = self._should_show_table_details(snapshot)
        self.table_page_details.setPlainText(details_text if show_details else "")
        self.table_page_details.setVisible(show_details)
        self._render_table_page_evidence(snapshot)
        self.table_undo_button.setEnabled(snapshot.can_undo)
        self.table_redo_button.setEnabled(snapshot.can_redo)

        # Power-cycle warning
        self.table_power_cycle_warning.setVisible(snapshot.any_requires_power_cycle)
        self.table_power_cycle_button.setVisible(snapshot.any_requires_power_cycle)

        # Help text (z-bins help as page-level context)
        help_text = snapshot.z_help or ""
        if help_text:
            self.table_help_label.setText(help_text)
            self.table_help_label.show()
        else:
            self.table_help_label.hide()

        # Staged changes diff table
        self._render_diff_table(self.table_diff_table, self.table_diff_group, snapshot.diff_entries)

        if snapshot.table_model is None:
            self._clear_table_page(snapshot.message or "No tune values available for this page.")
            return
        if not rebuild_grid:
            self._render_table_aux_sections(snapshot.auxiliary_sections)
            return

        tg = self._table_debug_start("build_render_model")
        render_model = self.table_rendering_service.build_render_model(
            snapshot.table_model,
            snapshot.x_labels,
            snapshot.y_labels,
        )
        self._table_debug_end(tg, "build_render_model")
        self._clear_table_highlights()
        self._display_to_model_row = list(render_model.row_index_map)

        tg = self._table_debug_start("set_render_model_and_bins",
                                     rows=len(snapshot.y_labels), cols=len(snapshot.x_labels))
        self.map_table.setUpdatesEnabled(False)
        self.x_bins_table.setUpdatesEnabled(False)
        self.y_bins_table.setUpdatesEnabled(False)
        x_blocker = QSignalBlocker(self.x_bins_table)
        y_blocker = QSignalBlocker(self.y_bins_table)
        try:
            self.map_table_model.set_render_model(render_model)

            x_range_tip = self._range_tooltip(snapshot.x_range, snapshot.x_help)
            self.x_bins_table.clear()
            self.x_bins_table.setRowCount(1)
            self.x_bins_table.setColumnCount(len(snapshot.x_labels))
            self.x_bins_table.setVerticalHeaderLabels([snapshot.x_parameter_name or "X Bins"])
            self.x_bins_table.setHorizontalHeaderLabels(list(snapshot.x_labels))
            for column_index, label in enumerate(snapshot.x_labels):
                item = QTableWidgetItem(label)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if x_range_tip:
                    item.setToolTip(x_range_tip)
                self.x_bins_table.setItem(0, column_index, item)

            y_range_tip = self._range_tooltip(snapshot.y_range, snapshot.y_help)
            self.y_bins_table.clear()
            self.y_bins_table.setRowCount(len(render_model.y_labels))
            self.y_bins_table.setColumnCount(1)
            self.y_bins_table.setHorizontalHeaderLabels([snapshot.y_parameter_name or "Y Bins"])
            self.y_bins_table.setVerticalHeaderLabels([str(index) for index in range(len(render_model.y_labels))])
            for row_index, label in enumerate(render_model.y_labels):
                item = QTableWidgetItem(label)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if y_range_tip:
                    item.setToolTip(y_range_tip)
                self.y_bins_table.setItem(row_index, 0, item)
        finally:
            del x_blocker, y_blocker
            self.map_table.setUpdatesEnabled(True)
            self.x_bins_table.setUpdatesEnabled(True)
            self.y_bins_table.setUpdatesEnabled(True)
        self._table_debug_end(tg, "set_render_model_and_bins")

        if self._active_display_cell is not None:
            row, column = self._active_display_cell
            if row < self._map_row_count() and column < self._map_column_count():
                self.map_table.setCurrentIndex(self.map_table_model.index(row, column))
        elif self._map_row_count() and self._map_column_count():
            self.map_table.setCurrentIndex(self.map_table_model.index(0, 0))
        self._fit_table_layout()
        self._apply_table_highlights()
        self._render_table_aux_sections(snapshot.auxiliary_sections)
        self._table_debug_end(
            started,
            "render_table_page",
            page_id=snapshot.page_id,
            rebuild_grid=rebuild_grid,
        )

    def _render_after_single_table_edit(
        self,
        snapshot: TuningWorkspaceSnapshot,
        *,
        display_row: int | None = None,
        column: int | None = None,
        axis: str | None = None,
        axis_index: int | None = None,
        notify_workspace: bool = True,
    ) -> None:
        started = self._table_debug_start(
            "render_after_single_table_edit",
            display_row=display_row,
            column=column,
            axis=axis,
            axis_index=axis_index,
            notify_workspace=notify_workspace,
        )
        self._updating_widgets = True
        try:
            self._render_overview(snapshot)
            self._render_navigation(snapshot)
            if snapshot.table_page is not None:
                self.editor_stack.setCurrentWidget(self.table_page_widget)
                self._render_table_page(snapshot.table_page, rebuild_grid=False)
                if display_row is not None and column is not None:
                    self._refresh_single_table_cell(snapshot.table_page, display_row, column)
                if axis is not None and axis_index is not None:
                    self._refresh_single_axis_cell(axis, axis_index)
            self._render_catalog(snapshot.catalog)
            self._render_operation_log(snapshot.operation_log)
            self._render_sync_state(snapshot)
            self._render_workspace_review(snapshot.workspace_review)
        finally:
            self._updating_widgets = False
        self._fit_active_editor()
        message = self.presenter.consume_message()
        if message:
            self.status_message.emit(message)
        if notify_workspace:
            self.workspace_changed.emit()
        self._table_debug_end(
            started,
            "render_after_single_table_edit",
            display_row=display_row,
            column=column,
            axis=axis,
            axis_index=axis_index,
            notify_workspace=notify_workspace,
        )

    def _refresh_single_table_cell(self, snapshot: TablePageSnapshot, display_row: int, column: int) -> None:
        if snapshot.table_model is None:
            return
        if display_row >= self._map_row_count() or column >= self._map_column_count():
            return
        render_model = self.table_rendering_service.build_render_model(
            snapshot.table_model,
            snapshot.x_labels,
            snapshot.y_labels,
        )
        if display_row >= render_model.rows or column >= render_model.columns:
            return
        cell = render_model.cells[display_row][column]
        self.map_table_model.update_cell(display_row, column, cell)
        self._apply_table_highlights()

    def _refresh_single_axis_cell(self, axis: str, index: int) -> None:
        if axis == "x":
            item = self.x_bins_table.item(0, index)
        else:
            item = self.y_bins_table.item(index, 0)
        if item is None:
            return
        self._restore_axis_item(item)
        self._apply_table_highlights()

    def _render_curve_page(self, snapshot: CurvePageSnapshot) -> None:
        self._curve_snapshot = snapshot
        self.curve_page_title_label.setText(snapshot.title)
        self.curve_page_state_label.setText(self._state_text(snapshot.state.kind.value, snapshot.state.detail))
        self.curve_page_summary_label.setText(snapshot.summary)
        self.curve_page_summary_label.setVisible(bool(snapshot.summary.strip()))
        if snapshot.x_channel:
            self.curve_channel_label.setText(f"Live: {snapshot.x_channel}")
            self.curve_channel_label.show()
        else:
            self.curve_channel_label.hide()
        self.curve_undo_button.setEnabled(snapshot.can_undo)
        self.curve_redo_button.setEnabled(snapshot.can_redo)

        # Rebuild the table
        blocker = QSignalBlocker(self.curve_table)
        try:
            n_y = len(snapshot.y_param_names)
            self.curve_table.setUpdatesEnabled(False)
            self.curve_table.setRowCount(0)
            self.curve_table.setColumnCount(1 + n_y)

            # Column headers: X label | Y label(s)
            x_header = snapshot.x_label
            if snapshot.x_units:
                x_header = f"{x_header} ({snapshot.x_units})"
            headers = [x_header]
            for label, units in zip(snapshot.y_labels, snapshot.y_units):
                h = label
                if units:
                    h = f"{h} ({units})"
                headers.append(h)
            self.curve_table.setHorizontalHeaderLabels(headers)

            # Populate rows
            for row in snapshot.rows:
                r = self.curve_table.rowCount()
                self.curve_table.insertRow(r)

                # X cell — read-only
                x_item = QTableWidgetItem(row.x_display)
                x_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                x_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.curve_table.setItem(r, 0, x_item)

                # Y cells — editable; highlight if staged
                for col_offset, (y_text, staged) in enumerate(zip(row.y_displays, row.is_staged)):
                    y_item = QTableWidgetItem(y_text)
                    y_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if staged:
                        y_item.setBackground(QColor("#fffbe6"))
                    self.curve_table.setItem(r, 1 + col_offset, y_item)

            self.curve_table.resizeColumnsToContents()
            self.curve_table.horizontalHeader().setStretchLastSection(True)
        finally:
            del blocker
            self.curve_table.setUpdatesEnabled(True)

    def _render_parameter_page(self, snapshot: ParameterPageSnapshot) -> None:
        self.parameter_page_header_label.setText(snapshot.title)
        self._render_related_page_tabs(
            self.parameter_related_pages_label,
            self.parameter_related_pages_tabs,
            snapshot.related_pages_title,
            snapshot.related_pages,
        )
        self.parameter_page_summary_label.setText(snapshot.summary)
        self.parameter_validation_summary_label.setText(f"Validation: {snapshot.validation_summary}")
        self.parameter_diff_summary_label.setText(f"Diff: {snapshot.diff_summary}")
        self.parameter_page_state_label.setText(self._state_text(snapshot.state.kind.value, snapshot.state.detail))
        self.parameter_page_details.setPlainText(snapshot.details_text)
        self._render_parameter_page_evidence(snapshot)
        self.parameter_undo_button.setEnabled(snapshot.can_undo)
        self.parameter_redo_button.setEnabled(snapshot.can_redo)
        self.parameter_power_cycle_button.setVisible(snapshot.any_requires_power_cycle)

        has_hardware = bool(snapshot.hardware_issues or snapshot.hardware_cards)
        has_setup = snapshot.generator_context is not None or snapshot.calculator_snapshot is not None
        self.parameter_page_tabs.setTabVisible(self._PARAM_TAB_HARDWARE, has_hardware)
        self.parameter_page_tabs.setTabVisible(self._PARAM_TAB_SETUP, has_setup)

        if has_hardware:
            self._render_hardware_cards(snapshot.hardware_cards)
            lines = []
            for issue in snapshot.hardware_issues:
                prefix = "Error" if issue.severity.value == "error" else "Warning"
                detail = f" {issue.detail}" if issue.detail else ""
                lines.append(f"{prefix}: {issue.message}{detail}")
            if snapshot.any_requires_power_cycle:
                lines.append("Restart required: one or more parameters on this page require a power cycle after changes.")
            self.parameter_hardware_summary.setText("\n".join(lines))
            self.parameter_hardware_summary.setVisible(bool(lines))
        else:
            self._render_hardware_cards(())
            self.parameter_hardware_summary.clear()

        self._render_operator_context_panel(snapshot)
        self._render_req_fuel_panel(snapshot.calculator_snapshot)
        self._render_diff_table(self.parameter_diff_table, self.parameter_diff_group, snapshot.diff_entries)
        written_set = frozenset(snapshot.written_values)
        section_key = frozenset(
            (field.name, field.is_dirty, field.name in written_set)
            for section in snapshot.sections
            for field in section.fields
        )
        if snapshot.page_id != self._last_parameter_page_id or section_key != self._last_parameter_section_key:
            self._render_scalar_sections(
                self.parameter_form_layout, snapshot.sections, written_names=written_set
            )
            self._last_parameter_page_id = snapshot.page_id
            self._last_parameter_section_key = section_key

    def _render_table_page_evidence(self, snapshot: TablePageSnapshot) -> None:
        te = self._table_debug_start("table_evidence_review")
        evidence_review = self._page_evidence_review_service.build(
            page_title=snapshot.title,
            page_id=snapshot.page_id,
            group_id=snapshot.group_id,
            page_family_id=snapshot.page_family_id,
            parameter_names=tuple(name for name in (snapshot.x_parameter_name, snapshot.y_parameter_name) if name),
            evidence_hints=snapshot.evidence_hints,
            evidence_snapshot=self._review_evidence_replay_snapshot,
        )
        evidence_text = evidence_review.detail_text if evidence_review is not None else ""
        comparison = self._build_evidence_comparison(
            evidence_review,
            baseline_snapshot=self._review_evidence_replay_snapshot,
            current_snapshot=self._latest_evidence_replay_snapshot,
        )
        if comparison is not None:
            evidence_text = f"{evidence_text}\n{comparison.detail_text}" if evidence_text else comparison.detail_text
        replay_context = self._table_replay_context_service.build(
            table_snapshot=snapshot,
            evidence_snapshot=self._review_evidence_replay_snapshot,
        )
        if replay_context is not None:
            evidence_text = f"{evidence_text}\n{replay_context.detail_text}" if evidence_text else replay_context.detail_text
        is_visible = evidence_review is not None or replay_context is not None
        if evidence_text != self._last_table_evidence_text:
            self.table_evidence_label.setText(evidence_text)
            self._last_table_evidence_text = evidence_text
        if is_visible != self._last_table_evidence_visible:
            self.table_evidence_label.setVisible(is_visible)
            self._last_table_evidence_visible = is_visible
        self._table_debug_end(te, "table_evidence_review")

    def _render_parameter_page_evidence(self, snapshot: ParameterPageSnapshot) -> None:
        evidence_review = self._page_evidence_review_service.build(
            page_title=snapshot.title,
            page_id=snapshot.page_id,
            group_id=snapshot.group_id,
            page_family_id=snapshot.page_family_id,
            parameter_names=tuple(row.name for row in snapshot.rows),
            evidence_hints=snapshot.evidence_hints,
            evidence_snapshot=self._review_evidence_replay_snapshot,
        )
        evidence_text = evidence_review.detail_text if evidence_review is not None else ""
        comparison = self._build_evidence_comparison(
            evidence_review,
            baseline_snapshot=self._review_evidence_replay_snapshot,
            current_snapshot=self._latest_evidence_replay_snapshot,
        )
        if comparison is not None:
            evidence_text = f"{evidence_text}\n{comparison.detail_text}" if evidence_text else comparison.detail_text
        is_visible = evidence_review is not None
        if evidence_text != self._last_parameter_evidence_text:
            self.parameter_evidence_label.setText(evidence_text)
            self._last_parameter_evidence_text = evidence_text
        if is_visible != self._last_parameter_evidence_visible:
            self.parameter_evidence_label.setVisible(is_visible)
            self._last_parameter_evidence_visible = is_visible

    def _build_evidence_comparison(self, evidence_review, *, baseline_snapshot, current_snapshot):
        if evidence_review is None:
            return None
        if baseline_snapshot is None or current_snapshot is None:
            return None
        return self._evidence_replay_comparison_service.build(
            baseline_snapshot=baseline_snapshot,
            current_snapshot=current_snapshot,
            relevant_channel_names=tuple(item.name for item in evidence_review.relevant_channels),
        )

    def _render_related_page_tabs(self, label: QLabel, tabs: QTabBar, family_title: str | None, related_pages: tuple) -> None:
        visible = len(related_pages) > 1 and bool(family_title)
        label.setVisible(visible)
        tabs.setVisible(visible)
        if not visible:
            blocker = QSignalBlocker(tabs)
            self._clear_tab_bar(tabs)
            del blocker
            return
        label.setText(family_title or "")
        blocker = QSignalBlocker(tabs)
        self._clear_tab_bar(tabs)
        active_index = 0
        for index, related_page in enumerate(related_pages):
            tabs.addTab(related_page.title)
            tabs.setTabData(index, related_page.page_id)
            tabs.setTabToolTip(index, f"{related_page.title} ({related_page.state_label})")
            tabs.setTabTextColor(index, self._tab_state_color(related_page.state_label))
            if related_page.is_active:
                active_index = index
        tabs.setCurrentIndex(active_index)
        del blocker

    def _on_table_related_page_changed(self, index: int) -> None:
        self._open_related_page_from_tabs(self.table_related_pages_tabs, index)

    def _on_parameter_related_page_changed(self, index: int) -> None:
        self._open_related_page_from_tabs(self.parameter_related_pages_tabs, index)

    def _open_related_page_from_tabs(self, tabs: QTabBar, index: int) -> None:
        if self._updating_widgets or index < 0:
            return
        page_id = tabs.tabData(index)
        if not page_id:
            return
        snapshot = self.presenter.select_page(str(page_id))
        self._render_and_emit(snapshot, notify_workspace=True)
        self._schedule_ui_state_changed()

    @staticmethod
    def _clear_tab_bar(tabs: QTabBar) -> None:
        while tabs.count():
            tabs.removeTab(tabs.count() - 1)

    @staticmethod
    def _tab_state_color(state_label: str) -> QColor:
        state = state_label.strip().lower()
        if state == "staged":
            return QColor("#f0c674")
        if state == "written":
            return QColor("#7fb3ff")
        if state == "invalid":
            return QColor("#ff9aa5")
        return QColor("#d7dde6")

    def _render_catalog(self, snapshot: CatalogSnapshot) -> None:
        blocker = QSignalBlocker(self.catalog_table)
        self.catalog_table.setUpdatesEnabled(False)
        try:
            self.catalog_table.setRowCount(len(snapshot.entries))
            for row_index, entry in enumerate(snapshot.entries):
                values = [
                    entry.name,
                    entry.kind,
                    "" if entry.page is None else str(entry.page),
                    "" if entry.offset is None else str(entry.offset),
                    entry.units or "",
                    entry.data_type,
                    entry.shape,
                    entry.tune_preview,
                ]
                for column_index, value in enumerate(values):
                    self.catalog_table.setItem(row_index, column_index, self._table_item(value, editable=False))
            details_text = snapshot.details_text.strip()
            self.catalog_details.setPlainText(details_text)
            self.catalog_details.setVisible(bool(details_text))
            if snapshot.selected_name:
                for row_index, entry in enumerate(snapshot.entries):
                    if entry.name == snapshot.selected_name:
                        self.catalog_table.selectRow(row_index)
                        break
            else:
                self.catalog_table.clearSelection()
        finally:
            self.catalog_table.setUpdatesEnabled(True)
            del blocker

    def _render_operation_log(self, snapshot: OperationLogSnapshot) -> None:
        self.operation_log_text.setPlainText(snapshot.summary_text)

    def _render_sync_state(self, snapshot: TuningWorkspaceSnapshot) -> None:
        sync_state = snapshot.sync_state
        if sync_state is None:
            self.sync_state_text.setPlainText("No sync state available.")
            return
        lines = [
            f"Connection: {sync_state.connection_state}",
            f"ECU RAM Snapshot: {'present' if sync_state.has_ecu_ram else 'none'}",
        ]
        if sync_state.mismatches:
            lines.append("")
            lines.append("Mismatches:")
            lines.extend(f"- {mismatch.detail}" for mismatch in sync_state.mismatches)
        else:
            lines.append("")
            lines.append("No mismatches detected.")
        self.sync_state_text.setPlainText("\n".join(lines))

    def _render_workspace_review(self, snapshot: WorkspaceReviewSnapshot) -> None:
        self.workspace_review_summary.setText(snapshot.summary_text)
        self.workspace_review_table.setRowCount(len(snapshot.entries))
        for row_index, entry in enumerate(snapshot.entries):
            page_item = self._table_item(entry.page_title, editable=False)
            if entry.is_written:
                page_item.setToolTip("Written to RAM")
            self.workspace_review_table.setItem(row_index, 0, page_item)
            self.workspace_review_table.setItem(row_index, 1, self._table_item(entry.name, editable=False))
            self.workspace_review_table.setItem(row_index, 2, self._table_item(entry.before_preview, editable=False))
            after_text = entry.preview + (" [RAM]" if entry.is_written else "")
            self.workspace_review_table.setItem(row_index, 3, self._table_item(after_text, editable=False))

    def _render_ve_analyze(self, ve: "VeAnalyzeSnapshot | None") -> None:
        if ve is None:
            # Not on a table page — hide VE Analyze controls and clear panel
            self.table_ve_analyze_start_button.setVisible(False)
            self.table_ve_analyze_stop_button.setVisible(False)
            self.table_ve_analyze_apply_button.setVisible(False)
            self.table_ve_analyze_reset_button.setVisible(False)
            self.ve_analyze_status_label.setText("Select a table page and click VE Analyze to start.")
            self.ve_analyze_detail_text.setPlainText("")
            return
        # Show/hide toolbar buttons based on state
        self.table_ve_analyze_start_button.setVisible(ve.can_start)
        self.table_ve_analyze_stop_button.setVisible(ve.can_stop)
        self.table_ve_analyze_apply_button.setVisible(ve.has_data and not ve.is_running)
        self.table_ve_analyze_apply_button.setEnabled(ve.can_apply)
        self.table_ve_analyze_reset_button.setVisible(ve.can_reset)
        # Update VE Analyze tab
        self.ve_analyze_status_label.setText(ve.status_text)
        self.ve_analyze_detail_text.setPlainText(ve.detail_text)

    # ------------------------------------------------------------------
    # VE Analyze button handlers
    # ------------------------------------------------------------------

    def _on_ve_analyze_start_clicked(self) -> None:
        snapshot = self.presenter.start_ve_analyze()
        self._render_and_emit(snapshot)

    def _on_ve_analyze_stop_clicked(self) -> None:
        snapshot = self.presenter.stop_ve_analyze()
        self._render_and_emit(snapshot)
        # Switch to VE Analyze tab so the operator can review proposals
        ve_tab_index = self.workspace_details_tabs.indexOf(self.ve_analyze_group)
        if ve_tab_index >= 0:
            self.workspace_details_tabs.setCurrentIndex(ve_tab_index)

    def _on_ve_analyze_apply_clicked(self) -> None:
        snapshot = self.presenter.apply_ve_analyze_proposals()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_ve_analyze_reset_clicked(self) -> None:
        snapshot = self.presenter.reset_ve_analyze()
        self._render_and_emit(snapshot)

    # ------------------------------------------------------------------
    # WUE Analyze rendering and handlers
    # ------------------------------------------------------------------

    def _render_wue_analyze(self, wue: "WueAnalyzeSnapshot | None") -> None:
        if wue is None:
            self.table_wue_analyze_start_button.setVisible(False)
            self.table_wue_analyze_stop_button.setVisible(False)
            self.table_wue_analyze_apply_button.setVisible(False)
            self.table_wue_analyze_reset_button.setVisible(False)
            self.wue_analyze_status_label.setText("Select a warmup table page and click WUE Analyze to start.")
            self.wue_analyze_detail_text.setPlainText("")
            return
        self.table_wue_analyze_start_button.setVisible(wue.can_start)
        self.table_wue_analyze_stop_button.setVisible(wue.can_stop)
        self.table_wue_analyze_apply_button.setVisible(wue.has_data and not wue.is_running)
        self.table_wue_analyze_apply_button.setEnabled(wue.can_apply)
        self.table_wue_analyze_reset_button.setVisible(wue.can_reset)
        self.wue_analyze_status_label.setText(wue.status_text)
        self.wue_analyze_detail_text.setPlainText(wue.detail_text)

    def _on_wue_analyze_start_clicked(self) -> None:
        snapshot = self.presenter.start_wue_analyze()
        self._render_and_emit(snapshot)

    def _on_wue_analyze_stop_clicked(self) -> None:
        snapshot = self.presenter.stop_wue_analyze()
        self._render_and_emit(snapshot)
        wue_tab_index = self.workspace_details_tabs.indexOf(self.wue_analyze_group)
        if wue_tab_index >= 0:
            self.workspace_details_tabs.setCurrentIndex(wue_tab_index)

    def _on_wue_analyze_apply_clicked(self) -> None:
        snapshot = self.presenter.apply_wue_analyze_proposals()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_wue_analyze_reset_clicked(self) -> None:
        snapshot = self.presenter.reset_wue_analyze()
        self._render_and_emit(snapshot)

    def _render_scalar_sections(
        self,
        target_layout: QVBoxLayout,
        sections: tuple,
        written_names: frozenset | None = None,
    ) -> None:
        if written_names is None:
            written_names = frozenset()
        while target_layout.count():
            item = target_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for section in sections:
            group = QGroupBox(section.title)
            group.setProperty("parameterPanelGroup", True)
            form = QFormLayout(group)
            for note in section.notes:
                note_label = QLabel(note.lstrip("!"))
                note_label.setWordWrap(True)
                form.addRow(note_label)
            for field in section.fields:
                editor = self._field_editor(field)
                label_text = field.label
                if field.is_dirty:
                    label_text = f"{label_text} *"
                if field.name in written_names:
                    label_text = f"{label_text} [RAM]"
                if field.requires_power_cycle:
                    label_text = f"{label_text} (restart)"
                helper_parts = []
                if field.units:
                    helper_parts.append(field.units)
                if field.min_value is not None or field.max_value is not None:
                    helper_parts.append(
                        f"{field.min_value if field.min_value is not None else '-inf'} to "
                        f"{field.max_value if field.max_value is not None else 'inf'}"
                    )
                if field.help_text:
                    helper_parts.append(field.help_text)
                helper = QLabel(" | ".join(helper_parts))
                helper.setWordWrap(True)
                row_widget = QWidget()
                row_layout = QVBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.addWidget(editor)
                row_layout.addWidget(helper)
                form.addRow(label_text, row_widget)
            target_layout.addWidget(group)
        target_layout.addStretch(1)

    def _field_editor(self, field) -> QWidget:
        if field.options:
            combo = QComboBox()
            option_values = field.option_values or tuple(str(index) for index, _ in enumerate(field.options))
            for label, value in zip(field.options, option_values):
                if label and label.upper() == "INVALID":
                    continue
                combo.addItem(label, value)
            current_index = combo.findData(field.value_text)
            if current_index < 0:
                try:
                    current_index = combo.findData(str(int(float(field.value_text or "0"))))
                except ValueError:
                    current_index = -1
            combo.setCurrentIndex(max(0, current_index))
            combo.currentIndexChanged.connect(partial(self._on_scalar_combo_changed, field.name))
            return combo
        line_edit = QLineEdit(field.value_text)
        line_edit.editingFinished.connect(partial(self._on_scalar_field_edited, field.name, line_edit))
        return line_edit

    def _render_operator_context_panel(self, snapshot: ParameterPageSnapshot) -> None:
        """Show the operator engine context panel when the page has generator context."""
        ctx = self.presenter.operator_engine_context_service.get()
        if snapshot.generator_context is None:
            self.operator_context_group.hide()
            return
        self.operator_context_group.show()
        blocker_disp = QSignalBlocker(self.op_displacement_edit)
        blocker_comp = QSignalBlocker(self.op_compression_edit)
        blocker_cam  = QSignalBlocker(self.op_cam_duration_edit)
        blocker_intent = QSignalBlocker(self.op_intent_combo)
        self.op_displacement_edit.setText(
            str(ctx.displacement_cc) if ctx.displacement_cc is not None else ""
        )
        self.op_compression_edit.setText(
            str(ctx.compression_ratio) if ctx.compression_ratio is not None else ""
        )
        self.op_cam_duration_edit.setText(
            str(ctx.cam_duration_deg) if ctx.cam_duration_deg is not None else ""
        )
        intent_index = (
            1 if ctx.calibration_intent == CalibrationIntent.DRIVABLE_BASE else 0
        )
        self.op_intent_combo.setCurrentIndex(intent_index)
        del blocker_disp, blocker_comp, blocker_cam, blocker_intent

    def _render_req_fuel_panel(self, calc: RequiredFuelCalculatorSnapshot | None) -> None:
        """Show the required fuel calculator panel when the snapshot is present."""
        if calc is None:
            self.req_fuel_group.hide()
            return
        self.req_fuel_group.show()
        if calc.missing_inputs:
            inputs_text = "Missing: " + ", ".join(calc.missing_inputs)
        else:
            parts = []
            if calc.displacement_cc is not None:
                parts.append(f"Displacement: {calc.displacement_cc:.0f} cc")
            if calc.cylinder_count is not None:
                parts.append(f"Cylinders: {calc.cylinder_count}")
            if calc.injector_flow_ccmin is not None:
                parts.append(f"Injector: {calc.injector_flow_ccmin:.0f} cc/min")
            parts.append(f"Stoich AFR: {calc.target_afr:.1f}")
            inputs_text = "  |  ".join(parts)
        self.req_fuel_inputs_label.setText(inputs_text)
        if calc.result is not None and calc.result.is_valid:
            self.req_fuel_result_label.setText(
                f"reqFuel = {calc.result.req_fuel_ms:.2f} ms  "
                f"(stored: {calc.result.req_fuel_stored})"
            )
        else:
            self.req_fuel_result_label.setText("Result not available — provide missing inputs above.")
        self.req_fuel_apply_button.setEnabled(calc.can_apply)

    # -- Operator context event handlers --

    def _on_op_displacement_changed(self) -> None:
        text = self.op_displacement_edit.text().strip()
        try:
            value: float | None = float(text) if text else None
        except ValueError:
            return
        snap = self.presenter.update_operator_engine_context(displacement_cc=value)
        self._render_and_emit(snap)

    def _on_op_compression_changed(self) -> None:
        text = self.op_compression_edit.text().strip()
        try:
            value = float(text) if text else None
        except ValueError:
            return
        snap = self.presenter.update_operator_engine_context(compression_ratio=value)
        self._render_and_emit(snap)

    def _on_op_cam_duration_changed(self) -> None:
        text = self.op_cam_duration_edit.text().strip()
        try:
            value = float(text) if text else None
        except ValueError:
            return
        snap = self.presenter.update_operator_engine_context(cam_duration_deg=value)
        self._render_and_emit(snap)

    def _on_op_intent_changed(self, index: int) -> None:
        if self._updating_widgets:
            return
        intent = (
            CalibrationIntent.DRIVABLE_BASE if index == 1 else CalibrationIntent.FIRST_START
        )
        snap = self.presenter.update_operator_engine_context(calibration_intent=intent)
        self._render_and_emit(snap)

    # -- ReqFuel Apply handler --

    def _on_apply_req_fuel_clicked(self) -> None:
        snap = self.presenter.apply_req_fuel_result()
        self._render_and_emit(snap, notify_workspace=True)

    def _render_hardware_cards(self, cards: tuple[HardwareSetupCardSnapshot, ...]) -> None:
        while self.parameter_hardware_cards_layout.count():
            item = self.parameter_hardware_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not cards:
            self.parameter_hardware_cards_layout.addStretch(1)
            return
        for section_title, section_cards in self._group_hardware_cards(cards):
            section_header = QLabel(section_title)
            section_header.setProperty("hardwareSectionTitle", True)
            self.parameter_hardware_cards_layout.addWidget(section_header)
            section_row = QWidget()
            section_layout = QVBoxLayout(section_row)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(8)
            for card in section_cards:
                section_layout.addWidget(self._hardware_card_widget(card), 0)
            self.parameter_hardware_cards_layout.addWidget(section_row)
        self.parameter_hardware_cards_layout.addStretch(1)

    def _hardware_card_widget(self, card: HardwareSetupCardSnapshot) -> QWidget:
        card_frame = QFrame()
        card_frame.setProperty("hardwareCard", card.severity)
        card_frame.setMinimumHeight(92)
        card_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card_layout = QVBoxLayout(card_frame)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        title = QLabel(card.title)
        title.setProperty("hardwareCardTitle", True)
        card_layout.addWidget(title)

        summary = QLabel(card.summary)
        summary.setWordWrap(True)
        summary.setProperty("hardwareCardSummary", True)
        card_layout.addWidget(summary)

        for line in card.detail_lines:
            detail = QLabel(line)
            detail.setWordWrap(True)
            detail.setProperty("hardwareCardDetail", True)
            card_layout.addWidget(detail)
        if card.links:
            links_row = QWidget()
            links_layout = QHBoxLayout(links_row)
            links_layout.setContentsMargins(0, 4, 0, 0)
            links_layout.setSpacing(6)
            for label, page_id in card.links:
                button = QPushButton(label)
                button.setProperty("hardwareCardLink", True)
                button.clicked.connect(partial(self.open_page, page_id))
                links_layout.addWidget(button)
            links_layout.addStretch(1)
            card_layout.addWidget(links_row)
        return card_frame

    @staticmethod
    def _group_hardware_cards(
        cards: tuple[HardwareSetupCardSnapshot, ...]
    ) -> tuple[tuple[str, tuple[HardwareSetupCardSnapshot, ...]], ...]:
        groups: list[tuple[str, tuple[HardwareSetupCardSnapshot, ...]]] = []
        ordered_sections = (
            ("Configured Now", tuple(card for card in cards if card.key in {"injector", "ignition", "trigger", "sensor"})),
            ("Required Next Checks", tuple(card for card in cards if card.key.endswith("_checklist"))),
            ("Hidden Follow-Ups", tuple(card for card in cards if card.key.endswith("_gated_followups"))),
            ("Apply / Restart Implications", tuple(card for card in cards if card.key == "safety")),
        )
        for title, section_cards in ordered_sections:
            if section_cards:
                groups.append((title, section_cards))
        remaining = tuple(
            card for card in cards
            if card not in {section_card for _title, section_cards in ordered_sections for section_card in section_cards}
        )
        if remaining:
            groups.append(("Additional Guidance", remaining))
        return tuple(groups)

    def _clear_table_page(self, message: str) -> None:
        self.map_table_model.set_render_model(None)
        self._clear_table_highlights()
        self._display_to_model_row = []
        self._active_display_cell = None
        self.x_bins_table.clear()
        self.x_bins_table.setRowCount(1)
        self.x_bins_table.setColumnCount(0)
        self.x_bins_table.setVerticalHeaderLabels(["X Bins"])
        self.y_bins_table.clear()
        self.y_bins_table.setRowCount(0)
        self.y_bins_table.setColumnCount(1)
        self.y_bins_table.setHorizontalHeaderLabels(["Y Bins"])
        self.table_page_summary_label.clear()
        self.table_page_summary_label.hide()
        self.table_validation_summary_label.clear()
        self.table_validation_summary_label.hide()
        self.table_diff_summary_label.clear()
        self.table_diff_summary_label.hide()
        self.table_axis_summary_label.clear()
        self.table_axis_summary_label.hide()
        self._refresh_table_header_sections()
        self.table_page_details.setPlainText(message)
        self.table_page_details.show()
        self.table_diff_group.hide()
        self.table_diff_table.setRowCount(0)
        self.table_help_label.hide()
        self.table_power_cycle_warning.hide()
        self._set_table_footer_attached(False)
        self._render_table_aux_sections(())
        self.table_cell_status_label.setText("RPM: n/a | Load: n/a | Selected: n/a")

    def _render_table_aux_sections(self, sections: tuple) -> None:
        while self.table_aux_layout.count():
            item = self.table_aux_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if widget is self.table_footer_hint:
                    widget.setParent(None)
                else:
                    widget.deleteLater()
        self.table_aux_layout.addWidget(self.table_footer_hint)
        for section in sections:
            if section.title:
                title = QLabel(section.title)
                title.setProperty("tableFooterTitle", True)
                self.table_aux_layout.addWidget(title)
            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(3)
            for note in section.notes:
                note_label = QLabel(note.lstrip("!"))
                note_label.setWordWrap(True)
                note_label.setProperty("tableFooterNote", True)
                body_layout.addWidget(note_label)
            for field in section.fields:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)
                label_text = field.label
                if field.is_dirty:
                    label_text = f"{label_text} *"
                if field.requires_power_cycle:
                    label_text = f"{label_text} (restart)"
                label = QLabel(label_text)
                label.setMinimumWidth(168)
                row_layout.addWidget(label)
                editor = self._field_editor(field)
                row_layout.addWidget(editor, 1)
                body_layout.addWidget(row)
                helper_parts = []
                if field.units:
                    helper_parts.append(field.units)
                if field.help_text:
                    helper_parts.append(field.help_text)
                if helper_parts:
                    helper = QLabel(" | ".join(helper_parts))
                    helper.setWordWrap(True)
                    helper.setProperty("tableFooterNote", True)
                    body_layout.addWidget(helper)
            self.table_aux_layout.addWidget(body)
        footer_visible = bool(sections) or bool(self.table_footer_hint.text().strip())
        self.table_footer_panel.setVisible(footer_visible)
        self._set_table_footer_attached(footer_visible)

    def _set_table_footer_attached(self, attached: bool) -> None:
        self.table_grid_panel.setProperty("tableAttachedFooter", attached)
        self.table_footer_panel.setProperty("tableAttached", attached)
        self._refresh_style(self.table_grid_panel)
        self._refresh_style(self.table_footer_panel)

    def _refresh_table_header_sections(self) -> None:
        has_meta = any(
            not label.isHidden()
            for label in (
                self.table_page_summary_label,
                self.table_validation_summary_label,
                self.table_diff_summary_label,
                self.table_axis_summary_label,
            )
        )
        self.table_meta_summary_panel.setVisible(has_meta)

    def _bind_table_shortcut(self, key_sequence: str, handler) -> None:
        shortcut = QShortcut(key_sequence, self.map_table)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(handler)
        self._table_shortcuts.append(shortcut)

    def _map_row_count(self) -> int:
        return self.map_table_model.rowCount()

    def _map_column_count(self) -> int:
        return self.map_table_model.columnCount()

    def _selected_table_range(self) -> TableSelection | None:
        if self._command_table_selection is not None:
            return self._command_table_selection
        selected_indexes = self.map_table.selectedIndexes()
        if selected_indexes:
            top_row = min(index.row() for index in selected_indexes)
            bottom_row = max(index.row() for index in selected_indexes)
            left_column = min(index.column() for index in selected_indexes)
            right_column = max(index.column() for index in selected_indexes)
        else:
            current_index = self.map_table.currentIndex()
            if not current_index.isValid():
                return None
            top_row = bottom_row = current_index.row()
            left_column = right_column = current_index.column()
        if self._display_to_model_row:
            mapped_rows = [self._display_to_model_row[row] for row in range(top_row, bottom_row + 1)]
            top = min(mapped_rows)
            bottom = max(mapped_rows)
        else:
            top = top_row
            bottom = bottom_row
        return TableSelection(
            top=top,
            left=left_column,
            bottom=bottom,
            right=right_column,
        )

    def _on_navigator_selection_changed(self) -> None:
        if self._updating_widgets:
            return
        current_item = self.navigator_tree.currentItem()
        if current_item is None:
            return
        page_id = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(page_id, str):
            return
        t0 = self._table_debug_start("navigator_select_page", page_id=page_id)
        snapshot = self.presenter.select_page(page_id)
        self._table_debug_end(t0, "navigator_select_page", page_id=page_id)
        self._render_and_emit(snapshot, notify_workspace=True)
        self._schedule_ui_state_changed()

    def _on_revert_page_clicked(self) -> None:
        if self._updating_widgets:
            return
        snapshot = self.presenter.revert_active_page()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_map_cell_edited(self, display_row: int, column: int, raw_value: str) -> None:
        if self._updating_widgets:
            return
        selection = self._selected_table_range()
        if selection is not None and (selection.width > 1 or selection.height > 1):
            snapshot = self.presenter.fill_table_selection(selection, raw_value)
            self._render_and_emit(snapshot, notify_workspace=True)
            return
        row = self._display_to_model_row[display_row] if self._display_to_model_row else display_row
        snapshot = self.presenter.stage_table_cell(row, column, raw_value)
        self._render_after_single_table_edit(
            snapshot,
            display_row=display_row,
            column=column,
            notify_workspace=True,
        )

    def _on_map_current_index_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        started = self._table_debug_start(
            "map_current_index_changed",
            current_row=current.row(),
            current_column=current.column(),
            previous_row=previous.row(),
            previous_column=previous.column(),
        )
        del previous
        if self._updating_widgets:
            self._table_debug_end(started, "map_current_index_changed", skipped="updating_widgets")
            return
        self._command_table_selection = None
        if not current.isValid():
            self._active_display_cell = None
            self.table_cell_status_label.setText("RPM: n/a | Load: n/a | Selected: n/a")
            self._table_debug_end(started, "map_current_index_changed", valid=False)
            return
        self._active_display_cell = (current.row(), current.column())
        self._schedule_table_highlights()
        self._table_debug_end(started, "map_current_index_changed", valid=True)

    def _on_map_selection_changed(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        started = self._table_debug_start(
            "map_selection_changed",
            selected_count=len(selected.indexes()),
            deselected_count=len(deselected.indexes()),
        )
        del selected, deselected
        if self._updating_widgets:
            self._table_debug_end(started, "map_selection_changed", skipped="updating_widgets")
            return
        selected_indexes = self.map_table.selectedIndexes()
        if len(selected_indexes) <= 1:
            self._command_table_selection = None
        self._schedule_table_highlights()
        self._table_debug_end(started, "map_selection_changed", selected_indexes=len(selected_indexes))

    def _on_map_empty_area_clicked(self) -> None:
        if self._updating_widgets:
            return
        self._command_table_selection = None
        self._active_display_cell = None
        self._schedule_table_highlights()

    def _on_x_bin_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_widgets:
            return
        snapshot = self.presenter.stage_x_axis_cell(item.column(), item.text())
        self._render_after_single_table_edit(
            snapshot,
            axis="x",
            axis_index=item.column(),
            notify_workspace=True,
        )

    def _on_x_axis_cell_clicked(self, _row: int, column: int) -> None:
        if self._map_row_count() == 0 or column >= self._map_column_count():
            return
        current_index = self.map_table.currentIndex()
        current_row = self._active_display_cell[0] if self._active_display_cell is not None else current_index.row()
        target_row = current_row if current_row >= 0 else 0
        self.map_table.clearSelection()
        self.map_table.selectColumn(column)
        self.map_table.setCurrentIndex(self.map_table_model.index(target_row, column))
        self._active_display_cell = (target_row, column)
        model_rows = [self._display_to_model_row[row] for row in range(self._map_row_count())] if self._display_to_model_row else list(range(self._map_row_count()))
        self._command_table_selection = TableSelection(
            top=min(model_rows),
            left=column,
            bottom=max(model_rows),
            right=column,
        )
        self._apply_table_highlights()
        self._active_display_cell = (target_row, column)

    def _on_y_bin_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_widgets:
            return
        model_row = self._display_to_model_row[item.row()] if self._display_to_model_row else item.row()
        snapshot = self.presenter.stage_y_axis_cell(model_row, item.text())
        self._render_after_single_table_edit(
            snapshot,
            axis="y",
            axis_index=item.row(),
            notify_workspace=True,
        )

    def _on_y_axis_cell_clicked(self, row: int, _column: int) -> None:
        if self._map_column_count() == 0 or row >= self._map_row_count():
            return
        current_index = self.map_table.currentIndex()
        current_column = self._active_display_cell[1] if self._active_display_cell is not None else current_index.column()
        target_column = current_column if current_column >= 0 else 0
        self.map_table.clearSelection()
        self.map_table.selectRow(row)
        self.map_table.setCurrentIndex(self.map_table_model.index(row, target_column))
        self._active_display_cell = (row, target_column)
        model_row = self._display_to_model_row[row] if self._display_to_model_row else row
        self._command_table_selection = TableSelection(
            top=model_row,
            left=0,
            bottom=model_row,
            right=self._map_column_count() - 1,
        )
        self._apply_table_highlights()
        self._active_display_cell = (row, target_column)

    def _on_scalar_field_edited(self, name: str, widget: QLineEdit) -> None:
        if self._updating_widgets:
            return
        self.presenter.select_active_page_parameter(name)
        snapshot = self.presenter.stage_active_page_parameter(widget.text())
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_scalar_combo_changed(self, name: str, index: int) -> None:
        if self._updating_widgets:
            return
        combo = self.sender()
        value = str(index)
        if isinstance(combo, QComboBox):
            data = combo.itemData(index)
            if data is not None:
                value = str(data)
        self.presenter.select_active_page_parameter(name)
        snapshot = self.presenter.stage_active_page_parameter(value)
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_copy_table_clicked(self) -> None:
        selection = self._selected_table_range()
        if selection is None:
            return
        snapshot = self.presenter.copy_table_selection(selection)
        QApplication.clipboard().setText(self.presenter._clipboard_text)
        self._render_and_emit(snapshot)

    def _on_paste_table_clicked(self) -> None:
        selection = self._selected_table_range()
        if selection is None:
            return
        snapshot = self.presenter.paste_table_selection(selection, QApplication.clipboard().text())
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_fill_table_clicked(self) -> None:
        selection = self._selected_table_range()
        if selection is None:
            return
        current_index = self.map_table.currentIndex()
        if not current_index.isValid():
            return
        current_text = current_index.data(Qt.ItemDataRole.EditRole)
        snapshot = self.presenter.fill_table_selection(selection, str(current_text or ""))
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_fill_selection_from_active_cell(self) -> None:
        self._on_fill_table_clicked()

    def _begin_edit_current_table_cell(self) -> None:
        current_index = self.map_table.currentIndex()
        if not current_index.isValid():
            return
        self.map_table.edit(current_index)

    def _on_fill_down_table_clicked(self) -> None:
        selection = self._selected_table_range()
        if selection is None or selection.height <= 1:
            return
        snapshot = self.presenter.fill_down_table_selection(selection)
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_fill_right_table_clicked(self) -> None:
        selection = self._selected_table_range()
        if selection is None or selection.width <= 1:
            return
        snapshot = self.presenter.fill_right_table_selection(selection)
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_interpolate_table_clicked(self) -> None:
        selection = self._selected_table_range()
        if selection is None:
            return
        snapshot = self.presenter.interpolate_table_selection(selection)
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_smooth_table_clicked(self) -> None:
        selection = self._selected_table_range()
        if selection is None:
            return
        snapshot = self.presenter.smooth_table_selection(selection)
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_undo_table_clicked(self) -> None:
        snapshot = self.presenter.undo_active_table()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_redo_table_clicked(self) -> None:
        snapshot = self.presenter.redo_active_table()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_undo_parameter_clicked(self) -> None:
        snapshot = self.presenter.undo_active_page_parameter()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_redo_parameter_clicked(self) -> None:
        snapshot = self.presenter.redo_active_page_parameter()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_curve_undo_clicked(self) -> None:
        if self._curve_snapshot is None:
            return
        for param_name in self._curve_snapshot.y_param_names:
            if self.presenter.local_tune_edit_service.can_undo(param_name):
                snapshot = self.presenter.undo_curve_param(param_name)
                self._render_and_emit(snapshot, notify_workspace=True)
                return

    def _on_curve_redo_clicked(self) -> None:
        if self._curve_snapshot is None:
            return
        for param_name in self._curve_snapshot.y_param_names:
            if self.presenter.local_tune_edit_service.can_redo(param_name):
                snapshot = self.presenter.redo_curve_param(param_name)
                self._render_and_emit(snapshot, notify_workspace=True)
                return

    def _on_curve_cell_changed(self, row: int, column: int) -> None:
        if self._updating_widgets or column == 0:
            return
        snapshot = self._curve_snapshot
        if snapshot is None:
            return
        param_index = column - 1
        if param_index >= len(snapshot.y_param_names):
            return
        param_name = snapshot.y_param_names[param_index]
        item = self.curve_table.item(row, column)
        if item is None:
            return
        value = item.text()
        self._updating_widgets = True
        try:
            new_snapshot = self.presenter.stage_curve_cell(param_name, row, value)
            self._render_and_emit(new_snapshot, notify_workspace=True)
        finally:
            self._updating_widgets = False

    def _on_select_active_row(self) -> None:
        current_index = self.map_table.currentIndex()
        if not current_index.isValid():
            return
        self.map_table.selectRow(current_index.row())
        self.map_table.setCurrentIndex(current_index)
        model_row = self._display_to_model_row[current_index.row()] if self._display_to_model_row else current_index.row()
        self._command_table_selection = TableSelection(
            top=model_row,
            left=0,
            bottom=model_row,
            right=self._map_column_count() - 1,
        )
        self._apply_table_highlights()

    def _on_select_active_column(self) -> None:
        current_index = self.map_table.currentIndex()
        if not current_index.isValid():
            return
        self.map_table.selectColumn(current_index.column())
        self.map_table.setCurrentIndex(current_index)
        model_rows = [self._display_to_model_row[row] for row in range(self._map_row_count())] if self._display_to_model_row else list(range(self._map_row_count()))
        self._command_table_selection = TableSelection(
            top=min(model_rows),
            left=current_index.column(),
            bottom=max(model_rows),
            right=current_index.column(),
        )
        self._apply_table_highlights()

    def _on_select_all_table(self) -> None:
        if self._map_row_count() == 0 or self._map_column_count() == 0:
            return
        self.map_table.clearSelection()
        self.map_table.selectAll()
        if self._active_display_cell is None:
            self._active_display_cell = (0, 0)
        self.map_table.setCurrentIndex(self.map_table_model.index(*self._active_display_cell))
        model_rows = [self._display_to_model_row[row] for row in range(self._map_row_count())] if self._display_to_model_row else list(range(self._map_row_count()))
        self._command_table_selection = TableSelection(
            top=min(model_rows),
            left=0,
            bottom=max(model_rows),
            right=self._map_column_count() - 1,
        )
        self._apply_table_highlights()

    def _on_write_page_clicked(self) -> None:
        snapshot = self.presenter.write_active_page()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_burn_page_clicked(self) -> None:
        snapshot = self.presenter.burn_active_page()
        self._render_and_emit(snapshot, notify_workspace=True)

    def _on_power_cycle_clicked(self) -> None:
        self.power_cycle_requested.emit()

    def _on_catalog_query_changed(self, query: str) -> None:
        if self._updating_widgets:
            return
        snapshot = self.presenter.set_catalog_query(query)
        self._render_and_emit(snapshot)
        self._schedule_ui_state_changed()

    def _on_catalog_kind_changed(self, kind: str) -> None:
        if self._updating_widgets:
            return
        snapshot = self.presenter.set_catalog_kind(kind)
        self._render_and_emit(snapshot)
        self._schedule_ui_state_changed()

    def _on_catalog_selection_changed(self) -> None:
        if self._updating_widgets:
            return
        selected_rows = self.catalog_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        name_item = self.catalog_table.item(selected_rows[0].row(), 0)
        if name_item is None:
            return
        snapshot = self.presenter.select_catalog_entry(name_item.text())
        self._render_and_emit(snapshot, notify_workspace=True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rebalance_splitter(self._last_active_page_kind)
        self._fit_active_editor()

    @staticmethod
    def _state_text(kind: str, detail: str | None) -> str:
        base = f"Page State: {kind}"
        if detail and kind == "invalid":
            return f"{base} ({detail})"
        return base

    def _apply_table_highlights(self) -> None:
        started = self._table_debug_start("apply_table_highlights")
        self._table_highlight_refresh_pending = False
        if self._active_display_cell is not None:
            current_row, current_column = self._active_display_cell
        else:
            current_index = self.map_table.currentIndex()
            current_row = current_index.row()
            current_column = current_index.column()
        if current_row < 0 or current_column < 0:
            self.table_cell_status_label.setText("RPM: n/a | Load: n/a | Selected: n/a")
            return
        current_index = self.map_table.model().index(current_row, current_column)
        if not current_index.isValid():
            self.table_cell_status_label.setText("RPM: n/a | Load: n/a | Selected: n/a")
            return
        current_text = current_index.data() if current_index.isValid() else ""
        if current_text is None:
            current_text = ""

        selected_indexes = {
            (index.row(), index.column())
            for index in self.map_table.selectedIndexes()
        }
        selected_rows = {row for row, _column in selected_indexes}
        selected_columns = {column for _row, column in selected_indexes}
        self._update_table_highlight_cache(selected_indexes, selected_rows, selected_columns, current_row, current_column)
        self.table_cell_status_label.setText(
            self._table_status_text(current_row, current_column, current_text, selected_indexes)
        )
        self._table_debug_end(
            started,
            "apply_table_highlights",
            current_row=current_row,
            current_column=current_column,
            selected=len(selected_indexes),
        )

    def _schedule_table_highlights(self) -> None:
        if self._table_highlight_refresh_pending:
            return
        self._table_highlight_refresh_pending = True
        QTimer.singleShot(0, self._apply_table_highlights)

    def _schedule_ui_state_changed(self) -> None:
        if self._updating_widgets or self._ui_state_emit_pending:
            return
        self._ui_state_emit_pending = True
        QTimer.singleShot(0, self._emit_ui_state_changed)

    def _emit_ui_state_changed(self) -> None:
        self._ui_state_emit_pending = False
        if not self._updating_widgets:
            self.ui_state_changed.emit()

    def _clear_table_highlights(self) -> None:
        x_blocker = QSignalBlocker(self.x_bins_table)
        y_blocker = QSignalBlocker(self.y_bins_table)
        for column in list(self._highlighted_x_axis_columns):
            item = self.x_bins_table.item(0, column)
            if item is not None:
                self._restore_axis_item(item)
        for row in list(self._highlighted_y_axis_rows):
            item = self.y_bins_table.item(row, 0)
            if item is not None:
                self._restore_axis_item(item)
        del x_blocker
        del y_blocker
        self._highlighted_x_axis_columns.clear()
        self._highlighted_y_axis_rows.clear()

    def _update_table_highlight_cache(
        self,
        selected_indexes: set[tuple[int, int]],
        selected_rows: set[int],
        selected_columns: set[int],
        current_row: int,
        current_column: int,
    ) -> None:
        new_x_columns = set(selected_columns)
        new_x_columns.add(current_column)
        new_y_rows = set(selected_rows)
        new_y_rows.add(current_row)

        x_blocker = QSignalBlocker(self.x_bins_table)
        y_blocker = QSignalBlocker(self.y_bins_table)

        for column in list(self._highlighted_x_axis_columns):
            item = self.x_bins_table.item(0, column)
            if item is not None:
                self._restore_axis_item(item)
        for row in list(self._highlighted_y_axis_rows):
            item = self.y_bins_table.item(row, 0)
            if item is not None:
                self._restore_axis_item(item)

        for column in selected_columns:
            axis_item = self.x_bins_table.item(0, column)
            if axis_item is not None:
                self._apply_axis_highlight(axis_item, active=False)
        for row in selected_rows:
            axis_item = self.y_bins_table.item(row, 0)
            if axis_item is not None:
                self._apply_axis_highlight(axis_item, active=False)
        current_x = self.x_bins_table.item(0, current_column)
        if current_x is not None:
            self._apply_axis_highlight(current_x, active=True)
        current_y = self.y_bins_table.item(current_row, 0)
        if current_y is not None:
            self._apply_axis_highlight(current_y, active=True)

        del x_blocker
        del y_blocker

        self._highlighted_x_axis_columns = new_x_columns
        self._highlighted_y_axis_rows = new_y_rows

    def _reset_table_colors(self) -> None:
        for row in range(self._map_row_count()):
            for column in range(self._map_column_count()):
                index = self.map_table_model.index(row, column)
                self.map_table_model.dataChanged.emit(
                    index,
                    index,
                    [Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole, Qt.ItemDataRole.FontRole],
                )

    def _restore_table_item(self, item: QTableWidgetItem) -> None:
        try:
            background_hex = item.data(Qt.ItemDataRole.UserRole)
            foreground_hex = item.data(Qt.ItemDataRole.UserRole + 1)
            if isinstance(background_hex, str):
                item.setBackground(QColor(background_hex))
            if isinstance(foreground_hex, str):
                item.setForeground(QColor(foreground_hex))
            font = item.font()
            font.setBold(False)
            item.setFont(font)
        except RuntimeError:
            return

    @staticmethod
    def _restore_axis_item(item: QTableWidgetItem) -> None:
        try:
            item.setBackground(QColor("#2f3540"))
            item.setForeground(QColor("#e5e7eb"))
            font = item.font()
            font.setBold(False)
            item.setFont(font)
        except RuntimeError:
            return

    def _highlight_axis_cells(self, row: int, column: int) -> None:
        x_item = self.x_bins_table.item(0, column)
        y_item = self.y_bins_table.item(row, 0)
        for axis_item in (x_item, y_item):
            if axis_item is None:
                continue
            self._apply_axis_highlight(axis_item, active=True)

    @staticmethod
    def _apply_axis_highlight(item: QTableWidgetItem, active: bool) -> None:
        try:
            item.setBackground(QColor("#705d1f") if active else QColor("#3a4350"))
            item.setForeground(QColor("#f3f4f6"))
            font = item.font()
            font.setBold(active)
            item.setFont(font)
        except RuntimeError:
            return

    @staticmethod
    def _apply_highlight(item: QTableWidgetItem, overlay: QColor, factor: float, bold: bool) -> None:
        try:
            base = item.background().color()
            blended = QColor(
                round(base.red() + ((overlay.red() - base.red()) * factor)),
                round(base.green() + ((overlay.green() - base.green()) * factor)),
                round(base.blue() + ((overlay.blue() - base.blue()) * factor)),
            )
            item.setBackground(blended)
            foreground = QColor("#ffffff") if ((blended.red() * 0.299) + (blended.green() * 0.587) + (blended.blue() * 0.114)) < 120 else QColor("#000000")
            item.setForeground(foreground)
            font = item.font()
            font.setBold(bold)
            item.setFont(font)
        except RuntimeError:
            return

    @staticmethod
    def _has_table_validation_details(summary: str) -> bool:
        return summary.strip() != "No validation issues."

    def _should_show_table_details(self, snapshot: TablePageSnapshot) -> bool:
        if snapshot.state.kind.value == "invalid":
            return True
        if self._has_table_validation_details(snapshot.validation_summary):
            return True
        return bool(snapshot.message)

    def _table_status_text(
        self,
        current_row: int,
        current_column: int,
        current_text: str,
        selected_indexes: set[tuple[int, int]],
    ) -> str:
        rpm = self.x_bins_table.item(0, current_column).text() if self.x_bins_table.item(0, current_column) else "n/a"
        load = self.y_bins_table.item(current_row, 0).text() if self.y_bins_table.item(current_row, 0) else "n/a"
        if len(selected_indexes) <= 1:
            return f"RPM: {rpm} | Load: {load} | Selected: {current_text}"
        rows = sorted({row for row, _column in selected_indexes})
        columns = sorted({column for _row, column in selected_indexes})
        rpm_start = self.x_bins_table.item(0, columns[0]).text() if self.x_bins_table.item(0, columns[0]) else "n/a"
        rpm_end = self.x_bins_table.item(0, columns[-1]).text() if self.x_bins_table.item(0, columns[-1]) else rpm_start
        load_start = self.y_bins_table.item(rows[0], 0).text() if self.y_bins_table.item(rows[0], 0) else "n/a"
        load_end = self.y_bins_table.item(rows[-1], 0).text() if self.y_bins_table.item(rows[-1], 0) else load_start
        return (
            f"RPM: {rpm_start} -> {rpm_end} | "
            f"Load: {load_start} -> {load_end} | "
            f"Selected: {len(selected_indexes)} cells"
        )

    def _rebalance_splitter(self, active_page_kind: str) -> None:
        total_width = max(self.main_splitter.width(), self.width(), 1)
        if active_page_kind == "table":
            navigator = max(220, min(280, round(total_width * 0.16)))
            catalog = max(240, min(300, round(total_width * 0.16)))
        elif active_page_kind == "curve":
            navigator = max(190, min(240, round(total_width * 0.16)))
            catalog = max(220, min(290, round(total_width * 0.18)))
        elif active_page_kind == "parameter-list":
            navigator = max(190, min(240, round(total_width * 0.18)))
            catalog = max(220, min(290, round(total_width * 0.20)))
        else:
            navigator = max(190, min(240, round(total_width * 0.18)))
            catalog = max(220, min(290, round(total_width * 0.20)))
        editor = max(420, total_width - navigator - catalog)
        self.main_splitter.setSizes([navigator, editor, catalog])

    def _fit_active_editor(self) -> None:
        if self.editor_stack.currentWidget() == self.table_page_widget:
            self._fit_table_layout()

    def _fit_table_layout(self) -> None:
        started = self._table_debug_start("fit_table_layout", rows=self._map_row_count(), columns=self._map_column_count())
        self._fit_table_column_widths()
        self._fit_y_axis_width()
        self._sync_x_bin_widths()
        self._scale_table_font()
        map_header_height = self.map_table.horizontalHeader().height()
        map_body_height = sum(self.map_table.rowHeight(row) for row in range(self._map_row_count()))
        map_frame = self.map_table.frameWidth() * 2
        self.map_table.setFixedHeight(map_header_height + map_body_height + map_frame + 2)

        y_header_height = self.y_bins_table.horizontalHeader().height()
        y_body_height = sum(self.y_bins_table.rowHeight(row) for row in range(self.y_bins_table.rowCount()))
        y_frame = self.y_bins_table.frameWidth() * 2
        self.y_bins_table.setFixedHeight(y_header_height + y_body_height + y_frame + 2)

        x_header_height = self.x_bins_table.horizontalHeader().height()
        x_row_height = self.x_bins_table.rowHeight(0) if self.x_bins_table.rowCount() else 24
        x_frame = self.x_bins_table.frameWidth() * 2
        if self.x_bins_table.horizontalHeader().isHidden():
            x_header_height = 0
        self.x_bins_table.setFixedHeight(x_header_height + x_row_height + x_frame + 2)
        self.axis_corner.setFixedHeight(self.x_bins_table.height())
        self.x_bins_table.verticalHeader().setFixedWidth(self.map_table.verticalHeader().width())
        self.axis_corner.setFixedWidth(self.y_bins_table.width())

        grid_height = max(self.map_table.height(), self.y_bins_table.height()) + self.x_bins_table.height()
        self.table_grid.setFixedHeight(grid_height)
        self.table_grid_panel.setFixedHeight(grid_height)

        if self._map_column_count():
            content_width = sum(self.map_table.columnWidth(column) for column in range(self._map_column_count()))
            frame_width = self.map_table.frameWidth() * 2
            header_width = self.map_table.verticalHeader().width()
            map_width = content_width + frame_width + header_width + 2
            x_width = content_width + frame_width + self.x_bins_table.verticalHeader().width() + 2
            grid_width = self.y_bins_table.width() + 1 + map_width
            self.map_table.setFixedWidth(map_width)
            self.x_bins_table.setFixedWidth(x_width)
            self.table_grid.setFixedWidth(grid_width)
            self.table_footer_panel.setFixedWidth(grid_width)
        self._table_debug_end(started, "fit_table_layout", rows=self._map_row_count(), columns=self._map_column_count())

    def _table_debug_start(self, event: str, **fields) -> float | None:
        if not self._table_debug_enabled:
            return None
        started = time.perf_counter()
        self._table_debug_log(f"{event}:start", **fields)
        return started

    def _table_debug_end(self, started: float | None, event: str, **fields) -> None:
        if not self._table_debug_enabled or started is None:
            return
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._table_debug_log(f"{event}:end", elapsed_ms=f"{elapsed_ms:.2f}", **fields)

    def _table_debug_log(self, event: str, **fields) -> None:
        if not self._table_debug_enabled:
            return
        field_text = " ".join(f"{key}={value}" for key, value in fields.items())
        emit_table_debug_log(f"[TUNER_TABLE_DEBUG] {event} {field_text}".rstrip())

    def _scale_table_font(self) -> None:
        cols = self._map_column_count()
        app = QApplication.instance()
        default_pt = app.font().pointSize() if app else 9
        if default_pt <= 0:
            default_pt = 9
        if cols > 12:
            pt = max(7, default_pt - 2)
        elif cols > 8:
            pt = max(8, default_pt - 1)
        else:
            pt = default_pt
        font = self.map_table.font()
        if font.pointSize() != pt:
            font.setPointSize(pt)
            self.map_table.setFont(font)
            self.x_bins_table.setFont(font)
            self.y_bins_table.setFont(font)

    def _fit_y_axis_width(self) -> None:
        metrics = self.y_bins_table.fontMetrics()
        width = 148
        header_item = self.y_bins_table.horizontalHeaderItem(0)
        if header_item is not None:
            width = max(width, metrics.horizontalAdvance(header_item.text()) + 32)
        for row in range(self.y_bins_table.rowCount()):
            item = self.y_bins_table.item(row, 0)
            if item is not None:
                width = max(width, metrics.horizontalAdvance(item.text()) + 28)
        width = min(196, width)
        self.y_bins_table.setFixedWidth(width)
        self.axis_corner.setFixedWidth(width)

    def _fit_table_column_widths(self) -> None:
        columns = self._map_column_count()
        if columns <= 0:
            return
        viewport_width = max(self.editor_stack.width() - self.y_bins_table.width() - 80, 320)
        target = compute_table_cell_width(viewport_width, columns)
        for column in range(columns):
            self.map_table.setColumnWidth(column, target)

    def _sync_x_bin_widths(self) -> None:
        if self.x_bins_table.columnCount() != self._map_column_count():
            return
        for column in range(self._map_column_count()):
            self.x_bins_table.setColumnWidth(column, self.map_table.columnWidth(column))

    def _on_map_header_resized(self, logical_index: int, old_size: int, new_size: int) -> None:
        del old_size
        if logical_index < self.x_bins_table.columnCount():
            self.x_bins_table.setColumnWidth(logical_index, new_size)

    @staticmethod
    def _table_item(value: str, editable: bool) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    @staticmethod
    def _render_diff_table(
        table: QTableWidget,
        group: QGroupBox,
        entries: tuple,
    ) -> None:
        if not entries:
            group.hide()
            table.setRowCount(0)
            return
        table.setRowCount(len(entries))
        for row_index, entry in enumerate(entries):
            for col_index, text in enumerate((entry.name, entry.before_preview, entry.after_preview)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row_index, col_index, item)
        row_h = 22 * len(entries) + table.horizontalHeader().height() + 8
        table.setMaximumHeight(min(160, max(60, row_h)))
        group.show()

    @staticmethod
    def _range_tooltip(range_: tuple | None, help_text: str | None) -> str:
        parts = []
        if range_ is not None:
            parts.append(f"Range: {range_[0]} – {range_[1]}")
        if help_text:
            parts.append(help_text)
        return "\n".join(parts)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QFrame {
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
            QLabel[emptyState="true"] {
                background: palette(base);
                border: 1px dashed palette(mid);
                border-radius: 16px;
                padding: 36px;
                font-size: 18px;
                color: palette(text);
            }
            QFrame[tableShell="header"] {
                background: #2f3136;
                border: 1px solid #666b73;
                border-radius: 10px;
            }
            QFrame[tableShell="grid"] {
                background: #2b2b2b;
                border: 1px solid #767676;
                border-radius: 10px;
            }
            QFrame[tableShell="grid"][tableAttachedFooter="true"] {
                border-bottom-left-radius: 0;
                border-bottom-right-radius: 0;
            }
            QFrame[tableShell="footer"] {
                background: #2f3136;
                border: 1px solid #666b73;
                border-top: 0;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
                border-top-left-radius: 0;
                border-top-right-radius: 0;
            }
            QFrame[tableShell="footer"][tableAttached="false"] {
                border-top: 1px solid #666b73;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QFrame[tableToolbar="true"] {
                background: #35383d;
                border: 1px solid #6b7280;
                border-radius: 8px;
            }
            QFrame[catalogPanel="true"] {
                background: #26292e;
                border: 1px solid #585f69;
                border-radius: 10px;
            }
            QFrame[navigatorPanel="true"] {
                background: #26292e;
                border: 1px solid #585f69;
                border-radius: 10px;
            }
            QLabel[navigatorCaption="true"] {
                color: #9aa6b2;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                padding: 0 2px;
            }
            QFrame[workspaceDetailsPanel="true"] {
                background: #26292e;
                border: 1px solid #585f69;
                border-radius: 10px;
            }
            QLabel[workspaceDetailsCaption="true"] {
                color: #9aa6b2;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                padding: 0 2px;
            }
            QLabel[catalogTitle="true"] {
                color: #c9d2dd;
                font-size: 13px;
                font-weight: 600;
                padding: 0 2px;
            }
            QLineEdit[catalogFilter="true"],
            QComboBox[catalogFilter="true"] {
                background: #31353b;
                border: 1px solid #585f69;
                border-radius: 7px;
                padding: 4px 6px;
                color: #e5e7eb;
            }
            QTableWidget[catalogTable="true"] {
                background: #24272c;
                alternate-background-color: #2b2f35;
            }
            QTextEdit[catalogDetails="true"] {
                background: #202328;
                border: 1px solid #505761;
                border-radius: 8px;
                color: #cbd5e1;
                padding: 4px 6px;
            }
            QTreeWidget[navigatorTree="true"] {
                background: #24272c;
                alternate-background-color: #2b2f35;
                border: 1px solid #505761;
                border-radius: 8px;
                color: #d7dde6;
                padding: 2px;
                outline: none;
            }
            QTreeWidget[navigatorTree="true"]::item {
                padding: 3px 4px;
                border-radius: 4px;
            }
            QTreeWidget[navigatorTree="true"]::item:selected {
                background: #1a2d42;
                color: #d7e8f7;
            }
            QTreeWidget[navigatorTree="true"]::branch {
                background: transparent;
            }
            QFrame[workspaceDetailsPanel="true"] QTabWidget::pane {
                border: 1px solid #505761;
                border-radius: 8px;
                top: -1px;
                background: #202328;
            }
            QFrame[workspaceDetailsPanel="true"] QTabBar::tab {
                background: #31353b;
                border: 1px solid #585f69;
                border-bottom: none;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                padding: 5px 10px;
                margin-right: 3px;
                color: #cbd5e1;
            }
            QFrame[workspaceDetailsPanel="true"] QTabBar::tab:selected {
                background: #202328;
                color: #f3f4f6;
            }
            QFrame[workspaceDetailsPanel="true"] QTabBar::tab:hover:!selected {
                background: #3a3f47;
            }
            QTableWidget {
                background: #2b2b2b;
                alternate-background-color: #31353b;
                color: #e5e7eb;
                gridline-color: #6b7280;
                selection-background-color: #4b7bd1;
                selection-color: #f8fafc;
            }
            QTableWidget QTableCornerButton::section {
                background: #2f3540;
                border: 1px solid #6b7280;
            }
            QHeaderView::section {
                background: #343841;
                color: #e5e7eb;
                border: 1px solid #6b7280;
                padding: 3px 4px;
            }
            QTableWidget::item {
                padding: 0px;
            }
            QLabel[tablePageTitle="true"] {
                font-size: 16px;
                font-weight: 700;
                padding: 0 2px;
                color: #f3f4f6;
            }
            QLabel[tableMeta="summary"] {
                color: #cbd5e1;
                font-weight: 600;
                padding: 0 2px;
            }
            QLabel[tableMeta="validation"] {
                color: #f0c674;
                padding: 0 2px;
            }
            QLabel[tableMeta="diff"] {
                color: #7fb3ff;
                padding: 0 2px;
            }
            QLabel[tableMeta="axis"] {
                color: #a7b0bb;
                padding: 0 2px;
            }
            QLabel[tableState="true"] {
                font-weight: 600;
                padding: 0 2px;
                color: #f3f4f6;
            }
            QLabel[tableStatus="true"] {
                color: #cbd5e1;
                padding: 0 2px;
            }
            QPushButton {
                min-height: 24px;
                padding: 2px 8px;
            }
            QFrame[tableToolbar="true"] QPushButton[tableActionRole="secondary"] {
                background: #3a3f47;
                border: 1px solid #606874;
                border-radius: 7px;
                color: #d5dae3;
                padding: 2px 7px;
            }
            QFrame[tableToolbar="true"] QPushButton[tableActionRole="primary"] {
                background: #1a2d42;
                border: 1px solid #40617f;
                border-radius: 7px;
                color: #d7e8f7;
                font-weight: 600;
                padding: 2px 8px;
            }
            QFrame[tableToolbar="true"] QPushButton[tableActionRole="warning"] {
                background: #3a2616;
                border: 1px solid #8a5a35;
                border-radius: 7px;
                color: #f6d6b8;
                font-weight: 600;
                padding: 2px 8px;
            }
            QFrame[tableToolbar="true"] QPushButton[tableActionRole="secondary"]:disabled,
            QFrame[tableToolbar="true"] QPushButton[tableActionRole="primary"]:disabled,
            QFrame[tableToolbar="true"] QPushButton[tableActionRole="warning"]:disabled {
                color: #7f8793;
                border-color: #555b65;
            }
            QLabel[tableFooterTitle="true"] {
                padding: 0 2px;
                font-weight: 600;
                color: #f3f4f6;
            }
            QLabel[tableFooterNote="true"] {
                padding: 0 2px;
                color: #a7b0bb;
            }
            QGroupBox[parameterPanelGroup="true"] {
                background: #26292e;
                border: 1px solid #585f69;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 8px;
                color: #d7dde6;
            }
            QGroupBox[parameterPanelGroup="true"]::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #c9d2dd;
                background: transparent;
            }
            QGroupBox[parameterPanelGroup="true"] QLabel {
                color: #cbd5e1;
            }
            QGroupBox[parameterPanelGroup="true"] QLineEdit,
            QGroupBox[parameterPanelGroup="true"] QComboBox,
            QGroupBox[parameterPanelGroup="true"] QTextEdit,
            QGroupBox[parameterPanelGroup="true"] QSpinBox {
                background: #202328;
                border: 1px solid #505761;
                border-radius: 7px;
                color: #e5e7eb;
                padding: 4px 6px;
            }
            QFrame[hardwareCard="info"] {
                background: #22313d;
                border: 1px solid #496273;
                border-radius: 10px;
            }
            QFrame[hardwareCard="warning"] {
                background: #3a2616;
                border: 1px solid #8a5a35;
                border-radius: 10px;
            }
            QLabel[hardwareCardTitle="true"] {
                font-weight: 700;
                color: #edf3f9;
            }
            QLabel[hardwareSectionTitle="true"] {
                font-weight: 700;
                color: #dbe4ec;
                padding: 4px 2px 0 2px;
            }
            QLabel[hardwareCardSummary="true"] {
                color: #d7dde6;
                font-weight: 600;
            }
            QLabel[hardwareCardDetail="true"] {
                color: #b6c0cb;
            }
            QPushButton[hardwareCardLink="true"] {
                background: #31353b;
                border: 1px solid #585f69;
                border-radius: 7px;
                color: #d7dde6;
                padding: 4px 8px;
            }
            """
        )

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
