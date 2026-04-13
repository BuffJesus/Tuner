from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tuner.domain.ecu_definition import ReferenceTableDefinition
from tuner.domain.generator_context import ForcedInductionTopology, SuperchargerType
from tuner.domain.operator_engine_context import CalibrationIntent
from tuner.services.hardware_preset_service import (
    HardwarePresetService,
    IgnitionHardwarePreset,
    InjectorHardwarePreset,
    TurboHardwarePreset,
    WidebandHardwarePreset,
)
from tuner.services.required_fuel_calculator_service import RequiredFuelCalculatorService
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter


def _set_form_row_visible(form: QFormLayout, field: QWidget, visible: bool) -> None:
    """Toggle a full QFormLayout row, not just the editor widget."""
    form.setRowVisible(field, visible)


class EngineSetupPanel(QWidget):
    """Always-visible Engine Setup wizard panel.

    Shows operator-supplied engine facts (displacement, cylinders, etc.),
    a live required fuel calculator, and a VE table generator button.
    Accessed via the "Engine Setup" top-level tab — no page navigation needed.

    All state mutations go through ``TuningWorkspacePresenter``; this widget
    is thin.  Call :meth:`set_presenter` when a project loads and
    :meth:`refresh` when the workspace changes.
    """

    status_message = Signal(str)
    workspace_state_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._presenter: TuningWorkspacePresenter | None = None
        self._hardware_preset_service = HardwarePresetService()
        self._updating = False
        self._active_wizard = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_presenter(self, presenter: TuningWorkspacePresenter | None) -> None:
        """Attach or detach the presenter.  Call when a project opens/closes."""
        self._presenter = presenter
        self.refresh()

    def refresh(self) -> None:
        """Re-read current context and update all displayed values."""
        if self._presenter is None:
            self._set_enabled(False)
            self._clear_calculated_fields()
            return
        self._set_enabled(True)
        self._populate_from_context()
        self._update_req_fuel_result()
        self._update_ve_table_combo()
        self._refresh_advanced_visibility()

    def open_hardware_setup_wizard(self, *, tab_index: int | None = None):
        """Open the guided hardware setup wizard for the current presenter."""
        if self._presenter is None:
            return None
        from tuner.ui.hardware_setup_wizard import HardwareSetupWizard

        wizard = self._active_wizard
        if wizard is None or not wizard.isVisible():
            wizard = HardwareSetupWizard(self._presenter, parent=self)
            wizard.status_message.connect(self.status_message)
            wizard.workspace_state_changed.connect(self.workspace_state_changed)
            self._active_wizard = wizard
        target_tab = self._suggest_wizard_tab_index() if tab_index is None else tab_index
        if target_tab is not None:
            wizard._tabs.setCurrentIndex(target_tab)  # noqa: SLF001
        wizard.show()
        wizard.raise_()
        wizard.activateWindow()
        return wizard

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # ---- Engine Facts ----
        facts_group = QGroupBox("Engine Facts")
        facts_form = QFormLayout(facts_group)
        facts_form.setContentsMargins(8, 8, 8, 8)

        self.displacement_edit = QLineEdit()
        self.displacement_edit.setPlaceholderText("e.g. 2000")
        self.displacement_edit.editingFinished.connect(self._on_displacement_changed)
        facts_form.addRow("Displacement (cc):", self.displacement_edit)

        self.cylinder_spin = QSpinBox()
        self.cylinder_spin.setRange(1, 16)
        self.cylinder_spin.setSpecialValueText("—")  # shows when value is 0
        self.cylinder_spin.setMinimum(0)             # 0 = not set
        self.cylinder_spin.valueChanged.connect(self._on_cylinders_changed)
        facts_form.addRow("Cylinders:", self.cylinder_spin)

        self.compression_edit = QLineEdit()
        self.compression_edit.setPlaceholderText("e.g. 9.5")
        self.compression_edit.editingFinished.connect(self._on_compression_changed)
        facts_form.addRow("Compression ratio:", self.compression_edit)

        self.advanced_mode_check = QCheckBox("Show Advanced Setup Inputs")
        self.advanced_mode_check.setToolTip(
            "Reveal Tier 2 setup facts that can improve generator quality without slowing the default first-start workflow."
        )
        self.advanced_mode_check.toggled.connect(self._refresh_advanced_visibility)
        facts_form.addRow("", self.advanced_mode_check)

        self.cam_edit = QLineEdit()
        self.cam_edit.setPlaceholderText("e.g. 240  (degrees @ 0.050\")")
        self.cam_edit.editingFinished.connect(self._on_cam_changed)
        facts_form.addRow("Cam duration (°):", self.cam_edit)

        self.head_flow_combo = QComboBox()
        self.head_flow_combo.addItem("Not set", None)
        self.head_flow_combo.addItem("Stock / OEM", "stock_oem")
        self.head_flow_combo.addItem("Mild ported", "mild_ported")
        self.head_flow_combo.addItem("Race ported / high flow", "race_ported")
        self.head_flow_combo.currentIndexChanged.connect(self._on_head_flow_class_changed)
        facts_form.addRow("Head flow class:", self.head_flow_combo)

        self.manifold_style_combo = QComboBox()
        self.manifold_style_combo.addItem("Not set", None)
        self.manifold_style_combo.addItem("Long runner plenum", "long_runner_plenum")
        self.manifold_style_combo.addItem("Short runner plenum", "short_runner_plenum")
        self.manifold_style_combo.addItem("ITB / individual runners", "itb")
        self.manifold_style_combo.addItem("Log / compact manifold", "log_compact")
        self.manifold_style_combo.currentIndexChanged.connect(self._on_manifold_style_changed)
        facts_form.addRow("Manifold style:", self.manifold_style_combo)

        self.intent_combo = QComboBox()
        self.intent_combo.addItems(["First Start", "Drivable Base"])
        self.intent_combo.setToolTip(
            "First Start: maximally conservative — engine should idle safely.\n"
            "Drivable Base: conservative but suitable for a first road drive."
        )
        self.intent_combo.currentIndexChanged.connect(self._on_intent_changed)
        facts_form.addRow("Calibration intent:", self.intent_combo)

        layout.addWidget(facts_group)

        # ---- Induction ----
        induction_group = QGroupBox("Induction")
        induction_form = QFormLayout(induction_group)
        induction_form.setContentsMargins(8, 8, 8, 8)
        self._induction_form = induction_form

        self.topology_combo = QComboBox()
        self.topology_combo.setToolTip(
            "Induction arrangement of your engine.\n"
            "Used by the VE and spark table generators to shape conservative starter tables."
        )
        for topology in ForcedInductionTopology:
            self.topology_combo.addItem(
                topology.value.replace("_", " ").title(), topology
            )
        self.topology_combo.currentIndexChanged.connect(self._on_topology_changed)
        induction_form.addRow("Topology:", self.topology_combo)

        self.boost_target_spin = QDoubleSpinBox()
        self.boost_target_spin.setRange(0.0, 43.5)
        self.boost_target_spin.setSingleStep(1.0)
        self.boost_target_spin.setDecimals(1)
        self.boost_target_spin.setSuffix(" psi")
        self.boost_target_spin.setToolTip(
            "Boost target in gauge psi (above atmospheric).\n"
            "0 psi = atmospheric (101 kPa absolute).\n"
            "Common targets: 8–12 psi street, 15–20 psi performance.\n"
            "Stored internally as kPa absolute for generator calculations."
        )
        self.boost_target_spin.valueChanged.connect(self._on_boost_target_changed)
        self._boost_target_row_label = QLabel("Boost target:")
        induction_form.addRow(self._boost_target_row_label, self.boost_target_spin)

        self.intercooler_check = QCheckBox("Intercooler fitted")
        self.intercooler_check.setToolTip(
            "Check if an air-to-air or air-to-water intercooler is installed.\n"
            "Affects charge-air temperature assumptions in generator helpers."
        )
        self.intercooler_check.toggled.connect(self._on_intercooler_changed)
        self._intercooler_row_label = QLabel("Intercooler:")
        induction_form.addRow(self._intercooler_row_label, self.intercooler_check)

        self.supercharger_type_combo = QComboBox()
        self.supercharger_type_combo.addItem("Not set", None)
        self.supercharger_type_combo.addItem("Roots", SuperchargerType.ROOTS)
        self.supercharger_type_combo.addItem("Twin-screw", SuperchargerType.TWIN_SCREW)
        self.supercharger_type_combo.addItem("Centrifugal", SuperchargerType.CENTRIFUGAL)
        self.supercharger_type_combo.setToolTip(
            "Supercharger technology changes low-RPM airflow assumptions for starter VE shaping."
        )
        self.supercharger_type_combo.currentIndexChanged.connect(self._on_supercharger_type_changed)
        induction_form.addRow("Supercharger type:", self.supercharger_type_combo)

        self.compressor_flow_spin = QDoubleSpinBox()
        self.compressor_flow_spin.setRange(0.0, 200.0)
        self.compressor_flow_spin.setSingleStep(1.0)
        self.compressor_flow_spin.setDecimals(1)
        self.compressor_flow_spin.setSuffix(" lb/min")
        self.compressor_flow_spin.setSpecialValueText("not set")
        self.compressor_flow_spin.setToolTip(
            "Approximate corrected compressor flow at peak efficiency. Advanced Tier 2 input for boosted VE shaping."
        )
        self.compressor_flow_spin.valueChanged.connect(self._on_compressor_flow_changed)
        induction_form.addRow("Compressor flow:", self.compressor_flow_spin)

        self.compressor_pr_spin = QDoubleSpinBox()
        self.compressor_pr_spin.setRange(0.0, 5.0)
        self.compressor_pr_spin.setSingleStep(0.05)
        self.compressor_pr_spin.setDecimals(2)
        self.compressor_pr_spin.setSpecialValueText("not set")
        self.compressor_pr_spin.setToolTip(
            "Approximate compressor pressure ratio at peak efficiency. Advanced Tier 2 input."
        )
        self.compressor_pr_spin.valueChanged.connect(self._on_compressor_pr_changed)
        induction_form.addRow("Compressor PR:", self.compressor_pr_spin)

        self.compressor_inducer_spin = QDoubleSpinBox()
        self.compressor_inducer_spin.setRange(0.0, 150.0)
        self.compressor_inducer_spin.setSingleStep(0.5)
        self.compressor_inducer_spin.setDecimals(1)
        self.compressor_inducer_spin.setSuffix(" mm")
        self.compressor_inducer_spin.setSpecialValueText("not set")
        self.compressor_inducer_spin.setToolTip("Compressor inducer diameter. Advanced Tier 2 turbo sizing input.")
        self.compressor_inducer_spin.valueChanged.connect(self._on_compressor_inducer_changed)
        induction_form.addRow("Compressor inducer:", self.compressor_inducer_spin)

        self.compressor_exducer_spin = QDoubleSpinBox()
        self.compressor_exducer_spin.setRange(0.0, 150.0)
        self.compressor_exducer_spin.setSingleStep(0.5)
        self.compressor_exducer_spin.setDecimals(1)
        self.compressor_exducer_spin.setSuffix(" mm")
        self.compressor_exducer_spin.setSpecialValueText("not set")
        self.compressor_exducer_spin.setToolTip("Compressor exducer diameter. Advanced Tier 2 turbo sizing input.")
        self.compressor_exducer_spin.valueChanged.connect(self._on_compressor_exducer_changed)
        induction_form.addRow("Compressor exducer:", self.compressor_exducer_spin)

        self.compressor_ar_spin = QDoubleSpinBox()
        self.compressor_ar_spin.setRange(0.0, 3.0)
        self.compressor_ar_spin.setSingleStep(0.01)
        self.compressor_ar_spin.setDecimals(2)
        self.compressor_ar_spin.setSpecialValueText("not set")
        self.compressor_ar_spin.setToolTip("Approximate turbine A/R. Advanced Tier 2 spool/context input.")
        self.compressor_ar_spin.valueChanged.connect(self._on_compressor_ar_changed)
        induction_form.addRow("Turbine A/R:", self.compressor_ar_spin)

        layout.addWidget(induction_group)
        self._induction_group = induction_group

        profile_group = QGroupBox("Hardware Profiles")
        profile_layout = QVBoxLayout(profile_group)
        profile_layout.setContentsMargins(8, 8, 8, 8)
        profile_layout.setSpacing(6)

        profile_note = QLabel(
            "Choose reviewed starter profiles for common ignition, injector, and wideband hardware. "
            "These settings are saved in the project context and used by the guided setup flow."
        )
        profile_note.setWordWrap(True)
        profile_layout.addWidget(profile_note)

        injector_form = QFormLayout()
        self.injector_profile_combo = QComboBox()
        self.injector_profile_combo.addItem("No injector profile", None)
        for preset in self._hardware_preset_service.injector_presets():
            self.injector_profile_combo.addItem(preset.label, preset)
        self.injector_profile_combo.currentIndexChanged.connect(self._on_injector_profile_changed)
        injector_form.addRow("Injector profile:", self.injector_profile_combo)

        self.base_fuel_pressure_spin = QDoubleSpinBox()
        self.base_fuel_pressure_spin.setRange(20.0, 100.0)
        self.base_fuel_pressure_spin.setSingleStep(0.5)
        self.base_fuel_pressure_spin.setDecimals(1)
        self.base_fuel_pressure_spin.setSuffix(" psi")
        self.base_fuel_pressure_spin.setValue(43.5)
        self.base_fuel_pressure_spin.valueChanged.connect(self._on_base_fuel_pressure_changed)
        injector_form.addRow("Base fuel pressure:", self.base_fuel_pressure_spin)

        self.injector_pressure_model_combo = QComboBox()
        self.injector_pressure_model_combo.addItem("Not set", None)
        self.injector_pressure_model_combo.addItem("Fixed pressure (no compensation)", "fixed_pressure")
        self.injector_pressure_model_combo.addItem("Vacuum referenced (rising-rate FPR)", "vacuum_referenced")
        self.injector_pressure_model_combo.addItem("Operator-specified pressure", "operator_specified")
        self.injector_pressure_model_combo.currentIndexChanged.connect(self._on_injector_pressure_model_changed)
        injector_form.addRow("Pressure model:", self.injector_pressure_model_combo)

        self.secondary_injector_pressure_spin = QDoubleSpinBox()
        self.secondary_injector_pressure_spin.setRange(0.0, 100.0)
        self.secondary_injector_pressure_spin.setSingleStep(0.5)
        self.secondary_injector_pressure_spin.setDecimals(1)
        self.secondary_injector_pressure_spin.setSuffix(" psi")
        self.secondary_injector_pressure_spin.setSpecialValueText("not set")
        self.secondary_injector_pressure_spin.valueChanged.connect(self._on_secondary_injector_pressure_changed)
        injector_form.addRow("Secondary ref pressure:", self.secondary_injector_pressure_spin)

        self.injector_characterization_combo = QComboBox()
        self.injector_characterization_combo.addItem("Not set", None)
        self.injector_characterization_combo.addItem("Nominal flow only", "nominal_flow_only")
        self.injector_characterization_combo.addItem("Flow + single dead time", "flow_plus_deadtime")
        self.injector_characterization_combo.addItem("Flow + voltage correction table", "flow_plus_voltage_table")
        self.injector_characterization_combo.addItem("Full pressure + voltage characterization", "full_characterization")
        self.injector_characterization_combo.currentIndexChanged.connect(self._on_injector_characterization_changed)
        injector_form.addRow("Injector data depth:", self.injector_characterization_combo)
        self._injector_form = injector_form
        profile_layout.addLayout(injector_form)

        self.injector_profile_summary = QLabel("")
        self.injector_profile_summary.setWordWrap(True)
        profile_layout.addWidget(self.injector_profile_summary)

        ignition_form = QFormLayout()
        self.ignition_profile_combo = QComboBox()
        self.ignition_profile_combo.addItem("No ignition profile", None)
        for preset in self._hardware_preset_service.ignition_presets():
            self.ignition_profile_combo.addItem(preset.label, preset)
        self.ignition_profile_combo.currentIndexChanged.connect(self._on_ignition_profile_changed)
        ignition_form.addRow("Ignition profile:", self.ignition_profile_combo)
        profile_layout.addLayout(ignition_form)

        self.ignition_profile_summary = QLabel("")
        self.ignition_profile_summary.setWordWrap(True)
        profile_layout.addWidget(self.ignition_profile_summary)

        wideband_form = QFormLayout()
        self.wideband_profile_combo = QComboBox()
        self.wideband_profile_combo.addItem("No wideband profile", None)
        for preset in self._hardware_preset_service.wideband_presets():
            self.wideband_profile_combo.addItem(preset.label, preset)
        self.wideband_profile_combo.currentIndexChanged.connect(self._on_wideband_profile_changed)
        wideband_form.addRow("Wideband profile:", self.wideband_profile_combo)

        self.wideband_reference_combo = QComboBox()
        self.wideband_reference_combo.setToolTip(
            "AFR calibration presets exposed by the current definition's AFR/O2 reference table."
        )
        self.wideband_reference_combo.currentIndexChanged.connect(self._on_wideband_reference_changed)
        wideband_form.addRow("AFR calibration preset:", self.wideband_reference_combo)
        self._wideband_form = wideband_form
        self._wideband_reference_table: ReferenceTableDefinition | None = None
        profile_layout.addLayout(wideband_form)

        self.wideband_profile_summary = QLabel("")
        self.wideband_profile_summary.setWordWrap(True)
        profile_layout.addWidget(self.wideband_profile_summary)

        turbo_form = QFormLayout()
        self.turbo_profile_combo = QComboBox()
        self.turbo_profile_combo.addItem("No turbo profile", None)
        for preset in self._hardware_preset_service.turbo_presets():
            self.turbo_profile_combo.addItem(preset.label, preset)
        self.turbo_profile_combo.currentIndexChanged.connect(self._on_turbo_profile_changed)
        turbo_form.addRow("Turbo profile:", self.turbo_profile_combo)
        profile_layout.addLayout(turbo_form)

        self.turbo_profile_summary = QLabel("")
        self.turbo_profile_summary.setWordWrap(True)
        profile_layout.addWidget(self.turbo_profile_summary)

        layout.addWidget(profile_group)

        # ---- Required Fuel Calculator ----
        req_group = QGroupBox("Required Fuel Calculator")
        req_layout = QVBoxLayout(req_group)
        req_layout.setContentsMargins(8, 8, 8, 8)
        req_layout.setSpacing(6)

        tune_note = QLabel(
            "Injector flow and stoich AFR are read from the loaded tune where available."
        )
        tune_note.setWordWrap(True)
        tune_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        req_layout.addWidget(tune_note)

        self.req_inputs_label = QLabel("—")
        self.req_inputs_label.setWordWrap(True)
        req_layout.addWidget(self.req_inputs_label)

        self.req_result_label = QLabel("—")
        self.req_result_label.setWordWrap(True)
        req_layout.addWidget(self.req_result_label)

        apply_row = QHBoxLayout()
        self.req_apply_button = QPushButton("Apply to reqFuel in Tune")
        self.req_apply_button.setToolTip(
            "Stages the computed reqFuel value on the injector page.\n"
            "The tune must be open and an injector page must be selected."
        )
        self.req_apply_button.clicked.connect(self._on_apply_req_fuel)
        apply_row.addWidget(self.req_apply_button)
        apply_row.addStretch(1)
        req_layout.addLayout(apply_row)

        layout.addWidget(req_group)

        # ---- Base Tune Generator ----
        gen_group = QGroupBox("Base Tune Generator")
        gen_layout = QVBoxLayout(gen_group)
        gen_layout.setContentsMargins(8, 8, 8, 8)
        gen_layout.setSpacing(6)

        gen_note = QLabel(
            "Generates a conservative 16 × 16 VE table shaped for the current engine "
            "and induction topology. The result is staged as a reviewable edit — "
            "nothing is written to the ECU automatically."
        )
        gen_note.setWordWrap(True)
        gen_layout.addWidget(gen_note)

        self.gen_topology_label = QLabel("Induction topology: —")
        gen_layout.addWidget(self.gen_topology_label)

        self.gen_status_label = QLabel("")
        self.gen_status_label.setWordWrap(True)
        gen_layout.addWidget(self.gen_status_label)

        table_row = QFormLayout()
        self.ve_table_combo = QComboBox()
        self.ve_table_combo.setEditable(True)
        self.ve_table_combo.setPlaceholderText("veTable")
        table_row.addRow("VE table parameter:", self.ve_table_combo)
        gen_layout.addLayout(table_row)

        gen_button_row = QHBoxLayout()
        self.gen_ve_button = QPushButton("Generate VE Table")
        self.gen_ve_button.setToolTip(
            "Generates a conservative starter VE table and stages it as an edit.\n"
            "Review the staged change, then Write to RAM / Burn to Flash as normal."
        )
        self.gen_ve_button.clicked.connect(self._on_generate_ve)
        gen_button_row.addWidget(self.gen_ve_button)
        gen_button_row.addStretch(1)
        gen_layout.addLayout(gen_button_row)

        layout.addWidget(gen_group)

        # ---- Hardware Setup Wizard ----
        wizard_group = QGroupBox("Hardware Setup Wizard")
        wizard_layout = QVBoxLayout(wizard_group)
        wizard_layout.setContentsMargins(8, 8, 8, 8)
        wizard_layout.setSpacing(6)

        wizard_note = QLabel(
            "Step-by-step configuration for board layout, engine geometry, "
            "injectors, trigger decoder, and sensors."
        )
        wizard_note.setWordWrap(True)
        wizard_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        wizard_layout.addWidget(wizard_note)

        wizard_button_row = QHBoxLayout()
        self.open_wizard_button = QPushButton("Open Hardware Setup Wizard...")
        self.open_wizard_button.setToolTip(
            "Opens a guided step-by-step dialog for configuring the board, "
            "engine geometry, injectors, trigger pattern, and sensors."
        )
        self.open_wizard_button.clicked.connect(self._on_open_wizard)
        wizard_button_row.addWidget(self.open_wizard_button)
        wizard_button_row.addStretch(1)
        wizard_layout.addLayout(wizard_button_row)

        layout.addWidget(wizard_group)
        layout.addStretch(1)
        self._facts_form = facts_form
        self._refresh_advanced_visibility()

        self._set_enabled(False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_enabled(self, enabled: bool) -> None:
        for widget in (
            self.displacement_edit,
            self.cylinder_spin,
            self.compression_edit,
            self.advanced_mode_check,
            self.cam_edit,
            self.head_flow_combo,
            self.manifold_style_combo,
            self.intent_combo,
            self.injector_profile_combo,
            self.base_fuel_pressure_spin,
            self.injector_pressure_model_combo,
            self.secondary_injector_pressure_spin,
            self.injector_characterization_combo,
            self.ignition_profile_combo,
            self.wideband_profile_combo,
            self.wideband_reference_combo,
            self.turbo_profile_combo,
            self.topology_combo,
            self.boost_target_spin,
            self.intercooler_check,
            self.supercharger_type_combo,
            self.compressor_flow_spin,
            self.compressor_pr_spin,
            self.compressor_inducer_spin,
            self.compressor_exducer_spin,
            self.compressor_ar_spin,
            self.req_apply_button,
            self.gen_ve_button,
            self.ve_table_combo,
            self.open_wizard_button,
        ):
            widget.setEnabled(enabled)

    def _clear_calculated_fields(self) -> None:
        self.req_inputs_label.setText("No tune loaded.")
        self.req_result_label.setText("—")
        self.req_apply_button.setEnabled(False)
        self.gen_topology_label.setText("Induction topology: —")
        self.gen_status_label.setText("")
        self.gen_ve_button.setEnabled(False)

    def _refresh_advanced_visibility(self) -> None:
        advanced = self.advanced_mode_check.isChecked()
        _set_form_row_visible(self._facts_form, self.cam_edit, advanced)
        _set_form_row_visible(self._facts_form, self.head_flow_combo, advanced)
        _set_form_row_visible(self._facts_form, self.manifold_style_combo, advanced)
        _set_form_row_visible(self._injector_form, self.injector_pressure_model_combo, advanced)
        _set_form_row_visible(
            self._injector_form,
            self.base_fuel_pressure_spin,
            advanced and self._effective_injector_pressure_model() != "fixed_pressure",
        )
        _set_form_row_visible(
            self._injector_form,
            self.secondary_injector_pressure_spin,
            advanced and self._should_show_secondary_injector_pressure(),
        )
        _set_form_row_visible(self._injector_form, self.injector_characterization_combo, advanced)
        forced = self.topology_combo.itemData(self.topology_combo.currentIndex()) != ForcedInductionTopology.NA
        show_airflow = advanced and forced
        for field in (
            self.compressor_flow_spin,
            self.compressor_pr_spin,
            self.compressor_inducer_spin,
            self.compressor_exducer_spin,
            self.compressor_ar_spin,
        ):
            _set_form_row_visible(self._induction_form, field, show_airflow)

    def _populate_from_context(self) -> None:
        if self._presenter is None:
            return
        ctx = self._presenter.operator_engine_context_service.get()
        self._updating = True
        try:
            self.displacement_edit.setText(
                str(ctx.displacement_cc) if ctx.displacement_cc is not None else ""
            )
            blocker = QSignalBlocker(self.cylinder_spin)
            self.cylinder_spin.setValue(ctx.cylinder_count if ctx.cylinder_count is not None else 0)
            del blocker
            self.compression_edit.setText(
                str(ctx.compression_ratio) if ctx.compression_ratio is not None else ""
            )
            blocker_advanced = QSignalBlocker(self.advanced_mode_check)
            self.advanced_mode_check.setChecked(
                ctx.cam_duration_deg is not None
                or ctx.head_flow_class is not None
                or ctx.intake_manifold_style is not None
                or (ctx.base_fuel_pressure_psi is not None and abs(ctx.base_fuel_pressure_psi - 43.5) > 1e-6)
                or ctx.injector_pressure_model is not None
                or ctx.secondary_injector_reference_pressure_psi is not None
                or ctx.injector_characterization is not None
                or ctx.supercharger_type is not None
            )
            del blocker_advanced
            self.cam_edit.setText(
                str(ctx.cam_duration_deg) if ctx.cam_duration_deg is not None else ""
            )
            blocker_head = QSignalBlocker(self.head_flow_combo)
            self.head_flow_combo.setCurrentIndex(max(0, self.head_flow_combo.findData(ctx.head_flow_class)))
            del blocker_head
            blocker_manifold = QSignalBlocker(self.manifold_style_combo)
            self.manifold_style_combo.setCurrentIndex(max(0, self.manifold_style_combo.findData(ctx.intake_manifold_style)))
            del blocker_manifold
            blocker2 = QSignalBlocker(self.intent_combo)
            self.intent_combo.setCurrentIndex(
                1 if ctx.calibration_intent == CalibrationIntent.DRIVABLE_BASE else 0
            )
            del blocker2

            blocker_profile = QSignalBlocker(self.injector_profile_combo)
            self.injector_profile_combo.setCurrentIndex(0)
            for i in range(1, self.injector_profile_combo.count()):
                preset = self.injector_profile_combo.itemData(i)
                if isinstance(preset, InjectorHardwarePreset) and preset.key == ctx.injector_preset_key:
                    self.injector_profile_combo.setCurrentIndex(i)
                    break
            del blocker_profile

            blocker_pressure = QSignalBlocker(self.base_fuel_pressure_spin)
            self.base_fuel_pressure_spin.setValue(ctx.base_fuel_pressure_psi or 43.5)
            del blocker_pressure
            blocker_pressure_model = QSignalBlocker(self.injector_pressure_model_combo)
            self.injector_pressure_model_combo.setCurrentIndex(
                max(0, self.injector_pressure_model_combo.findData(ctx.injector_pressure_model))
            )
            del blocker_pressure_model
            blocker_secondary_pressure = QSignalBlocker(self.secondary_injector_pressure_spin)
            self.secondary_injector_pressure_spin.setValue(ctx.secondary_injector_reference_pressure_psi or 0.0)
            del blocker_secondary_pressure
            blocker_inj_char = QSignalBlocker(self.injector_characterization_combo)
            self.injector_characterization_combo.setCurrentIndex(
                max(0, self.injector_characterization_combo.findData(ctx.injector_characterization))
            )
            del blocker_inj_char

            blocker_ign = QSignalBlocker(self.ignition_profile_combo)
            self.ignition_profile_combo.setCurrentIndex(0)
            for i in range(1, self.ignition_profile_combo.count()):
                preset = self.ignition_profile_combo.itemData(i)
                if isinstance(preset, IgnitionHardwarePreset) and preset.key == ctx.ignition_preset_key:
                    self.ignition_profile_combo.setCurrentIndex(i)
                    break
            del blocker_ign

            blocker_wideband = QSignalBlocker(self.wideband_profile_combo)
            self.wideband_profile_combo.setCurrentIndex(0)
            for i in range(1, self.wideband_profile_combo.count()):
                preset = self.wideband_profile_combo.itemData(i)
                if isinstance(preset, WidebandHardwarePreset) and preset.key == ctx.wideband_preset_key:
                    self.wideband_profile_combo.setCurrentIndex(i)
                    break
            del blocker_wideband
            self._refresh_wideband_reference_options(
                preferred_label=ctx.wideband_reference_table_label,
                prefer_match=True,
            )

            blocker_turbo = QSignalBlocker(self.turbo_profile_combo)
            self.turbo_profile_combo.setCurrentIndex(0)
            for i in range(1, self.turbo_profile_combo.count()):
                preset = self.turbo_profile_combo.itemData(i)
                if isinstance(preset, TurboHardwarePreset) and preset.key == ctx.turbo_preset_key:
                    self.turbo_profile_combo.setCurrentIndex(i)
                    break
            del blocker_turbo

            # Induction
            blocker3 = QSignalBlocker(self.topology_combo)
            for i in range(self.topology_combo.count()):
                if self.topology_combo.itemData(i) == ctx.forced_induction_topology:
                    self.topology_combo.setCurrentIndex(i)
                    break
            del blocker3

            blocker4 = QSignalBlocker(self.boost_target_spin)
            kpa_abs = ctx.boost_target_kpa or 170.0  # default ~10 psi gauge
            self.boost_target_spin.setValue(max(0.0, (kpa_abs - 101.325) / 6.89476))
            del blocker4

            blocker5 = QSignalBlocker(self.intercooler_check)
            self.intercooler_check.setChecked(ctx.intercooler_present)
            del blocker5
            blocker_sc = QSignalBlocker(self.supercharger_type_combo)
            self.supercharger_type_combo.setCurrentIndex(
                max(0, self.supercharger_type_combo.findData(ctx.supercharger_type))
            )
            del blocker_sc

            blocker_flow = QSignalBlocker(self.compressor_flow_spin)
            self.compressor_flow_spin.setValue(ctx.compressor_corrected_flow_lbmin or 0.0)
            del blocker_flow
            blocker_pr = QSignalBlocker(self.compressor_pr_spin)
            self.compressor_pr_spin.setValue(ctx.compressor_pressure_ratio or 0.0)
            del blocker_pr
            blocker_inducer = QSignalBlocker(self.compressor_inducer_spin)
            self.compressor_inducer_spin.setValue(ctx.compressor_inducer_mm or 0.0)
            del blocker_inducer
            blocker_exducer = QSignalBlocker(self.compressor_exducer_spin)
            self.compressor_exducer_spin.setValue(ctx.compressor_exducer_mm or 0.0)
            del blocker_exducer
            blocker_ar = QSignalBlocker(self.compressor_ar_spin)
            self.compressor_ar_spin.setValue(ctx.compressor_ar or 0.0)
            del blocker_ar

            self._update_induction_visibility(ctx.forced_induction_topology)
            self._refresh_profile_summaries()
            self._refresh_advanced_visibility()
        finally:
            self._updating = False

    def _refresh_profile_summaries(self) -> None:
        if self._presenter is None:
            self.injector_profile_summary.setText("")
            self.ignition_profile_summary.setText("")
            self.wideband_profile_summary.setText("")
            self.turbo_profile_summary.setText("")
            return
        ctx = self._presenter.operator_engine_context_service.get()
        injector_key = ctx.injector_preset_key
        injector_preset = next(
            (item for item in self._hardware_preset_service.injector_presets() if item.key == injector_key),
            None,
        )
        if injector_preset is None:
            self.injector_profile_summary.setText("Injector profile: manual / not set.")
        else:
            pressure = ctx.base_fuel_pressure_psi or 43.5
            scaled_flow = self._hardware_preset_service.injector_flow_for_pressure(injector_preset, pressure)
            confidence = self._hardware_preset_service.source_confidence_label(
                source_note=injector_preset.source_note,
                source_url=injector_preset.source_url,
            )
            self.injector_profile_summary.setText(
                f"Injector profile: {injector_preset.label} | {scaled_flow:.0f} cc/min at {pressure:.1f} psi"
                f" | Pressure model: {self._injector_pressure_model_text(ctx.injector_pressure_model)}"
                f" | Secondary ref: {self._secondary_injector_pressure_text(ctx.secondary_injector_reference_pressure_psi)}"
                f" | [{confidence}] {injector_preset.source_note}"
            )

        ignition_key = ctx.ignition_preset_key
        ignition_preset = next(
            (item for item in self._hardware_preset_service.ignition_presets() if item.key == ignition_key),
            None,
        )
        if ignition_preset is None:
            self.ignition_profile_summary.setText("Ignition profile: manual / not set.")
        else:
            confidence = self._hardware_preset_service.source_confidence_label(
                source_note=ignition_preset.source_note,
                source_url=ignition_preset.source_url,
            )
            self.ignition_profile_summary.setText(
                f"Ignition profile: {ignition_preset.label} | Dwell {ignition_preset.running_dwell_ms:.1f}/{ignition_preset.cranking_dwell_ms:.1f} ms | [{confidence}] {ignition_preset.source_note}"
            )

        wideband_key = ctx.wideband_preset_key
        wideband_preset = next(
            (item for item in self._hardware_preset_service.wideband_presets() if item.key == wideband_key),
            None,
        )
        if wideband_preset is None:
            self.wideband_profile_summary.setText("Wideband profile: manual / not set.")
        else:
            confidence = self._hardware_preset_service.source_confidence_label(
                source_note=wideband_preset.source_note,
                source_url=wideband_preset.source_url,
            )
            reference_table = ctx.wideband_reference_table_label or "not set"
            suggested_label = None
            matched_index = self._match_wideband_reference_solution_index(wideband_preset)
            if matched_index > 0:
                suggested_label = self.wideband_reference_combo.itemText(matched_index)
            suggestion_text = ""
            if suggested_label and suggested_label != reference_table:
                suggestion_text = f" | Suggested ref: {suggested_label}"
            self.wideband_profile_summary.setText(
                f"Wideband profile: {wideband_preset.label} | AFR: {wideband_preset.afr_equation}"
                f" | Ref table: {reference_table}{suggestion_text} | [{confidence}] {wideband_preset.source_note}"
            )

        turbo_key = ctx.turbo_preset_key
        turbo_preset = next(
            (item for item in self._hardware_preset_service.turbo_presets() if item.key == turbo_key),
            None,
        )
        if turbo_preset is None:
            self.turbo_profile_summary.setText("Turbo profile: manual / not set.")
        else:
            confidence = self._hardware_preset_service.source_confidence_label(
                source_note=turbo_preset.source_note,
                source_url=turbo_preset.source_url,
            )
            flow_text = (
                f"{turbo_preset.compressor_corrected_flow_lbmin:.0f} lb/min"
                if turbo_preset.compressor_corrected_flow_lbmin is not None
                else "flow not set"
            )
            self.turbo_profile_summary.setText(
                f"Turbo profile: {turbo_preset.label} | Compressor {turbo_preset.compressor_inducer_mm:.1f}/{turbo_preset.compressor_exducer_mm:.1f} mm | "
                f"Turbine A/R {turbo_preset.turbine_ar:.2f} | {flow_text} | [{confidence}] {turbo_preset.source_note}"
            )

    @staticmethod
    def _injector_pressure_model_text(value: str | None) -> str:
        labels = {
            "fixed_pressure": "fixed pressure",
            "vacuum_referenced": "vacuum referenced",
            "operator_specified": "operator-specified pressure",
            "not_modeled": "not modeled",
        }
        return labels.get(value, "not set")

    @staticmethod
    def _secondary_injector_pressure_text(value: float | None) -> str:
        return f"{value:.1f} psi" if value is not None else "not set"

    @staticmethod
    def _normalize_preset_label(text: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else " " for ch in text).strip()

    def _selected_wideband_reference_label(self) -> str | None:
        value = self.wideband_reference_combo.currentData()
        return value if isinstance(value, str) and value.strip() else None

    def _find_wideband_reference_index_by_label(self, label: str | None) -> int:
        if not label:
            return -1
        for index in range(self.wideband_reference_combo.count()):
            if self.wideband_reference_combo.itemData(index) == label:
                return index
        return -1

    def _match_wideband_reference_solution_index(self, preset: WidebandHardwarePreset | None) -> int:
        if preset is None or self._wideband_reference_table is None:
            return -1
        aliases = {self._normalize_preset_label(alias) for alias in preset.reference_table_aliases}
        if not aliases:
            return -1
        for index, solution in enumerate(self._wideband_reference_table.solutions, start=1):
            label = self._normalize_preset_label(solution.label)
            if any(alias in label for alias in aliases):
                return index
        return -1

    def _refresh_wideband_reference_options(
        self,
        *,
        preferred_label: str | None = None,
        prefer_match: bool = False,
    ) -> None:
        self._wideband_reference_table = None
        if self._presenter is not None and self._presenter.definition is not None:
            self._wideband_reference_table = next(
                (
                    table
                    for table in self._presenter.definition.reference_tables
                    if any(token in f"{table.table_id} {table.label}".lower() for token in ("geno2", "afr", "o2"))
                ),
                None,
            )
        blocker = QSignalBlocker(self.wideband_reference_combo)
        self.wideband_reference_combo.clear()
        table = self._wideband_reference_table
        if table is None:
            self.wideband_reference_combo.addItem("(no AFR presets exposed by definition)", None)
            self.wideband_reference_combo.setCurrentIndex(0)
            _set_form_row_visible(self._wideband_form, self.wideband_reference_combo, False)
            del blocker
            return
        self.wideband_reference_combo.addItem("Definition default / not set", None)
        for solution in table.solutions:
            self.wideband_reference_combo.addItem(solution.label, solution.label)
        selected_index = self._find_wideband_reference_index_by_label(preferred_label)
        if selected_index < 0 and prefer_match:
            preset = self.wideband_profile_combo.currentData()
            selected_index = self._match_wideband_reference_solution_index(
                preset if isinstance(preset, WidebandHardwarePreset) else None
            )
        self.wideband_reference_combo.setCurrentIndex(max(0, selected_index))
        _set_form_row_visible(self._wideband_form, self.wideband_reference_combo, True)
        del blocker

    def _effective_injector_pressure_model(self) -> str:
        if self._presenter is None:
            return "fixed_pressure"
        value = self._presenter.operator_engine_context_service.get().injector_pressure_model
        if value == "not_modeled":
            return "operator_specified"
        return value or "fixed_pressure"

    def _should_show_secondary_injector_pressure(self) -> bool:
        if self._presenter is None:
            return False
        ctx = self._presenter.operator_engine_context_service.get()
        if ctx.secondary_injector_reference_pressure_psi is not None:
            return True
        gen_ctx = self._build_generator_context()
        if gen_ctx is not None and gen_ctx.injector_flow_secondary_ccmin not in (None, 0.0):
            return True
        raw_inj = self._presenter.local_tune_edit_service.get_value("nInjectors")
        raw_cyl = self._presenter.local_tune_edit_service.get_value("nCylinders")
        if raw_inj is None or raw_cyl is None:
            return False
        try:
            return int(float(raw_inj.value)) > int(float(raw_cyl.value))
        except (TypeError, ValueError):
            return False

    def _update_req_fuel_result(self) -> None:
        if self._presenter is None:
            return

        ctx = self._presenter.operator_engine_context_service.get()

        # Pull injector flow and stoich from the generator context if a tune is loaded
        gen_ctx = self._build_generator_context()
        injector_flow = gen_ctx.injector_flow_ccmin if gen_ctx else None
        stoich = (gen_ctx.stoich_ratio if gen_ctx else None) or 14.7
        cylinder_count = (
            ctx.cylinder_count
            or (gen_ctx.cylinder_count if gen_ctx else None)
        )
        displacement = ctx.displacement_cc or (gen_ctx.displacement_cc if gen_ctx else None)

        # Topology
        topology = gen_ctx.forced_induction_topology if gen_ctx else ctx.forced_induction_topology
        topology_text = topology.value.replace("_", " ").title()
        self.gen_topology_label.setText(f"Induction topology: {topology_text}")

        # Build inputs summary
        missing: list[str] = []
        if not displacement:
            missing.append("displacement (enter above)")
        if not cylinder_count:
            missing.append("cylinders (enter above)")
        if not injector_flow:
            missing.append("injector flow (set in tune)")

        if missing:
            self.req_inputs_label.setText("Still needed: " + ", ".join(missing))
            self.req_result_label.setText("—")
            self.req_apply_button.setEnabled(False)
            return

        parts = [
            f"{displacement:.0f} cc",
            f"{cylinder_count} cyl",
            f"{injector_flow:.0f} cc/min",
            f"AFR {stoich:.1f}",
        ]
        self.req_inputs_label.setText("  |  ".join(parts))

        result = RequiredFuelCalculatorService().calculate(
            displacement_cc=displacement,
            cylinder_count=cylinder_count,
            injector_flow_ccmin=injector_flow,
            target_afr=stoich,
        )
        if result.is_valid:
            self.req_result_label.setText(
                f"reqFuel = {result.req_fuel_ms:.2f} ms   "
                f"(stored value: {result.req_fuel_stored})"
            )
            # Apply is only possible when a page is active that has reqFuel
            self.req_apply_button.setEnabled(True)
        else:
            self.req_result_label.setText("Could not compute — check inputs.")
            self.req_apply_button.setEnabled(False)

    def _update_ve_table_combo(self) -> None:
        if self._presenter is None:
            return
        current = self._preferred_ve_table_name() or self.ve_table_combo.currentText() or "veTable"
        blocker = QSignalBlocker(self.ve_table_combo)
        self.ve_table_combo.clear()
        # Populate from table parameters in the loaded definition
        if self._presenter.definition is not None:
            for table in self._presenter.definition.tables:
                name_lower = table.name.lower()
                # Prioritise VE-related tables at the top
                if any(kw in name_lower for kw in ("ve", "fuel", "inj")):
                    self.ve_table_combo.insertItem(0, table.name)
                else:
                    self.ve_table_combo.addItem(table.name)
        if self.ve_table_combo.count() == 0:
            self.ve_table_combo.addItem("veTable")
        # Restore previous selection if still present
        idx = self.ve_table_combo.findText(current)
        if idx >= 0:
            self.ve_table_combo.setCurrentIndex(idx)
        else:
            self.ve_table_combo.setCurrentIndex(0)
        del blocker

    def _preferred_ve_table_name(self) -> str | None:
        if self._presenter is None or self._presenter.definition is None:
            return None
        table_names = {table.name for table in self._presenter.definition.tables}
        active_page = self._presenter.pages_by_id.get(self._presenter.active_page_id)
        if active_page is not None and active_page.table_name in table_names:
            return active_page.table_name
        if self._presenter.catalog_selected_name in table_names:
            return self._presenter.catalog_selected_name
        return None

    def _suggest_wizard_tab_index(self) -> int:
        """Return the most relevant Hardware Setup Wizard tab for current gaps."""
        if self._presenter is None:
            return 1
        ctx = self._presenter.operator_engine_context_service.get()
        gen_ctx = self._build_generator_context()
        if not ctx.displacement_cc or not ctx.cylinder_count or not ctx.compression_ratio:
            return 1  # Engine
        if ctx.forced_induction_topology != ForcedInductionTopology.NA:
            if ctx.boost_target_kpa is None or ctx.turbo_preset_key is not None:
                return 2  # Induction
        if gen_ctx is None or "Injector flow rate" in gen_ctx.missing_for_injector_helper:
            return 3  # Injectors
        return 1

    def _build_generator_context(self):
        """Build a generator context from all hardware setup pages, or None."""
        if self._presenter is None:
            return None
        hw_pages = tuple(
            page
            for group in self._presenter.page_groups
            if group.group_id == "hardware_setup"
            for page in group.pages
        )
        if not hw_pages:
            hw_pages = tuple(
                page
                for group in self._presenter.page_groups
                for page in group.pages
            )
        try:
            return self._presenter.hardware_setup_generator_context_service.build(
                hw_pages,
                self._presenter.local_tune_edit_service,
                operator_context=self._presenter.operator_engine_context_service.get(),
            )
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_displacement_changed(self) -> None:
        if self._updating or self._presenter is None:
            return
        text = self.displacement_edit.text().strip()
        try:
            value: float | None = float(text) if text else None
        except ValueError:
            return
        self._presenter.update_operator_engine_context(displacement_cc=value)
        self._update_req_fuel_result()
        self.workspace_state_changed.emit()

    def _on_cylinders_changed(self, value: int) -> None:
        if self._updating or self._presenter is None:
            return
        count: int | None = value if value > 0 else None
        self._presenter.update_operator_engine_context(cylinder_count=count)
        self._update_req_fuel_result()
        self.workspace_state_changed.emit()

    def _on_compression_changed(self) -> None:
        if self._updating or self._presenter is None:
            return
        text = self.compression_edit.text().strip()
        try:
            value = float(text) if text else None
        except ValueError:
            return
        self._presenter.update_operator_engine_context(compression_ratio=value)
        self.workspace_state_changed.emit()

    def _on_cam_changed(self) -> None:
        if self._updating or self._presenter is None:
            return
        text = self.cam_edit.text().strip()
        try:
            value = float(text) if text else None
        except ValueError:
            return
        self._presenter.update_operator_engine_context(cam_duration_deg=value)
        self.workspace_state_changed.emit()

    def _on_head_flow_class_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(head_flow_class=self.head_flow_combo.itemData(index))
        self.workspace_state_changed.emit()

    def _on_manifold_style_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(intake_manifold_style=self.manifold_style_combo.itemData(index))
        self.workspace_state_changed.emit()

    def _on_intent_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        intent = (
            CalibrationIntent.DRIVABLE_BASE if index == 1 else CalibrationIntent.FIRST_START
        )
        self._presenter.update_operator_engine_context(calibration_intent=intent)
        self.workspace_state_changed.emit()

    def _on_injector_profile_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        preset = self.injector_profile_combo.itemData(index)
        key = preset.key if isinstance(preset, InjectorHardwarePreset) else None
        self._presenter.update_operator_engine_context(injector_preset_key=key)
        self._refresh_profile_summaries()
        self.workspace_state_changed.emit()

    def _on_base_fuel_pressure_changed(self, value: float) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(base_fuel_pressure_psi=value)
        self._refresh_profile_summaries()
        self.workspace_state_changed.emit()

    def _on_injector_pressure_model_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(
            injector_pressure_model=self.injector_pressure_model_combo.itemData(index)
        )
        self._refresh_advanced_visibility()
        self._refresh_profile_summaries()
        self.workspace_state_changed.emit()

    def _on_secondary_injector_pressure_changed(self, value: float) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(
            secondary_injector_reference_pressure_psi=value or None
        )
        self._refresh_advanced_visibility()
        self._refresh_profile_summaries()
        self.workspace_state_changed.emit()

    def _on_injector_characterization_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(
            injector_characterization=self.injector_characterization_combo.itemData(index)
        )
        self.workspace_state_changed.emit()

    def _on_ignition_profile_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        preset = self.ignition_profile_combo.itemData(index)
        key = preset.key if isinstance(preset, IgnitionHardwarePreset) else None
        self._presenter.update_operator_engine_context(ignition_preset_key=key)
        self._refresh_profile_summaries()
        self.workspace_state_changed.emit()

    def _on_wideband_profile_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        preset = self.wideband_profile_combo.itemData(index)
        key = preset.key if isinstance(preset, WidebandHardwarePreset) else None
        self._presenter.update_operator_engine_context(wideband_preset_key=key)
        self._refresh_wideband_reference_options(
            preferred_label=self._selected_wideband_reference_label(),
            prefer_match=True,
        )
        self._presenter.update_operator_engine_context(
            wideband_reference_table_label=self._selected_wideband_reference_label()
        )
        self._refresh_profile_summaries()
        self.workspace_state_changed.emit()

    def _on_wideband_reference_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        del index
        self._presenter.update_operator_engine_context(
            wideband_reference_table_label=self._selected_wideband_reference_label()
        )
        self._refresh_profile_summaries()
        self.workspace_state_changed.emit()

    def _on_turbo_profile_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        preset = self.turbo_profile_combo.itemData(index)
        if not isinstance(preset, TurboHardwarePreset):
            self._presenter.update_operator_engine_context(turbo_preset_key=None)
            self._refresh_profile_summaries()
            self.workspace_state_changed.emit()
            return
        self._presenter.update_operator_engine_context(
            turbo_preset_key=preset.key,
            compressor_corrected_flow_lbmin=preset.compressor_corrected_flow_lbmin,
            compressor_inducer_mm=preset.compressor_inducer_mm,
            compressor_exducer_mm=preset.compressor_exducer_mm,
            compressor_ar=preset.turbine_ar,
        )
        self._refresh_profile_summaries()
        self.workspace_state_changed.emit()

    def _update_induction_visibility(self, topology: ForcedInductionTopology) -> None:
        forced = topology != ForcedInductionTopology.NA
        supercharged = topology in {
            ForcedInductionTopology.SINGLE_SUPERCHARGER,
            ForcedInductionTopology.TWIN_CHARGE,
        }
        _set_form_row_visible(self._induction_form, self.boost_target_spin, forced)
        _set_form_row_visible(self._induction_form, self.intercooler_check, forced)
        _set_form_row_visible(self._induction_form, self.supercharger_type_combo, supercharged)
        self._refresh_advanced_visibility()

    def _on_topology_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        topology = self.topology_combo.itemData(index)
        if topology is None:
            return
        self._presenter.update_operator_engine_context(forced_induction_topology=topology)
        self._update_induction_visibility(topology)
        self._update_req_fuel_result()
        self.workspace_state_changed.emit()

    def _on_boost_target_changed(self, value: float) -> None:
        if self._updating or self._presenter is None:
            return
        kpa_abs = value * 6.89476 + 101.325
        self._presenter.update_operator_engine_context(boost_target_kpa=kpa_abs)
        self.workspace_state_changed.emit()

    def _on_intercooler_changed(self, checked: bool) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(intercooler_present=checked)
        self.workspace_state_changed.emit()

    def _on_supercharger_type_changed(self, index: int) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(
            supercharger_type=self.supercharger_type_combo.itemData(index)
        )
        self.workspace_state_changed.emit()

    def _on_compressor_flow_changed(self, value: float) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(compressor_corrected_flow_lbmin=value or None)
        self.workspace_state_changed.emit()

    def _on_compressor_pr_changed(self, value: float) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(compressor_pressure_ratio=value or None)
        self.workspace_state_changed.emit()

    def _on_compressor_inducer_changed(self, value: float) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(compressor_inducer_mm=value or None)
        self.workspace_state_changed.emit()

    def _on_compressor_exducer_changed(self, value: float) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(compressor_exducer_mm=value or None)
        self.workspace_state_changed.emit()

    def _on_compressor_ar_changed(self, value: float) -> None:
        if self._updating or self._presenter is None:
            return
        self._presenter.update_operator_engine_context(compressor_ar=value or None)
        self.workspace_state_changed.emit()

    def _ve_assumption_summary(self) -> str:
        if self._presenter is None:
            return ""
        ctx = self._presenter.operator_engine_context_service.get()
        tier1: list[str] = []
        tier2: list[str] = []
        if ctx.displacement_cc is not None:
            tier1.append("displacement")
        if ctx.cylinder_count is not None:
            tier1.append("cylinders")
        if ctx.compression_ratio is not None:
            tier1.append("compression")
        if ctx.forced_induction_topology != ForcedInductionTopology.NA:
            tier1.append("topology")
            if ctx.boost_target_kpa is not None:
                tier1.append("boost target")
        if ctx.supercharger_type is not None:
            tier2.append("supercharger type")
        if ctx.calibration_intent is not None:
            tier1.append("intent")
        if ctx.cam_duration_deg is not None:
            tier2.append("cam duration")
        if ctx.head_flow_class is not None:
            tier2.append("head flow class")
        if ctx.intake_manifold_style is not None:
            tier2.append("manifold style")
        if ctx.base_fuel_pressure_psi is not None:
            tier2.append("fuel pressure")
        if ctx.injector_pressure_model is not None:
            tier2.append("injector pressure model")
        if ctx.secondary_injector_reference_pressure_psi is not None:
            tier2.append("secondary injector pressure")
        if ctx.injector_characterization is not None:
            tier2.append("injector data depth")
        if ctx.compressor_corrected_flow_lbmin is not None:
            tier2.append("compressor flow")
        if ctx.compressor_pressure_ratio is not None:
            tier2.append("compressor PR")
        if ctx.compressor_inducer_mm is not None or ctx.compressor_exducer_mm is not None:
            tier2.append("compressor wheel sizing")
        if ctx.compressor_ar is not None:
            tier2.append("turbine A/R")
        confidence = "Tier 1 + Tier 2" if tier2 else "Tier 1 only"
        tier1_text = ", ".join(tier1) if tier1 else "default conservative assumptions"
        tier2_text = ", ".join(tier2) if tier2 else "none"
        return f"Assumptions: [{confidence}] Tier 1 inputs: {tier1_text}. Tier 2 inputs: {tier2_text}."

    def _on_open_wizard(self) -> None:
        self.open_hardware_setup_wizard()

    def _on_apply_req_fuel(self) -> None:
        if self._presenter is None:
            return
        self._presenter.apply_req_fuel_result()
        msg = self._presenter.consume_message()
        if msg:
            self.status_message.emit(msg)
        self.workspace_state_changed.emit()

    def _on_generate_ve(self) -> None:
        if self._presenter is None:
            return
        table_name = self.ve_table_combo.currentText().strip() or "veTable"
        snap = self._presenter.generate_and_stage_ve_table(table_name)
        msg = self._presenter.consume_message() or ""
        assumption_summary = self._ve_assumption_summary()
        self.gen_status_label.setText(f"{msg}\n{assumption_summary}" if assumption_summary else msg)
        self.status_message.emit(msg)
        self.workspace_state_changed.emit()
        # Show warnings from the generator if available
        del snap
