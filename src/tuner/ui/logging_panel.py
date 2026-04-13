from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from tuner.domain.datalog_profile import DatalogChannelEntry, DatalogProfile
from tuner.domain.ecu_definition import ScalarParameterDefinition
from tuner.services.datalog_profile_service import DatalogProfileService

_POLL_INTERVALS: list[tuple[str, int]] = [
    ("250 ms", 250),
    ("500 ms", 500),
    ("1 s", 1000),
    ("2 s", 2000),
    ("5 s", 5000),
]
_DEFAULT_POLL_MS = 500

_PANEL_STYLES = """
    QFrame[loggingPanel="true"] {
        background: #26292e;
        border: 1px solid #585f69;
        border-radius: 10px;
    }
    QLabel[panelTitle="true"] {
        color: #c9d2dd;
        font-size: 13px;
        font-weight: 600;
        padding: 0 2px;
    }
    QLabel[panelNote="true"] {
        color: #9aa3ad;
        padding: 0 2px;
    }
    QFrame[loggingPanel="true"] QLineEdit,
    QFrame[loggingPanel="true"] QComboBox,
    QFrame[loggingPanel="true"] QSpinBox {
        background: #202328;
        border: 1px solid #505761;
        border-radius: 7px;
        color: #e5e7eb;
        padding: 4px 6px;
    }
    QFrame[loggingPanel="true"] QPushButton[role="primary"] {
        background: #1a2d42;
        border: 1px solid #40617f;
        border-radius: 8px;
        color: #d7e8f7;
        font-weight: 600;
        padding: 6px 10px;
    }
    QFrame[loggingPanel="true"] QPushButton[role="secondary"] {
        background: #31353b;
        border: 1px solid #585f69;
        border-radius: 8px;
        color: #d7dde6;
        padding: 6px 10px;
    }
    QFrame[loggingPanel="true"] QPushButton[role="danger"] {
        background: #3a1616;
        border: 1px solid #7f4040;
        border-radius: 8px;
        color: #f7d7d7;
        padding: 6px 10px;
    }
    QFrame[loggingPanel="true"] QTextEdit[surfaceLog="true"] {
        background: #202328;
        border: 1px solid #505761;
        border-radius: 8px;
        color: #d7dde6;
    }
    QFrame[loggingPanel="true"] QCheckBox {
        color: #d7dde6;
    }
    QGroupBox {
        color: #c9d2dd;
        font-weight: 600;
        border: 1px solid #505761;
        border-radius: 8px;
        margin-top: 10px;
        padding-top: 8px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }
"""


# ---------------------------------------------------------------------------
# Profile editor dialog
# ---------------------------------------------------------------------------

class _DatalogProfileEditorDialog(QDialog):
    """Edit a logging profile: name, channel enable/disable."""

    def __init__(
        self,
        profile: DatalogProfile,
        all_channel_defs: list[ScalarParameterDefinition],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Logging Profile")
        self.setMinimumSize(560, 440)
        self._name = profile.name
        self._channels: list[DatalogChannelEntry] = [
            DatalogChannelEntry(
                name=ch.name,
                label=ch.label,
                units=ch.units,
                enabled=ch.enabled,
                format_digits=ch.format_digits,
            )
            for ch in profile.channels
        ]
        existing_names = {ch.name for ch in self._channels}
        for defn in all_channel_defs:
            if defn.name not in existing_names:
                self._channels.append(DatalogChannelEntry(
                    name=defn.name,
                    label=defn.label or defn.name,
                    units=defn.units,
                    enabled=False,
                    format_digits=defn.digits if hasattr(defn, "digits") else None,
                ))
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Profile Name:"))
        self._name_edit = QLineEdit(self._name)
        name_row.addWidget(self._name_edit, 1)
        root.addLayout(name_row)

        bulk_row = QHBoxLayout()
        enable_all = QPushButton("Enable All")
        enable_all.clicked.connect(self._enable_all)
        bulk_row.addWidget(enable_all)
        disable_all = QPushButton("Disable All")
        disable_all.clicked.connect(self._disable_all)
        bulk_row.addWidget(disable_all)
        bulk_row.addStretch(1)
        self._count_label = QLabel()
        bulk_row.addWidget(self._count_label)
        root.addLayout(bulk_row)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", "Channel", "Label", "Units"])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, hh.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, hh.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, hh.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, hh.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, 1)

        self._populate_table()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _populate_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._channels))
        for row, ch in enumerate(self._channels):
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Checked if ch.enabled else Qt.CheckState.Unchecked)
            self._table.setItem(row, 0, chk)
            self._table.setItem(row, 1, QTableWidgetItem(ch.name))
            self._table.setItem(row, 2, QTableWidgetItem(ch.label or ""))
            self._table.setItem(row, 3, QTableWidgetItem(ch.units or ""))
        self._table.blockSignals(False)
        self._refresh_count()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            row = item.row()
            if 0 <= row < len(self._channels):
                self._channels[row].enabled = item.checkState() == Qt.CheckState.Checked
                self._refresh_count()

    def _enable_all(self) -> None:
        for ch in self._channels:
            ch.enabled = True
        self._populate_table()

    def _disable_all(self) -> None:
        for ch in self._channels:
            ch.enabled = False
        self._populate_table()

    def _refresh_count(self) -> None:
        n = sum(1 for ch in self._channels if ch.enabled)
        self._count_label.setText(f"{n} / {len(self._channels)} enabled")

    def result_profile(self) -> DatalogProfile:
        name = self._name_edit.text().strip() or self._name
        return DatalogProfile(name=name, channels=list(self._channels))


