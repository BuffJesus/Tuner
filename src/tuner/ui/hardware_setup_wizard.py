"""Hardware Setup Wizard — step-by-step guided configuration dialog.

Presents six focused tabs covering the most critical Speeduino parameters:
    1. Board & Controller  — pinLayout, stroke
    2. Engine Config       — nCylinders, nInjectors, injLayout, twoStroke,
                             calibration intent, idle RPM target generation
    3. Induction           — topology (NA/turbo/SC/twin-charge), boost target,
                             intercooler, VE table generation
    4. Injectors           — injOpen, reqFuel, stoich; plus guided reqFuel
                             calculator and base fuel table generators
                             (AFR targets, WUE, cranking enrichment, ASE)
    5. Trigger / Decoder   — TrigPattern, numTeeth, missingTeeth, sparkMode,
                             dwellcrank, dwellrun, spark table generation
    6. Sensors             — egoType, stoich

Each field change is immediately staged or saved in the operator engine context
via ``presenter.stage_named_parameter`` / ``presenter.update_operator_engine_context``.
This widget is thin; all business logic lives in services.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from tuner.domain.generator_context import ForcedInductionTopology, SuperchargerType
from tuner.domain.operator_engine_context import CalibrationIntent
from tuner.domain.setup_checklist import ChecklistItemStatus, SetupChecklistItem
from tuner.services.hardware_preset_service import (
    HardwarePresetService,
    IgnitionHardwarePreset,
    InjectorHardwarePreset,
    PressureSensorPreset,
    TurboHardwarePreset,
    WidebandHardwarePreset,
)
from tuner.services.pressure_sensor_calibration_service import PressureSensorCalibrationService
from tuner.services.required_fuel_calculator_service import RequiredFuelCalculatorService
from tuner.services.speeduino_runtime_telemetry_service import SpeeduinoRuntimeTelemetryService

if TYPE_CHECKING:
    from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOTE_TEXT_COLOR = "#b6c0cb"

def _scroll_wrap(widget: QWidget) -> QScrollArea:
    """Wrap *widget* in a scroll area so long tab contents stay accessible."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(widget)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    return scroll