# ---------------------------------------------------------------------------
# Main logging panel
# ---------------------------------------------------------------------------

class LoggingPanel(QWidget):
    """Dedicated logging surface: profile management, live capture, and datalog replay."""

    # Upward signals (MainWindow connects these)
    capture_start_requested = Signal(object, int, object)   # DatalogProfile, poll_ms, Path|None
    capture_stop_requested = Signal()
    capture_clear_requested = Signal()
    capture_save_requested = Signal()
    poll_interval_changed = Signal(int)                     # ms
    browse_datalog_requested = Signal()
    load_datalog_requested = Signal(str)                    # path
    select_replay_row_requested = Signal(int)               # 1-based
    use_replay_row_requested = Signal()

    def __init__(
        self,
        profile_service: DatalogProfileService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._profile_service = profile_service or DatalogProfileService()
        self._profiles: list[DatalogProfile] = [DatalogProfile(name="Default")]
        self._active_idx: int = 0
        self._project_path: Path | None = None
        self._channel_defs: list[ScalarParameterDefinition] = []
        self._plot_widget = None
        self._build()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(10)

        panel = QFrame()
        panel.setProperty("loggingPanel", True)
        panel.setStyleSheet(_PANEL_STYLES)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(12)

        title = QLabel("Graphing & Logging")
        title.setProperty("panelTitle", True)
        panel_layout.addWidget(title)

        panel_layout.addWidget(self._build_profile_group())
        panel_layout.addWidget(self._build_capture_group())
        panel_layout.addWidget(self._build_replay_group())
        panel_layout.addStretch(1)

        inner_layout.addWidget(panel, 1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

    def _build_profile_group(self) -> QGroupBox:
        group = QGroupBox("Logging Profile")
        form = QFormLayout(group)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        profile_row = QHBoxLayout()
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(160)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_combo_changed)
        profile_row.addWidget(self._profile_combo, 1)

        self._add_profile_btn = QPushButton("+")
        self._add_profile_btn.setProperty("role", "secondary")
        self._add_profile_btn.setToolTip("New profile")
        self._add_profile_btn.setFixedWidth(30)
        self._add_profile_btn.clicked.connect(self._on_add_profile)
        profile_row.addWidget(self._add_profile_btn)

        self._del_profile_btn = QPushButton("−")
        self._del_profile_btn.setProperty("role", "danger")
        self._del_profile_btn.setToolTip("Delete profile")
        self._del_profile_btn.setFixedWidth(30)
        self._del_profile_btn.clicked.connect(self._on_delete_profile)
        profile_row.addWidget(self._del_profile_btn)

        self._edit_profile_btn = QPushButton("Edit Profile…")
        self._edit_profile_btn.setProperty("role", "secondary")
        self._edit_profile_btn.clicked.connect(self._on_edit_profile)
        profile_row.addWidget(self._edit_profile_btn)
        form.addRow("Profile", profile_row)

        self._profile_channel_label = QLabel("")
        self._profile_channel_label.setProperty("panelNote", True)
        form.addRow("", self._profile_channel_label)

        self._refresh_profile_combo()
        return group

    def _build_capture_group(self) -> QGroupBox:
        group = QGroupBox("Live Capture")
        form = QFormLayout(group)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        # Polling interval
        self._interval_combo = QComboBox()
        for label, ms in _POLL_INTERVALS:
            self._interval_combo.addItem(label, ms)
        # Default to 500 ms
        default_idx = next(
            (i for i, (_, ms) in enumerate(_POLL_INTERVALS) if ms == _DEFAULT_POLL_MS), 1
        )
        self._interval_combo.setCurrentIndex(default_idx)
        self._interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        form.addRow("Poll Interval", self._interval_combo)

        # Capture-to-file
        file_row = QHBoxLayout()
        self._capture_to_file_check = QCheckBox("Capture to file")
        self._capture_to_file_check.toggled.connect(self._on_capture_to_file_toggled)
        file_row.addWidget(self._capture_to_file_check)
        self._capture_path_edit = QLineEdit()
        self._capture_path_edit.setPlaceholderText("Output path…")
        self._capture_path_edit.setEnabled(False)
        file_row.addWidget(self._capture_path_edit, 1)
        self._browse_capture_path_btn = QPushButton("Browse…")
        self._browse_capture_path_btn.setProperty("role", "secondary")
        self._browse_capture_path_btn.setEnabled(False)
        self._browse_capture_path_btn.clicked.connect(self._on_browse_capture_path)
        file_row.addWidget(self._browse_capture_path_btn)
        form.addRow("", file_row)

        # Capture buttons
        btns = QHBoxLayout()
        self._start_btn = QPushButton("Start Log")
        self._start_btn.setProperty("role", "primary")
        self._start_btn.clicked.connect(self._on_start)
        btns.addWidget(self._start_btn)
        self._stop_btn = QPushButton("Stop Log")
        self._stop_btn.setProperty("role", "secondary")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.capture_stop_requested)
        btns.addWidget(self._stop_btn)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setProperty("role", "secondary")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._on_clear)
        btns.addWidget(self._clear_btn)
        self._save_btn = QPushButton("Save Log…")
        self._save_btn.setProperty("role", "secondary")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self.capture_save_requested)
        btns.addWidget(self._save_btn)
        btns.addStretch(1)
        form.addRow("", btns)

        # Status
        self._status_label = QLabel("Ready")
        self._status_label.setProperty("panelNote", True)
        self._status_label.setWordWrap(True)
        form.addRow("Status", self._status_label)

        self._warning_label = QLabel("")
        self._warning_label.setProperty("panelNote", True)
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(False)
        form.addRow("", self._warning_label)

        return group

    def _build_replay_group(self) -> QGroupBox:
        group = QGroupBox("Datalog Import & Replay")
        form = QFormLayout(group)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._datalog_path_edit = QLineEdit()
        self._datalog_path_edit.setPlaceholderText("CSV file path…")
        form.addRow("CSV Path", self._datalog_path_edit)

        replay_btns = QHBoxLayout()
        self._browse_datalog_btn = QPushButton("Browse CSV")
        self._browse_datalog_btn.setProperty("role", "secondary")
        self._browse_datalog_btn.clicked.connect(self._on_browse_datalog)
        replay_btns.addWidget(self._browse_datalog_btn)
        self._load_datalog_btn = QPushButton("Load Datalog")
        self._load_datalog_btn.setProperty("role", "secondary")
        self._load_datalog_btn.clicked.connect(self._on_load_datalog)
        replay_btns.addWidget(self._load_datalog_btn)
        self._use_replay_btn = QPushButton("Use Replay Row")
        self._use_replay_btn.setProperty("role", "secondary")
        self._use_replay_btn.clicked.connect(self.use_replay_row_requested)
        replay_btns.addWidget(self._use_replay_btn)
        replay_btns.addStretch(1)
        form.addRow("", replay_btns)

        self._row_spin = QSpinBox()
        self._row_spin.setRange(1, 1)
        self._row_spin.setEnabled(False)
        self._row_spin.valueChanged.connect(self._on_row_spin_changed)
        form.addRow("Replay Row", self._row_spin)

        self._datalog_summary_label = QLabel(
            "Import a runtime datalog CSV to review one row at a time "
            "and pin it into workspace evidence review."
        )
        self._datalog_summary_label.setWordWrap(True)
        self._datalog_summary_label.setProperty("panelNote", True)
        form.addRow("", self._datalog_summary_label)

        self._datalog_preview = QTextEdit()
        self._datalog_preview.setReadOnly(True)
        self._datalog_preview.setProperty("surfaceLog", True)
        self._datalog_preview.setMaximumHeight(120)
        self._datalog_preview.setPlainText("Preview: no datalog loaded.")
        form.addRow("", self._datalog_preview)

        self._chart_label = QLabel("Chart review: no datalog loaded.")
        self._chart_label.setWordWrap(True)
        self._chart_label.setProperty("panelNote", True)
        form.addRow("", self._chart_label)

        try:
            import pyqtgraph as pg
            self._plot_widget = pg.PlotWidget()
            self._plot_widget.setBackground("#202328")
            self._plot_widget.showGrid(x=True, y=True, alpha=0.18)
            self._plot_widget.setMinimumHeight(180)
            self._plot_widget.addLegend(offset=(8, 8))
            form.addRow("", self._plot_widget)
        except Exception:
            self._plot_widget = None

        return group

    # ------------------------------------------------------------------
    # Public API — called by MainWindow
    # ------------------------------------------------------------------

    def get_active_profile(self) -> DatalogProfile:
        if 0 <= self._active_idx < len(self._profiles):
            return self._profiles[self._active_idx]
        return DatalogProfile(name="Default")

    def get_poll_interval_ms(self) -> int:
        return self._interval_combo.currentData() or _DEFAULT_POLL_MS

    def set_project(self, project) -> None:  # noqa: ANN001
        """Called on project open/close — loads profile collection from sidecar."""
        if project is None or project.project_path is None:
            self._project_path = None
            return
        self._project_path = project.project_path
        sidecar = self._project_path.with_suffix(".logging-profile.json")
        if sidecar.exists():
            try:
                profiles, active_name = self._profile_service.load_collection(sidecar)
                if self._channel_defs:
                    for p in profiles:
                        self._profile_service.apply_definition_metadata(p, self._channel_defs)
                self._profiles = profiles
                self._active_idx = next(
                    (i for i, p in enumerate(profiles) if p.name == active_name), 0
                )
                self._refresh_profile_combo()
            except Exception:
                pass  # Corrupt sidecar — keep defaults

    def set_channel_defs(self, defs: list[ScalarParameterDefinition]) -> None:
        """Called when a definition is loaded — back-fills metadata on existing profiles."""
        self._channel_defs = list(defs)
        for profile in self._profiles:
            if not profile.channels:
                # Bare default profile — replace with definition-aware default
                new = self._profile_service.default_profile(defs)
                profile.name = profile.name  # keep name
                profile.channels.extend(new.channels)
            else:
                self._profile_service.apply_definition_metadata(profile, defs)
        self._refresh_profile_channel_label()

    def update_capture_status(self, status_text: str) -> None:
        self._status_label.setText(status_text)

    def set_recording(self, recording: bool) -> None:
        self._start_btn.setEnabled(not recording)
        self._stop_btn.setEnabled(recording)

    def set_capture_has_data(self, has_data: bool) -> None:
        self._clear_btn.setEnabled(has_data)
        self._save_btn.setEnabled(has_data)

    def set_capture_channel_warning(self, text: str) -> None:
        if text:
            self._warning_label.setText(text)
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)

    # Datalog replay update methods
    def set_datalog_path(self, path: str) -> None:
        self._datalog_path_edit.setText(path)

    @property
    def datalog_path(self) -> str:
        return self._datalog_path_edit.text().strip()

    def update_datalog_loaded(
        self,
        row_count: int,
        summary_text: str,
        preview_text: str,
    ) -> None:
        self._row_spin.blockSignals(True)
        self._row_spin.setRange(1, row_count)
        self._row_spin.setValue(1)
        self._row_spin.blockSignals(False)
        self._row_spin.setEnabled(True)
        self._datalog_summary_label.setText(summary_text)
        self._datalog_preview.setPlainText(preview_text)

    def update_datalog_row(
        self,
        summary_text: str,
        preview_text: str,
        chart_text: str,
    ) -> None:
        self._datalog_summary_label.setText(summary_text)
        self._datalog_preview.setPlainText(preview_text)
        self._chart_label.setText(chart_text)

    def clear_datalog(self) -> None:
        self._row_spin.blockSignals(True)
        self._row_spin.setRange(1, 1)
        self._row_spin.setValue(1)
        self._row_spin.blockSignals(False)
        self._row_spin.setEnabled(False)
        self._datalog_summary_label.setText(
            "Import a runtime datalog CSV to review one row at a time "
            "and pin it into workspace evidence review."
        )
        self._datalog_preview.setPlainText("Preview: no datalog loaded.")
        self._chart_label.setText("Chart review: no datalog loaded.")
        self._clear_plot()

    def render_review(self, review) -> None:  # noqa: ANN001
        """Render a datalog review (with traces) into the chart widget."""
        if self._plot_widget is None:
            return
        import pyqtgraph as pg
        self._plot_widget.clear()
        if review is None:
            return
        colors = ("#4fc3f7", "#ffb74d", "#81c784")
        for index, trace in enumerate(review.traces):
            self._plot_widget.plot(
                list(trace.x_values),
                list(trace.y_values),
                name=getattr(trace, "name", f"ch{index}"),
                pen=pg.mkPen(color=colors[index % len(colors)], width=1.5),
            )
        marker = pg.InfiniteLine(
            pos=review.marker_x, angle=90, pen=pg.mkPen(color="#f6d6b8", width=1)
        )
        self._plot_widget.addItem(marker)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_profile_combo_changed(self, index: int) -> None:
        if 0 <= index < len(self._profiles):
            self._active_idx = index
            self._refresh_profile_channel_label()
            self._save_collection()

    def _on_add_profile(self) -> None:
        base_name = "New Profile"
        existing = {p.name for p in self._profiles}
        name = base_name
        counter = 2
        while name in existing:
            name = f"{base_name} {counter}"
            counter += 1
        new_profile = self._profile_service.default_profile(self._channel_defs)
        new_profile = DatalogProfile(name=name, channels=new_profile.channels)
        self._profiles.append(new_profile)
        self._active_idx = len(self._profiles) - 1
        self._refresh_profile_combo()
        self._save_collection()
        # Open editor immediately so user can name it
        self._on_edit_profile()

    def _on_delete_profile(self) -> None:
        if len(self._profiles) <= 1:
            return
        self._profiles.pop(self._active_idx)
        self._active_idx = max(0, self._active_idx - 1)
        self._refresh_profile_combo()
        self._save_collection()

    def _on_edit_profile(self) -> None:
        if not (0 <= self._active_idx < len(self._profiles)):
            return
        dlg = _DatalogProfileEditorDialog(
            profile=self._profiles[self._active_idx],
            all_channel_defs=self._channel_defs,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.result_profile()
            self._profiles[self._active_idx] = updated
            self._refresh_profile_combo()
            self._refresh_profile_channel_label()
            self._save_collection()

    def _on_interval_changed(self, _index: int) -> None:
        self.poll_interval_changed.emit(self.get_poll_interval_ms())

    def _on_capture_to_file_toggled(self, checked: bool) -> None:
        self._capture_path_edit.setEnabled(checked)
        self._browse_capture_path_btn.setEnabled(checked)

    def _on_browse_capture_path(self) -> None:
        start = self._capture_path_edit.text().strip() or ""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Capture Log To File",
            start,
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if path:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            self._capture_path_edit.setText(path)

    def _on_start(self) -> None:
        profile = self.get_active_profile()
        poll_ms = self.get_poll_interval_ms()
        output_path: Path | None = None
        if self._capture_to_file_check.isChecked():
            raw = self._capture_path_edit.text().strip()
            if raw:
                output_path = Path(raw)
        self.capture_start_requested.emit(profile, poll_ms, output_path)

    def _on_clear(self) -> None:
        self.capture_clear_requested.emit()
        self.set_capture_has_data(False)
        self._status_label.setText("Ready")
        self._warning_label.setVisible(False)

    def _on_browse_datalog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Datalog CSV",
            self._datalog_path_edit.text(),
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if path:
            self._datalog_path_edit.setText(path)
            self.load_datalog_requested.emit(path)
        else:
            self.browse_datalog_requested.emit()

    def _on_load_datalog(self) -> None:
        path = self._datalog_path_edit.text().strip()
        self.load_datalog_requested.emit(path)

    def _on_row_spin_changed(self, value: int) -> None:
        self.select_replay_row_requested.emit(value)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_profile_combo(self) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for p in self._profiles:
            self._profile_combo.addItem(p.name)
        self._profile_combo.setCurrentIndex(self._active_idx)
        self._del_profile_btn.setEnabled(len(self._profiles) > 1)
        self._profile_combo.blockSignals(False)
        self._refresh_profile_channel_label()

    def _refresh_profile_channel_label(self) -> None:
        profile = self.get_active_profile()
        enabled = sum(1 for ch in profile.channels if ch.enabled)
        total = len(profile.channels)
        if total > 0:
            self._profile_channel_label.setText(f"{enabled} / {total} channels enabled")
        else:
            self._profile_channel_label.setText("No channels — edit profile to add channels")

    def _save_collection(self) -> None:
        if self._project_path is None:
            return
        sidecar = self._project_path.with_suffix(".logging-profile.json")
        active_name = self.get_active_profile().name
        try:
            self._profile_service.save_collection(sidecar, self._profiles, active_name)
        except Exception:
            pass

    def _clear_plot(self) -> None:
        if self._plot_widget is not None:
            self._plot_widget.clear()