def _note(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lbl.setStyleSheet(f"color: {_NOTE_TEXT_COLOR};")
    return lbl


def _warn(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lbl.setStyleSheet("color: #c0392b; font-weight: bold;")
    return lbl


def _reboot_note() -> QLabel:
    return _warn(
        "Changes to this field require a power cycle of the ECU to take effect."
    )


def _set_form_row_visible(form: QFormLayout, field: QWidget, visible: bool) -> None:
    """Show or hide an entire ``QFormLayout`` row for *field*."""
    form.setRowVisible(field, visible)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class HardwareSetupWizard(QDialog):
    """Step-by-step hardware setup wizard.

    Open with::

        wizard = HardwareSetupWizard(presenter, parent=self)
        wizard.show()

    The wizard stages changes immediately; the user can review them in the
    workspace diff and Write to RAM / Burn to Flash as normal.
    """

    status_message = Signal(str)
    workspace_state_changed = Signal()

    def __init__(
        self,
        presenter: TuningWorkspacePresenter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hardware Setup Wizard")
        self.resize(600, 560)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint
        )
        self._presenter = presenter
        self._hardware_preset_service = HardwarePresetService()
        self._speeduino_runtime_telemetry_service = SpeeduinoRuntimeTelemetryService()
        self._updating = False
        self._pending_parameter_values: dict[str, str] = {}
        self._pending_array_values: dict[str, list[float]] = {}
        self._pending_context_updates: dict[str, object] = {}

        # Build all step tabs
        self._tabs = QTabWidget()
        self._build_board_tab()
        self._build_engine_tab()
        self._build_induction_tab()
        self._build_injector_tab()
        self._build_trigger_tab()
        self._build_sensor_tab()

        # Bottom close button
        btn_box = QDialogButtonBox()
        self._apply_button = btn_box.addButton("Apply", QDialogButtonBox.ButtonRole.ApplyRole)
        self._apply_button.clicked.connect(self._apply_pending_changes)
        self._close_button = btn_box.addButton(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.accept)

        outer = QVBoxLayout(self)
        outer.addWidget(self._tabs)
        outer.addWidget(btn_box)

        # Populate from current tune values
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read current tune values and repopulate all widgets."""
        self._updating = True
        try:
            self._refresh_board_tab()
            self._refresh_engine_tab()
            self._refresh_induction_tab()
            self._refresh_injector_tab()
            self._refresh_trigger_tab()
            self._refresh_sensor_tab()
            self._update_apply_button_state()
        finally:
            self._updating = False

    def _has_pending_changes(self) -> bool:
        return bool(self._pending_parameter_values or self._pending_array_values or self._pending_context_updates)

    def _update_apply_button_state(self) -> None:
        self._apply_button.setEnabled(self._has_pending_changes())

    def _effective_operator_context(self):
        base = self._presenter.operator_engine_context_service.get()
        if not self._pending_context_updates:
            return base
        return replace(base, **self._pending_context_updates)

    def _queue_context_update(self, **updates: object) -> None:
        base = self._presenter.operator_engine_context_service.get()
        changed = False
        for name, value in updates.items():
            if getattr(base, name) == value:
                if name in self._pending_context_updates:
                    del self._pending_context_updates[name]
                    changed = True
                continue
            if self._pending_context_updates.get(name) != value:
                self._pending_context_updates[name] = value
                changed = True
        if changed:
            self._update_apply_button_state()

    def _apply_pending_changes(self) -> None:
        if not self._has_pending_changes():
            return
        context_updates = dict(self._pending_context_updates)
        parameter_updates = dict(self._pending_parameter_values)
        array_updates = {name: list(values) for name, values in self._pending_array_values.items()}
        if context_updates:
            self._presenter.update_operator_engine_context(**context_updates)
        for name, value in parameter_updates.items():
            self._presenter.stage_named_parameter(name, value)
        for name, values in array_updates.items():
            self._presenter.stage_named_array(name, values)
        self._pending_context_updates.clear()
        self._pending_parameter_values.clear()
        self._pending_array_values.clear()
        msg = self._presenter.consume_message() or "Hardware setup changes applied."
        self.status_message.emit(msg)
        self.refresh()
        self.workspace_state_changed.emit()

    def _raw_values_equal(self, left: str | None, right: str | None) -> bool:
        if left == right:
            return True
        if left is None or right is None:
            return False
        try:
            return float(left) == float(right)
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Tab 1: Board & Controller
    # ------------------------------------------------------------------

    def _build_board_tab(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(_note(
            "Select the hardware board that matches your physical controller. "
            "This determines which pins are available for fuel, ignition, and sensor outputs."
        ))
        layout.addWidget(_reboot_note())

        grp = QGroupBox("Board Layout")
        form = QFormLayout(grp)

        self._pinlayout_combo = QComboBox()
        self._pinlayout_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self._pinlayout_combo.currentIndexChanged.connect(
            lambda idx: self._stage_combo("pinLayout", self._pinlayout_combo, idx)
        )
        form.addRow("Board / Layout:", self._pinlayout_combo)

        layout.addWidget(grp)

        self._board_capability_note = _note(
            "Connected board capability data will appear here when a live Speeduino session is available."
        )
        layout.addWidget(self._board_capability_note)

        stroke_grp = QGroupBox("Engine Cycle")
        stroke_form = QFormLayout(stroke_grp)
        self._stroke_combo = QComboBox()
        self._stroke_combo.addItem("Four-stroke", "0")
        self._stroke_combo.addItem("Two-stroke", "1")
        self._stroke_combo.setToolTip(
            "Most car engines are four-stroke. Two-stroke is rare and changes "
            "fuel/ignition timing significantly."
        )
        self._stroke_combo.currentIndexChanged.connect(
            lambda idx: self._stage_combo("twoStroke", self._stroke_combo, idx)
        )
        stroke_form.addRow("Stroke type:", self._stroke_combo)
        layout.addWidget(stroke_grp)

        layout.addStretch(1)
        self._tabs.addTab(_scroll_wrap(container), "Board")

    def _refresh_board_tab(self) -> None:
        # Populate pinLayout options from definition
        from PySide6.QtCore import QSignalBlocker
        blocker = QSignalBlocker(self._pinlayout_combo)
        self._pinlayout_combo.clear()
        param = self._get_definition_scalar("pinLayout")
        if param and param.options:
            for opt in param.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._pinlayout_combo.addItem(opt.label, opt.value)
        if self._pinlayout_combo.count() == 0:
            self._pinlayout_combo.addItem("(no board options — reload tune)")
        del blocker

        raw = self._get_tune_str("pinLayout")
        if raw is not None:
            idx = self._find_combo_by_value(self._pinlayout_combo, raw)
            if idx >= 0:
                self._pinlayout_combo.setCurrentIndex(idx)

        raw_stroke = self._get_tune_str("twoStroke")
        if raw_stroke is not None:
            idx = self._find_combo_by_value(self._stroke_combo, raw_stroke)
            if idx >= 0:
                from PySide6.QtCore import QSignalBlocker as SB
                b2 = SB(self._stroke_combo)
                self._stroke_combo.setCurrentIndex(idx)
                del b2

        self._refresh_board_capability_note()

    def _refresh_board_capability_note(self) -> None:
        snapshot = self._presenter.current_runtime_snapshot
        if snapshot is None:
            self._board_capability_note.setText(
                "Connected board capability data will appear here when a live Speeduino session is available."
            )
            return
        telemetry = self._speeduino_runtime_telemetry_service.decode(snapshot)
        caps = telemetry.board_capabilities
        if caps.raw_value is None:
            self._board_capability_note.setText(
                "The current runtime stream does not expose Speeduino board capability channels."
            )
            return

        lines = [telemetry.capability_summary_text]
        lines.append(telemetry.persistence_summary_text)
        if caps.native_can:
            lines.append("Native CAN hardware is available on the connected board.")
        if caps.wifi_transport:
            lines.append("An onboard Wi-Fi transport coprocessor is advertised by the connected board.")
        if caps.unrestricted_interrupts:
            lines.append("Trigger and sensor input placement is less constrained because unrestricted interrupts are advertised.")
        else:
            lines.append("Use interrupt-capable input pins for trigger hardware; this board does not advertise unrestricted interrupts.")
        self._board_capability_note.setText(" ".join(lines))

    # ------------------------------------------------------------------
    # Tab 2: Engine Config
    # ------------------------------------------------------------------

    def _build_engine_tab(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(_note(
            "Configure the basic engine geometry. These settings are used by "
            "Speeduino to calculate pulse widths and ignition timing."
        ))

        grp = QGroupBox("Engine Geometry")
        form = QFormLayout(grp)

        self._ncylinders_spin = QSpinBox()
        self._ncylinders_spin.setRange(1, 8)
        self._ncylinders_spin.setToolTip(
            "Number of cylinders. Affects injector and ignition channel assignment."
        )
        self._ncylinders_spin.valueChanged.connect(self._on_ncylinders_changed)
        form.addRow("Cylinders:", self._ncylinders_spin)

        self._displacement_edit = QDoubleSpinBox()
        self._displacement_edit.setRange(0.0, 20000.0)
        self._displacement_edit.setSingleStep(50.0)
        self._displacement_edit.setDecimals(0)
        self._displacement_edit.setSuffix(" cc")
        self._displacement_edit.setSpecialValueText("not set")
        self._displacement_edit.setToolTip(
            "Operator-supplied engine displacement used by the reqFuel calculator "
            "and starter-table generators. This is stored in the project sidecar, not the ECU."
        )
        self._displacement_edit.valueChanged.connect(self._on_displacement_changed)
        form.addRow("Displacement:", self._displacement_edit)

        self._compression_edit = QDoubleSpinBox()
        self._compression_edit.setRange(0.0, 25.0)
        self._compression_edit.setSingleStep(0.1)
        self._compression_edit.setDecimals(1)
        self._compression_edit.setSpecialValueText("not set")
        self._compression_edit.setToolTip(
            "Static compression ratio for guided spark and VE baseline generation."
        )
        self._compression_edit.valueChanged.connect(self._on_compression_changed)
        form.addRow("Compression ratio:", self._compression_edit)

        self._engine_advanced_check = QCheckBox("Show Advanced Inputs")
        self._engine_advanced_check.setToolTip(
            "Reveal Tier 2 setup facts that can improve generator quality without slowing the default first-start workflow."
        )
        self._engine_advanced_check.toggled.connect(self._refresh_engine_advanced_visibility)
        form.addRow("", self._engine_advanced_check)

        self._cam_duration_spin = QDoubleSpinBox()
        self._cam_duration_spin.setRange(0.0, 400.0)
        self._cam_duration_spin.setSingleStep(1.0)
        self._cam_duration_spin.setDecimals(0)
        self._cam_duration_spin.setSuffix(" deg")
        self._cam_duration_spin.setSpecialValueText("not set")
        self._cam_duration_spin.setToolTip(
            "Approximate cam duration used to bias conservative idle and airflow assumptions."
        )
        self._cam_duration_spin.valueChanged.connect(self._on_cam_duration_changed)
        form.addRow("Cam duration:", self._cam_duration_spin)

        self._head_flow_combo = QComboBox()
        self._head_flow_combo.addItem("Not set", None)
        self._head_flow_combo.addItem("Stock / OEM", "stock_oem")
        self._head_flow_combo.addItem("Mild ported", "mild_ported")
        self._head_flow_combo.addItem("Race ported / high flow", "race_ported")
        self._head_flow_combo.currentIndexChanged.connect(self._on_head_flow_class_changed)
        form.addRow("Head flow class:", self._head_flow_combo)

        self._manifold_style_combo = QComboBox()
        self._manifold_style_combo.addItem("Not set", None)
        self._manifold_style_combo.addItem("Long runner plenum", "long_runner_plenum")
        self._manifold_style_combo.addItem("Short runner plenum", "short_runner_plenum")
        self._manifold_style_combo.addItem("ITB / individual runners", "itb")
        self._manifold_style_combo.addItem("Log / compact manifold", "log_compact")
        self._manifold_style_combo.currentIndexChanged.connect(self._on_manifold_style_changed)
        form.addRow("Manifold style:", self._manifold_style_combo)

        self._ninjectors_spin = QSpinBox()
        self._ninjectors_spin.setRange(1, 8)
        self._ninjectors_spin.setToolTip("Number of primary injectors.")
        self._ninjectors_spin.valueChanged.connect(
            lambda v: self._stage_bits_enum_spin("nInjectors", v)
        )
        form.addRow("Injectors:", self._ninjectors_spin)

        self._injlayout_combo = QComboBox()
        self._injlayout_combo.setToolTip(
            "Paired: 2 injectors per output channel (most common for 4-cyl).\n"
            "Semi-Sequential: mirrored channels, 4-cyl only.\n"
            "Sequential: 1 injector per output — needs cam sync."
        )
        self._injlayout_combo.currentIndexChanged.connect(self._on_injlayout_changed)
        form.addRow("Injector layout:", self._injlayout_combo)

        self._intent_combo = QComboBox()
        self._intent_combo.addItem("First Start", CalibrationIntent.FIRST_START)
        self._intent_combo.addItem("Drivable Base", CalibrationIntent.DRIVABLE_BASE)
        self._intent_combo.setToolTip(
            "First Start stays maximally conservative. Drivable Base allows a slightly more usable starter tune."
        )
        self._intent_combo.currentIndexChanged.connect(self._on_calibration_intent_changed)
        form.addRow("Calibration intent:", self._intent_combo)
        self._engine_form = form

        layout.addWidget(grp)

        load_grp = QGroupBox("Load Source")
        load_form = QFormLayout(load_grp)

        self._algorithm_combo = QComboBox()
        self._algorithm_combo.setToolTip(
            "Selects whether the fuel and ignition tables use MAP, TPS, or combined load.\n"
            "MAP: standard speed-density (most common for turbo/NA).\n"
            "TPS: alpha-N (common for carb-replacement or ITBs).\n"
            "IMAP/EMAP: combined MAP and exhaust MAP (rare)."
        )
        self._algorithm_combo.currentIndexChanged.connect(
            lambda idx: self._stage_combo("algorithm", self._algorithm_combo, idx)
        )
        load_form.addRow("Load algorithm:", self._algorithm_combo)

        self._boost_enabled_combo = QComboBox()
        self._boost_enabled_combo.setToolTip(
            "Enables the Speeduino boost controller.\n"
            "When On, the boost control tables and outputs become active.\n"
            "Set to Off for naturally-aspirated engines."
        )
        self._boost_enabled_combo.currentIndexChanged.connect(
            lambda idx: self._stage_combo("boostEnabled", self._boost_enabled_combo, idx)
        )
        load_form.addRow("Boost control:", self._boost_enabled_combo)

        layout.addWidget(load_grp)

        # Idle RPM target generator
        idle_grp = QGroupBox("Idle RPM Targets")
        idle_layout = QVBoxLayout(idle_grp)
        idle_layout.setContentsMargins(8, 8, 8, 8)
        idle_layout.setSpacing(6)
        idle_layout.addWidget(_note(
            "Generates a conservative CLT-based idle RPM curve (10 bins) from the "
            "current engine and calibration-intent context. Staged as a reviewable edit."
        ))
        self._idle_status_label = QLabel("")
        self._idle_status_label.setWordWrap(True)
        self._idle_status_label.setVisible(False)
        idle_btn_row = QHBoxLayout()
        idle_btn = QPushButton("Generate Idle RPM Targets")
        idle_btn.setToolTip(
            "Generates conservative iacBins and iacCLValues and stages them for review.\n"
            "Review and adjust before writing to RAM."
        )
        idle_btn.clicked.connect(self._on_generate_idle_rpm)
        idle_btn_row.addWidget(idle_btn)
        idle_btn_row.addStretch(1)
        idle_layout.addLayout(idle_btn_row)
        idle_layout.addWidget(self._idle_status_label)
        layout.addWidget(idle_grp)

        layout.addWidget(_reboot_note())
        layout.addStretch(1)
        self._refresh_engine_advanced_visibility()

        self._tabs.addTab(_scroll_wrap(container), "Engine")

    def _refresh_engine_tab(self) -> None:
        from PySide6.QtCore import QSignalBlocker
        operator_context = self._effective_operator_context()

        raw_cyl = self._get_tune_str("nCylinders")
        if raw_cyl is not None:
            try:
                b = QSignalBlocker(self._ncylinders_spin)
                self._ncylinders_spin.setValue(int(float(raw_cyl)))
                del b
            except (ValueError, IndexError):
                pass

        b_disp = QSignalBlocker(self._displacement_edit)
        self._displacement_edit.setValue(operator_context.displacement_cc or 0.0)
        del b_disp

        b_comp = QSignalBlocker(self._compression_edit)
        self._compression_edit.setValue(operator_context.compression_ratio or 0.0)
        del b_comp

        b_engine_advanced = QSignalBlocker(self._engine_advanced_check)
        self._engine_advanced_check.setChecked(
            operator_context.cam_duration_deg is not None
            or operator_context.head_flow_class is not None
            or operator_context.intake_manifold_style is not None
        )
        del b_engine_advanced

        b_cam = QSignalBlocker(self._cam_duration_spin)
        self._cam_duration_spin.setValue(operator_context.cam_duration_deg or 0.0)
        del b_cam
        b_head = QSignalBlocker(self._head_flow_combo)
        self._head_flow_combo.setCurrentIndex(max(0, self._head_flow_combo.findData(operator_context.head_flow_class)))
        del b_head
        b_manifold = QSignalBlocker(self._manifold_style_combo)
        self._manifold_style_combo.setCurrentIndex(
            max(0, self._manifold_style_combo.findData(operator_context.intake_manifold_style))
        )
        del b_manifold
        self._refresh_engine_advanced_visibility()

        raw_inj = self._get_tune_str("nInjectors")
        if raw_inj is not None:
            try:
                b = QSignalBlocker(self._ninjectors_spin)
                self._ninjectors_spin.setValue(int(float(raw_inj)))
                del b
            except (ValueError, IndexError):
                pass

        # injLayout options from definition
        b2 = QSignalBlocker(self._injlayout_combo)
        self._injlayout_combo.clear()
        param = self._get_definition_scalar("injLayout")
        if param and param.options:
            for opt in param.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._injlayout_combo.addItem(opt.label, opt.value)
        if self._injlayout_combo.count() == 0:
            for label in ("Paired", "Semi-Sequential", "Sequential"):
                self._injlayout_combo.addItem(label)
        del b2

        raw_layout = self._get_tune_str("injLayout")
        if raw_layout is not None:
            idx = self._find_combo_by_value(self._injlayout_combo, raw_layout)
            if idx >= 0:
                from PySide6.QtCore import QSignalBlocker as SB
                b3 = SB(self._injlayout_combo)
                self._injlayout_combo.setCurrentIndex(idx)
                del b3

        # algorithm
        b_alg = QSignalBlocker(self._algorithm_combo)
        self._algorithm_combo.clear()
        param_alg = self._get_definition_scalar("algorithm")
        if param_alg and param_alg.options:
            for opt in param_alg.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._algorithm_combo.addItem(opt.label, opt.value)
        if self._algorithm_combo.count() == 0:
            for label in ("MAP (Speed Density)", "TPS (Alpha-N)", "MAP + TPS", "IMAP/EMAP"):
                self._algorithm_combo.addItem(label)
        del b_alg
        raw_alg = self._get_tune_str("algorithm")
        if raw_alg is not None:
            idx = self._find_combo_by_value(self._algorithm_combo, raw_alg)
            if idx >= 0:
                b_alg2 = QSignalBlocker(self._algorithm_combo)
                self._algorithm_combo.setCurrentIndex(idx)
                del b_alg2

        # boostEnabled
        b_boost = QSignalBlocker(self._boost_enabled_combo)
        self._boost_enabled_combo.clear()
        param_boost = self._get_definition_scalar("boostEnabled")
        if param_boost and param_boost.options:
            for opt in param_boost.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._boost_enabled_combo.addItem(opt.label, opt.value)
        if self._boost_enabled_combo.count() == 0:
            self._boost_enabled_combo.addItems(["Off", "On"])
        del b_boost
        raw_boost = self._get_tune_str("boostEnabled")
        if raw_boost is not None:
            idx = self._find_combo_by_value(self._boost_enabled_combo, raw_boost)
            if idx >= 0:
                b_boost2 = QSignalBlocker(self._boost_enabled_combo)
                self._boost_enabled_combo.setCurrentIndex(idx)
                del b_boost2

        intent_index = 1 if operator_context.calibration_intent == CalibrationIntent.DRIVABLE_BASE else 0
        b_intent = QSignalBlocker(self._intent_combo)
        self._intent_combo.setCurrentIndex(intent_index)
        del b_intent

    def _refresh_engine_advanced_visibility(self) -> None:
        self._engine_form.setRowVisible(self._cam_duration_spin, self._engine_advanced_check.isChecked())
        self._engine_form.setRowVisible(self._head_flow_combo, self._engine_advanced_check.isChecked())
        self._engine_form.setRowVisible(self._manifold_style_combo, self._engine_advanced_check.isChecked())

    def _on_ncylinders_changed(self, value: int) -> None:
        if self._updating:
            return
        self._stage_bits_enum_spin("nCylinders", value)
        self._queue_context_update(cylinder_count=value)
        self._refresh_req_fuel_guidance()
        self._refresh_fuel_trim_guidance()

    def _on_injlayout_changed(self, index: int) -> None:
        if self._updating:
            return
        self._stage_combo("injLayout", self._injlayout_combo, index)
        self._refresh_fuel_trim_guidance()
        self._refresh_trigger_tab()

    def _on_displacement_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(displacement_cc=value or None)
        self._refresh_req_fuel_guidance()

    def _on_compression_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(compression_ratio=value or None)

    def _on_cam_duration_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(cam_duration_deg=value or None)

    def _on_head_flow_class_changed(self, index: int) -> None:
        if self._updating:
            return
        self._queue_context_update(head_flow_class=self._head_flow_combo.itemData(index))

    def _on_manifold_style_changed(self, index: int) -> None:
        if self._updating:
            return
        self._queue_context_update(intake_manifold_style=self._manifold_style_combo.itemData(index))

    def _on_calibration_intent_changed(self, index: int) -> None:
        if self._updating:
            return
        intent = self._intent_combo.itemData(index)
        if intent is None:
            return
        self._queue_context_update(calibration_intent=intent)

    def _on_generate_idle_rpm(self) -> None:
        try:
            snap = self._presenter.generate_and_stage_idle_rpm_targets(
                operator_context=self._effective_operator_context()
            )
            msg = self._presenter.consume_message() or ""
            if not msg:
                msg = snap.operation_log[-1].summary if snap.operation_log else "Idle RPM targets staged."
        except Exception as exc:
            msg = f"Idle RPM generation failed: {exc}"
        self._idle_status_label.setText(self._format_generator_status(msg, task="idle"))
        self._idle_status_label.setVisible(True)
        self.status_message.emit(msg)
        self.workspace_state_changed.emit()

    # ------------------------------------------------------------------
    # Tab 3: Induction
    # ------------------------------------------------------------------

    def _build_induction_tab(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(_note(
            "Configure the induction arrangement. For naturally-aspirated engines "
            "select N/A. For forced induction, set the topology, boost target, and "
            "intercooler presence — these shape the conservative starter VE table."
        ))

        induction_grp = QGroupBox("Induction")
        self._induction_form = QFormLayout(induction_grp)
        self._induction_form.setContentsMargins(8, 8, 8, 8)

        self._topology_combo = QComboBox()
        self._topology_combo.setToolTip(
            "Induction arrangement used by the VE and spark table generators "
            "to shape conservative starter tables."
        )
        for topology in ForcedInductionTopology:
            self._topology_combo.addItem(
                topology.value.replace("_", " ").title(), topology
            )
        self._topology_combo.currentIndexChanged.connect(self._on_topology_changed)
        self._induction_form.addRow("Topology:", self._topology_combo)

        self._boost_target_spin = QDoubleSpinBox()
        self._boost_target_spin.setRange(0.0, 43.5)
        self._boost_target_spin.setSingleStep(1.0)
        self._boost_target_spin.setDecimals(1)
        self._boost_target_spin.setSuffix(" psi")
        self._boost_target_spin.setToolTip(
            "Boost target in gauge psi above atmospheric. "
            "Common targets: 8–12 psi street, 15–20 psi performance. "
            "Stored internally as kPa absolute."
        )
        self._boost_target_spin.valueChanged.connect(self._on_boost_target_changed)
        self._induction_form.addRow("Boost target:", self._boost_target_spin)

        self._intercooler_check = QCheckBox("Intercooler fitted")
        self._intercooler_check.setToolTip(
            "Check if an air-to-air or air-to-water intercooler is installed. "
            "Affects charge-air temperature assumptions in generator helpers."
        )
        self._intercooler_check.toggled.connect(self._on_intercooler_changed)
        self._induction_form.addRow("Intercooler:", self._intercooler_check)

        self._supercharger_type_combo = QComboBox()
        self._supercharger_type_combo.addItem("Not set", None)
        self._supercharger_type_combo.addItem("Roots", SuperchargerType.ROOTS)
        self._supercharger_type_combo.addItem("Twin-screw", SuperchargerType.TWIN_SCREW)
        self._supercharger_type_combo.addItem("Centrifugal", SuperchargerType.CENTRIFUGAL)
        self._supercharger_type_combo.setToolTip(
            "Supercharger technology changes low-RPM airflow assumptions for starter VE shaping."
        )
        self._supercharger_type_combo.currentIndexChanged.connect(self._on_supercharger_type_changed)
        self._induction_form.addRow("Supercharger type:", self._supercharger_type_combo)

        self._induction_advanced_check = QCheckBox("Show Advanced Induction Inputs")
        self._induction_advanced_check.setToolTip(
            "Reveal Tier 2 turbo and airflow facts that can improve generator quality without slowing the default first-start workflow."
        )
        self._induction_advanced_check.toggled.connect(self._refresh_induction_advanced_visibility)
        self._induction_form.addRow("", self._induction_advanced_check)

        self._compressor_flow_spin = QDoubleSpinBox()
        self._compressor_flow_spin.setRange(0.0, 200.0)
        self._compressor_flow_spin.setSingleStep(1.0)
        self._compressor_flow_spin.setDecimals(1)
        self._compressor_flow_spin.setSuffix(" lb/min")
        self._compressor_flow_spin.setToolTip(
            "Approximate corrected compressor flow at peak efficiency. Advanced Tier 2 input for boosted VE shaping."
        )
        self._compressor_flow_spin.valueChanged.connect(self._on_compressor_flow_changed)
        self._induction_form.addRow("Compressor flow:", self._compressor_flow_spin)

        self._compressor_pr_spin = QDoubleSpinBox()
        self._compressor_pr_spin.setRange(0.0, 5.0)
        self._compressor_pr_spin.setSingleStep(0.05)
        self._compressor_pr_spin.setDecimals(2)
        self._compressor_pr_spin.setToolTip(
            "Approximate compressor pressure ratio at peak efficiency. Advanced Tier 2 input."
        )
        self._compressor_pr_spin.valueChanged.connect(self._on_compressor_pr_changed)
        self._induction_form.addRow("Compressor PR:", self._compressor_pr_spin)

        self._compressor_inducer_spin = QDoubleSpinBox()
        self._compressor_inducer_spin.setRange(0.0, 150.0)
        self._compressor_inducer_spin.setSingleStep(0.5)
        self._compressor_inducer_spin.setDecimals(1)
        self._compressor_inducer_spin.setSuffix(" mm")
        self._compressor_inducer_spin.setToolTip("Compressor inducer diameter. Advanced Tier 2 turbo sizing input.")
        self._compressor_inducer_spin.valueChanged.connect(self._on_compressor_inducer_changed)
        self._induction_form.addRow("Compressor inducer:", self._compressor_inducer_spin)

        self._compressor_exducer_spin = QDoubleSpinBox()
        self._compressor_exducer_spin.setRange(0.0, 150.0)
        self._compressor_exducer_spin.setSingleStep(0.5)
        self._compressor_exducer_spin.setDecimals(1)
        self._compressor_exducer_spin.setSuffix(" mm")
        self._compressor_exducer_spin.setToolTip("Compressor exducer diameter. Advanced Tier 2 turbo sizing input.")
        self._compressor_exducer_spin.valueChanged.connect(self._on_compressor_exducer_changed)
        self._induction_form.addRow("Compressor exducer:", self._compressor_exducer_spin)

        self._compressor_ar_spin = QDoubleSpinBox()
        self._compressor_ar_spin.setRange(0.0, 3.0)
        self._compressor_ar_spin.setSingleStep(0.01)
        self._compressor_ar_spin.setDecimals(2)
        self._compressor_ar_spin.setToolTip("Approximate turbine A/R. Advanced Tier 2 spool/context input.")
        self._compressor_ar_spin.valueChanged.connect(self._on_compressor_ar_changed)
        self._induction_form.addRow("Turbine A/R:", self._compressor_ar_spin)

        layout.addWidget(induction_grp)

        preset_grp = QGroupBox("Turbo Hardware Preset")
        preset_layout = QVBoxLayout(preset_grp)
        preset_layout.setContentsMargins(8, 8, 8, 8)
        preset_layout.setSpacing(6)
        preset_layout.addWidget(_note(
            "Load reviewed turbo sizing facts into the draft context. "
            "This fills compressor and turbine sizing fields for generator guidance; click Apply to commit the draft."
        ))
        preset_row = QHBoxLayout()
        self._turbo_preset_combo = QComboBox()
        self._turbo_preset_combo.addItem("Choose turbo preset...", None)
        for preset in self._hardware_preset_service.turbo_presets():
            self._turbo_preset_combo.addItem(preset.label, preset)
        preset_row.addWidget(self._turbo_preset_combo, 1)
        self._turbo_preset_button = QPushButton("Load Turbo Preset")
        self._turbo_preset_button.clicked.connect(self._on_apply_turbo_preset)
        preset_row.addWidget(self._turbo_preset_button)
        preset_layout.addLayout(preset_row)
        self._turbo_preset_note = _note("")
        self._turbo_preset_note.setVisible(False)
        preset_layout.addWidget(self._turbo_preset_note)
        layout.addWidget(preset_grp)

        # VE table generator
        ve_grp = QGroupBox("VE Table Generator")
        ve_layout = QVBoxLayout(ve_grp)
        ve_layout.setContentsMargins(8, 8, 8, 8)
        ve_layout.setSpacing(6)
        ve_layout.addWidget(_note(
            "Generates a conservative 16 × 16 VE table shaped for the current engine "
            "geometry and induction topology. Staged as a reviewable edit — nothing is "
            "written to the ECU automatically."
        ))
        self._ve_status_label = QLabel("")
        self._ve_status_label.setWordWrap(True)
        self._ve_status_label.setVisible(False)
        ve_btn_row = QHBoxLayout()
        ve_btn = QPushButton("Generate VE Table")
        ve_btn.setToolTip(
            "Stages a conservative 16×16 VE table for review.\n"
            "Review and adjust before writing to RAM."
        )
        ve_btn.clicked.connect(self._on_generate_ve_table)
        ve_btn_row.addWidget(ve_btn)
        ve_btn_row.addStretch(1)
        ve_layout.addLayout(ve_btn_row)
        ve_layout.addWidget(self._ve_status_label)
        layout.addWidget(ve_grp)

        layout.addStretch(1)
        self._tabs.addTab(_scroll_wrap(container), "Induction")

    def _refresh_induction_tab(self) -> None:
        from PySide6.QtCore import QSignalBlocker
        ctx = self._effective_operator_context()

        b_topo = QSignalBlocker(self._topology_combo)
        for i in range(self._topology_combo.count()):
            if self._topology_combo.itemData(i) == ctx.forced_induction_topology:
                self._topology_combo.setCurrentIndex(i)
                break
        del b_topo

        is_forced = ctx.forced_induction_topology != ForcedInductionTopology.NA

        b_boost = QSignalBlocker(self._boost_target_spin)
        kpa_abs = ctx.boost_target_kpa or 170.0
        self._boost_target_spin.setValue(max(0.0, (kpa_abs - 101.325) / 6.89476))
        del b_boost

        b_ic = QSignalBlocker(self._intercooler_check)
        self._intercooler_check.setChecked(ctx.intercooler_present)
        del b_ic
        b_sc = QSignalBlocker(self._supercharger_type_combo)
        self._supercharger_type_combo.setCurrentIndex(
            max(0, self._supercharger_type_combo.findData(ctx.supercharger_type))
        )
        del b_sc

        b_adv = QSignalBlocker(self._induction_advanced_check)
        self._induction_advanced_check.setChecked(
            any(
                value is not None
                for value in (
                    ctx.compressor_corrected_flow_lbmin,
                    ctx.compressor_pressure_ratio,
                    ctx.compressor_inducer_mm,
                    ctx.compressor_exducer_mm,
                    ctx.compressor_ar,
                )
            )
        )
        del b_adv

        b_flow = QSignalBlocker(self._compressor_flow_spin)
        self._compressor_flow_spin.setValue(ctx.compressor_corrected_flow_lbmin or 0.0)
        del b_flow
        b_pr = QSignalBlocker(self._compressor_pr_spin)
        self._compressor_pr_spin.setValue(ctx.compressor_pressure_ratio or 0.0)
        del b_pr
        b_ind = QSignalBlocker(self._compressor_inducer_spin)
        self._compressor_inducer_spin.setValue(ctx.compressor_inducer_mm or 0.0)
        del b_ind
        b_ex = QSignalBlocker(self._compressor_exducer_spin)
        self._compressor_exducer_spin.setValue(ctx.compressor_exducer_mm or 0.0)
        del b_ex
        b_ar = QSignalBlocker(self._compressor_ar_spin)
        self._compressor_ar_spin.setValue(ctx.compressor_ar or 0.0)
        del b_ar

        b_turbo = QSignalBlocker(self._turbo_preset_combo)
        self._turbo_preset_combo.setCurrentIndex(0)
        for i in range(1, self._turbo_preset_combo.count()):
            preset = self._turbo_preset_combo.itemData(i)
            if isinstance(preset, TurboHardwarePreset) and preset.key == ctx.turbo_preset_key:
                self._turbo_preset_combo.setCurrentIndex(i)
                break
        del b_turbo

        _set_form_row_visible(self._induction_form, self._boost_target_spin, is_forced)
        _set_form_row_visible(self._induction_form, self._intercooler_check, is_forced)
        _set_form_row_visible(
            self._induction_form,
            self._supercharger_type_combo,
            ctx.forced_induction_topology in (
                ForcedInductionTopology.SINGLE_SUPERCHARGER,
                ForcedInductionTopology.TWIN_CHARGE,
            ),
        )
        self._refresh_induction_advanced_visibility()

    def _on_topology_changed(self, index: int) -> None:
        if self._updating:
            return
        topology = self._topology_combo.itemData(index)
        if topology is None:
            return
        self._queue_context_update(forced_induction_topology=topology)
        is_forced = topology != ForcedInductionTopology.NA
        _set_form_row_visible(self._induction_form, self._boost_target_spin, is_forced)
        _set_form_row_visible(self._induction_form, self._intercooler_check, is_forced)
        _set_form_row_visible(
            self._induction_form,
            self._supercharger_type_combo,
            topology in (ForcedInductionTopology.SINGLE_SUPERCHARGER, ForcedInductionTopology.TWIN_CHARGE),
        )
        if topology not in (ForcedInductionTopology.SINGLE_SUPERCHARGER, ForcedInductionTopology.TWIN_CHARGE):
            self._queue_context_update(supercharger_type=None)
        self._refresh_induction_advanced_visibility()

    def _on_boost_target_changed(self, value: float) -> None:
        if self._updating:
            return
        kpa_abs = value * 6.89476 + 101.325
        self._queue_context_update(boost_target_kpa=kpa_abs)

    def _on_intercooler_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._queue_context_update(intercooler_present=checked)

    def _on_supercharger_type_changed(self, index: int) -> None:
        if self._updating:
            return
        self._queue_context_update(supercharger_type=self._supercharger_type_combo.itemData(index))

    def _refresh_induction_advanced_visibility(self) -> None:
        show = self._induction_advanced_check.isChecked() and self._topology_combo.currentData() != ForcedInductionTopology.NA
        for field in (
            self._compressor_flow_spin,
            self._compressor_pr_spin,
            self._compressor_inducer_spin,
            self._compressor_exducer_spin,
            self._compressor_ar_spin,
        ):
            _set_form_row_visible(self._induction_form, field, show)

    def _on_compressor_flow_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(compressor_corrected_flow_lbmin=value or None)

    def _on_compressor_pr_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(compressor_pressure_ratio=value or None)

    def _on_compressor_inducer_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(compressor_inducer_mm=value or None)

    def _on_compressor_exducer_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(compressor_exducer_mm=value or None)

    def _on_compressor_ar_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(compressor_ar=value or None)

    def _on_apply_turbo_preset(self) -> None:
        preset = self._turbo_preset_combo.currentData()
        if not isinstance(preset, TurboHardwarePreset):
            self._turbo_preset_note.setText("Choose a turbo preset first.")
            self._turbo_preset_note.setVisible(True)
            return
        self._queue_context_update(
            turbo_preset_key=preset.key,
            compressor_corrected_flow_lbmin=preset.compressor_corrected_flow_lbmin,
            compressor_inducer_mm=preset.compressor_inducer_mm,
            compressor_exducer_mm=preset.compressor_exducer_mm,
            compressor_ar=preset.turbine_ar,
        )
        confidence = self._hardware_preset_service.source_confidence_label(
            source_note=preset.source_note,
            source_url=preset.source_url,
        )
        flow_text = (
            f"{preset.compressor_corrected_flow_lbmin:.0f} lb/min inferred flow"
            if preset.compressor_corrected_flow_lbmin is not None
            else "flow not set"
        )
        self._turbo_preset_note.setText(
            f"{preset.description} Loaded compressor {preset.compressor_inducer_mm:.1f}/{preset.compressor_exducer_mm:.1f} mm, "
            f"turbine {preset.turbine_inducer_mm:.1f}/{preset.turbine_exducer_mm:.1f} mm, turbine A/R {preset.turbine_ar:.2f}, "
            f"and {flow_text}. [{confidence}] {preset.source_note} Click Apply to stage the preset."
        )
        self._turbo_preset_note.setVisible(True)
        self._refresh_induction_tab()
        self._update_apply_button_state()

    def _on_generate_ve_table(self) -> None:
        try:
            snap = self._presenter.generate_and_stage_ve_table(
                self._resolve_ve_table_name(),
                operator_context=self._effective_operator_context(),
            )
            msg = self._presenter.consume_message() or ""
            if not msg:
                msg = snap.operation_log[-1].summary if snap.operation_log else "VE table staged."
        except Exception as exc:
            msg = f"VE table generation failed: {exc}"
        self._ve_status_label.setText(self._format_generator_status(msg, task="ve"))
        self._ve_status_label.setVisible(True)
        self.status_message.emit(msg)
        self.workspace_state_changed.emit()

    # ------------------------------------------------------------------
    # Tab 4: Injectors
    # ------------------------------------------------------------------

    def _build_injector_tab(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(_note(
            "Set injector characteristics. reqFuel is the base injector pulse "
            "width and is calculated from displacement, injector flow, and stoich AFR. "
            "Use the Engine Setup tab to compute it automatically."
        ))

        preset_grp = QGroupBox("Injector Hardware Preset")
        preset_layout = QVBoxLayout(preset_grp)
        preset_layout.setContentsMargins(8, 8, 8, 8)
        preset_layout.setSpacing(6)
        preset_layout.addWidget(_note(
            "Load a reviewed starter preset for common injector hardware. "
            "The preset only fills the wizard draft; click Apply to stage it into the tune."
        ))
        preset_row = QHBoxLayout()
        self._injector_preset_combo = QComboBox()
        self._injector_preset_combo.addItem("Choose injector preset...", None)
        for preset in self._hardware_preset_service.injector_presets():
            self._injector_preset_combo.addItem(preset.label, preset)
        preset_row.addWidget(self._injector_preset_combo, 1)
        self._injector_preset_btn = QPushButton("Load Preset")
        self._injector_preset_btn.clicked.connect(self._on_apply_injector_preset)
        preset_row.addWidget(self._injector_preset_btn)
        preset_layout.addLayout(preset_row)
        self._injector_advanced_check = QCheckBox("Show Advanced Injector Inputs")
        self._injector_advanced_check.setToolTip(
            "Reveal Tier 2 injector characterization inputs such as installed base fuel pressure."
        )
        self._injector_advanced_check.toggled.connect(self._refresh_injector_advanced_visibility)
        preset_layout.addWidget(self._injector_advanced_check)
        self._injector_pressure_model_row = QWidget()
        pressure_model_row = QHBoxLayout(self._injector_pressure_model_row)
        pressure_model_row.setContentsMargins(0, 0, 0, 0)
        pressure_model_row.addWidget(QLabel("Pressure compensation:"))
        self._injector_pressure_model_combo = QComboBox()
        self._injector_pressure_model_combo.addItem("Fixed pressure (no compensation)", "fixed_pressure")
        self._injector_pressure_model_combo.addItem("Vacuum-referenced (rising-rate FPR)", "vacuum_referenced")
        self._injector_pressure_model_combo.addItem("Operator-specified pressure", "operator_specified")
        self._injector_pressure_model_combo.currentIndexChanged.connect(self._on_injector_pressure_model_changed)
        pressure_model_row.addWidget(self._injector_pressure_model_combo, 1)
        preset_layout.addWidget(self._injector_pressure_model_row)
        self._injector_pressure_row = QWidget()
        pressure_row = QHBoxLayout(self._injector_pressure_row)
        pressure_row.setContentsMargins(0, 0, 0, 0)
        pressure_row.addWidget(QLabel("Base rail pressure at idle:"))
        self._injector_base_pressure_spin = QDoubleSpinBox()
        self._injector_base_pressure_spin.setRange(20.0, 100.0)
        self._injector_base_pressure_spin.setSingleStep(0.5)
        self._injector_base_pressure_spin.setDecimals(1)
        self._injector_base_pressure_spin.setSuffix(" psi")
        self._injector_base_pressure_spin.setValue(43.5)
        self._injector_base_pressure_spin.setToolTip(
            "Injector preset flow is scaled from its published reference pressure "
            "to this installed base differential pressure using the standard square-root approximation."
        )
        self._injector_base_pressure_spin.valueChanged.connect(self._on_injector_base_pressure_changed)
        pressure_row.addWidget(self._injector_base_pressure_spin)
        pressure_row.addStretch(1)
        preset_layout.addWidget(self._injector_pressure_row)

        self._secondary_injector_pressure_row = QWidget()
        secondary_pressure_row = QHBoxLayout(self._secondary_injector_pressure_row)
        secondary_pressure_row.setContentsMargins(0, 0, 0, 0)
        secondary_pressure_row.addWidget(QLabel("Secondary ref pressure:"))
        self._secondary_injector_pressure_spin = QDoubleSpinBox()
        self._secondary_injector_pressure_spin.setRange(0.0, 100.0)
        self._secondary_injector_pressure_spin.setSingleStep(0.5)
        self._secondary_injector_pressure_spin.setDecimals(1)
        self._secondary_injector_pressure_spin.setSuffix(" psi")
        self._secondary_injector_pressure_spin.setSpecialValueText("not set")
        self._secondary_injector_pressure_spin.valueChanged.connect(self._on_secondary_injector_pressure_changed)
        secondary_pressure_row.addWidget(self._secondary_injector_pressure_spin)
        secondary_pressure_row.addStretch(1)
        preset_layout.addWidget(self._secondary_injector_pressure_row)

        self._injector_characterization_row = QWidget()
        injector_char_layout = QHBoxLayout(self._injector_characterization_row)
        injector_char_layout.setContentsMargins(0, 0, 0, 0)
        injector_char_layout.addWidget(QLabel("Injector data depth:"))
        self._injector_characterization_combo = QComboBox()
        self._injector_characterization_combo.addItem("Not set", None)
        self._injector_characterization_combo.addItem("Nominal flow only", "nominal_flow_only")
        self._injector_characterization_combo.addItem("Flow + single dead time", "flow_plus_deadtime")
        self._injector_characterization_combo.addItem("Flow + voltage correction table", "flow_plus_voltage_table")
        self._injector_characterization_combo.addItem("Full pressure + voltage characterization", "full_characterization")
        self._injector_characterization_combo.currentIndexChanged.connect(self._on_injector_characterization_changed)
        injector_char_layout.addWidget(self._injector_characterization_combo, 1)
        preset_layout.addWidget(self._injector_characterization_row)
        self._injector_preset_summary = QLabel("")
        self._injector_preset_summary.setWordWrap(True)
        self._injector_preset_summary.setVisible(False)
        preset_layout.addWidget(self._injector_preset_summary)
        self._injector_preset_note = QLabel("")
        self._injector_preset_note.setWordWrap(True)
        self._injector_preset_note.setVisible(False)
        preset_layout.addWidget(self._injector_preset_note)
        self._injector_characterization_note = QLabel("")
        self._injector_characterization_note.setWordWrap(True)
        self._injector_characterization_note.setVisible(False)
        preset_layout.addWidget(self._injector_characterization_note)
        self._injector_pressure_guidance_label = QLabel("")
        self._injector_pressure_guidance_label.setWordWrap(True)
        self._injector_pressure_guidance_label.setVisible(False)
        preset_layout.addWidget(self._injector_pressure_guidance_label)
        layout.addWidget(preset_grp)

        grp = QGroupBox("Injector Settings")
        form = QFormLayout(grp)

        self._inj_open_spin = QDoubleSpinBox()
        self._inj_open_spin.setRange(0.1, 25.5)
        self._inj_open_spin.setSingleStep(0.05)
        self._inj_open_spin.setDecimals(3)
        self._inj_open_spin.setSuffix(" ms")
        self._inj_open_spin.setToolTip(
            "Injector dead time (opening time). Typically 0.5–1.5 ms for most "
            "modern injectors. Wrong values cause incorrect fuelling at idle."
        )
        self._inj_open_spin.valueChanged.connect(
            lambda v: self._stage_float("injOpen", v)
        )
        form.addRow("Injector open time:", self._inj_open_spin)

        self._req_fuel_spin = QDoubleSpinBox()
        self._req_fuel_spin.setRange(0.0, 25.5)
        self._req_fuel_spin.setSingleStep(0.1)
        self._req_fuel_spin.setDecimals(1)
        self._req_fuel_spin.setSuffix(" ms")
        self._req_fuel_spin.setToolTip(
            "Required fuel pulse width. Use the Engine Setup tab to calculate "
            "this value from displacement, cylinder count, and injector flow."
        )
        self._req_fuel_spin.valueChanged.connect(
            lambda v: self._stage_req_fuel(v)
        )
        form.addRow("Required fuel (reqFuel):", self._req_fuel_spin)

        self._stoich_spin = QDoubleSpinBox()
        self._stoich_spin.setRange(0.0, 25.5)
        self._stoich_spin.setSingleStep(0.1)
        self._stoich_spin.setDecimals(1)
        self._stoich_spin.setSuffix(" :1")
        self._stoich_spin.setToolTip(
            "Stoichiometric AFR for your fuel. Petrol ≈ 14.7, E85 ≈ 9.8, "
            "methanol ≈ 6.5. Used by the EGO controller and VE table generators."
        )
        self._stoich_spin.valueChanged.connect(
            lambda v: self._stage_float("stoich", v)
        )
        form.addRow("Stoich AFR:", self._stoich_spin)

        layout.addWidget(grp)

        calc_grp = QGroupBox("reqFuel Guidance")
        calc_layout = QVBoxLayout(calc_grp)
        calc_layout.setContentsMargins(8, 8, 8, 8)
        calc_layout.setSpacing(6)
        calc_layout.addWidget(_note(
            "This guided calculation combines the injector settings on this page with "
            "the engine facts from the Engine tab. The result is staged only when you click Apply."
        ))
        self._req_fuel_inputs_label = QLabel("Still needed: engine displacement, cylinder count, injector flow.")
        self._req_fuel_inputs_label.setWordWrap(True)
        calc_layout.addWidget(self._req_fuel_inputs_label)
        self._req_fuel_result_label = QLabel("No reqFuel result yet.")
        self._req_fuel_result_label.setWordWrap(True)
        calc_layout.addWidget(self._req_fuel_result_label)
        self._req_fuel_apply_btn = QPushButton("Apply Calculated reqFuel")
        self._req_fuel_apply_btn.clicked.connect(self._on_apply_req_fuel_clicked)
        calc_layout.addWidget(self._req_fuel_apply_btn)
        layout.addWidget(calc_grp)

        trim_grp = QGroupBox("Sequential Fuel Trims")
        trim_layout = QVBoxLayout(trim_grp)
        trim_layout.setContentsMargins(8, 8, 8, 8)
        trim_layout.setSpacing(6)
        trim_layout.addWidget(_note(
            "Per-cylinder fuel trims are useful after the engine is running well on sequential fuel. "
            "They are not needed for most first-start setups."
        ))
        self._fuel_trim_form = QFormLayout()
        self._fuel_trim_enabled_combo = QComboBox()
        self._fuel_trim_enabled_combo.addItems(["Disabled", "Enabled"])
        self._fuel_trim_enabled_combo.setToolTip(
            "Enable individual cylinder fuel trim tables when true sequential fuel is available."
        )
        self._fuel_trim_enabled_combo.currentIndexChanged.connect(self._on_fuel_trim_enabled_changed)
        self._fuel_trim_form.addRow("Individual fuel trims:", self._fuel_trim_enabled_combo)
        trim_layout.addLayout(self._fuel_trim_form)
        self._fuel_trim_summary_label = QLabel("")
        self._fuel_trim_summary_label.setWordWrap(True)
        trim_layout.addWidget(self._fuel_trim_summary_label)
        layout.addWidget(trim_grp)

        # Base fuel table generators
        fuel_gen_grp = QGroupBox("Base Fuel Table Generators")
        fuel_gen_layout = QVBoxLayout(fuel_gen_grp)
        fuel_gen_layout.setContentsMargins(8, 8, 8, 8)
        fuel_gen_layout.setSpacing(8)
        fuel_gen_layout.addWidget(_note(
            "Generate conservative starter tables from the current engine and injector context. "
            "All outputs are staged for review — nothing is written to the ECU automatically."
        ))

        # AFR target table
        afr_row = QHBoxLayout()
        afr_btn = QPushButton("Generate AFR Target Table")
        afr_btn.setToolTip(
            "Generates a conservative 16×16 AFR target table shaped for the current "
            "induction topology and fuel type. Staged for review."
        )
        afr_btn.clicked.connect(self._on_generate_afr_table)
        afr_row.addWidget(afr_btn)
        afr_row.addStretch(1)
        fuel_gen_layout.addLayout(afr_row)
        self._afr_status_label = QLabel("")
        self._afr_status_label.setWordWrap(True)
        self._afr_status_label.setVisible(False)
        fuel_gen_layout.addWidget(self._afr_status_label)

        # WUE
        wue_row = QHBoxLayout()
        wue_btn = QPushButton("Generate Warm-Up Enrichment (WUE)")
        wue_btn.setToolTip(
            "Generates a 10-bin CLT-based warm-up enrichment curve (wueRates). "
            "Reference-scaled and stoich-aware. Staged for review."
        )
        wue_btn.clicked.connect(self._on_generate_wue)
        wue_row.addWidget(wue_btn)
        wue_row.addStretch(1)
        fuel_gen_layout.addLayout(wue_row)
        self._wue_status_label = QLabel("")
        self._wue_status_label.setWordWrap(True)
        self._wue_status_label.setVisible(False)
        fuel_gen_layout.addWidget(self._wue_status_label)

        # Cranking enrichment
        crank_row = QHBoxLayout()
        crank_btn = QPushButton("Generate Cranking Enrichment")
        crank_btn.setToolTip(
            "Generates a 4-bin CLT-based cranking enrichment curve. "
            "Compression-ratio adjusted. Staged for review."
        )
        crank_btn.clicked.connect(self._on_generate_cranking_enrichment)
        crank_row.addWidget(crank_btn)
        crank_row.addStretch(1)
        fuel_gen_layout.addLayout(crank_row)
        self._crank_status_label = QLabel("")
        self._crank_status_label.setWordWrap(True)
        self._crank_status_label.setVisible(False)
        fuel_gen_layout.addWidget(self._crank_status_label)

        # After-start enrichment
        ase_row = QHBoxLayout()
        ase_btn = QPushButton("Generate After-Start Enrichment (ASE)")
        ase_btn.setToolTip(
            "Generates 4-bin ASE enrichment percentage and duration curves. "
            "Intent and induction-aware. Staged for review."
        )
        ase_btn.clicked.connect(self._on_generate_ase)
        ase_row.addWidget(ase_btn)
        ase_row.addStretch(1)
        fuel_gen_layout.addLayout(ase_row)
        self._ase_status_label = QLabel("")
        self._ase_status_label.setWordWrap(True)
        self._ase_status_label.setVisible(False)
        fuel_gen_layout.addWidget(self._ase_status_label)

        layout.addWidget(fuel_gen_grp)

        layout.addWidget(_reboot_note())
        layout.addStretch(1)
        self._refresh_injector_advanced_visibility()

        self._tabs.addTab(_scroll_wrap(container), "Injectors")

    def _refresh_injector_tab(self) -> None:
        from PySide6.QtCore import QSignalBlocker
        operator_context = self._effective_operator_context()

        for name, spin in (
            ("injOpen", self._inj_open_spin),
            ("stoich", self._stoich_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                b = QSignalBlocker(spin)
                spin.setValue(raw)
                del b

        raw_rf = self._get_tune_float("reqFuel")
        if raw_rf is not None:
            b = QSignalBlocker(self._req_fuel_spin)
            self._req_fuel_spin.setValue(raw_rf)
            del b
        b_pressure = QSignalBlocker(self._injector_base_pressure_spin)
        self._injector_base_pressure_spin.setValue(operator_context.base_fuel_pressure_psi or 43.5)
        del b_pressure
        b_pressure_model = QSignalBlocker(self._injector_pressure_model_combo)
        self._injector_pressure_model_combo.setCurrentIndex(
            max(0, self._injector_pressure_model_combo.findData(self._effective_injector_pressure_model()))
        )
        del b_pressure_model
        b_secondary_pressure = QSignalBlocker(self._secondary_injector_pressure_spin)
        self._secondary_injector_pressure_spin.setValue(operator_context.secondary_injector_reference_pressure_psi or 0.0)
        del b_secondary_pressure
        b_injector_advanced = QSignalBlocker(self._injector_advanced_check)
        self._injector_advanced_check.setChecked(
            (operator_context.base_fuel_pressure_psi is not None and abs(operator_context.base_fuel_pressure_psi - 43.5) > 1e-6)
            or operator_context.injector_pressure_model is not None
            or operator_context.secondary_injector_reference_pressure_psi is not None
            or operator_context.injector_characterization is not None
        )
        del b_injector_advanced
        b_inj_char = QSignalBlocker(self._injector_characterization_combo)
        self._injector_characterization_combo.setCurrentIndex(
            max(0, self._injector_characterization_combo.findData(operator_context.injector_characterization))
        )
        del b_inj_char
        b_preset = QSignalBlocker(self._injector_preset_combo)
        self._injector_preset_combo.setCurrentIndex(0)
        for index in range(1, self._injector_preset_combo.count()):
            preset = self._injector_preset_combo.itemData(index)
            if isinstance(preset, InjectorHardwarePreset) and preset.key == operator_context.injector_preset_key:
                self._injector_preset_combo.setCurrentIndex(index)
                break
        del b_preset
        self._refresh_injector_advanced_visibility()
        self._refresh_injector_preset_summary()
        self._refresh_injector_characterization_note()
        self._refresh_injector_pressure_guidance()
        self._refresh_req_fuel_guidance()
        self._refresh_fuel_trim_guidance()

    def _refresh_injector_advanced_visibility(self) -> None:
        self._injector_pressure_model_row.setVisible(True)
        self._injector_pressure_row.setVisible(self._effective_injector_pressure_model() != "fixed_pressure")
        self._secondary_injector_pressure_row.setVisible(self._should_show_secondary_injector_pressure())
        self._injector_characterization_row.setVisible(self._injector_advanced_check.isChecked())

    def _refresh_injector_preset_summary(self) -> None:
        context = self._effective_operator_context()
        key = context.injector_preset_key
        if not key:
            self._injector_preset_summary.setVisible(False)
            return
        preset = next((item for item in self._hardware_preset_service.injector_presets() if item.key == key), None)
        if preset is None:
            self._injector_preset_summary.setVisible(False)
            return
        pressure = context.base_fuel_pressure_psi or 43.5
        scaled_flow = self._hardware_preset_service.injector_flow_for_pressure(preset, pressure)
        self._injector_preset_summary.setText(
            f"Current injector profile: {preset.label} | {scaled_flow:.0f} cc/min at {pressure:.1f} psi"
            f" | Pressure model: {self._injector_pressure_model_text(self._effective_injector_pressure_model())}"
            f" | Secondary ref: {self._secondary_injector_pressure_text(context.secondary_injector_reference_pressure_psi)}"
            f" | Source: [{self._hardware_preset_service.source_confidence_label(source_note=preset.source_note, source_url=preset.source_url)}] {preset.source_note}"
        )
        self._injector_preset_summary.setVisible(True)

    @staticmethod
    def _injector_pressure_model_text(value: str | None) -> str:
        labels = {
            "fixed_pressure": "fixed pressure",
            "vacuum_referenced": "vacuum referenced",
            "operator_specified": "operator-specified pressure",
            "not_modeled": "operator-specified pressure",
        }
        return labels.get(value, "fixed pressure")

    @staticmethod
    def _secondary_injector_pressure_text(value: float | None) -> str:
        return f"{value:.1f} psi" if value is not None else "not set"

    def _secondary_injector_flow(self) -> float | None:
        name = self._first_definition_scalar_name(
            ("stagedInjSizeSec", "injSizeSec", "injFlowSec", "secondaryInjectorFlow")
        )
        if not name:
            return None
        value = self._get_tune_float(name)
        return value if value and value > 0.0 else None

    def _has_secondary_injector_bank(self) -> bool:
        return self._secondary_injector_flow() is not None

    def _effective_injector_pressure_model(self) -> str:
        model = self._effective_operator_context().injector_pressure_model
        if model == "not_modeled":
            return "operator_specified"
        return model or "fixed_pressure"

    def _should_show_secondary_injector_pressure(self) -> bool:
        if self._has_secondary_injector_bank():
            return True
        raw_inj = self._get_tune_str("nInjectors")
        raw_cyl = self._get_tune_str("nCylinders")
        if raw_inj is None or raw_cyl is None:
            return False
        try:
            return int(float(raw_inj)) > int(float(raw_cyl))
        except ValueError:
            return False

    @staticmethod
    def _injector_characterization_from_preset(preset: InjectorHardwarePreset) -> str:
        if preset.dead_time_pressure_compensation or (preset.flow_samples_ccmin and preset.voltage_offset_samples_ms):
            return "full_characterization"
        if preset.dead_time_ms is not None or preset.voltage_offset_samples_ms or preset.flow_samples_ccmin:
            return "flow_plus_deadtime"
        return "nominal_flow_only"

    def _refresh_injector_characterization_note(self) -> None:
        preset = self._injector_preset_combo.currentData()
        if isinstance(preset, InjectorHardwarePreset):
            characterization = self._injector_characterization_from_preset(preset)
        else:
            characterization = self._effective_operator_context().injector_characterization
        if characterization is None:
            self._injector_characterization_note.setVisible(False)
            self._injector_characterization_note.setText("")
            return
        explanation = {
            "nominal_flow_only": "Only nominal flow is known, so reqFuel and VE confidence stays low until you verify dead time and pressure behavior.",
            "flow_plus_deadtime": "Flow and dead time are known, so starter reqFuel and VE confidence is moderate but pressure behavior still needs review.",
            "flow_plus_voltage_table": "Voltage offset data is available, but pressure compensation still needs review under load.",
            "full_characterization": "Pressure and voltage behavior are characterized, giving the best starter confidence for reqFuel and VE generation.",
        }.get(characterization, "Injector data depth recorded for generator confidence tracking.")
        self._injector_characterization_note.setText(
            f"Injector characterization: {characterization}. {explanation}"
        )
        self._injector_characterization_note.setVisible(True)

    def _refresh_injector_pressure_guidance(self) -> None:
        context = self._effective_operator_context()
        lines: list[str] = []
        model = self._effective_injector_pressure_model()
        pressure = context.base_fuel_pressure_psi or 43.5
        if model == "vacuum_referenced":
            lines.append(
                f"Primary injectors are modeled as vacuum referenced around {pressure:.1f} psi differential pressure."
            )
        elif model == "fixed_pressure":
            lines.append(
                "Primary injectors are modeled as fixed pressure with no active pressure compensation."
            )
        elif model == "operator_specified":
            lines.append(
                f"Primary injectors use an operator-specified idle rail pressure of {pressure:.1f} psi for generator assumptions."
            )

        secondary_flow = self._secondary_injector_flow()
        if secondary_flow is not None:
            if context.secondary_injector_reference_pressure_psi is None:
                lines.append(
                    f"Secondary injectors are configured at {secondary_flow:.0f} cc/min, but their reference pressure is not set."
                )
            else:
                lines.append(
                    f"Secondary injector reference pressure is {context.secondary_injector_reference_pressure_psi:.1f} psi for the staged bank."
                )

        if not lines:
            self._injector_pressure_guidance_label.setVisible(False)
            self._injector_pressure_guidance_label.setText("")
            return
        self._injector_pressure_guidance_label.setText(" ".join(lines))
        self._injector_pressure_guidance_label.setVisible(True)

    def _resolve_injector_flow_param_name(self) -> str | None:
        return self._first_definition_scalar_name(
            ("injflow", "injectorFlow", "injectorSize", "stagedInjSizePri", "injFlow")
        )

    def _on_injector_base_pressure_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(base_fuel_pressure_psi=value)
        self._refresh_injector_preset_summary()
        self._refresh_injector_pressure_guidance()
        self._refresh_req_fuel_guidance()

    def _on_injector_pressure_model_changed(self, index: int) -> None:
        if self._updating:
            return
        self._queue_context_update(injector_pressure_model=self._injector_pressure_model_combo.itemData(index))
        self._refresh_injector_advanced_visibility()
        self._refresh_injector_preset_summary()
        self._refresh_injector_pressure_guidance()
        self._refresh_req_fuel_guidance()

    def _on_secondary_injector_pressure_changed(self, value: float) -> None:
        if self._updating:
            return
        self._queue_context_update(secondary_injector_reference_pressure_psi=value or None)
        self._refresh_injector_preset_summary()
        self._refresh_injector_pressure_guidance()
        self._refresh_req_fuel_guidance()

    def _on_injector_characterization_changed(self, index: int) -> None:
        if self._updating:
            return
        self._queue_context_update(injector_characterization=self._injector_characterization_combo.itemData(index))
        self._refresh_injector_characterization_note()
        self._refresh_injector_pressure_guidance()

    def _on_apply_injector_preset(self) -> None:
        preset = self._injector_preset_combo.currentData()
        if not isinstance(preset, InjectorHardwarePreset):
            self._injector_preset_note.setText("Choose an injector preset first.")
            self._injector_preset_note.setVisible(True)
            return

        target_pressure = self._injector_base_pressure_spin.value()
        scaled_flow = self._hardware_preset_service.injector_flow_for_pressure(preset, target_pressure)
        dead_time_ms = self._hardware_preset_service.injector_dead_time_for_pressure(preset, target_pressure)
        if dead_time_ms is not None:
            self._stage_float("injOpen", dead_time_ms)
            self._inj_open_spin.setValue(dead_time_ms)

        flow_param = self._resolve_injector_flow_param_name()
        if flow_param is not None:
            self._stage_float(flow_param, scaled_flow)
        voltage_bins_name = self._first_existing_list_name(
            ("brvBins", "batteryVoltageBins", "injBatteryVoltageBins"),
            keywords=("brv", "bin"),
        )
        correction_rates_name = self._first_existing_list_name(
            ("injBatRates", "injectorBatteryCorrection", "injectorVoltageCorrection", "injVoltageCorrection"),
            keywords=("inj", "bat"),
        )
        voltage_curve_note = ""
        if voltage_bins_name and correction_rates_name:
            voltage_bins = self._get_committed_tune_list(voltage_bins_name)
            if voltage_bins:
                correction_rates = self._hardware_preset_service.injector_battery_correction_percentages(
                    preset,
                    voltage_bins,
                    target_pressure,
                )
                if correction_rates is not None and len(correction_rates) == len(voltage_bins):
                    self._stage_array(correction_rates_name, correction_rates)
                    voltage_curve_note = (
                        f" Applied injector voltage correction to '{correction_rates_name}' using existing '{voltage_bins_name}' bins."
                    )
        self._queue_context_update(
            injector_preset_key=preset.key,
            base_fuel_pressure_psi=target_pressure,
            injector_characterization=self._injector_characterization_from_preset(preset),
        )

        note = (
            f"{preset.description} Loaded {scaled_flow:.0f} cc/min"
            f" at {target_pressure:.1f} psi"
        )
        if dead_time_ms is not None:
            if preset.voltage_offset_samples_ms or preset.dead_time_pressure_compensation:
                note += f" and {dead_time_ms:.3f} ms pressure-compensated dead time."
            else:
                note += f" and {dead_time_ms:.3f} ms dead time."
        else:
            note += "."
        note += (
            f" [{self._hardware_preset_service.source_confidence_label(source_note=preset.source_note, source_url=preset.source_url)}]"
            f" {preset.source_note}"
        )
        if flow_param is None:
            note += " This definition does not expose a recognized injector-flow parameter on the wizard path, so only dead time was loaded."
        note += voltage_curve_note
        note += " Click Apply to stage the preset."
        self._injector_preset_note.setText(note)
        self._injector_preset_note.setVisible(True)
        self._refresh_injector_preset_summary()
        self._refresh_injector_characterization_note()
        self._refresh_injector_pressure_guidance()
        self._refresh_req_fuel_guidance()

    def _stage_req_fuel(self, value_ms: float) -> None:
        if self._updating:
            return
        self._stage_raw("reqFuel", str(value_ms))

    def _refresh_req_fuel_guidance(self) -> None:
        generator_context = self._build_generator_context()
        operator_context = self._effective_operator_context()
        displacement = operator_context.displacement_cc or (generator_context.displacement_cc if generator_context else None)
        cylinder_count = (
            operator_context.cylinder_count
            or (generator_context.cylinder_count if generator_context else None)
            or self._get_tune_float("nCylinders")
        )
        injector_flow = (
            (generator_context.injector_flow_ccmin if generator_context else None)
            or (self._get_tune_float(self._resolve_injector_flow_param_name()) if self._resolve_injector_flow_param_name() else None)
        )
        stoich = (generator_context.stoich_ratio if generator_context and generator_context.stoich_ratio else None) or self._get_tune_float("stoich") or 14.7

        missing: list[str] = []
        if not displacement:
            missing.append("engine displacement")
        if not cylinder_count:
            missing.append("cylinder count")
        if not injector_flow:
            missing.append("injector flow")

        if missing:
            self._req_fuel_inputs_label.setText("Still needed: " + ", ".join(missing) + ".")
            self._req_fuel_result_label.setText("No reqFuel result yet.")
            self._req_fuel_apply_btn.setEnabled(False)
            return

        result = RequiredFuelCalculatorService().calculate(
            displacement_cc=displacement,
            cylinder_count=cylinder_count,
            injector_flow_ccmin=injector_flow,
            target_afr=stoich,
        )
        self._req_fuel_inputs_label.setText(
            f"Inputs: {displacement:.0f} cc | {cylinder_count} cyl | {injector_flow:.0f} cc/min | stoich {stoich:.1f}"
        )
        if not result.is_valid:
            self._req_fuel_result_label.setText("Could not calculate reqFuel from the current inputs.")
            self._req_fuel_apply_btn.setEnabled(False)
            return
        result_lines = [
            f"Calculated reqFuel: {result.req_fuel_ms:.2f} ms (stored value {result.req_fuel_stored})."
        ]
        pressure_model = (
            generator_context.injector_pressure_model
            if generator_context and generator_context.injector_pressure_model is not None
            else self._effective_operator_context().injector_pressure_model
        )
        if pressure_model == "vacuum_referenced":
            result_lines.append("Pressure model: vacuum referenced.")
        elif pressure_model == "fixed_pressure":
            result_lines.append("Pressure model: fixed pressure (no compensation).")
        elif pressure_model in {"operator_specified", "not_modeled"}:
            result_lines.append("Pressure model: operator-specified pressure. Review reqFuel against measured rail pressure under load.")
        secondary_flow = self._secondary_injector_flow()
        if secondary_flow is not None:
            secondary_pressure = self._effective_operator_context().secondary_injector_reference_pressure_psi
            if secondary_pressure is None:
                result_lines.append("Secondary injectors are configured, but their reference pressure is not set.")
            else:
                result_lines.append(f"Secondary injector reference pressure: {secondary_pressure:.1f} psi.")
        self._req_fuel_result_label.setText(" ".join(result_lines))
        self._req_fuel_apply_btn.setEnabled(True)

    def _on_apply_req_fuel_clicked(self) -> None:
        generator_context = self._build_generator_context()
        operator_context = self._effective_operator_context()
        displacement = operator_context.displacement_cc or (generator_context.displacement_cc if generator_context else None)
        cylinder_count = (
            operator_context.cylinder_count
            or (generator_context.cylinder_count if generator_context else None)
            or self._get_tune_float("nCylinders")
        )
        injector_flow = (
            (generator_context.injector_flow_ccmin if generator_context else None)
            or (self._get_tune_float(self._resolve_injector_flow_param_name()) if self._resolve_injector_flow_param_name() else None)
        )
        stoich = (generator_context.stoich_ratio if generator_context and generator_context.stoich_ratio else None) or self._get_tune_float("stoich") or 14.7
        if not displacement or not cylinder_count or not injector_flow:
            self.status_message.emit("Enter displacement, cylinder count, and injector flow before applying reqFuel.")
            return
        result = RequiredFuelCalculatorService().calculate(
            displacement_cc=displacement,
            cylinder_count=cylinder_count,
            injector_flow_ccmin=injector_flow,
            target_afr=stoich,
        )
        if not result.is_valid:
            self.status_message.emit("Could not calculate reqFuel from the current inputs.")
            return
        snapshot = self._presenter.stage_named_parameter("reqFuel", str(result.req_fuel_ms))
        msg = self._presenter.consume_message() or "Calculated reqFuel staged."
        self.status_message.emit(msg)
        del snapshot
        self.refresh()
        self.workspace_state_changed.emit()

    def _refresh_fuel_trim_guidance(self) -> None:
        fuel_trim_param = self._get_definition_scalar("fuelTrimEnabled")
        if fuel_trim_param is None:
            _set_form_row_visible(self._fuel_trim_form, self._fuel_trim_enabled_combo, False)
            self._fuel_trim_summary_label.setText(
                "This definition does not expose individual fuel trims through a simple hardware-setup parameter."
            )
            return

        _set_form_row_visible(self._fuel_trim_form, self._fuel_trim_enabled_combo, True)
        blocker = QSignalBlocker(self._fuel_trim_enabled_combo)
        self._fuel_trim_enabled_combo.clear()
        if fuel_trim_param.options:
            for opt in fuel_trim_param.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._fuel_trim_enabled_combo.addItem(opt.label, opt.value)
        if self._fuel_trim_enabled_combo.count() == 0:
            self._fuel_trim_enabled_combo.addItem("Disabled", "0")
            self._fuel_trim_enabled_combo.addItem("Enabled", "1")
        del blocker

        enabled = False
        raw_enabled = self._get_tune_str("fuelTrimEnabled")
        if raw_enabled is not None:
            try:
                enabled = float(raw_enabled) > 0
            except (TypeError, ValueError):
                enabled = False
            idx = self._find_combo_by_value(self._fuel_trim_enabled_combo, raw_enabled)
            if idx >= 0:
                blocker = QSignalBlocker(self._fuel_trim_enabled_combo)
                self._fuel_trim_enabled_combo.setCurrentIndex(idx)
                del blocker

        cyl_count = self._get_tune_float("nCylinders") or 0.0
        fuel_channels = self._get_tune_float("nFuelChannels") or 0.0
        sequential = self._inj_layout_requires_cam_sync(self._injlayout_combo.currentIndex())
        trim_available = sequential and cyl_count > 0 and fuel_channels >= cyl_count

        if not sequential:
            self._fuel_trim_summary_label.setText(
                "Fuel trims stay hidden in normal use until injector layout is set to true sequential."
            )
            return
        if cyl_count <= 0 or fuel_channels <= 0:
            self._fuel_trim_summary_label.setText(
                "Set cylinder count and available fuel channels before enabling sequential fuel trims."
            )
            return
        if not trim_available:
            self._fuel_trim_summary_label.setText(
                f"Sequential fuel trims are not available yet: {int(cyl_count)} cylinders need at least {int(cyl_count)} fuel channels, but the tune exposes {int(fuel_channels)}."
            )
            return

        state = "enabled" if enabled else "disabled"
        self._fuel_trim_summary_label.setText(
            f"Sequential fuel trims are available for this setup and are currently {state}. "
            "Leave them off for first start unless you already need per-cylinder trim tables."
        )

    def _on_fuel_trim_enabled_changed(self, index: int) -> None:
        self._stage_combo("fuelTrimEnabled", self._fuel_trim_enabled_combo, index)

    def _on_generate_afr_table(self) -> None:
        try:
            snap = self._presenter.generate_and_stage_afr_table(
                self._resolve_afr_table_name(),
                operator_context=self._effective_operator_context(),
            )
            msg = self._presenter.consume_message() or ""
            if not msg:
                msg = snap.operation_log[-1].summary if snap.operation_log else "AFR target table staged."
        except Exception as exc:
            msg = f"AFR table generation failed: {exc}"
        self._afr_status_label.setText(self._format_generator_status(msg, task="afr"))
        self._afr_status_label.setVisible(True)
        self.status_message.emit(msg)
        self.workspace_state_changed.emit()

    def _on_generate_wue(self) -> None:
        try:
            snap = self._presenter.generate_and_stage_wue(
                operator_context=self._effective_operator_context()
            )
            msg = self._presenter.consume_message() or ""
            if not msg:
                msg = snap.operation_log[-1].summary if snap.operation_log else "WUE staged."
        except Exception as exc:
            msg = f"WUE generation failed: {exc}"
        self._wue_status_label.setText(self._format_generator_status(msg, task="startup"))
        self._wue_status_label.setVisible(True)
        self.status_message.emit(msg)
        self.workspace_state_changed.emit()

    def _on_generate_cranking_enrichment(self) -> None:
        try:
            snap = self._presenter.generate_and_stage_cranking_enrichment(
                operator_context=self._effective_operator_context()
            )
            msg = self._presenter.consume_message() or ""
            if not msg:
                msg = snap.operation_log[-1].summary if snap.operation_log else "Cranking enrichment staged."
        except Exception as exc:
            msg = f"Cranking enrichment generation failed: {exc}"
        self._crank_status_label.setText(self._format_generator_status(msg, task="startup"))
        self._crank_status_label.setVisible(True)
        self.status_message.emit(msg)
        self.workspace_state_changed.emit()

    def _on_generate_ase(self) -> None:
        try:
            snap = self._presenter.generate_and_stage_ase(
                operator_context=self._effective_operator_context()
            )
            msg = self._presenter.consume_message() or ""
            if not msg:
                msg = snap.operation_log[-1].summary if snap.operation_log else "ASE staged."
        except Exception as exc:
            msg = f"ASE generation failed: {exc}"
        self._ase_status_label.setText(self._format_generator_status(msg, task="startup"))
        self._ase_status_label.setVisible(True)
        self.status_message.emit(msg)
        self.workspace_state_changed.emit()

    # ------------------------------------------------------------------
    # Tab 5: Trigger / Decoder
    # ------------------------------------------------------------------

    def _build_trigger_tab(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(_note(
            "Configure the trigger wheel and ignition system. "
            "Missing tooth (36-1) is the most common pattern for aftermarket setups. "
            "Match your physical crank trigger wheel exactly."
        ))

        trig_grp = QGroupBox("Trigger Wheel")
        trig_form = QFormLayout(trig_grp)

        self._trig_pattern_combo = QComboBox()
        self._trig_pattern_combo.setToolTip("Crank trigger decoder pattern.")
        self._trig_pattern_combo.currentIndexChanged.connect(self._on_trig_pattern_changed)
        trig_form.addRow("Trigger pattern:", self._trig_pattern_combo)

        self._num_teeth_spin = QSpinBox()
        self._num_teeth_spin.setRange(0, 255)
        self._num_teeth_spin.setToolTip(
            "Total number of teeth on the crank trigger wheel "
            "(including the missing tooth gap — e.g. 36 for a 36-1 wheel)."
        )
        self._num_teeth_spin.valueChanged.connect(
            lambda v: self._stage_int("numTeeth", v)
        )
        trig_form.addRow("Primary teeth:", self._num_teeth_spin)

        self._missing_teeth_spin = QSpinBox()
        self._missing_teeth_spin.setRange(0, 255)
        self._missing_teeth_spin.setToolTip(
            "Number of missing teeth. 1 for 36-1, 2 for 60-2, etc."
        )
        self._missing_teeth_spin.valueChanged.connect(
            lambda v: self._stage_int("missingTeeth", v)
        )
        trig_form.addRow("Missing teeth:", self._missing_teeth_spin)

        layout.addWidget(trig_grp)

        summary_grp = QGroupBox("Trigger Summary")
        summary_layout = QVBoxLayout(summary_grp)
        summary_layout.setContentsMargins(8, 8, 8, 8)
        summary_layout.setSpacing(6)
        self._trigger_summary_label = QLabel()
        self._trigger_summary_label.setWordWrap(True)
        summary_layout.addWidget(self._trigger_summary_label)
        self._trigger_topology_label = QLabel()
        self._trigger_topology_label.setWordWrap(True)
        summary_layout.addWidget(self._trigger_topology_label)
        self._trigger_risk_label = QLabel()
        self._trigger_risk_label.setWordWrap(True)
        summary_layout.addWidget(self._trigger_risk_label)
        self._trigger_power_cycle_label = _warn(
            "Trigger and ignition mode changes should be power-cycled before timing checks or first start."
        )
        summary_layout.addWidget(self._trigger_power_cycle_label)
        layout.addWidget(summary_grp)

        preset_grp = QGroupBox("Ignition Hardware Preset")
        preset_layout = QVBoxLayout(preset_grp)
        preset_layout.setContentsMargins(8, 8, 8, 8)
        preset_layout.setSpacing(6)
        preset_layout.addWidget(_note(
            "Load a reviewed starter preset for common ignition hardware. "
            "The preset fills the wizard draft only; click Apply before writing or burning."
        ))
        preset_row = QHBoxLayout()
        self._ignition_preset_combo = QComboBox()
        self._ignition_preset_combo.addItem("Choose ignition preset...", None)
        for preset in self._hardware_preset_service.ignition_presets():
            self._ignition_preset_combo.addItem(preset.label, preset)
        preset_row.addWidget(self._ignition_preset_combo, 1)
        self._ignition_preset_btn = QPushButton("Load Preset")
        self._ignition_preset_btn.clicked.connect(self._on_apply_ignition_preset)
        preset_row.addWidget(self._ignition_preset_btn)
        preset_layout.addLayout(preset_row)
        self._ignition_preset_summary = QLabel("")
        self._ignition_preset_summary.setWordWrap(True)
        self._ignition_preset_summary.setVisible(False)
        preset_layout.addWidget(self._ignition_preset_summary)
        self._ignition_preset_note = QLabel("")
        self._ignition_preset_note.setWordWrap(True)
        self._ignition_preset_note.setVisible(False)
        preset_layout.addWidget(self._ignition_preset_note)
        layout.addWidget(preset_grp)

        ign_grp = QGroupBox("Ignition System")
        ign_form = QFormLayout(ign_grp)
        self._ign_form = ign_form

        self._spark_mode_combo = QComboBox()
        self._spark_mode_combo.setToolTip(
            "Wasted Spark: pairs cylinders (most common, no cam sync needed).\n"
            "Wasted COP: individual coils, no cam sync needed.\n"
            "Sequential: requires cam sync signal."
        )
        self._spark_mode_combo.currentIndexChanged.connect(self._on_spark_mode_changed)
        ign_form.addRow("Spark mode:", self._spark_mode_combo)

        self._cam_input_param_name = self._first_definition_scalar_name(
            ("camInput", "secondTrigger", "secondaryTrigger", "camSignal", "trigPatternSec")
        )
        self._cam_input_combo = QComboBox()
        self._cam_input_combo.setToolTip(
            "Secondary trigger / cam-sync input. Required for sequential ignition strategies."
        )
        self._cam_input_combo.currentIndexChanged.connect(self._on_cam_input_changed)
        ign_form.addRow("Cam / sync input:", self._cam_input_combo)

        self._dwell_crank_spin = QDoubleSpinBox()
        self._dwell_crank_spin.setRange(0.0, 25.0)
        self._dwell_crank_spin.setSingleStep(0.1)
        self._dwell_crank_spin.setDecimals(1)
        self._dwell_crank_spin.setSuffix(" ms")
        self._dwell_crank_spin.setToolTip(
            "Dwell time during cranking. Usually slightly higher than running dwell "
            "to ensure a strong spark at low cranking RPM. Typical: 4–6 ms."
        )
        self._dwell_crank_spin.valueChanged.connect(
            lambda v: self._stage_float("dwellcrank", v)
        )
        ign_form.addRow("Cranking dwell:", self._dwell_crank_spin)

        self._dwell_run_spin = QDoubleSpinBox()
        self._dwell_run_spin.setRange(0.0, 8.0)
        self._dwell_run_spin.setSingleStep(0.1)
        self._dwell_run_spin.setDecimals(1)
        self._dwell_run_spin.setSuffix(" ms")
        self._dwell_run_spin.setToolTip(
            "Running dwell — coil charge time while the engine is running. "
            "Setting too high can damage coils. Typical: 3–4 ms. "
            "Check your coil's datasheet."
        )
        self._dwell_run_spin.valueChanged.connect(
            lambda v: self._stage_float("dwellrun", v)
        )
        ign_form.addRow("Running dwell:", self._dwell_run_spin)

        layout.addWidget(ign_grp)

        checklist_grp = QGroupBox("Ignition / Trigger Checklist")
        checklist_layout = QVBoxLayout(checklist_grp)
        checklist_layout.setContentsMargins(8, 8, 8, 8)
        checklist_layout.setSpacing(6)
        checklist_layout.addWidget(_note(
            "Cross-checks dwell, trigger geometry, reference angle, knock input, and related setup dependencies."
        ))
        self._trigger_checklist_label = QLabel()
        self._trigger_checklist_label.setWordWrap(True)
        self._trigger_checklist_label.setTextFormat(Qt.TextFormat.RichText)
        checklist_layout.addWidget(self._trigger_checklist_label)
        layout.addWidget(checklist_grp)

        gen_grp = QGroupBox("Starter Ignition Table")
        gen_layout = QVBoxLayout(gen_grp)
        gen_layout.addWidget(_note(
            "Generate a conservative ignition advance table based on compression "
            "ratio and calibration intent. The result is staged for your review — "
            "it is never applied automatically."
        ))
        self._gen_spark_btn = QPushButton("Generate Spark Table...")
        self._gen_spark_btn.setToolTip(
            "Generates a conservative 16 × 16 ignition advance table and stages it "
            "for review. Set compression ratio on the Engine Setup tab first."
        )
        self._gen_spark_btn.clicked.connect(self._on_generate_spark_table)
        self._gen_spark_label = QLabel()
        self._gen_spark_label.setWordWrap(True)
        self._gen_spark_label.setVisible(False)
        gen_layout.addWidget(self._gen_spark_btn)
        gen_layout.addWidget(self._gen_spark_label)
        layout.addWidget(gen_grp)

        layout.addWidget(_reboot_note())
        layout.addStretch(1)

        self._tabs.addTab(_scroll_wrap(container), "Trigger")

    def _refresh_trigger_tab(self) -> None:
        from PySide6.QtCore import QSignalBlocker

        # TrigPattern combo
        b = QSignalBlocker(self._trig_pattern_combo)
        self._trig_pattern_combo.clear()
        param = self._get_definition_scalar("TrigPattern")
        if param and param.options:
            for opt in param.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._trig_pattern_combo.addItem(opt.label, opt.value)
        if self._trig_pattern_combo.count() == 0:
            self._trig_pattern_combo.addItem("Missing Tooth")
        del b

        raw_tp = self._get_tune_str("TrigPattern")
        if raw_tp is not None:
            idx = self._find_combo_by_value(self._trig_pattern_combo, raw_tp)
            if idx >= 0:
                b2 = QSignalBlocker(self._trig_pattern_combo)
                self._trig_pattern_combo.setCurrentIndex(idx)
                del b2

        # sparkMode combo
        b3 = QSignalBlocker(self._spark_mode_combo)
        self._spark_mode_combo.clear()
        sp = self._get_definition_scalar("sparkMode")
        if sp and sp.options:
            for opt in sp.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._spark_mode_combo.addItem(opt.label, opt.value)
        if self._spark_mode_combo.count() == 0:
            for label in ("Wasted Spark", "Single Channel", "Wasted COP", "Sequential"):
                self._spark_mode_combo.addItem(label)
        del b3

        raw_sm = self._get_tune_str("sparkMode")
        spark_idx = 0
        if raw_sm is not None:
            idx = self._find_combo_by_value(self._spark_mode_combo, raw_sm)
            if idx >= 0:
                b4 = QSignalBlocker(self._spark_mode_combo)
                self._spark_mode_combo.setCurrentIndex(idx)
                del b4
                spark_idx = idx

        self._cam_input_param_name = self._first_definition_scalar_name(
            ("camInput", "secondTrigger", "secondaryTrigger", "camSignal", "trigPatternSec")
        )
        b_cam = QSignalBlocker(self._cam_input_combo)
        self._cam_input_combo.clear()
        if self._cam_input_param_name is not None:
            cam_param = self._get_definition_scalar(self._cam_input_param_name)
            if cam_param and cam_param.options:
                for opt in cam_param.options:
                    if opt.label and opt.label.upper() != "INVALID":
                        self._cam_input_combo.addItem(opt.label, opt.value)
            if self._cam_input_combo.count() == 0:
                self._cam_input_combo.addItem("(configure in definition-backed page)")
            raw_cam = self._get_tune_str(self._cam_input_param_name)
            if raw_cam is not None:
                idx = self._find_combo_by_value(self._cam_input_combo, raw_cam)
                if idx >= 0:
                    self._cam_input_combo.setCurrentIndex(idx)
        del b_cam
        self._update_cam_input_visibility(spark_idx)

        for name, spin in (
            ("numTeeth", self._num_teeth_spin),
            ("missingTeeth", self._missing_teeth_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(int(raw))
                del bx

        for name, spin in (
            ("dwellcrank", self._dwell_crank_spin),
            ("dwellrun", self._dwell_run_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(raw)
                del bx
        operator_context = self._effective_operator_context()
        b_preset = QSignalBlocker(self._ignition_preset_combo)
        self._ignition_preset_combo.setCurrentIndex(0)
        for index in range(1, self._ignition_preset_combo.count()):
            preset = self._ignition_preset_combo.itemData(index)
            if isinstance(preset, IgnitionHardwarePreset) and preset.key == operator_context.ignition_preset_key:
                self._ignition_preset_combo.setCurrentIndex(index)
                break
        del b_preset
        self._refresh_ignition_preset_summary()
        self._refresh_trigger_summary()
        self._refresh_trigger_checklist()

    def _refresh_trigger_summary(self) -> None:
        pattern = self._trig_pattern_combo.currentText().strip() or "Unknown pattern"
        teeth = int(self._num_teeth_spin.value())
        missing = int(self._missing_teeth_spin.value())
        spark_mode = self._spark_mode_combo.currentText().strip() or "Unknown spark mode"
        spark_requires_cam = self._spark_mode_requires_cam_sync(self._spark_mode_combo.currentIndex())
        injector_layout = self._injlayout_combo.currentText().strip() or "Unknown injector layout"
        injection_requires_cam = self._inj_layout_requires_cam_sync(self._injlayout_combo.currentIndex())
        trigger_cam_requirement = self._trigger_cam_requirement(pattern)
        cam_available = self._cam_input_param_name is not None and self._cam_input_combo.count() > 0
        cam_text = self._cam_input_combo.currentText().strip() if cam_available else "not exposed"
        if not spark_requires_cam and not injection_requires_cam and trigger_cam_requirement == "not_used":
            cam_text = "not required"

        wheel_text = "wheel not configured"
        if teeth > 0:
            wheel_text = f"{teeth}-{missing}" if missing > 0 else f"{teeth}-tooth"
        self._trigger_summary_label.setText(
            f"Pattern: {pattern} | Wheel: {wheel_text} | Spark mode: {spark_mode} | Fuel mode: {injector_layout} | Cam sync: {cam_text}"
        )

        if trigger_cam_requirement == "required":
            self._trigger_topology_label.setText("Trigger topology: crank + cam required by the selected decoder.")
        elif trigger_cam_requirement == "optional":
            self._trigger_topology_label.setText("Trigger topology: crank trigger with optional cam / secondary sync available.")
        elif spark_requires_cam and injection_requires_cam:
            self._trigger_topology_label.setText("Trigger topology: crank trigger plus cam sync required for sequential fuel and spark modes.")
        elif spark_requires_cam:
            self._trigger_topology_label.setText("Trigger topology: crank trigger plus cam sync required for sequential spark mode.")
        elif injection_requires_cam:
            self._trigger_topology_label.setText("Trigger topology: crank trigger plus cam sync required for sequential fuel mode.")
        else:
            self._trigger_topology_label.setText("Trigger topology: crank-only trigger.")

        risks: list[str] = []
        if teeth > 0 and missing >= teeth:
            risks.append("Missing-tooth count must be less than total teeth or the ECU cannot sync.")
        elif teeth > 0 and missing >= max(1, teeth // 2):
            risks.append("Missing-tooth count is unusually large for the selected wheel. Recheck the physical trigger wheel.")
        cam_unassigned = cam_text.lower() in {"off", "none", "unassigned", "invalid", "", "(configure in definition-backed page)"}
        if trigger_cam_requirement == "required":
            if not cam_available:
                risks.append("The selected decoder needs a cam/secondary trigger input, but no cam-sync parameter is exposed on this page.")
            elif cam_unassigned:
                risks.append("The selected decoder needs a cam/secondary trigger input, but it is not assigned.")
        if spark_requires_cam:
            if not cam_available:
                risks.append("Sequential spark mode needs a cam/secondary trigger input before the engine can be timed correctly.")
            elif cam_unassigned:
                risks.append("Sequential spark mode is selected but the cam/secondary trigger input is not assigned.")
        if injection_requires_cam:
            if not cam_available:
                risks.append("Sequential fuel mode needs a cam/secondary trigger input before fully sequential injection can work.")
            elif cam_unassigned:
                risks.append("Sequential fuel mode is selected but the cam/secondary trigger input is not assigned.")
        dwell_run = self._get_tune_float("dwellrun")
        if dwell_run is not None and dwell_run > 6.0:
            risks.append("Running dwell is higher than the typical 1–6 ms range. Verify against the coil datasheet.")
        if not risks:
            risks.append("No immediate trigger-pattern risks detected. Confirm final timing with a timing light after power cycle.")
            self._trigger_risk_label.setStyleSheet(f"color: {_NOTE_TEXT_COLOR};")
        else:
            self._trigger_risk_label.setStyleSheet("color: #c0392b; font-weight: bold;")
        self._trigger_risk_label.setText("Known risks: " + " ".join(risks))

    def _refresh_trigger_checklist(self) -> None:
        ignition_page = None
        trigger_page = None
        for group in self._presenter.page_groups:
            for page in group.pages:
                page_kind = self._presenter.hardware_setup_summary_service._page_kind(page)  # noqa: SLF001
                if page_kind == "ignition" and ignition_page is None:
                    ignition_page = page
                elif page_kind == "trigger" and trigger_page is None:
                    trigger_page = page

        items = self._presenter.ignition_trigger_cross_validation_service.validate(
            ignition_page=ignition_page,
            trigger_page=trigger_page,
            edits=self._presenter.local_tune_edit_service,
        )
        capability_item = self._connected_trigger_capability_item()
        if capability_item is not None:
            items = items + (capability_item,)
        self._render_checklist_items(
            items,
            self._trigger_checklist_label,
            empty_message="No ignition/trigger checklist items are available for this definition.",
        )

    def _connected_trigger_capability_item(self) -> SetupChecklistItem | None:
        snapshot = self._presenter.current_runtime_snapshot
        if snapshot is None:
            return None
        telemetry = self._speeduino_runtime_telemetry_service.decode(snapshot)
        caps = telemetry.board_capabilities
        if caps.raw_value is None:
            return None
        if caps.unrestricted_interrupts:
            return SetupChecklistItem(
                key="connected_interrupt_capability",
                title="Connected board interrupt capability",
                status=ChecklistItemStatus.OK,
                detail=(
                    "The connected board advertises unrestricted interrupts. "
                    "Trigger input placement is less constrained than on restricted-interrupt hardware."
                ),
            )
        return SetupChecklistItem(
            key="connected_interrupt_capability",
            title="Connected board interrupt capability",
            status=ChecklistItemStatus.WARNING,
            detail=(
                "The connected board does not advertise unrestricted interrupts. "
                "Verify crank and cam inputs use interrupt-capable pins before first start."
            ),
        )

    def _on_apply_ignition_preset(self) -> None:
        preset = self._ignition_preset_combo.currentData()
        if not isinstance(preset, IgnitionHardwarePreset):
            self._ignition_preset_note.setText("Choose an ignition preset first.")
            self._ignition_preset_note.setVisible(True)
            return

        self._stage_float("dwellrun", preset.running_dwell_ms)
        self._stage_float("dwellcrank", preset.cranking_dwell_ms)
        self._queue_context_update(ignition_preset_key=preset.key)
        self._dwell_run_spin.setValue(preset.running_dwell_ms)
        self._dwell_crank_spin.setValue(preset.cranking_dwell_ms)

        note = (
            f"{preset.description} Loaded {preset.running_dwell_ms:.1f} ms running dwell"
            f" and {preset.cranking_dwell_ms:.1f} ms cranking dwell. "
            f"[{self._hardware_preset_service.source_confidence_label(source_note=preset.source_note, source_url=preset.source_url)}] {preset.source_note} Click Apply to stage the preset."
        )
        self._ignition_preset_note.setText(note)
        self._ignition_preset_note.setVisible(True)
        self._refresh_ignition_preset_summary()
        self._refresh_trigger_summary()
        self._refresh_trigger_checklist()

    def _refresh_ignition_preset_summary(self) -> None:
        context = self._effective_operator_context()
        key = context.ignition_preset_key
        if not key:
            self._ignition_preset_summary.setVisible(False)
            return
        preset = next((item for item in self._hardware_preset_service.ignition_presets() if item.key == key), None)
        if preset is None:
            self._ignition_preset_summary.setVisible(False)
            return
        self._ignition_preset_summary.setText(
            f"Current ignition profile: {preset.label} | Dwell {preset.running_dwell_ms:.1f}/{preset.cranking_dwell_ms:.1f} ms"
            f" | Source: [{self._hardware_preset_service.source_confidence_label(source_note=preset.source_note, source_url=preset.source_url)}] {preset.source_note}"
        )
        self._ignition_preset_summary.setVisible(True)

    @staticmethod
    def _normalize_preset_label(text: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else " " for ch in text).strip()

    def _find_wideband_preset(self, key: str | None) -> WidebandHardwarePreset | None:
        if not key:
            return None
        return next(
            (item for item in self._hardware_preset_service.wideband_presets() if item.key == key),
            None,
        )

    def _selected_wideband_reference_label(self) -> str | None:
        if self._wideband_reference_table is None or self._wideband_ref_combo.count() == 0:
            return None
        label = self._wideband_ref_combo.currentText().strip()
        if not label or label.startswith("(no AFR presets exposed)"):
            return None
        return label

    def _find_wideband_reference_index_by_label(self, label: str | None) -> int:
        if not label:
            return -1
        for index in range(self._wideband_ref_combo.count()):
            if self._wideband_ref_combo.itemText(index).strip() == label.strip():
                return index
        return -1

    def _match_wideband_reference_solution_index(self, preset: WidebandHardwarePreset | None) -> int:
        if preset is None or self._wideband_reference_table is None:
            return -1
        aliases = {self._normalize_preset_label(alias) for alias in preset.reference_table_aliases}
        if not aliases:
            return -1
        for index, solution in enumerate(self._wideband_reference_table.solutions):
            label = self._normalize_preset_label(solution.label)
            if any(alias in label for alias in aliases):
                return index
        return -1

    def _refresh_wideband_preset_summary(self) -> None:
        preset = self._find_wideband_preset(self._effective_operator_context().wideband_preset_key)
        if preset is None:
            self._wideband_preset_summary.setVisible(False)
            return
        lines = [
            f"Current wideband controller: {preset.label}",
            f"AFR: {preset.afr_equation}",
            f"Lambda: {preset.lambda_equation}",
            f"Source: [{self._hardware_preset_service.source_confidence_label(source_note=preset.source_note, source_url=preset.source_url)}] {preset.source_note}",
        ]
        self._wideband_preset_summary.setText(" | ".join(lines))
        self._wideband_preset_summary.setVisible(True)

    def _apply_pressure_preset(
        self,
        preset: PressureSensorPreset | None,
        *,
        min_param: str,
        max_param: str,
        min_spin: QDoubleSpinBox,
        max_spin: QDoubleSpinBox,
        note_label: QLabel,
        enable_param: str | None = None,
        enable_combo: QComboBox | None = None,
        pin_param: str | None = None,
        pin_combo: QComboBox | None = None,
    ) -> None:
        if preset is None:
            note_label.setText("Choose a sensor preset first.")
            note_label.setVisible(True)
            return
        if enable_param is not None and enable_combo is not None:
            enable_combo.setCurrentIndex(1)
        if pin_param is not None and pin_combo is not None:
            self._stage_profile_default_if_missing(pin_param, pin_combo)
        self._stage_float(min_param, preset.minimum_value)
        self._stage_float(max_param, preset.maximum_value)
        min_spin.setValue(preset.minimum_value)
        max_spin.setValue(preset.maximum_value)
        note_label.setText(
            f"{preset.description} Loaded {preset.minimum_value:.0f}-{preset.maximum_value:.0f} {preset.units}. "
            f"[{self._hardware_preset_service.source_confidence_label(source_note=preset.source_note, source_url=preset.source_url)}] {preset.source_note} Click Apply to stage the preset."
        )
        note_label.setVisible(True)

    # ------------------------------------------------------------------
    # Tab 5: Sensors
    # ------------------------------------------------------------------

    def _build_sensor_tab(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ---- O2 / Lambda ----
        o2_grp = QGroupBox("Oxygen / Lambda Sensor")
        o2_form = QFormLayout(o2_grp)
        self._o2_form = o2_form

        self._ego_type_combo = QComboBox()
        self._ego_type_combo.setToolTip(
            "Disabled: no O2 correction.\n"
            "Narrow Band: standard 0–1 V sensor, limited accuracy.\n"
            "Wide Band: wide-range sensor (0–5 V or CAN), required for autotune."
        )
        self._ego_type_combo.currentIndexChanged.connect(self._on_ego_type_changed)
        o2_form.addRow("O2 sensor type:", self._ego_type_combo)

        self._stoich_sensor_spin = QDoubleSpinBox()
        self._stoich_sensor_spin.setRange(0.0, 25.5)
        self._stoich_sensor_spin.setSingleStep(0.1)
        self._stoich_sensor_spin.setDecimals(1)
        self._stoich_sensor_spin.setSuffix(" :1")
        self._stoich_sensor_spin.setToolTip(
            "Stoichiometric AFR for your fuel. Petrol ≈ 14.7, E85 ≈ 9.8, methanol ≈ 6.5."
        )
        self._stoich_sensor_spin.valueChanged.connect(
            lambda v: self._stage_float("stoich", v)
        )
        o2_form.addRow("Stoich AFR:", self._stoich_sensor_spin)

        self._wideband_cal_param_name = self._first_definition_scalar_name(
            ("afrCal", "widebandCal", "lambdaCal", "afrcal", "widebandcal", "lambdacal")
        )
        self._wideband_cal_spin = QDoubleSpinBox()
        self._wideband_cal_spin.setRange(0.0, 25.5)
        self._wideband_cal_spin.setSingleStep(0.1)
        self._wideband_cal_spin.setDecimals(2)
        self._wideband_cal_spin.setSuffix(" :1")
        self._wideband_cal_spin.setToolTip(
            "Wideband calibration / reference value exposed by the loaded definition."
        )
        self._wideband_cal_spin.valueChanged.connect(self._on_wideband_cal_changed)
        o2_form.addRow("Wideband calibration:", self._wideband_cal_spin)

        self._wideband_cal_note = _note(
            "Wideband is enabled. Verify calibration on the related sensor or EGO setup page before trusting logs or autotune."
        )
        o2_form.addRow(self._wideband_cal_note)
        self._wideband_preset_combo = QComboBox()
        self._wideband_preset_combo.addItem("Manual / not set", None)
        for preset in self._hardware_preset_service.wideband_presets():
            self._wideband_preset_combo.addItem(preset.label, preset)
        self._wideband_preset_combo.setToolTip(
            "Common wideband controller presets with known analog equations. "
            "These help match the controller hardware to the ECU definition's calibration path."
        )
        self._wideband_preset_combo.currentIndexChanged.connect(self._on_wideband_preset_changed)
        o2_form.addRow("Wideband controller:", self._wideband_preset_combo)
        self._wideband_preset_summary = _note("")
        self._wideband_preset_summary.setVisible(False)
        o2_form.addRow(self._wideband_preset_summary)
        self._wideband_reference_table = None
        self._wideband_ref_group = QWidget()
        self._wideband_ref_layout = QVBoxLayout(self._wideband_ref_group)
        self._wideband_ref_layout.setContentsMargins(0, 0, 0, 0)
        self._wideband_ref_layout.setSpacing(4)
        self._wideband_ref_combo = QComboBox()
        self._wideband_ref_combo.setToolTip(
            "AFR calibration presets exposed by the current definition's AFR/O2 reference table."
        )
        self._wideband_ref_combo.currentIndexChanged.connect(self._on_wideband_reference_changed)
        self._wideband_ref_note = _note("")
        self._wideband_ref_note.setVisible(False)
        self._wideband_ref_layout.addWidget(self._wideband_ref_combo)
        self._wideband_ref_layout.addWidget(self._wideband_ref_note)
        o2_form.addRow("AFR calibration preset:", self._wideband_ref_group)
        layout.addWidget(o2_grp)

        afr_protect_grp = QGroupBox("AFR Lean Protection")
        self._afr_protect_form = QFormLayout(afr_protect_grp)
        self._afr_protect_form.addRow(_note(
            "Optional safety cut for lean conditions under load. This is most useful once wideband setup is correct."
        ))

        self._engine_protect_type_combo = QComboBox()
        self._engine_protect_type_combo.setToolTip(
            "Determines whether engine protection cuts spark, fuel, or both when a protection condition triggers."
        )
        self._engine_protect_type_combo.currentIndexChanged.connect(self._on_engine_protect_type_changed)
        self._afr_protect_form.addRow("Protection cut:", self._engine_protect_type_combo)

        self._engine_protect_rpm_spin = QDoubleSpinBox()
        self._engine_protect_rpm_spin.setRange(0.0, 30000.0)
        self._engine_protect_rpm_spin.setSingleStep(100.0)
        self._engine_protect_rpm_spin.setDecimals(0)
        self._engine_protect_rpm_spin.setSuffix(" rpm")
        self._engine_protect_rpm_spin.setToolTip(
            "Minimum RPM above which engine protection is allowed to act."
        )
        self._engine_protect_rpm_spin.valueChanged.connect(lambda v: self._stage_float("engineProtectMaxRPM", v))
        self._afr_protect_form.addRow("Protection RPM limit:", self._engine_protect_rpm_spin)

        self._afr_protect_mode_combo = QComboBox()
        self._afr_protect_mode_combo.setToolTip(
            "Fixed mode uses a fixed AFR/lambda ceiling. Table mode allows deviation from the target table."
        )
        self._afr_protect_mode_combo.currentIndexChanged.connect(self._on_afr_protect_mode_changed)
        self._afr_protect_form.addRow("AFR protection mode:", self._afr_protect_mode_combo)

        self._afr_protect_map_spin = QDoubleSpinBox()
        self._afr_protect_map_spin.setRange(0.0, 600.0)
        self._afr_protect_map_spin.setSingleStep(1.0)
        self._afr_protect_map_spin.setDecimals(0)
        self._afr_protect_map_spin.setSuffix(" kPa")
        self._afr_protect_map_spin.valueChanged.connect(lambda v: self._stage_float("afrProtectMAP", v))
        self._afr_protect_form.addRow("Minimum MAP:", self._afr_protect_map_spin)

        self._afr_protect_rpm_threshold_spin = QDoubleSpinBox()
        self._afr_protect_rpm_threshold_spin.setRange(0.0, 30000.0)
        self._afr_protect_rpm_threshold_spin.setSingleStep(100.0)
        self._afr_protect_rpm_threshold_spin.setDecimals(0)
        self._afr_protect_rpm_threshold_spin.setSuffix(" rpm")
        self._afr_protect_rpm_threshold_spin.valueChanged.connect(lambda v: self._stage_float("afrProtectRPM", v))
        self._afr_protect_form.addRow("Minimum engine RPM:", self._afr_protect_rpm_threshold_spin)

        self._afr_protect_tps_spin = QDoubleSpinBox()
        self._afr_protect_tps_spin.setRange(0.0, 100.0)
        self._afr_protect_tps_spin.setSingleStep(0.5)
        self._afr_protect_tps_spin.setDecimals(1)
        self._afr_protect_tps_spin.setSuffix(" %")
        self._afr_protect_tps_spin.valueChanged.connect(lambda v: self._stage_float("afrProtectTPS", v))
        self._afr_protect_form.addRow("Minimum TPS:", self._afr_protect_tps_spin)

        self._afr_protect_afr_spin = QDoubleSpinBox()
        self._afr_protect_afr_spin.setRange(0.0, 25.5)
        self._afr_protect_afr_spin.setSingleStep(0.1)
        self._afr_protect_afr_spin.setDecimals(1)
        self._afr_protect_afr_spin.setSuffix(" AFR")
        self._afr_protect_afr_spin.valueChanged.connect(lambda v: self._stage_float("afrProtectDeviation", v))
        self._afr_protect_form.addRow("Maximum AFR:", self._afr_protect_afr_spin)

        self._afr_protect_cut_time_spin = QDoubleSpinBox()
        self._afr_protect_cut_time_spin.setRange(0.0, 10.0)
        self._afr_protect_cut_time_spin.setSingleStep(0.1)
        self._afr_protect_cut_time_spin.setDecimals(1)
        self._afr_protect_cut_time_spin.setSuffix(" s")
        self._afr_protect_cut_time_spin.valueChanged.connect(lambda v: self._stage_float("afrProtectCutTime", v))
        self._afr_protect_form.addRow("Time before cut:", self._afr_protect_cut_time_spin)

        self._afr_protect_reactivation_tps_spin = QDoubleSpinBox()
        self._afr_protect_reactivation_tps_spin.setRange(0.0, 100.0)
        self._afr_protect_reactivation_tps_spin.setSingleStep(0.5)
        self._afr_protect_reactivation_tps_spin.setDecimals(1)
        self._afr_protect_reactivation_tps_spin.setSuffix(" %")
        self._afr_protect_reactivation_tps_spin.valueChanged.connect(
            lambda v: self._stage_float("afrProtectReactivationTPS", v)
        )
        self._afr_protect_form.addRow("Reactivate below TPS:", self._afr_protect_reactivation_tps_spin)
        layout.addWidget(afr_protect_grp)

        sensor_summary_grp = QGroupBox("Sensor Summary")
        sensor_summary_layout = QVBoxLayout(sensor_summary_grp)
        sensor_summary_layout.setContentsMargins(8, 8, 8, 8)
        sensor_summary_layout.setSpacing(6)
        self._sensor_summary_label = QLabel()
        self._sensor_summary_label.setWordWrap(True)
        sensor_summary_layout.addWidget(self._sensor_summary_label)
        self._sensor_risk_label = QLabel()
        self._sensor_risk_label.setWordWrap(True)
        sensor_summary_layout.addWidget(self._sensor_risk_label)
        self._sensor_power_cycle_label = _warn(
            "Recheck sensor readings after calibration or sensor-mode changes before trusting logs, EGO correction, or autotune."
        )
        sensor_summary_layout.addWidget(self._sensor_power_cycle_label)
        layout.addWidget(sensor_summary_grp)

        sensor_checklist_grp = QGroupBox("Sensor Checklist")
        sensor_checklist_layout = QVBoxLayout(sensor_checklist_grp)
        sensor_checklist_layout.setContentsMargins(8, 8, 8, 8)
        sensor_checklist_layout.setSpacing(6)
        sensor_checklist_layout.addWidget(_note(
            "Use this as the last sensor-config sanity pass before enabling corrections, logs, or autotune."
        ))
        self._sensor_checklist_label = QLabel()
        self._sensor_checklist_label.setWordWrap(True)
        self._sensor_checklist_label.setTextFormat(Qt.TextFormat.RichText)
        sensor_checklist_layout.addWidget(self._sensor_checklist_label)
        layout.addWidget(sensor_checklist_grp)

        # ---- TPS Calibration ----
        tps_grp = QGroupBox("Throttle Position Sensor (TPS)")
        tps_form = QFormLayout(tps_grp)
        tps_form.addRow(_note(
            "Raw ADC counts at 0 % and 100 % throttle. "
            "Calibrate with the throttle closed then fully open."
        ))

        self._tps_min_spin = QSpinBox()
        self._tps_min_spin.setRange(0, 1023)
        self._tps_min_spin.setToolTip("ADC reading at fully closed throttle (0 %).")
        self._tps_min_spin.valueChanged.connect(lambda v: self._stage_int("tpsMin", v))
        tps_form.addRow("TPS min (closed):", self._tps_min_spin)

        self._tps_max_spin = QSpinBox()
        self._tps_max_spin.setRange(0, 1023)
        self._tps_max_spin.setToolTip("ADC reading at fully open throttle (100 %).")
        self._tps_max_spin.valueChanged.connect(lambda v: self._stage_int("tpsMax", v))
        tps_form.addRow("TPS max (open):", self._tps_max_spin)
        layout.addWidget(tps_grp)

        # ---- MAP Sensor ----
        map_grp = QGroupBox("MAP Sensor")
        map_form = QFormLayout(map_grp)
        map_form.addRow(_note(
            "Voltage-to-pressure calibration for the manifold absolute pressure sensor. "
            "Common values: GM 1-bar (20–105 kPa), 2-bar (20–200 kPa), 3-bar (20–300 kPa)."
        ))

        self._map_min_spin = QDoubleSpinBox()
        self._map_min_spin.setRange(0.0, 400.0)
        self._map_min_spin.setSingleStep(1.0)
        self._map_min_spin.setDecimals(0)
        self._map_min_spin.setSuffix(" kPa")
        self._map_min_spin.setToolTip("Pressure reading at 0 V (fully open vacuum).")
        self._map_min_spin.valueChanged.connect(self._on_map_min_changed)
        map_form.addRow("MAP at 0 V:", self._map_min_spin)

        self._map_max_spin = QDoubleSpinBox()
        self._map_max_spin.setRange(0.0, 800.0)
        self._map_max_spin.setSingleStep(1.0)
        self._map_max_spin.setDecimals(0)
        self._map_max_spin.setSuffix(" kPa")
        self._map_max_spin.setToolTip("Pressure reading at 5 V (maximum sensor output).")
        self._map_max_spin.valueChanged.connect(self._on_map_max_changed)
        map_form.addRow("MAP at 5 V:", self._map_max_spin)
        self._map_preset_combo = QComboBox()
        self._map_preset_combo.addItem("Manual / not set", None)
        for preset in self._hardware_preset_service.map_sensor_presets():
            self._map_preset_combo.addItem(preset.label, preset)
        self._map_preset_combo.setToolTip("Load a common MAP sensor calibration range into the draft values.")
        map_form.addRow("MAP sensor preset:", self._map_preset_combo)
        self._map_preset_button = QPushButton("Load MAP Preset")
        self._map_preset_button.clicked.connect(self._on_apply_map_preset)
        map_form.addRow("", self._map_preset_button)
        self._map_preset_note = _note("")
        self._map_preset_note.setVisible(False)
        map_form.addRow(self._map_preset_note)
        self._map_preset_summary = _note("")
        self._map_preset_summary.setVisible(False)
        map_form.addRow(self._map_preset_summary)

        self._map_sample_combo = QComboBox()
        self._map_sample_combo.setToolTip(
            "Instantaneous: raw reading — most responsive.\n"
            "Cycle Average: average over one engine cycle — smoother.\n"
            "Cycle Minimum: lowest reading per cycle — vacuum-based fuelling.\n"
            "Event Average: average over the injection event."
        )
        self._map_sample_combo.currentIndexChanged.connect(
            lambda idx: self._stage_combo("mapSample", self._map_sample_combo, idx)
        )
        map_form.addRow("MAP sampling:", self._map_sample_combo)
        layout.addWidget(map_grp)

        # ---- Flex Fuel ----
        flex_grp = QGroupBox("Flex Fuel Sensor")
        flex_form = QFormLayout(flex_grp)
        self._flex_form = flex_form
        flex_form.addRow(_note(
            "Enable this when an ethanol-content sensor is installed. "
            "Standard GM/Continental flex sensors are typically 50 Hz at E0 and 150 Hz at E100."
        ))

        self._flex_enable_combo = QComboBox()
        self._flex_enable_combo.addItems(["Disabled", "Enabled"])
        self._flex_enable_combo.setToolTip(
            "Enable the flex fuel sensor input and ethanol-based fuel, ignition, and boost corrections."
        )
        self._flex_enable_combo.currentIndexChanged.connect(self._on_flex_enable_changed)
        flex_form.addRow("Flex fuel sensor:", self._flex_enable_combo)

        self._flex_freq_low_spin = QDoubleSpinBox()
        self._flex_freq_low_spin.setRange(0.0, 500.0)
        self._flex_freq_low_spin.setSingleStep(1.0)
        self._flex_freq_low_spin.setDecimals(0)
        self._flex_freq_low_spin.setSuffix(" Hz")
        self._flex_freq_low_spin.setToolTip("Sensor frequency at 0% ethanol (E0). Standard GM/Continental: 50 Hz.")
        self._flex_freq_low_spin.valueChanged.connect(lambda v: self._stage_float("flexFreqLow", v))
        flex_form.addRow("Low frequency (E0):", self._flex_freq_low_spin)

        self._flex_freq_high_spin = QDoubleSpinBox()
        self._flex_freq_high_spin.setRange(0.0, 500.0)
        self._flex_freq_high_spin.setSingleStep(1.0)
        self._flex_freq_high_spin.setDecimals(0)
        self._flex_freq_high_spin.setSuffix(" Hz")
        self._flex_freq_high_spin.setToolTip("Sensor frequency at 100% ethanol (E100). Standard GM/Continental: 150 Hz.")
        self._flex_freq_high_spin.valueChanged.connect(lambda v: self._stage_float("flexFreqHigh", v))
        flex_form.addRow("High frequency (E100):", self._flex_freq_high_spin)
        self._flex_preset_button = QPushButton("Use GM / Continental 50-150 Hz")
        self._flex_preset_button.setToolTip(
            "Apply the common 50 Hz (E0) / 150 Hz (E100) flex sensor calibration used by standard GM/Continental sensors."
        )
        self._flex_preset_button.clicked.connect(self._on_apply_standard_flex_preset)
        flex_form.addRow("", self._flex_preset_button)
        layout.addWidget(flex_grp)

        # ---- Knock Sensor ----
        knock_grp = QGroupBox("Knock Sensor")
        knock_form = QFormLayout(knock_grp)
        self._knock_form = knock_form

        self._knock_mode_combo = QComboBox()
        self._knock_mode_combo.setToolTip(
            "Off: knock detection disabled.\n"
            "Digital: hardware knock module outputs a pulse (e.g. Bosch 0 261 231 173).\n"
            "Analog: raw piezo voltage read by an ADC channel."
        )
        self._knock_mode_combo.currentIndexChanged.connect(self._on_knock_mode_changed)
        knock_form.addRow("Knock mode:", self._knock_mode_combo)

        # Digital-only fields
        self._knock_digital_pin_combo = QComboBox()
        self._knock_digital_pin_combo.setToolTip(
            "Digital input pin for the knock signal. Options loaded from the board definition."
        )
        self._knock_digital_pin_combo.currentIndexChanged.connect(
            lambda idx: self._stage_combo("knock_digital_pin", self._knock_digital_pin_combo, idx)
        )
        knock_form.addRow("Digital input pin:", self._knock_digital_pin_combo)

        # Analog-only fields
        self._knock_analog_pin_combo = QComboBox()
        self._knock_analog_pin_combo.setToolTip(
            "Analog input pin for the knock sensor voltage. Options loaded from the board definition."
        )
        self._knock_analog_pin_combo.currentIndexChanged.connect(
            lambda idx: self._stage_combo("knock_analog_pin", self._knock_analog_pin_combo, idx)
        )
        knock_form.addRow("Analog input pin:", self._knock_analog_pin_combo)

        self._knock_threshold_spin = QDoubleSpinBox()
        self._knock_threshold_spin.setRange(0.0, 5.0)
        self._knock_threshold_spin.setSingleStep(0.05)
        self._knock_threshold_spin.setDecimals(2)
        self._knock_threshold_spin.setSuffix(" V")
        self._knock_threshold_spin.setToolTip(
            "Minimum voltage to trigger a knock event (analog mode). "
            "Set above the normal noise floor."
        )
        self._knock_threshold_spin.valueChanged.connect(
            lambda v: self._stage_float("knock_threshold", v)
        )
        self._knock_threshold_label = knock_form.addRow("Threshold:", self._knock_threshold_spin)

        # Common (when knock enabled)
        self._knock_max_retard_spin = QDoubleSpinBox()
        self._knock_max_retard_spin.setRange(0.0, 30.0)
        self._knock_max_retard_spin.setSingleStep(1.0)
        self._knock_max_retard_spin.setDecimals(1)
        self._knock_max_retard_spin.setSuffix(" °")
        self._knock_max_retard_spin.setToolTip(
            "Maximum total timing retard applied when knock is detected."
        )
        self._knock_max_retard_spin.valueChanged.connect(
            lambda v: self._stage_float("knock_maxRetard", v)
        )
        self._knock_max_retard_label = knock_form.addRow("Max retard:", self._knock_max_retard_spin)

        self._knock_first_step_spin = QDoubleSpinBox()
        self._knock_first_step_spin.setRange(0.0, 10.0)
        self._knock_first_step_spin.setSingleStep(0.5)
        self._knock_first_step_spin.setDecimals(1)
        self._knock_first_step_spin.setSuffix(" °")
        self._knock_first_step_spin.setToolTip("Initial retard applied on first knock event.")
        self._knock_first_step_spin.valueChanged.connect(
            lambda v: self._stage_float("knock_firstStep", v)
        )
        self._knock_first_step_label = knock_form.addRow("First step retard:", self._knock_first_step_spin)

        self._knock_step_size_spin = QDoubleSpinBox()
        self._knock_step_size_spin.setRange(0.0, 10.0)
        self._knock_step_size_spin.setSingleStep(0.5)
        self._knock_step_size_spin.setDecimals(1)
        self._knock_step_size_spin.setSuffix(" °")
        self._knock_step_size_spin.setToolTip("Additional retard per successive knock event.")
        self._knock_step_size_spin.valueChanged.connect(
            lambda v: self._stage_float("knock_stepSize", v)
        )
        self._knock_step_size_label = knock_form.addRow("Step retard:", self._knock_step_size_spin)

        layout.addWidget(knock_grp)

        # ---- Coolant & IAT Filters ----
        filter_grp = QGroupBox("Sensor Filters (CLT / IAT)")
        filter_form = QFormLayout(filter_grp)
        filter_form.addRow(_note(
            "Analog filter strength for coolant (CLT) and intake air temperature (IAT) sensors. "
            "Higher values smooth out noise; lower values respond faster. Range 0–255. "
            "Sensor pins are hardcoded on the board."
        ))

        self._clt_filter_spin = QSpinBox()
        self._clt_filter_spin.setRange(0, 255)
        self._clt_filter_spin.setToolTip(
            "Coolant temperature sensor analog filter (0 = raw, 255 = maximum smoothing)."
        )
        self._clt_filter_spin.valueChanged.connect(
            lambda v: self._stage_int("ADCFILTER_CLT", v)
        )
        filter_form.addRow("CLT filter:", self._clt_filter_spin)

        self._iat_filter_spin = QSpinBox()
        self._iat_filter_spin.setRange(0, 255)
        self._iat_filter_spin.setToolTip(
            "Intake air temperature sensor analog filter (0 = raw, 255 = maximum smoothing)."
        )
        self._iat_filter_spin.valueChanged.connect(
            lambda v: self._stage_int("ADCFILTER_IAT", v)
        )
        filter_form.addRow("IAT filter:", self._iat_filter_spin)
        layout.addWidget(filter_grp)

        # ---- Oil Pressure ----
        oil_grp = QGroupBox("Oil Pressure Sensor")
        oil_form = QFormLayout(oil_grp)
        self._oil_form = oil_form

        self._oil_pressure_enable_combo = QComboBox()
        self._oil_pressure_enable_combo.addItems(["Disabled", "Enabled"])
        self._oil_pressure_enable_combo.setToolTip("Enable the oil pressure sensor input.")
        self._oil_pressure_enable_combo.currentIndexChanged.connect(
            self._on_oil_pressure_enable_changed
        )
        oil_form.addRow("Oil pressure sensor:", self._oil_pressure_enable_combo)

        self._oil_pin_combo = QComboBox()
        self._oil_pin_combo.setToolTip("Analog input pin for the oil pressure sensor.")
        self._oil_pin_combo.currentIndexChanged.connect(
            lambda index: self._stage_combo("oilPressurePin", self._oil_pin_combo, index)
        )
        self._oil_pin_label = oil_form.addRow("Analog pin:", self._oil_pin_combo)

        self._oil_min_spin = QDoubleSpinBox()
        self._oil_min_spin.setRange(0.0, 10.0)
        self._oil_min_spin.setSingleStep(0.1)
        self._oil_min_spin.setDecimals(2)
        self._oil_min_spin.setSuffix(" bar")
        self._oil_min_spin.setToolTip("Pressure reading at 0 V (sensor zero-point).")
        self._oil_min_spin.valueChanged.connect(lambda v: self._stage_float("oilPressureMin", v))
        self._oil_min_label = oil_form.addRow("Pressure at 0 V:", self._oil_min_spin)

        self._oil_max_spin = QDoubleSpinBox()
        self._oil_max_spin.setRange(0.0, 20.0)
        self._oil_max_spin.setSingleStep(0.5)
        self._oil_max_spin.setDecimals(2)
        self._oil_max_spin.setSuffix(" bar")
        self._oil_max_spin.setToolTip("Pressure reading at 5 V (sensor full-scale).")
        self._oil_max_spin.valueChanged.connect(lambda v: self._stage_float("oilPressureMax", v))
        self._oil_max_label = oil_form.addRow("Pressure at 5 V:", self._oil_max_spin)
        self._oil_preset_combo = QComboBox()
        self._oil_preset_combo.addItem("Manual / not set", None)
        for preset in self._hardware_preset_service.oil_pressure_presets():
            self._oil_preset_combo.addItem(preset.label, preset)
        self._oil_preset_combo.setToolTip("Load a common oil-pressure sensor range into the draft values.")
        oil_form.addRow("Oil pressure preset:", self._oil_preset_combo)
        self._oil_preset_button = QPushButton("Load Oil Pressure Preset")
        self._oil_preset_button.clicked.connect(self._on_apply_oil_pressure_preset)
        oil_form.addRow("", self._oil_preset_button)
        self._oil_preset_note = _note("")
        self._oil_preset_note.setVisible(False)
        oil_form.addRow(self._oil_preset_note)

        layout.addWidget(oil_grp)

        # ---- External Barometric Pressure ----
        baro_grp = QGroupBox("External Barometric Pressure Sensor")
        baro_form = QFormLayout(baro_grp)
        self._baro_form = baro_form
        baro_form.addRow(_note(
            "An optional external baro sensor improves fuel accuracy at altitude. "
            "Without it, Speeduino uses the MAP reading at startup as the baro reference."
        ))

        self._baro_enable_combo = QComboBox()
        self._baro_enable_combo.addItems(["No", "Yes"])
        self._baro_enable_combo.setToolTip("Enable the external barometric pressure sensor.")
        self._baro_enable_combo.currentIndexChanged.connect(self._on_baro_enable_changed)
        baro_form.addRow("External baro sensor:", self._baro_enable_combo)

        self._baro_pin_combo = QComboBox()
        self._baro_pin_combo.setToolTip("Analog input pin for the baro sensor.")
        self._baro_pin_combo.currentIndexChanged.connect(
            lambda index: self._stage_combo("baroPin", self._baro_pin_combo, index)
        )
        self._baro_pin_label = baro_form.addRow("Analog pin:", self._baro_pin_combo)

        self._baro_min_spin = QDoubleSpinBox()
        self._baro_min_spin.setRange(0.0, 400.0)
        self._baro_min_spin.setSingleStep(1.0)
        self._baro_min_spin.setDecimals(0)
        self._baro_min_spin.setSuffix(" kPa")
        self._baro_min_spin.setToolTip("Pressure at 0 V.")
        self._baro_min_spin.valueChanged.connect(self._on_baro_min_changed)
        self._baro_min_label = baro_form.addRow("Pressure at 0 V:", self._baro_min_spin)

        self._baro_max_spin = QDoubleSpinBox()
        self._baro_max_spin.setRange(0.0, 400.0)
        self._baro_max_spin.setSingleStep(1.0)
        self._baro_max_spin.setDecimals(0)
        self._baro_max_spin.setSuffix(" kPa")
        self._baro_max_spin.setToolTip("Pressure at 5 V.")
        self._baro_max_spin.valueChanged.connect(self._on_baro_max_changed)
        self._baro_max_label = baro_form.addRow("Pressure at 5 V:", self._baro_max_spin)
        self._baro_preset_combo = QComboBox()
        self._baro_preset_combo.addItem("Manual / not set", None)
        for preset in self._hardware_preset_service.baro_sensor_presets():
            self._baro_preset_combo.addItem(preset.label, preset)
        self._baro_preset_combo.setToolTip("Load a common external baro sensor range into the draft values.")
        baro_form.addRow("Baro sensor preset:", self._baro_preset_combo)
        self._baro_preset_button = QPushButton("Load Baro Preset")
        self._baro_preset_button.clicked.connect(self._on_apply_baro_preset)
        baro_form.addRow("", self._baro_preset_button)
        self._baro_preset_note = _note("")
        self._baro_preset_note.setVisible(False)
        baro_form.addRow(self._baro_preset_note)
        self._baro_preset_summary = _note("")
        self._baro_preset_summary.setVisible(False)
        baro_form.addRow(self._baro_preset_summary)

        layout.addWidget(baro_grp)

        # ---- CLT / IAT Thermistor Calibration ----
        self._clt_cal_widgets = self._build_calibration_group(
            "Coolant Temperature Sensor (CLT) Calibration", layout, sensor_kind="clt"
        )
        self._iat_cal_widgets = self._build_calibration_group(
            "Intake Air Temperature Sensor (IAT) Calibration", layout, sensor_kind="iat"
        )

        layout.addStretch(1)

        self._tabs.addTab(_scroll_wrap(container), "Sensors")
        self._update_afr_protection_visibility(False, 0)
        self._update_flex_visibility(False)
        self._update_knock_visibility(0)
        self._update_oil_visibility(False)
        self._update_baro_visibility(False)
        self._update_wideband_visibility(0)

    def _refresh_sensor_tab(self) -> None:
        from PySide6.QtCore import QSignalBlocker

        # O2 / Lambda
        b = QSignalBlocker(self._ego_type_combo)
        self._ego_type_combo.clear()
        param = self._get_definition_scalar("egoType")
        if param and param.options:
            for opt in param.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._ego_type_combo.addItem(opt.label, opt.value)
        if self._ego_type_combo.count() == 0:
            for label in ("Disabled", "Narrow Band", "Wide Band"):
                self._ego_type_combo.addItem(label)
        del b
        raw_ego = self._get_tune_str("egoType")
        ego_idx = 0
        if raw_ego is not None:
            idx = self._find_combo_by_value(self._ego_type_combo, raw_ego)
            if idx >= 0:
                bx = QSignalBlocker(self._ego_type_combo)
                self._ego_type_combo.setCurrentIndex(idx)
                del bx
                ego_idx = idx

        raw_stoich = self._get_tune_float("stoich")
        if raw_stoich is not None:
            bx = QSignalBlocker(self._stoich_sensor_spin)
            self._stoich_sensor_spin.setValue(raw_stoich)
            del bx

        self._wideband_cal_param_name = self._first_definition_scalar_name(
            ("afrCal", "widebandCal", "lambdaCal", "afrcal", "widebandcal", "lambdacal")
        )
        preset_context = self._effective_operator_context()
        blocker = QSignalBlocker(self._wideband_preset_combo)
        self._wideband_preset_combo.setCurrentIndex(0)
        for i in range(1, self._wideband_preset_combo.count()):
            preset = self._wideband_preset_combo.itemData(i)
            if isinstance(preset, WidebandHardwarePreset) and preset.key == preset_context.wideband_preset_key:
                self._wideband_preset_combo.setCurrentIndex(i)
                break
        del blocker
        self._wideband_reference_table = None
        if self._wideband_cal_param_name is not None:
            raw_cal = self._get_tune_float(self._wideband_cal_param_name)
            if raw_cal is not None:
                bx = QSignalBlocker(self._wideband_cal_spin)
                self._wideband_cal_spin.setValue(raw_cal)
                del bx
        if self._presenter.definition is not None:
            self._wideband_reference_table = next(
                (
                    table
                    for table in self._presenter.definition.reference_tables
                    if any(token in f"{table.table_id} {table.label}".lower() for token in ("geno2", "afr", "o2"))
                ),
                None,
            )
        self._refresh_wideband_reference_table()
        self._refresh_wideband_preset_summary()
        self._update_wideband_visibility(ego_idx)

        # AFR protection / engine protection
        bx = QSignalBlocker(self._engine_protect_type_combo)
        self._engine_protect_type_combo.clear()
        protect_type_param = self._get_definition_scalar("engineProtectType")
        if protect_type_param and protect_type_param.options:
            for opt in protect_type_param.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._engine_protect_type_combo.addItem(opt.label, opt.value)
        if self._engine_protect_type_combo.count() == 0:
            for label in ("Off", "Spark Only", "Fuel Only", "Both"):
                self._engine_protect_type_combo.addItem(label)
        del bx
        raw_engine_protect_type = self._get_tune_str("engineProtectType")
        engine_protect_idx = 0
        if raw_engine_protect_type is not None:
            idx = self._find_combo_by_value(self._engine_protect_type_combo, raw_engine_protect_type)
            if idx >= 0:
                bx = QSignalBlocker(self._engine_protect_type_combo)
                self._engine_protect_type_combo.setCurrentIndex(idx)
                del bx
                engine_protect_idx = idx

        raw_engine_protect_rpm = self._get_tune_float("engineProtectMaxRPM")
        if raw_engine_protect_rpm is not None:
            bx = QSignalBlocker(self._engine_protect_rpm_spin)
            self._engine_protect_rpm_spin.setValue(raw_engine_protect_rpm)
            del bx

        bx = QSignalBlocker(self._afr_protect_mode_combo)
        self._afr_protect_mode_combo.clear()
        afr_protect_param = self._get_definition_scalar("afrProtectEnabled")
        if afr_protect_param and afr_protect_param.options:
            for opt in afr_protect_param.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._afr_protect_mode_combo.addItem(opt.label, opt.value)
        if self._afr_protect_mode_combo.count() == 0:
            for label in ("Off", "Fixed mode", "Table mode"):
                self._afr_protect_mode_combo.addItem(label)
        del bx
        raw_afr_protect_mode = self._get_tune_str("afrProtectEnabled")
        afr_protect_idx = 0
        if raw_afr_protect_mode is not None:
            idx = self._find_combo_by_value(self._afr_protect_mode_combo, raw_afr_protect_mode)
            if idx >= 0:
                bx = QSignalBlocker(self._afr_protect_mode_combo)
                self._afr_protect_mode_combo.setCurrentIndex(idx)
                del bx
                afr_protect_idx = idx

        for name, spin in (
            ("afrProtectMAP", self._afr_protect_map_spin),
            ("afrProtectRPM", self._afr_protect_rpm_threshold_spin),
            ("afrProtectTPS", self._afr_protect_tps_spin),
            ("afrProtectDeviation", self._afr_protect_afr_spin),
            ("afrProtectCutTime", self._afr_protect_cut_time_spin),
            ("afrProtectReactivationTPS", self._afr_protect_reactivation_tps_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(raw)
                del bx
        self._update_afr_protection_visibility(self._ego_type_is_wideband(ego_idx), afr_protect_idx)

        # TPS
        for name, spin in (("tpsMin", self._tps_min_spin), ("tpsMax", self._tps_max_spin)):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(int(raw))
                del bx

        # MAP
        for name, spin in (("mapMin", self._map_min_spin), ("mapMax", self._map_max_spin)):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(raw)
                del bx
        self._refresh_pressure_sensor_guidance(
            sensor_kind="map",
            minimum_value=self._map_min_spin.value(),
            maximum_value=self._map_max_spin.value(),
            summary_label=self._map_preset_summary,
            presets=self._hardware_preset_service.map_sensor_presets(),
        )

        bx = QSignalBlocker(self._map_sample_combo)
        self._map_sample_combo.clear()
        param_ms = self._get_definition_scalar("mapSample")
        if param_ms and param_ms.options:
            for opt in param_ms.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._map_sample_combo.addItem(opt.label, opt.value)
        if self._map_sample_combo.count() == 0:
            for label in ("Instantaneous", "Cycle Average", "Cycle Minimum", "Event Average"):
                self._map_sample_combo.addItem(label)
        del bx
        raw_ms = self._get_tune_str("mapSample")
        if raw_ms is not None:
            idx = self._find_combo_by_value(self._map_sample_combo, raw_ms)
            if idx >= 0:
                bx2 = QSignalBlocker(self._map_sample_combo)
                self._map_sample_combo.setCurrentIndex(idx)
                del bx2

        # Flex fuel
        self._populate_enable_combo(
            self._flex_enable_combo,
            "flexEnabled",
            disabled_label="Disabled",
            enabled_label="Enabled",
        )
        raw_flex = self._get_tune_float("flexEnabled")
        flex_enabled = raw_flex is not None and raw_flex > 0
        raw_flex_str = self._get_tune_str("flexEnabled")
        if raw_flex_str is not None:
            idx = self._find_combo_by_value(self._flex_enable_combo, raw_flex_str)
            if idx >= 0:
                bx = QSignalBlocker(self._flex_enable_combo)
                self._flex_enable_combo.setCurrentIndex(idx)
                del bx
        for name, spin in (
            ("flexFreqLow", self._flex_freq_low_spin),
            ("flexFreqHigh", self._flex_freq_high_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(raw)
                del bx
        self._update_flex_visibility(flex_enabled)

        # Knock mode
        bx = QSignalBlocker(self._knock_mode_combo)
        self._knock_mode_combo.clear()
        param_km = self._get_definition_scalar("knock_mode")
        if param_km and param_km.options:
            for opt in param_km.options:
                if opt.label and opt.label.upper() != "INVALID":
                    self._knock_mode_combo.addItem(opt.label, opt.value)
        if self._knock_mode_combo.count() == 0:
            for label in ("Off", "Digital", "Analog"):
                self._knock_mode_combo.addItem(label)
        del bx
        raw_km = self._get_tune_str("knock_mode")
        knock_idx = 0
        if raw_km is not None:
            idx = self._find_combo_by_value(self._knock_mode_combo, raw_km)
            if idx >= 0:
                bx2 = QSignalBlocker(self._knock_mode_combo)
                self._knock_mode_combo.setCurrentIndex(idx)
                del bx2
                knock_idx = idx

        for name, combo in (
            ("knock_digital_pin", self._knock_digital_pin_combo),
            ("knock_analog_pin", self._knock_analog_pin_combo),
        ):
            bx = QSignalBlocker(combo)
            combo.clear()
            param_pin = self._get_definition_scalar(name)
            if param_pin and param_pin.options:
                for opt in param_pin.options:
                    if opt.label and opt.label.upper() != "INVALID":
                        combo.addItem(opt.label, opt.value)
            if combo.count() == 0:
                combo.addItem("(no pin options — reload tune)")
            del bx
            raw = self._get_tune_str(name)
            if raw is not None:
                idx = self._find_combo_by_value(combo, raw)
                if idx >= 0:
                    bx2 = QSignalBlocker(combo)
                    combo.setCurrentIndex(idx)
                    del bx2

        for name, spin in (
            ("knock_threshold", self._knock_threshold_spin),
            ("knock_maxRetard", self._knock_max_retard_spin),
            ("knock_firstStep", self._knock_first_step_spin),
            ("knock_stepSize", self._knock_step_size_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(raw)
                del bx

        self._update_knock_visibility(knock_idx)

        # CLT / IAT filters
        for name, spin in (
            ("ADCFILTER_CLT", self._clt_filter_spin),
            ("ADCFILTER_IAT", self._iat_filter_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(int(raw))
                del bx

        # Oil pressure
        self._populate_enable_combo(
            self._oil_pressure_enable_combo,
            "oilPressureEnable",
            disabled_label="Disabled",
            enabled_label="Enabled",
        )
        raw_oil = self._get_tune_float("oilPressureEnable")
        oil_enabled = raw_oil is not None and raw_oil > 0
        raw_oil_str = self._get_tune_str("oilPressureEnable")
        if raw_oil_str is not None:
            idx = self._find_combo_by_value(self._oil_pressure_enable_combo, raw_oil_str)
            if idx >= 0:
                bx = QSignalBlocker(self._oil_pressure_enable_combo)
                self._oil_pressure_enable_combo.setCurrentIndex(idx)
                del bx
        for name, combo in (
            ("oilPressurePin", self._oil_pin_combo),
        ):
            self._populate_analog_pin_combo(combo, name)
            self._sync_pin_combo_value(name, combo)
        for name, spin in (
            ("oilPressureMin", self._oil_min_spin),
            ("oilPressureMax", self._oil_max_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(raw)
                del bx
        self._update_oil_visibility(oil_enabled)

        # External baro
        self._populate_enable_combo(
            self._baro_enable_combo,
            "useExtBaro",
            disabled_label="No",
            enabled_label="Yes",
        )
        raw_baro = self._get_tune_float("useExtBaro")
        baro_enabled = raw_baro is not None and raw_baro > 0
        raw_baro_str = self._get_tune_str("useExtBaro")
        if raw_baro_str is not None:
            idx = self._find_combo_by_value(self._baro_enable_combo, raw_baro_str)
            if idx >= 0:
                bx = QSignalBlocker(self._baro_enable_combo)
                self._baro_enable_combo.setCurrentIndex(idx)
                del bx
        for name, combo in (
            ("baroPin", self._baro_pin_combo),
        ):
            self._populate_analog_pin_combo(combo, name)
            self._sync_pin_combo_value(name, combo)
        for name, spin in (
            ("baroMin", self._baro_min_spin),
            ("baroMax", self._baro_max_spin),
        ):
            raw = self._get_tune_float(name)
            if raw is not None:
                bx = QSignalBlocker(spin)
                spin.setValue(raw)
                del bx
        self._update_baro_visibility(baro_enabled)
        self._refresh_pressure_sensor_guidance(
            sensor_kind="baro",
            minimum_value=self._baro_min_spin.value() if baro_enabled else None,
            maximum_value=self._baro_max_spin.value() if baro_enabled else None,
            summary_label=self._baro_preset_summary,
            presets=self._hardware_preset_service.baro_sensor_presets(),
        )
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _refresh_sensor_summary(self) -> None:
        map_assessment = PressureSensorCalibrationService().assess(
            minimum_value=self._map_min_spin.value(),
            maximum_value=self._map_max_spin.value(),
            presets=self._hardware_preset_service.map_sensor_presets(),
            sensor_kind="map",
        )
        baro_assessment = PressureSensorCalibrationService().assess(
            minimum_value=self._baro_min_spin.value() if self._combo_is_active(self._baro_enable_combo) else None,
            maximum_value=self._baro_max_spin.value() if self._combo_is_active(self._baro_enable_combo) else None,
            presets=self._hardware_preset_service.baro_sensor_presets(),
            sensor_kind="baro",
        )
        ego_type = self._ego_type_combo.currentText().strip() or "Unknown O2 type"
        stoich = self._stoich_sensor_spin.value()
        map_range = f"{self._map_min_spin.value():.0f}-{self._map_max_spin.value():.0f} kPa"
        afr_protect_status = self._afr_protect_mode_combo.currentText().strip() or "Off"
        wideband_ref = self._selected_wideband_reference_label()
        flex_status = "enabled" if self._combo_is_active(self._flex_enable_combo) else "off"
        knock_mode = self._knock_mode_combo.currentText().strip() or "Off"
        oil_status = "enabled" if self._combo_is_active(self._oil_pressure_enable_combo) else "off"
        baro_status = "enabled" if self._combo_is_active(self._baro_enable_combo) else "off"
        wideband_ref_segment = f" | AFR ref: {wideband_ref}" if wideband_ref else ""
        self._sensor_summary_label.setText(
            f"O2: {ego_type} | Stoich: {stoich:.1f}:1{wideband_ref_segment} | MAP range: {map_range} | AFR protection: {afr_protect_status} | Flex fuel: {flex_status} | Knock: {knock_mode} | Oil pressure: {oil_status} | External baro: {baro_status}"
        )

        risks: list[str] = []
        wideband = self._ego_type_is_wideband(self._ego_type_combo.currentIndex())
        if wideband and self._wideband_cal_param_name is None and self._wideband_reference_table is None:
            risks.append("Wideband is enabled but no calibration parameter or AFR calibration table is exposed on this definition-backed page.")
        elif wideband and self._wideband_cal_spin.value() <= 0.0:
            risks.append("Wideband is enabled but the calibration value is zero or unset.")
        preset = self._find_wideband_preset(self._effective_operator_context().wideband_preset_key)
        matched_reference_index = self._match_wideband_reference_solution_index(preset)
        if wideband and preset is not None and self._wideband_reference_table is not None:
            if matched_reference_index < 0:
                risks.append(
                    f"No direct AFR calibration preset match was found for {preset.label}; verify the selected analog equation manually."
                )
            else:
                matched_label = self._wideband_ref_combo.itemText(matched_reference_index).strip()
                selected_label = self._selected_wideband_reference_label()
                if selected_label and selected_label != matched_label:
                    risks.append(
                        f"Wideband controller preset suggests '{matched_label}', but AFR calibration preset is set to '{selected_label}'."
                    )

        afr_protect_enabled = self._combo_is_active(self._afr_protect_mode_combo)
        if afr_protect_enabled and not wideband:
            risks.append("AFR lean protection is enabled but the O2 sensor is not configured as wideband.")
        if self._ego_type_uses_can(self._ego_type_combo.currentIndex()) and self._connected_board_native_can_available() is False:
            risks.append("A CAN-based O2/wideband path is selected, but the connected board does not advertise native CAN support.")
        if afr_protect_enabled and not self._combo_is_active(self._engine_protect_type_combo):
            risks.append("AFR lean protection is configured but engine protection cut is still off.")
        if afr_protect_enabled and self._engine_protect_rpm_spin.value() <= 0.0:
            risks.append("Set a protection RPM limit so AFR protection only acts in the intended operating range.")
        if afr_protect_enabled and self._afr_protect_cut_time_spin.value() <= 0.0:
            risks.append("AFR lean protection cut time is zero; use a short delay to avoid false trips from transients.")

        if self._combo_is_active(self._flex_enable_combo) and self._flex_freq_high_spin.value() <= self._flex_freq_low_spin.value():
            risks.append("Flex fuel high frequency must be greater than the low frequency calibration.")

        if self._tps_max_spin.value() <= self._tps_min_spin.value():
            risks.append("TPS max must be greater than TPS min or throttle position will be inverted or flatlined.")

        if self._map_max_spin.value() <= self._map_min_spin.value():
            risks.append("MAP 5 V pressure must be greater than the 0 V pressure.")

        knock_mode_index = self._knock_mode_combo.currentIndex()
        knock_mode_kind = self._knock_mode_kind(knock_mode_index)
        if knock_mode_kind == "digital" and self._knock_digital_pin_combo.currentText().strip().lower() in {"", "off", "none", "invalid", "(no pin options — reload tune)"}:
            risks.append("Digital knock mode is enabled but no valid digital input pin is selected.")
        if knock_mode_kind == "analog" and self._knock_analog_pin_combo.currentText().strip().lower() in {"", "off", "none", "invalid", "(no pin options — reload tune)"}:
            risks.append("Analog knock mode is enabled but no valid analog input pin is selected.")

        if self._combo_is_active(self._oil_pressure_enable_combo) and self._oil_max_spin.value() <= self._oil_min_spin.value():
            risks.append("Oil-pressure 5 V calibration must be greater than the 0 V calibration.")

        if self._combo_is_active(self._baro_enable_combo) and self._baro_max_spin.value() <= self._baro_min_spin.value():
            risks.append("External-baro 5 V calibration must be greater than the 0 V calibration.")
        elif baro_assessment.warning:
            risks.append(baro_assessment.warning)

        if map_assessment.matching_preset is None:
            risks.append("MAP calibration does not match a curated preset; verify the sensor part number and range.")

        if not risks:
            risks.append("No immediate sensor-configuration risks detected. Confirm live sensor readings before enabling corrections or autotune.")
            self._sensor_risk_label.setStyleSheet(f"color: {_NOTE_TEXT_COLOR};")
        else:
            self._sensor_risk_label.setStyleSheet("color: #c0392b; font-weight: bold;")
        self._sensor_risk_label.setText("Known risks: " + " ".join(risks))

    def _refresh_sensor_checklist(self) -> None:
        from tuner.services.sensor_setup_checklist_service import SensorSetupChecklistService

        sensor_pages = tuple(
            page
            for group in self._presenter.page_groups
            for page in group.pages
            if self._presenter.hardware_setup_summary_service._page_kind(page) == "sensor"  # noqa: SLF001
        )
        items = SensorSetupChecklistService().validate(
            sensor_pages=sensor_pages,
            edits=self._presenter.local_tune_edit_service,
        )

        # Supplement: wideband cal check from live widget state when no sensor page exists
        wideband = self._ego_type_is_wideband(self._ego_type_combo.currentIndex())
        if wideband and self._wideband_cal_param_name is None and self._wideband_reference_table is not None:
            items = tuple(
                item
                for item in items
                if not (
                    item.key == "wideband_cal"
                    and item.parameter_name is None
                    and item.status == ChecklistItemStatus.WARNING
                )
            )
        has_wideband_cal_item = any(i.key == "wideband_cal" for i in items)
        if wideband and not has_wideband_cal_item:
            if self._wideband_cal_param_name is None and self._wideband_reference_table is None:
                items = items + (SetupChecklistItem(
                    key="wideband_cal",
                    title="Wideband calibration parameter not in definition",
                    status=ChecklistItemStatus.WARNING,
                    detail="Wide band EGO is selected but no calibration parameter was found. "
                           "Verify calibration on the related sensor page.",
                    parameter_name=None,
                ),)
            elif self._wideband_cal_param_name is None and self._wideband_reference_table is not None:
                items = items + (SetupChecklistItem(
                    key="wideband_cal",
                    title="Wideband calibration table available",
                    status=ChecklistItemStatus.INFO,
                    detail=f"This definition exposes AFR calibration through '{self._wideband_reference_table.label}'. Review the preset list in this wizard before trusting logs or autotune.",
                    parameter_name=None,
                ),)
            elif self._wideband_cal_spin.value() <= 0.0:
                items = items + (SetupChecklistItem(
                    key="wideband_cal",
                    title="Set wideband calibration",
                    status=ChecklistItemStatus.NEEDED,
                    detail="Wide band EGO is selected but the calibration value is zero or missing.",
                    parameter_name=self._wideband_cal_param_name,
                ),)
        preset = self._find_wideband_preset(self._effective_operator_context().wideband_preset_key)
        matched_reference_index = self._match_wideband_reference_solution_index(preset)
        selected_reference = self._selected_wideband_reference_label()
        if wideband and self._wideband_reference_table is not None and preset is not None:
            if matched_reference_index < 0:
                items = items + (SetupChecklistItem(
                    key="wideband_reference_match",
                    title="Review AFR calibration preset",
                    status=ChecklistItemStatus.WARNING,
                    detail=f"No direct AFR calibration preset match was found for {preset.label}. Verify the analog equation on the related calibration page.",
                    parameter_name=None,
                ),)
            else:
                matched_label = self._wideband_ref_combo.itemText(matched_reference_index).strip()
                if selected_reference and selected_reference != matched_label:
                    items = items + (SetupChecklistItem(
                        key="wideband_reference_match",
                        title="Align AFR calibration preset with controller",
                        status=ChecklistItemStatus.WARNING,
                        detail=f"{preset.label} best matches '{matched_label}', but the selected AFR calibration preset is '{selected_reference}'.",
                        parameter_name=None,
                    ),)

        flex_enabled = self._combo_is_active(self._flex_enable_combo)
        has_flex_item = any(i.key == "flex_calibration" for i in items)
        if flex_enabled and not has_flex_item:
            low = self._flex_freq_low_spin.value()
            high = self._flex_freq_high_spin.value()
            if high <= low:
                items = items + (SetupChecklistItem(
                    key="flex_calibration",
                    title="Flex sensor calibration invalid",
                    status=ChecklistItemStatus.ERROR,
                    detail=f"Flex sensor high frequency ({high:.0f} Hz) must be greater than low frequency ({low:.0f} Hz).",
                    parameter_name="flexFreqLow",
                ),)
            else:
                items = items + (SetupChecklistItem(
                    key="flex_calibration",
                    title="Flex sensor calibration OK",
                    status=ChecklistItemStatus.OK,
                    detail=f"Flex sensor frequency span is {low:.0f}–{high:.0f} Hz.",
                    parameter_name="flexFreqLow",
                ),)

        afr_protect_enabled = self._combo_is_active(self._afr_protect_mode_combo)
        if afr_protect_enabled:
            if not self._combo_is_active(self._engine_protect_type_combo):
                items = items + (SetupChecklistItem(
                    key="afr_protection",
                    title="Enable engine protection cut for AFR protection",
                    status=ChecklistItemStatus.WARNING,
                    detail="AFR lean protection is configured, but the global engine protection cut method is still Off.",
                    parameter_name="engineProtectType",
                ),)
            elif self._engine_protect_rpm_spin.value() <= 0.0:
                items = items + (SetupChecklistItem(
                    key="afr_protection",
                    title="Set AFR protection RPM limit",
                    status=ChecklistItemStatus.NEEDED,
                    detail="AFR lean protection is enabled, but the engine protection RPM limit is not set.",
                    parameter_name="engineProtectMaxRPM",
                ),)
            elif self._afr_protect_cut_time_spin.value() <= 0.0:
                items = items + (SetupChecklistItem(
                    key="afr_protection",
                    title="Review AFR protection delay",
                    status=ChecklistItemStatus.WARNING,
                    detail="AFR lean protection delay is zero seconds, which may cause false trips during transients.",
                    parameter_name="afrProtectCutTime",
                ),)
            else:
                items = items + (SetupChecklistItem(
                    key="afr_protection",
                    title="AFR protection configured",
                    status=ChecklistItemStatus.OK,
                    detail=(
                        f"{self._afr_protect_mode_combo.currentText().strip()} with cut above "
                        f"{self._engine_protect_rpm_spin.value():.0f} rpm and {self._afr_protect_cut_time_spin.value():.1f} s delay."
                    ),
                    parameter_name="afrProtectEnabled",
                ),)

        can_ego_selected = self._ego_type_uses_can(self._ego_type_combo.currentIndex())
        native_can_available = self._connected_board_native_can_available()
        if can_ego_selected and native_can_available is False:
            items = items + (SetupChecklistItem(
                key="connected_can_capability",
                title="Connected board does not advertise native CAN support",
                status=ChecklistItemStatus.WARNING,
                detail="A CAN-based O2/wideband path is selected, but the connected board does not advertise native CAN support.",
                parameter_name=None,
            ),)
        elif can_ego_selected and native_can_available is True:
            items = items + (SetupChecklistItem(
                key="connected_can_capability",
                title="Connected board advertises native CAN support",
                status=ChecklistItemStatus.OK,
                detail="A CAN-based O2/wideband path is selected and the connected board advertises native CAN support.",
                parameter_name=None,
            ),)

        # Always append a post-calibration reminder
        items = items + (SetupChecklistItem(
            key="sensor_refresh_reminder",
            title="Refresh live readings after calibration changes",
            status=ChecklistItemStatus.INFO,
            detail="After any sensor or calibration changes, confirm live gauges before enabling "
                   "EGO correction or collecting datalogs.",
            parameter_name=None,
        ),)

        self._render_checklist_items(
            items,
            self._sensor_checklist_label,
            empty_message="No sensor pages found in the current definition.",
        )

    # ------------------------------------------------------------------
    # Thermistor calibration helpers
    # ------------------------------------------------------------------

    def _build_calibration_group(self, title: str, parent_layout: QVBoxLayout, *, sensor_kind: str) -> dict:
        """Build a calibration group box and add it to *parent_layout*.

        Returns a dict of key widget references so the refresh/write
        handlers can operate without per-sensor instance attributes.
        """
        from tuner.services.thermistor_calibration_service import (
            CalibrationSensor,
            ThermistorCalibrationService,
        )

        grp = QGroupBox(title)
        form = QFormLayout(grp)
        form.addRow(_note(
            "Select the thermistor matching your physical sensor. "
            "For unlisted sensors, choose 'Custom' and enter the three "
            "resistance points from the sensor datasheet."
        ))

        preset_combo = QComboBox()
        sensor = CalibrationSensor.CLT if sensor_kind == "clt" else CalibrationSensor.IAT
        for p in ThermistorCalibrationService().presets_for_sensor(sensor):
            preset_combo.addItem(p.name, p.name)
        preset_combo.addItem("Custom", "__custom__")
        preset_combo.setToolTip("Select the thermistor brand/model.")
        form.addRow("Sensor preset:", preset_combo)

        # Custom entry (hidden unless 'Custom' is selected)
        custom_widget = QWidget()
        custom_form = QFormLayout(custom_widget)
        custom_form.setContentsMargins(0, 0, 0, 0)

        pullup_spin = QDoubleSpinBox()
        pullup_spin.setRange(100.0, 200_000.0)
        pullup_spin.setSingleStep(100.0)
        pullup_spin.setDecimals(0)
        pullup_spin.setSuffix(" Ω")
        pullup_spin.setValue(2490.0)
        pullup_spin.setToolTip("Pull-up resistor value on the sensor circuit (typically 2490 Ω).")
        custom_form.addRow("Pull-up resistor:", pullup_spin)

        temp_spins: list[QDoubleSpinBox] = []
        res_spins: list[QDoubleSpinBox] = []
        for i, (label, t_default, r_default) in enumerate([
            ("Low point",  -40.0, 100_700.0),
            ("Mid point",   30.0,   2_238.0),
            ("High point",  99.0,     177.0),
        ]):
            t_spin = QDoubleSpinBox()
            t_spin.setRange(-40.0, 200.0)
            t_spin.setSingleStep(1.0)
            t_spin.setDecimals(1)
            t_spin.setSuffix(" °C")
            t_spin.setValue(t_default)
            t_spin.setToolTip(f"{label} temperature from the sensor datasheet.")
            custom_form.addRow(f"{label} temp:", t_spin)
            temp_spins.append(t_spin)

            r_spin = QDoubleSpinBox()
            r_spin.setRange(1.0, 10_000_000.0)
            r_spin.setSingleStep(100.0)
            r_spin.setDecimals(0)
            r_spin.setSuffix(" Ω")
            r_spin.setValue(r_default)
            r_spin.setToolTip(f"Resistance at the {label} temperature.")
            custom_form.addRow(f"{label} resistance:", r_spin)
            res_spins.append(r_spin)

        custom_widget.setVisible(False)
        form.addRow(custom_widget)

        source_label = _note("")
        source_label.setVisible(False)
        form.addRow("Preset source:", source_label)

        # Preview label
        preview_label = QLabel()
        preview_label.setWordWrap(True)
        preview_label.setStyleSheet(f"color: {_NOTE_TEXT_COLOR}; font-size: 9pt;")
        form.addRow("Table preview:", preview_label)

        # Write button
        write_btn = QPushButton("Write Calibration to ECU")
        write_btn.setToolTip(
            "Sends the calibration table directly to ECU EEPROM via the 't' command.\n"
            "Requires a live ECU connection. Does not require a separate burn step."
        )
        form.addRow(write_btn)

        status_label = QLabel()
        status_label.setWordWrap(True)
        status_label.setVisible(False)
        form.addRow(status_label)

        parent_layout.addWidget(grp)

        widgets = {
            "preset_combo": preset_combo,
            "custom_widget": custom_widget,
            "pullup_spin": pullup_spin,
            "temp_spins": temp_spins,
            "res_spins": res_spins,
            "source_label": source_label,
            "preview_label": preview_label,
            "write_btn": write_btn,
            "status_label": status_label,
            "sensor_kind": sensor_kind,
        }

        # Wire combo → show/hide custom and update preview
        preset_combo.currentIndexChanged.connect(
            lambda _: self._on_cal_preset_changed(widgets)
        )
        write_btn.clicked.connect(
            lambda: self._on_cal_write(widgets)
        )

        # Initial preview
        self._refresh_cal_source_note(widgets)
        self._refresh_cal_preview(widgets)
        return widgets

    def _on_cal_preset_changed(self, widgets: dict) -> None:
        combo: QComboBox = widgets["preset_combo"]
        is_custom = combo.currentData() == "__custom__"
        widgets["custom_widget"].setVisible(is_custom)
        self._refresh_cal_source_note(widgets)
        self._refresh_cal_preview(widgets)

    def _refresh_cal_source_note(self, widgets: dict) -> None:
        source_label: QLabel = widgets["source_label"]
        combo: QComboBox = widgets["preset_combo"]
        if combo.currentData() == "__custom__":
            source_label.setText("Custom curve from your entered pull-up resistor and three resistance points.")
            source_label.setVisible(True)
            return
        preset = self._cal_preset_from_widgets(widgets)
        if preset is None or not preset.source_note:
            source_label.setText("")
            source_label.setVisible(False)
            return
        from tuner.services.thermistor_calibration_service import ThermistorCalibrationService
        confidence = ThermistorCalibrationService.source_confidence_label(preset)
        source_label.setText(f"[{confidence}] {preset.source_note}")
        source_label.setVisible(True)

    def _refresh_cal_preview(self, widgets: dict) -> None:
        """Regenerate the preview label from the current preset / custom values."""
        from tuner.services.thermistor_calibration_service import (
            CalibrationSensor,
            ThermistorCalibrationService,
            ThermistorPoint,
            ThermistorPreset,
        )
        preset = self._cal_preset_from_widgets(widgets)
        if preset is None:
            widgets["preview_label"].setText("(enter all three points to preview)")
            return
        try:
            result = ThermistorCalibrationService().generate(preset, CalibrationSensor.CLT)
            pts = result.preview_points()
            parts = [f"{adc}: {t:.0f}°C" for adc, t in pts[::3]]
            widgets["preview_label"].setText("  |  ".join(parts))
        except Exception as exc:
            widgets["preview_label"].setText(f"Preview error: {exc}")

    def _cal_preset_from_widgets(self, widgets: dict):
        """Return a ThermistorPreset from the current widget state, or None."""
        from tuner.services.thermistor_calibration_service import (
            ThermistorCalibrationService,
            ThermistorPoint,
            ThermistorPreset,
        )
        combo: QComboBox = widgets["preset_combo"]
        data = combo.currentData()
        if data != "__custom__":
            return ThermistorCalibrationService().preset_by_name(data)
        # Custom — build from widget values
        try:
            pullup = widgets["pullup_spin"].value()
            t_spins: list[QDoubleSpinBox] = widgets["temp_spins"]
            r_spins: list[QDoubleSpinBox] = widgets["res_spins"]
            return ThermistorPreset(
                name="Custom",
                pullup_ohms=pullup,
                point1=ThermistorPoint(t_spins[0].value(), r_spins[0].value()),
                point2=ThermistorPoint(t_spins[1].value(), r_spins[1].value()),
                point3=ThermistorPoint(t_spins[2].value(), r_spins[2].value()),
            )
        except Exception:
            return None

    def _on_cal_write(self, widgets: dict) -> None:
        """Write the selected calibration to the ECU via the presenter."""
        # Determine which sensor this group is for (CLT uses index 0, IAT index 1)
        from tuner.services.thermistor_calibration_service import CalibrationSensor
        sensor = (
            CalibrationSensor.CLT
            if widgets is self._clt_cal_widgets
            else CalibrationSensor.IAT
        )
        preset = self._cal_preset_from_widgets(widgets)
        if preset is None:
            msg = "Please select a preset or complete all three custom calibration points."
        else:
            try:
                snap = self._presenter.write_thermistor_calibration(sensor, preset)
                msg = self._presenter.consume_message() or "Calibration written."
                del snap
            except Exception as exc:
                msg = f"Write failed: {exc}"
        widgets["status_label"].setText(msg)
        widgets["status_label"].setVisible(True)
        self.status_message.emit(msg)
        if preset is not None:
            self.workspace_state_changed.emit()

    def _update_knock_visibility(self, mode_index: int) -> None:
        """Show/hide knock fields based on the selected mode."""
        mode_kind = self._knock_mode_kind(mode_index)
        digital = mode_kind == "digital"
        analog = mode_kind == "analog"
        active = mode_kind in {"digital", "analog"}
        _set_form_row_visible(self._knock_form, self._knock_digital_pin_combo, digital)
        _set_form_row_visible(self._knock_form, self._knock_analog_pin_combo, analog)
        _set_form_row_visible(self._knock_form, self._knock_threshold_spin, analog)
        _set_form_row_visible(self._knock_form, self._knock_max_retard_spin, active)
        _set_form_row_visible(self._knock_form, self._knock_first_step_spin, active)
        _set_form_row_visible(self._knock_form, self._knock_step_size_spin, active)

    def _update_flex_visibility(self, enabled: bool) -> None:
        for field in (self._flex_freq_low_spin, self._flex_freq_high_spin):
            _set_form_row_visible(self._flex_form, field, enabled)

    def _update_afr_protection_visibility(self, wideband: bool, mode_index: int) -> None:
        mode_active = self._combo_numeric_value(self._afr_protect_mode_combo, mode_index) not in (None, 0.0)
        _set_form_row_visible(self._afr_protect_form, self._engine_protect_type_combo, wideband)
        _set_form_row_visible(self._afr_protect_form, self._engine_protect_rpm_spin, wideband)
        _set_form_row_visible(self._afr_protect_form, self._afr_protect_mode_combo, wideband)
        for field in (
            self._afr_protect_map_spin,
            self._afr_protect_rpm_threshold_spin,
            self._afr_protect_tps_spin,
            self._afr_protect_afr_spin,
            self._afr_protect_cut_time_spin,
            self._afr_protect_reactivation_tps_spin,
        ):
            _set_form_row_visible(self._afr_protect_form, field, wideband and mode_active)

    def _update_oil_visibility(self, enabled: bool) -> None:
        for field in (self._oil_pin_combo, self._oil_min_spin, self._oil_max_spin):
            _set_form_row_visible(self._oil_form, field, enabled)

    def _update_baro_visibility(self, enabled: bool) -> None:
        for field in (self._baro_pin_combo, self._baro_min_spin, self._baro_max_spin):
            _set_form_row_visible(self._baro_form, field, enabled)

    def _update_cam_input_visibility(self, spark_mode_index: int) -> None:
        if self._cam_input_param_name is None:
            _set_form_row_visible(self._ign_form, self._cam_input_combo, False)
            return
        trigger_mode = self._trigger_cam_requirement(self._trig_pattern_combo.currentText())
        active = (
            self._spark_mode_requires_cam_sync(spark_mode_index)
            or self._inj_layout_requires_cam_sync(self._injlayout_combo.currentIndex())
            or trigger_mode in {"required", "optional"}
        )
        _set_form_row_visible(self._ign_form, self._cam_input_combo, active)

    def _update_wideband_visibility(self, ego_type_index: int) -> None:
        wideband = self._ego_type_is_wideband(ego_type_index)
        has_cal_param = self._wideband_cal_param_name is not None
        has_reference_table = self._wideband_reference_table is not None
        _set_form_row_visible(self._o2_form, self._wideband_cal_spin, wideband and has_cal_param)
        _set_form_row_visible(self._o2_form, self._wideband_cal_note, wideband and not has_cal_param and not has_reference_table)
        _set_form_row_visible(self._o2_form, self._wideband_preset_combo, wideband)
        _set_form_row_visible(self._o2_form, self._wideband_preset_summary, wideband and self._wideband_preset_summary.isVisible())
        _set_form_row_visible(self._o2_form, self._wideband_ref_group, wideband and has_reference_table)

    def _on_knock_mode_changed(self, index: int) -> None:
        self._stage_combo("knock_mode", self._knock_mode_combo, index)
        self._update_knock_visibility(index)

    def _on_flex_enable_changed(self, index: int) -> None:
        self._stage_combo("flexEnabled", self._flex_enable_combo, index)
        if self._combo_numeric_value(self._flex_enable_combo, index) not in (None, 0.0):
            self._apply_standard_flex_preset_if_missing()
        self._update_flex_visibility(
            self._combo_numeric_value(self._flex_enable_combo, index) not in (None, 0.0)
        )

    def _apply_standard_flex_preset_if_missing(self) -> None:
        low_raw = self._get_tune_float("flexFreqLow")
        high_raw = self._get_tune_float("flexFreqHigh")
        if low_raw is None:
            self._stage_float("flexFreqLow", 50.0)
        if high_raw is None:
            self._stage_float("flexFreqHigh", 150.0)

    def _on_apply_standard_flex_preset(self) -> None:
        if self._updating:
            return
        self._stage_float("flexFreqLow", 50.0)
        self._stage_float("flexFreqHigh", 150.0)

    def _on_engine_protect_type_changed(self, index: int) -> None:
        self._stage_combo("engineProtectType", self._engine_protect_type_combo, index)

    def _on_afr_protect_mode_changed(self, index: int) -> None:
        self._stage_combo("afrProtectEnabled", self._afr_protect_mode_combo, index)
        self._update_afr_protection_visibility(
            self._ego_type_is_wideband(self._ego_type_combo.currentIndex()),
            index,
        )

    def _on_trig_pattern_changed(self, index: int) -> None:
        self._stage_combo("TrigPattern", self._trig_pattern_combo, index)
        self._update_cam_input_visibility(self._spark_mode_combo.currentIndex())

    def _on_spark_mode_changed(self, index: int) -> None:
        self._stage_combo("sparkMode", self._spark_mode_combo, index)
        self._update_cam_input_visibility(index)

    def _on_cam_input_changed(self, index: int) -> None:
        if self._cam_input_param_name is None:
            return
        self._stage_combo(self._cam_input_param_name, self._cam_input_combo, index)

    def _on_ego_type_changed(self, index: int) -> None:
        self._stage_combo("egoType", self._ego_type_combo, index)
        self._update_wideband_visibility(index)
        self._update_afr_protection_visibility(self._ego_type_is_wideband(index), self._afr_protect_mode_combo.currentIndex())

    def _on_wideband_cal_changed(self, value: float) -> None:
        if self._wideband_cal_param_name is None:
            return
        self._stage_float(self._wideband_cal_param_name, value)

    def _on_wideband_preset_changed(self, index: int) -> None:
        preset = self._wideband_preset_combo.itemData(index)
        if isinstance(preset, WidebandHardwarePreset):
            self._queue_context_update(wideband_preset_key=preset.key)
        else:
            self._queue_context_update(wideband_preset_key=None)
        self._refresh_wideband_reference_table()
        self._queue_context_update(
            wideband_reference_table_label=self._selected_wideband_reference_label()
        )
        self._refresh_wideband_preset_summary()
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _on_wideband_reference_changed(self, index: int) -> None:
        if self._updating:
            return
        del index
        self._queue_context_update(
            wideband_reference_table_label=self._selected_wideband_reference_label()
        )
        self._refresh_wideband_reference_table()
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _refresh_pressure_sensor_guidance(
        self,
        *,
        sensor_kind: str,
        minimum_value: float | None,
        maximum_value: float | None,
        summary_label: QLabel,
        presets: tuple[PressureSensorPreset, ...],
    ) -> None:
        assessment = PressureSensorCalibrationService().assess(
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            presets=presets,
            sensor_kind="baro" if sensor_kind == "baro" else "map",
        )
        summary_label.setText(assessment.guidance)
        summary_label.setVisible(True)

    def _on_map_min_changed(self, value: float) -> None:
        self._stage_float("mapMin", value)
        self._refresh_pressure_sensor_guidance(
            sensor_kind="map",
            minimum_value=value,
            maximum_value=self._map_max_spin.value(),
            summary_label=self._map_preset_summary,
            presets=self._hardware_preset_service.map_sensor_presets(),
        )
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _on_map_max_changed(self, value: float) -> None:
        self._stage_float("mapMax", value)
        self._refresh_pressure_sensor_guidance(
            sensor_kind="map",
            minimum_value=self._map_min_spin.value(),
            maximum_value=value,
            summary_label=self._map_preset_summary,
            presets=self._hardware_preset_service.map_sensor_presets(),
        )
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _on_baro_min_changed(self, value: float) -> None:
        self._stage_float("baroMin", value)
        self._refresh_pressure_sensor_guidance(
            sensor_kind="baro",
            minimum_value=value if self._combo_is_active(self._baro_enable_combo) else None,
            maximum_value=self._baro_max_spin.value() if self._combo_is_active(self._baro_enable_combo) else None,
            summary_label=self._baro_preset_summary,
            presets=self._hardware_preset_service.baro_sensor_presets(),
        )
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _on_baro_max_changed(self, value: float) -> None:
        self._stage_float("baroMax", value)
        self._refresh_pressure_sensor_guidance(
            sensor_kind="baro",
            minimum_value=self._baro_min_spin.value() if self._combo_is_active(self._baro_enable_combo) else None,
            maximum_value=value if self._combo_is_active(self._baro_enable_combo) else None,
            summary_label=self._baro_preset_summary,
            presets=self._hardware_preset_service.baro_sensor_presets(),
        )
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _on_apply_map_preset(self) -> None:
        preset = self._map_preset_combo.currentData()
        self._apply_pressure_preset(
            preset if isinstance(preset, PressureSensorPreset) else None,
            min_param="mapMin",
            max_param="mapMax",
            min_spin=self._map_min_spin,
            max_spin=self._map_max_spin,
            note_label=self._map_preset_note,
        )
        self._refresh_pressure_sensor_guidance(
            sensor_kind="map",
            minimum_value=self._map_min_spin.value(),
            maximum_value=self._map_max_spin.value(),
            summary_label=self._map_preset_summary,
            presets=self._hardware_preset_service.map_sensor_presets(),
        )
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _on_apply_oil_pressure_preset(self) -> None:
        preset = self._oil_preset_combo.currentData()
        self._apply_pressure_preset(
            preset if isinstance(preset, PressureSensorPreset) else None,
            min_param="oilPressureMin",
            max_param="oilPressureMax",
            min_spin=self._oil_min_spin,
            max_spin=self._oil_max_spin,
            note_label=self._oil_preset_note,
            enable_param="oilPressureEnable",
            enable_combo=self._oil_pressure_enable_combo,
            pin_param="oilPressurePin",
            pin_combo=self._oil_pin_combo,
        )
        self._update_oil_visibility(True)
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _on_apply_baro_preset(self) -> None:
        preset = self._baro_preset_combo.currentData()
        self._apply_pressure_preset(
            preset if isinstance(preset, PressureSensorPreset) else None,
            min_param="baroMin",
            max_param="baroMax",
            min_spin=self._baro_min_spin,
            max_spin=self._baro_max_spin,
            note_label=self._baro_preset_note,
            enable_param="useExtBaro",
            enable_combo=self._baro_enable_combo,
            pin_param="baroPin",
            pin_combo=self._baro_pin_combo,
        )
        self._update_baro_visibility(True)
        self._refresh_pressure_sensor_guidance(
            sensor_kind="baro",
            minimum_value=self._baro_min_spin.value(),
            maximum_value=self._baro_max_spin.value(),
            summary_label=self._baro_preset_summary,
            presets=self._hardware_preset_service.baro_sensor_presets(),
        )
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _refresh_wideband_reference_table(self) -> None:
        blocker = QSignalBlocker(self._wideband_ref_combo)
        self._wideband_ref_combo.clear()
        table = self._wideband_reference_table
        context = self._effective_operator_context()
        preset = self._find_wideband_preset(context.wideband_preset_key)
        if table is not None:
            for solution in table.solutions:
                label = solution.label.strip()
                if label:
                    self._wideband_ref_combo.addItem(label, solution.expression)
            if self._wideband_ref_combo.count() == 0:
                self._wideband_ref_combo.addItem("(no AFR presets exposed)")
            selected_index = self._find_wideband_reference_index_by_label(
                context.wideband_reference_table_label
            )
            matched_index = self._match_wideband_reference_solution_index(preset)
            if selected_index >= 0:
                self._wideband_ref_combo.setCurrentIndex(selected_index)
            elif matched_index >= 0:
                self._wideband_ref_combo.setCurrentIndex(matched_index)
            selected_label = self._selected_wideband_reference_label()
            if matched_index >= 0:
                matched_label = self._wideband_ref_combo.itemText(matched_index)
                if selected_label and selected_label != matched_label:
                    self._wideband_ref_note.setText(
                        f"Selected AFR calibration preset is '{selected_label}', but {preset.label} best matches '{matched_label}'. "
                        "Review the controller's analog equation before trusting logs or autotune."
                    )
                elif selected_label:
                    self._wideband_ref_note.setText(
                        f"Selected AFR calibration preset '{selected_label}' matches {preset.label}."
                    )
                else:
                    self._wideband_ref_note.setText(
                        f"The selected controller best matches '{matched_label}'. Click Apply to keep this AFR calibration preset in the project context."
                    )
            elif preset is not None:
                chosen_label = selected_label or self._wideband_ref_combo.currentText().strip()
                self._wideband_ref_note.setText(
                    f"AFR calibration is exposed by the definition as '{table.label}', but no direct preset match was found for {preset.label}. "
                    f"Current selection is '{chosen_label}'. Verify the controller's analog equation before trusting logs or autotune."
                )
            elif selected_label:
                self._wideband_ref_note.setText(
                    f"AFR calibration is exposed by the definition as '{table.label}'. "
                    f"Selected AFR calibration preset: '{selected_label}'. Click Apply to keep this review note in the project context."
                )
            else:
                self._wideband_ref_note.setText(
                    f"AFR calibration is exposed by the definition as '{table.label}'. "
                    "Select the closest preset and confirm the analog equation on the related calibration page."
                )
            self._wideband_ref_note.setVisible(True)
        else:
            if preset is not None:
                self._wideband_ref_note.setText(
                    f"{preset.label}: {preset.afr_equation}. This definition does not expose an AFR preset table, so verify the analog calibration manually."
                )
                self._wideband_ref_note.setVisible(True)
            else:
                self._wideband_ref_note.setText("")
                self._wideband_ref_note.setVisible(False)
        del blocker

    def _on_oil_pressure_enable_changed(self, index: int) -> None:
        self._stage_combo("oilPressureEnable", self._oil_pressure_enable_combo, index)
        enabled = self._combo_numeric_value(self._oil_pressure_enable_combo, index) not in (None, 0.0)
        if enabled:
            self._stage_profile_default_if_missing("oilPressurePin", self._oil_pin_combo)
        self._update_oil_visibility(enabled)

    def _on_baro_enable_changed(self, index: int) -> None:
        self._stage_combo("useExtBaro", self._baro_enable_combo, index)
        enabled = self._combo_numeric_value(self._baro_enable_combo, index) not in (None, 0.0)
        if enabled:
            self._stage_profile_default_if_missing("baroPin", self._baro_pin_combo)
        self._update_baro_visibility(enabled)
        self._refresh_pressure_sensor_guidance(
            sensor_kind="baro",
            minimum_value=self._baro_min_spin.value() if enabled else None,
            maximum_value=self._baro_max_spin.value() if enabled else None,
            summary_label=self._baro_preset_summary,
            presets=self._hardware_preset_service.baro_sensor_presets(),
        )
        self._refresh_sensor_summary()
        self._refresh_sensor_checklist()

    def _on_generate_spark_table(self) -> None:
        """Generate a conservative spark advance table and stage it for review."""
        try:
            snap = self._presenter.generate_and_stage_spark_table(
                self._resolve_primary_spark_table_name(),
                operator_context=self._effective_operator_context(),
            )
            msg = self._presenter.consume_message() or ""
            if not msg:
                msg = snap.operation_log[-1].summary if snap.operation_log else "Spark table staged."
        except Exception as exc:
            msg = f"Spark table generation failed: {exc}"
        self._gen_spark_label.setText(self._format_generator_status(msg, task="spark"))
        self._gen_spark_label.setVisible(True)
        self.status_message.emit(msg)
        self.workspace_state_changed.emit()

    # ------------------------------------------------------------------
    # Checklist rendering helper
    # ------------------------------------------------------------------

    _CHECKLIST_SEVERITY_ORDER: dict = {
        ChecklistItemStatus.ERROR: 0,
        ChecklistItemStatus.NEEDED: 1,
        ChecklistItemStatus.WARNING: 2,
        ChecklistItemStatus.INFO: 3,
        ChecklistItemStatus.OK: 4,
    }
    _CHECKLIST_COLOR: dict = {
        ChecklistItemStatus.ERROR: "#c0392b",
        ChecklistItemStatus.NEEDED: "#c0392b",
        ChecklistItemStatus.WARNING: "#d35400",
        ChecklistItemStatus.INFO: "#7f8c8d",
        ChecklistItemStatus.OK: "#27ae60",
    }
    _CHECKLIST_PREFIX: dict = {
        ChecklistItemStatus.ERROR: "✗ Error",
        ChecklistItemStatus.NEEDED: "● Needed",
        ChecklistItemStatus.WARNING: "⚠ Warning",
        ChecklistItemStatus.INFO: "ℹ Info",
        ChecklistItemStatus.OK: "✓ OK",
    }

    def _render_checklist_items(
        self,
        items: tuple[SetupChecklistItem, ...],
        label: QLabel,
        *,
        empty_message: str = "No checklist items available.",
    ) -> None:
        """Render *items* into *label* as severity-sorted colored HTML."""
        if not items:
            label.setText(empty_message)
            return

        sorted_items = sorted(
            items, key=lambda i: self._CHECKLIST_SEVERITY_ORDER.get(i.status, 5)
        )

        # Summary header
        counts: dict = {}
        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1
        summary_parts: list[str] = []
        for status, label_text in (
            (ChecklistItemStatus.ERROR, "error"),
            (ChecklistItemStatus.NEEDED, "needed"),
            (ChecklistItemStatus.WARNING, "warning"),
        ):
            n = counts.get(status, 0)
            if n:
                color = self._CHECKLIST_COLOR[status]
                plural = "s" if n > 1 and label_text != "needed" else ""
                summary_parts.append(f'<span style="color:{color}"><b>{n} {label_text}{plural}</b></span>')
        if not summary_parts:
            header = '<span style="color:#27ae60"><b>✓ All items OK</b></span>'
        else:
            header = " · ".join(summary_parts)

        # Item rows
        lines = [header]
        for item in sorted_items:
            color = self._CHECKLIST_COLOR.get(item.status, "#7f8c8d")
            prefix = self._CHECKLIST_PREFIX.get(item.status, item.status.value)
            cross = " <i>(other page)</i>" if item.cross_page else ""
            lines.append(
                f'<span style="color:{color}"><b>{prefix}:</b> {item.title}{cross}</span>'
                f'<br/><span style="color:#555555">{item.detail}</span>'
            )
        label.setText("<br/><br/>".join(lines))

    # ------------------------------------------------------------------
    # Staging helpers
    # ------------------------------------------------------------------

    def _stage_raw(self, name: str, value: str) -> None:
        if self._updating:
            return
        current = self._get_committed_tune_str(name)
        if self._raw_values_equal(current, value):
            self._pending_parameter_values.pop(name, None)
        else:
            self._pending_parameter_values[name] = value
        self._update_apply_button_state()

    def _stage_array(self, name: str, values: list[float]) -> None:
        if self._updating:
            return
        current = self._get_committed_tune_list(name)
        if current is not None and len(current) == len(values):
            if all(abs(left - right) <= 1e-6 for left, right in zip(current, values)):
                self._pending_array_values.pop(name, None)
                self._update_apply_button_state()
                return
        self._pending_array_values[name] = list(values)
        self._update_apply_button_state()

    def _stage_float(self, name: str, value: float) -> None:
        if self._updating:
            return
        # Store as raw value string (presenter / service handles scaling)
        self._stage_raw(name, str(value))

    def _stage_int(self, name: str, value: int) -> None:
        if self._updating:
            return
        self._stage_raw(name, str(value))

    def _stage_bits_index(self, name: str, index: int) -> None:
        """Stage a bits field by raw index (0-based)."""
        if self._updating:
            return
        self._stage_raw(name, str(index))

    def _stage_bits_enum_spin(self, name: str, value: int) -> None:
        """Stage a bits enum field that stores the numeric value directly (e.g. nCylinders)."""
        if self._updating:
            return
        self._stage_raw(name, str(value))

    def _stage_combo(self, name: str, combo: QComboBox, index: int) -> None:
        if self._updating:
            return
        stored_value = combo.itemData(index)
        if stored_value is None:
            stored_value = str(index)
        self._stage_raw(name, str(stored_value))

    def _build_generator_context(self):
        hardware_pages = tuple(
            page
            for group in self._presenter.page_groups
            for page in group.pages
            if self._presenter.hardware_setup_summary_service._page_kind(page) is not None  # noqa: SLF001
        )
        if not hardware_pages:
            return None
        try:
            return self._presenter.hardware_setup_generator_context_service.build(
                hardware_pages,
                self._presenter.local_tune_edit_service,
                operator_context=self._effective_operator_context(),
            )
        except Exception:
            return None

    def _format_generator_status(self, message: str, *, task: str) -> str:
        summary = self._generator_assumption_summary(task)
        return f"{message}\n{summary}" if summary else message

    def _generator_assumption_summary(self, task: str) -> str:
        ctx = self._effective_operator_context()
        generator_context = self._build_generator_context()
        tier1: list[str] = []
        tier2: list[str] = []

        def add_unique(target: list[str], label: str, condition: bool) -> None:
            if condition and label not in target:
                target.append(label)

        add_unique(
            tier1,
            "displacement",
            ctx.displacement_cc is not None or bool(generator_context and generator_context.displacement_cc is not None),
        )
        add_unique(
            tier1,
            "cylinders",
            ctx.cylinder_count is not None or bool(generator_context and generator_context.cylinder_count is not None),
        )
        add_unique(
            tier1,
            "compression",
            ctx.compression_ratio is not None or bool(generator_context and generator_context.compression_ratio is not None),
        )
        add_unique(tier1, "injector flow", bool(generator_context and generator_context.injector_flow_ccmin is not None))
        add_unique(tier1, "injector dead time", bool(generator_context and generator_context.injector_dead_time_ms is not None))
        add_unique(tier1, "stoich / fuel type", bool(generator_context and generator_context.stoich_ratio is not None))
        add_unique(tier1, "intent", ctx.calibration_intent is not None)
        add_unique(tier1, "topology", ctx.forced_induction_topology != ForcedInductionTopology.NA)
        add_unique(
            tier1,
            "boost target",
            ctx.forced_induction_topology != ForcedInductionTopology.NA and ctx.boost_target_kpa is not None,
        )
        add_unique(tier1, "intercooler state", ctx.forced_induction_topology != ForcedInductionTopology.NA)

        add_unique(tier2, "cam duration", ctx.cam_duration_deg is not None)
        add_unique(tier2, "head flow class", ctx.head_flow_class is not None)
        add_unique(tier2, "manifold style", ctx.intake_manifold_style is not None)
        add_unique(tier2, "fuel pressure", ctx.base_fuel_pressure_psi is not None)
        add_unique(tier2, "injector pressure model", ctx.injector_pressure_model is not None)
        add_unique(tier2, "secondary injector pressure", ctx.secondary_injector_reference_pressure_psi is not None)
        add_unique(tier2, "injector data depth", ctx.injector_characterization is not None)
        add_unique(tier2, "compressor flow", ctx.compressor_corrected_flow_lbmin is not None)
        add_unique(tier2, "compressor PR", ctx.compressor_pressure_ratio is not None)
        add_unique(tier2, "compressor wheel sizing", ctx.compressor_inducer_mm is not None or ctx.compressor_exducer_mm is not None)
        add_unique(tier2, "turbine A/R", ctx.compressor_ar is not None)

        relevant_tier1, relevant_tier2 = self._filter_generator_assumptions(task, tier1, tier2)
        missing = self._generator_missing_inputs(task, generator_context, ctx)

        if missing:
            confidence = "Tier 1 + conservative fallbacks"
        elif relevant_tier2:
            confidence = "Tier 1 + Tier 2"
        elif relevant_tier1:
            confidence = "Tier 1 only"
        else:
            confidence = "Conservative defaults"

        tier1_text = ", ".join(relevant_tier1) if relevant_tier1 else "default conservative assumptions"
        tier2_text = ", ".join(relevant_tier2) if relevant_tier2 else "none"
        missing_text = ", ".join(missing) if missing else "none"
        return (
            f"Assumptions: [{confidence}] Tier 1 inputs: {tier1_text}. "
            f"Tier 2 inputs: {tier2_text}. Conservative fallbacks: {missing_text}."
        )

    @staticmethod
    def _filter_generator_assumptions(task: str, tier1: list[str], tier2: list[str]) -> tuple[list[str], list[str]]:
        task_filters = {
            "ve": (
                {"displacement", "cylinders", "compression", "injector flow", "stoich / fuel type", "intent", "topology", "boost target", "intercooler state"},
                {"cam duration", "head flow class", "manifold style", "fuel pressure", "injector pressure model", "secondary injector pressure", "injector data depth", "compressor flow", "compressor PR", "compressor wheel sizing", "turbine A/R"},
            ),
            "spark": (
                {"displacement", "cylinders", "compression", "stoich / fuel type", "intent", "topology", "boost target", "intercooler state"},
                {"cam duration", "head flow class", "manifold style", "compressor flow", "compressor PR", "compressor wheel sizing", "turbine A/R"},
            ),
            "afr": (
                {"injector flow", "stoich / fuel type", "intent", "topology", "boost target", "intercooler state"},
                {"fuel pressure", "injector pressure model", "secondary injector pressure", "injector data depth", "compressor flow", "compressor PR", "compressor wheel sizing", "turbine A/R"},
            ),
            "idle": (
                {"compression", "intent", "topology", "intercooler state"},
                {"cam duration", "head flow class", "manifold style"},
            ),
            "startup": (
                {"compression", "injector flow", "injector dead time", "stoich / fuel type", "intent", "topology", "boost target", "intercooler state"},
                {"cam duration", "head flow class", "manifold style", "fuel pressure", "injector pressure model", "secondary injector pressure", "injector data depth"},
            ),
        }
        allowed_tier1, allowed_tier2 = task_filters.get(task, (set(tier1), set(tier2)))
        return ([item for item in tier1 if item in allowed_tier1], [item for item in tier2 if item in allowed_tier2])

    @staticmethod
    def _generator_missing_inputs(task: str, generator_context, operator_context) -> tuple[str, ...]:
        if generator_context is None:
            if task == "startup":
                missing: list[str] = []
                if operator_context.base_fuel_pressure_psi is None:
                    missing.append("fuel pressure")
                if operator_context.injector_pressure_model is None:
                    missing.append("injector pressure model")
                missing.extend(["injector flow", "injector dead time", "stoich / fuel type"])
                return tuple(dict.fromkeys(missing))
            if task == "afr":
                missing = ["stoich / fuel type"]
                if operator_context.forced_induction_topology != ForcedInductionTopology.NA and operator_context.boost_target_kpa is None:
                    missing.append("boost target")
                return tuple(missing)
            if task == "idle":
                return () if operator_context.compression_ratio is not None else ("compression",)
            return ()
        if task == "ve":
            return generator_context.missing_for_ve_generation
        if task == "spark":
            return generator_context.missing_for_spark_helper
        if task == "startup":
            missing = list(generator_context.missing_for_injector_helper)
            if generator_context.stoich_ratio is None and "stoich / fuel type" not in missing:
                missing.append("stoich / fuel type")
            if generator_context.injector_dead_time_ms is None and "injector dead time" not in missing:
                missing.append("injector dead time")
            if generator_context.injector_pressure_model is None:
                missing.append("injector pressure model")
            if generator_context.injector_flow_secondary_ccmin is not None and generator_context.secondary_injector_pressure_kpa is None:
                missing.append("secondary injector pressure")
            return tuple(missing)
        if task == "afr":
            missing: list[str] = []
            if generator_context.stoich_ratio is None:
                missing.append("stoich / fuel type")
            if operator_context.forced_induction_topology != ForcedInductionTopology.NA and operator_context.boost_target_kpa is None:
                missing.append("boost target")
            if generator_context.injector_pressure_model is None:
                missing.append("injector pressure model")
            return tuple(missing)
        if task == "idle":
            return () if operator_context.compression_ratio is not None else ("compression",)
        return ()

    def _resolve_ve_table_name(self) -> str:
        """Resolve the best VE/fuel table name for the loaded definition."""
        return self._resolve_table_name(
            keywords=("ve", "fuel", "volumetric"),
            fallback="veTable",
            primary_tokens=("vetable", "fueltable", "ve_table"),
        )

    def _resolve_afr_table_name(self) -> str:
        """Resolve the best AFR/lambda target table name for the loaded definition."""
        return self._resolve_table_name(
            keywords=("afr", "target", "lambda"),
            fallback="afrTable",
            primary_tokens=(
                "afrtable",
                "afrtarget",
                "targetafr",
                "lambdatable",
                "lambdatarget",
                "targetlambda",
            ),
        )

    def _resolve_table_name(
        self,
        keywords: tuple[str, ...],
        fallback: str,
        primary_tokens: tuple[str, ...] = (),
    ) -> str:
        """Generic helper: find the best-matching list parameter by keyword set."""
        definition = self._presenter.definition
        if definition is None:
            return fallback

        candidates: list[str] = []
        for editor in definition.table_editors:
            editor_text = " ".join(
                part.strip().lower()
                for part in (editor.table_id, editor.map_id, editor.title)
                if part
            )
            if any(kw in editor_text for kw in keywords):
                if editor.z_bins:
                    candidates.append(editor.z_bins)

        for table in definition.tables:
            table_text = " ".join(
                part.strip().lower()
                for part in (table.name, table.label or "")
                if part
            )
            if any(kw in table_text for kw in keywords):
                candidates.append(table.name)

        candidates.append(fallback)

        seen: set[str] = set()
        ordered: list[str] = []
        for name in candidates:
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)

        def _key(name: str) -> tuple[int, int, int]:
            lower = name.lower()
            tune_value = self._presenter.local_tune_edit_service.get_value(name)
            is_list = int(isinstance(tune_value.value, list)) if tune_value is not None else 0
            is_primary = int(
                not any(t in lower for t in ("2", "second", "secondary", "_2"))
            )
            strong = int(any(t in lower for t in primary_tokens)) if primary_tokens else 0
            return (strong, is_list, is_primary)

        ordered.sort(key=_key, reverse=True)
        return ordered[0] if ordered else fallback

    def _resolve_primary_spark_table_name(self) -> str:
        """Resolve the best primary ignition table name for the loaded definition/tune."""
        definition = self._presenter.definition
        if definition is None:
            return "ignitionTable"

        candidates: list[str] = []

        for editor in definition.table_editors:
            editor_text = " ".join(
                part.strip().lower()
                for part in (editor.table_id, editor.map_id, editor.title)
                if part
            )
            if any(keyword in editor_text for keyword in ("spark", "ignition", "advance", "timing")):
                if editor.z_bins:
                    candidates.append(editor.z_bins)

        for table in definition.tables:
            table_text = " ".join(
                part.strip().lower()
                for part in (table.name, table.label or "")
                if part
            )
            if any(keyword in table_text for keyword in ("spark", "ign", "adv", "timing")):
                candidates.append(table.name)

        legacy_fallbacks = ("advTable1", "sparkTable", "ignitionTable")
        candidates.extend(legacy_fallbacks)

        seen: set[str] = set()
        ordered_candidates: list[str] = []
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            ordered_candidates.append(candidate)

        # Lower insertion index = derived from definition (not a legacy fallback) — prefer it.
        priority_by_name = {name: -i for i, name in enumerate(ordered_candidates)}

        def sort_key(name: str) -> tuple[int, int, int, int]:
            lower = name.lower()
            tune_value = self._presenter.local_tune_edit_service.get_value(name)
            is_list = int(isinstance(tune_value.value, list)) if tune_value is not None else 0
            is_primary = int(
                not any(token in lower for token in ("2", "second", "secondary", "_2"))
            )
            strong_name = int(
                any(token in lower for token in ("advtable1", "spark", "ignition", "timing"))
            )
            return (is_list, strong_name, is_primary, priority_by_name[name])

        ordered_candidates.sort(key=sort_key, reverse=True)
        return ordered_candidates[0] if ordered_candidates else "ignitionTable"

    # ------------------------------------------------------------------
    # Tune / definition read helpers
    # ------------------------------------------------------------------

    def _get_committed_tune_str(self, name: str) -> str | None:
        """Read a raw string value from the loaded tune, or None."""
        try:
            tv = self._presenter.local_tune_edit_service.get_value(name)
            if tv is None:
                return None
            v = tv.value
            return str(v) if not isinstance(v, list) else None
        except Exception:
            return None

    def _get_tune_str(self, name: str) -> str | None:
        if name in self._pending_parameter_values:
            return self._pending_parameter_values[name]
        return self._get_committed_tune_str(name)

    def _get_committed_tune_list(self, name: str) -> list[float] | None:
        try:
            tv = self._presenter.local_tune_edit_service.get_value(name)
            if tv is None or not isinstance(tv.value, list):
                return None
            return list(tv.value)
        except Exception:
            return None

    def _get_tune_float(self, name: str) -> float | None:
        raw = self._get_tune_str(name)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _is_dropbear_profile(self) -> bool:
        board_text = self._pinlayout_combo.currentText().strip().lower()
        if "dropbear" in board_text or "drop bear" in board_text:
            return True
        definition = self._presenter.definition
        if definition is not None:
            for candidate in (definition.name, definition.firmware_signature):
                text = (candidate or "").strip().lower()
                if "dropbear" in text or "drop bear" in text:
                    return True
        tune_file = self._presenter.local_tune_edit_service.base_tune_file
        if tune_file is not None:
            for candidate in (tune_file.firmware_info, tune_file.signature):
                text = (candidate or "").strip().lower()
                if "dropbear" in text or "drop bear" in text:
                    return True
        return False

    def _profile_default_spin_value(self, name: str) -> int | None:
        if not self._is_dropbear_profile():
            return None
        defaults = {
            "baroPin": 12,          # A12 in shipped DropBear base tunes
            "oilPressurePin": 15,   # A15 in shipped DropBear base tunes
        }
        return defaults.get(name)

    def _populate_analog_pin_combo(self, combo: QComboBox, name: str) -> None:
        blocker = QSignalBlocker(combo)
        combo.clear()
        param_pin = self._get_definition_scalar(name)
        if param_pin and param_pin.options:
            for opt in param_pin.options:
                if opt.label and opt.label.upper() != "INVALID":
                    combo.addItem(opt.label, opt.value)
        if combo.count() == 0:
            for index in range(16):
                combo.addItem(f"A{index}", str(index))
        del blocker

    def _populate_enable_combo(
        self,
        combo: QComboBox,
        name: str,
        *,
        disabled_label: str,
        enabled_label: str,
    ) -> None:
        blocker = QSignalBlocker(combo)
        combo.clear()
        param = self._get_definition_scalar(name)
        if param and param.options:
            for opt in param.options:
                if opt.label and opt.label.upper() != "INVALID":
                    combo.addItem(opt.label, opt.value)
        if combo.count() == 0:
            combo.addItem(disabled_label, "0")
            combo.addItem(enabled_label, "1")
        del blocker

    def _set_pin_combo_value(self, combo: QComboBox, value: int) -> None:
        index = self._find_combo_by_value(combo, str(value))
        if index < 0:
            return
        blocker = QSignalBlocker(combo)
        combo.setCurrentIndex(index)
        del blocker

    def _sync_pin_combo_value(self, name: str, combo: QComboBox) -> None:
        raw = self._get_tune_float(name)
        if raw is not None:
            self._set_pin_combo_value(combo, int(raw))
            return
        default_value = self._profile_default_spin_value(name)
        if default_value is not None:
            self._set_pin_combo_value(combo, default_value)

    def _stage_profile_default_if_missing(self, name: str, combo: QComboBox) -> None:
        if self._get_tune_str(name) is not None:
            return
        default_value = self._profile_default_spin_value(name)
        if default_value is None:
            return
        self._set_pin_combo_value(combo, default_value)
        self._stage_int(name, default_value)

    def _get_definition_scalar(self, name: str):
        """Return the ScalarParameterDefinition for *name*, or None."""
        try:
            defn = self._presenter.definition
            if defn is None:
                return None
            for s in defn.scalars:
                if s.name == name:
                    return s
            return None
        except Exception:
            return None

    def _first_definition_scalar_name(self, candidates: tuple[str, ...]) -> str | None:
        for name in candidates:
            if self._get_definition_scalar(name) is not None:
                return name
        return None

    def _first_existing_list_name(self, candidates: tuple[str, ...], keywords: tuple[str, ...] = ()) -> str | None:
        tune_file = self._presenter.local_tune_edit_service.base_tune_file
        if tune_file is None:
            return None
        values = [*tune_file.constants, *tune_file.pc_variables]
        available = {
            item.name: item
            for item in values
            if isinstance(item.value, list)
        }
        for name in candidates:
            if name in available:
                return name
        lowered = tuple(keyword.lower() for keyword in keywords)
        if lowered:
            for name in available:
                haystack = name.lower()
                if all(keyword in haystack for keyword in lowered):
                    return name
        return None

    def _spark_mode_requires_cam_sync(self, index: int) -> bool:
        text = self._spark_mode_combo.itemText(index).strip().lower()
        data = self._spark_mode_combo.itemData(index)
        if "sequential" in text:
            return True
        if data is not None and "sequential" in str(data).strip().lower():
            return True
        return False

    def _inj_layout_requires_cam_sync(self, index: int) -> bool:
        text = self._injlayout_combo.itemText(index).strip().lower()
        data = self._injlayout_combo.itemData(index)
        if "sequential" in text and "semi" not in text:
            return True
        if data is None:
            return False
        raw = str(data).strip().lower()
        if "sequential" in raw and "semi" not in raw:
            return True
        return raw in {"3", "3.0"}

    @staticmethod
    def _combo_numeric_value(combo: QComboBox, index: int | None = None) -> float | None:
        actual_index = combo.currentIndex() if index is None else index
        if actual_index < 0:
            return None
        data = combo.itemData(actual_index)
        if data is None:
            return None
        try:
            return float(data)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _combo_is_active(cls, combo: QComboBox, index: int | None = None) -> bool:
        value = cls._combo_numeric_value(combo, index)
        if value is not None:
            return value > 0.0
        actual_index = combo.currentIndex() if index is None else index
        return actual_index > 0

    def _knock_mode_kind(self, index: int | None = None) -> str:
        actual_index = self._knock_mode_combo.currentIndex() if index is None else index
        text = self._knock_mode_combo.itemText(actual_index).strip().lower()
        if "digital" in text:
            return "digital"
        if "analog" in text:
            return "analog"
        value = self._combo_numeric_value(self._knock_mode_combo, actual_index)
        if value == 1.0:
            return "digital"
        if value == 2.0:
            return "analog"
        return "off"

    @staticmethod
    def _trigger_cam_requirement(pattern_text: str) -> str:
        text = pattern_text.strip().lower()
        required_keywords = (
            "dual wheel",
            "crank+cam",
            "crank + cam",
            "crank and cam",
            "with cam",
            "secondary trigger",
            "second trigger",
            "cam sync",
            "primary + secondary",
        )
        optional_keywords = (
            "optional cam",
            "cam optional",
            "secondary optional",
        )
        if any(keyword in text for keyword in optional_keywords):
            return "optional"
        if any(keyword in text for keyword in required_keywords):
            return "required"
        return "not_used"

    def _ego_type_is_wideband(self, index: int) -> bool:
        text = self._ego_type_combo.itemText(index).strip().lower()
        data = self._ego_type_combo.itemData(index)
        if "wide" in text:
            return True
        try:
            return float(data) == 2.0
        except (TypeError, ValueError):
            return False

    def _ego_type_uses_can(self, index: int) -> bool:
        return "can" in self._ego_type_combo.itemText(index).strip().lower()

    def _connected_board_native_can_available(self) -> bool | None:
        snapshot = self._presenter.current_runtime_snapshot
        if snapshot is None:
            return None
        telemetry = self._speeduino_runtime_telemetry_service.decode(snapshot)
        caps = telemetry.board_capabilities
        if caps.raw_value is None:
            return None
        return caps.native_can

    @staticmethod
    def _find_combo_by_value(combo: QComboBox, value: str) -> int:
        """Find a combo box item by its stored value data (or text if no data)."""
        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            numeric_value = None
        for i in range(combo.count()):
            data = combo.itemData(i)
            if data is not None and str(data) == value:
                return i
            if data is not None and numeric_value is not None:
                try:
                    if float(data) == numeric_value:
                        return i
                except (ValueError, TypeError):
                    pass
            # Fallback: match by index
        try:
            idx = int(float(value))
            if 0 <= idx < combo.count():
                return idx
        except (ValueError, TypeError):
            pass
        return -1
