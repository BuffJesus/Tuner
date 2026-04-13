from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.ecu_definition import DialogDefinition, DialogFieldDefinition, MenuDefinition, MenuItemDefinition, ScalarParameterDefinition
from tuner.domain.ecu_definition import ReferenceTableDefinition, ReferenceTableSolution
from tuner.domain.generator_context import ForcedInductionTopology, SuperchargerType
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter
from tuner.ui.engine_setup_panel import EngineSetupPanel
import tuner.ui.hardware_setup_wizard as hardware_setup_wizard_module


def test_forced_induction_topology_reveals_boost_and_intercooler_rows() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert not panel._induction_form.isRowVisible(panel.boost_target_spin)
    assert not panel._induction_form.isRowVisible(panel.intercooler_check)

    turbo_index = next(
        i
        for i in range(panel.topology_combo.count())
        if panel.topology_combo.itemData(i) == ForcedInductionTopology.SINGLE_TURBO
    )
    panel.topology_combo.setCurrentIndex(turbo_index)
    app.processEvents()

    assert panel._induction_form.isRowVisible(panel.boost_target_spin)
    assert panel._induction_form.isRowVisible(panel.intercooler_check)
    assert presenter.operator_engine_context_service.get().forced_induction_topology == ForcedInductionTopology.SINGLE_TURBO

    panel.boost_target_spin.setValue(12.0)
    app.processEvents()

    ctx = presenter.operator_engine_context_service.get()
    assert ctx.boost_target_kpa is not None
    assert ctx.boost_target_kpa > 101.325


def test_supercharger_topology_reveals_supercharger_type_row_and_updates_context() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert not panel._induction_form.isRowVisible(panel.supercharger_type_combo)

    sc_index = next(
        i
        for i in range(panel.topology_combo.count())
        if panel.topology_combo.itemData(i) == ForcedInductionTopology.SINGLE_SUPERCHARGER
    )
    panel.topology_combo.setCurrentIndex(sc_index)
    app.processEvents()

    assert panel._induction_form.isRowVisible(panel.supercharger_type_combo)

    _select_combo_item_by_text(panel.supercharger_type_combo, "Centrifugal")
    app.processEvents()

    assert presenter.operator_engine_context_service.get().supercharger_type == SuperchargerType.CENTRIFUGAL


def test_refresh_restores_forced_induction_rows_and_values_from_presenter_context() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    presenter.update_operator_engine_context(
        forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
        boost_target_kpa=200.0,
        intercooler_present=True,
    )

    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel._induction_form.isRowVisible(panel.boost_target_spin)
    assert panel._induction_form.isRowVisible(panel.intercooler_check)
    assert panel.boost_target_spin.value() > 0.0
    assert panel.intercooler_check.isChecked() is True

    turbo_index = next(
        i
        for i in range(panel.topology_combo.count())
        if panel.topology_combo.itemData(i) == ForcedInductionTopology.SINGLE_TURBO
    )
    assert panel.topology_combo.currentIndex() == turbo_index


def test_refresh_restores_supercharger_type_from_presenter_context() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    presenter.update_operator_engine_context(
        forced_induction_topology=ForcedInductionTopology.TWIN_CHARGE,
        supercharger_type=SuperchargerType.TWIN_SCREW,
        boost_target_kpa=180.0,
    )

    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel._induction_form.isRowVisible(panel.supercharger_type_combo)
    assert panel.supercharger_type_combo.currentText() == "Twin-screw"


def test_generator_topology_label_uses_operator_context_without_hardware_pages() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    presenter.update_operator_engine_context(
        forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
        boost_target_kpa=180.0,
    )

    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert "Single Turbo" in panel.gen_topology_label.text()


def test_ve_table_combo_tracks_active_selected_table_page() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter_with_tables()
    presenter.select_page("table-editor:ve2Table")

    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel.ve_table_combo.currentText() == "ve2Table"


def test_reqfuel_apply_enables_when_injector_flow_exists_on_non_hardware_page() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter_with_fuel_constants_page()
    presenter.update_operator_engine_context(displacement_cc=4900.0, cylinder_count=6)

    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert "injector flow" not in panel.req_inputs_label.text().lower()
    assert "reqFuel =" in panel.req_result_label.text()
    assert panel.req_apply_button.isEnabled() is True


def test_engine_setup_panel_emits_workspace_state_changed_on_context_edit() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    seen: list[bool] = []
    panel.workspace_state_changed.connect(lambda: seen.append(True))

    panel.displacement_edit.setText("2000")
    panel._on_displacement_changed()

    assert seen


def test_engine_setup_panel_updates_hardware_profiles_in_operator_context() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    _select_combo_item_by_text(panel.injector_profile_combo, "Injector Dynamics ID1050x / XDS")
    panel.base_fuel_pressure_spin.setValue(58.0)
    _select_combo_item_by_text(panel.ignition_profile_combo, "GM LS Coil PN 19005218")
    _select_combo_item_by_text(panel.wideband_profile_combo, "AEM UEGO X-Series")
    app.processEvents()

    context = presenter.operator_engine_context_service.get()
    assert context.injector_preset_key == "id1050x_xds"
    assert context.base_fuel_pressure_psi == 58.0
    assert context.ignition_preset_key == "gm_ls_19005218"
    assert context.wideband_preset_key == "aem_x_series"
    assert "1230 cc/min" in panel.injector_profile_summary.text()
    assert "[Trusted Secondary]" in panel.injector_profile_summary.text()
    assert "19005218" in panel.ignition_profile_summary.text()
    assert "[Official]" in panel.ignition_profile_summary.text()
    assert "AEM UEGO X-Series" in panel.wideband_profile_summary.text()
    assert "Ref table: not set" in panel.wideband_profile_summary.text()


def test_engine_setup_panel_wideband_summary_includes_reference_table_label() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter_with_wideband_reference_table()
    presenter.update_operator_engine_context(
        wideband_preset_key="aem_x_series",
        wideband_reference_table_label="AEM Linear AEM-30-42xx",
    )

    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel.wideband_profile_combo.currentText() == "AEM UEGO X-Series"
    assert "AEM Linear AEM-30-42xx" in panel.wideband_profile_summary.text()


def test_engine_setup_panel_matches_wideband_reference_table_from_selected_preset() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter_with_wideband_reference_table()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel.wideband_reference_combo.isVisible() is True
    _select_combo_item_by_text(panel.wideband_profile_combo, "AEM UEGO X-Series")
    app.processEvents()

    context = presenter.operator_engine_context_service.get()
    assert panel.wideband_reference_combo.currentText() == "AEM Linear AEM-30-42xx"
    assert context.wideband_reference_table_label == "AEM Linear AEM-30-42xx"


def test_engine_setup_panel_allows_manual_wideband_reference_override() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter_with_wideband_reference_table()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    _select_combo_item_by_text(panel.wideband_profile_combo, "AEM UEGO X-Series")
    _select_combo_item_by_text(panel.wideband_reference_combo, "Innovate LC-1 / LC-2 Default")
    app.processEvents()

    context = presenter.operator_engine_context_service.get()
    assert context.wideband_reference_table_label == "Innovate LC-1 / LC-2 Default"
    assert "Suggested ref: AEM Linear AEM-30-42xx" in panel.wideband_profile_summary.text()


def test_engine_setup_panel_updates_turbo_profile_in_operator_context() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    _select_combo_item_by_text(panel.turbo_profile_combo, "Maxpeedingrods GT2871")
    app.processEvents()

    context = presenter.operator_engine_context_service.get()
    assert context.turbo_preset_key == "maxpeedingrods_gt2871"
    assert context.compressor_corrected_flow_lbmin == 35.0
    assert context.compressor_inducer_mm == 49.2
    assert context.compressor_exducer_mm == 71.0
    assert context.compressor_ar == 0.64
    assert "gt2871" in panel.turbo_profile_summary.text().lower()


def test_engine_setup_panel_hides_advanced_inputs_until_enabled() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel._facts_form.isRowVisible(panel.cam_edit) is False
    assert panel._facts_form.isRowVisible(panel.head_flow_combo) is False
    assert panel._facts_form.isRowVisible(panel.manifold_style_combo) is False
    assert panel._injector_form.isRowVisible(panel.base_fuel_pressure_spin) is False
    assert panel._injector_form.isRowVisible(panel.injector_pressure_model_combo) is False
    assert panel._injector_form.isRowVisible(panel.secondary_injector_pressure_spin) is False
    assert panel._injector_form.isRowVisible(panel.injector_characterization_combo) is False

    panel.advanced_mode_check.setChecked(True)
    app.processEvents()

    assert panel._facts_form.isRowVisible(panel.cam_edit) is True
    assert panel._facts_form.isRowVisible(panel.head_flow_combo) is True
    assert panel._facts_form.isRowVisible(panel.manifold_style_combo) is True
    assert panel._injector_form.isRowVisible(panel.injector_pressure_model_combo) is True
    assert panel._injector_form.isRowVisible(panel.base_fuel_pressure_spin) is False
    assert panel._injector_form.isRowVisible(panel.secondary_injector_pressure_spin) is False
    assert panel._injector_form.isRowVisible(panel.injector_characterization_combo) is True


def test_engine_setup_panel_auto_reveals_advanced_inputs_when_context_has_values() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    presenter.update_operator_engine_context(
        cam_duration_deg=228.0,
        head_flow_class="mild_ported",
        intake_manifold_style="itb",
        base_fuel_pressure_psi=58.0,
        injector_pressure_model="vacuum_referenced",
        secondary_injector_reference_pressure_psi=52.0,
        injector_characterization="full_characterization",
    )
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel.advanced_mode_check.isChecked() is True
    assert panel._facts_form.isRowVisible(panel.cam_edit) is True
    assert panel._facts_form.isRowVisible(panel.head_flow_combo) is True
    assert panel._facts_form.isRowVisible(panel.manifold_style_combo) is True
    assert panel._injector_form.isRowVisible(panel.base_fuel_pressure_spin) is True
    assert panel._injector_form.isRowVisible(panel.injector_pressure_model_combo) is True
    assert panel._injector_form.isRowVisible(panel.secondary_injector_pressure_spin) is True
    assert panel._injector_form.isRowVisible(panel.injector_characterization_combo) is True


def test_engine_setup_panel_updates_additional_tier2_context_fields() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    panel.advanced_mode_check.setChecked(True)
    app.processEvents()

    _select_combo_item_by_text(panel.head_flow_combo, "Mild ported")
    _select_combo_item_by_text(panel.manifold_style_combo, "ITB / individual runners")
    _select_combo_item_by_text(
        panel.injector_characterization_combo,
        "Full pressure + voltage characterization",
    )
    app.processEvents()

    context = presenter.operator_engine_context_service.get()
    assert context.head_flow_class == "mild_ported"
    assert context.intake_manifold_style == "itb"
    assert context.injector_characterization == "full_characterization"


def test_engine_setup_panel_updates_injector_pressure_context_fields() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    panel.advanced_mode_check.setChecked(True)
    app.processEvents()

    _select_combo_item_by_text(panel.injector_pressure_model_combo, "Vacuum referenced (rising-rate FPR)")
    panel.secondary_injector_pressure_spin.setValue(58.0)
    app.processEvents()

    context = presenter.operator_engine_context_service.get()
    assert context.injector_pressure_model == "vacuum_referenced"
    assert context.secondary_injector_reference_pressure_psi == 58.0


def test_engine_setup_panel_injector_visibility_tracks_pressure_model_and_staging() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    panel.advanced_mode_check.setChecked(True)
    app.processEvents()

    assert panel._injector_form.isRowVisible(panel.base_fuel_pressure_spin) is False

    _select_combo_item_by_text(panel.injector_pressure_model_combo, "Operator-specified pressure")
    app.processEvents()

    assert panel._injector_form.isRowVisible(panel.base_fuel_pressure_spin) is True
    assert presenter.operator_engine_context_service.get().injector_pressure_model == "operator_specified"


def test_engine_setup_panel_shows_tier2_airflow_inputs_only_for_advanced_forced_induction() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel._induction_form.isRowVisible(panel.compressor_flow_spin) is False

    panel.advanced_mode_check.setChecked(True)
    app.processEvents()
    assert panel._induction_form.isRowVisible(panel.compressor_flow_spin) is False

    turbo_index = next(
        i
        for i in range(panel.topology_combo.count())
        if panel.topology_combo.itemData(i) == ForcedInductionTopology.SINGLE_TURBO
    )
    panel.topology_combo.setCurrentIndex(turbo_index)
    app.processEvents()

    assert panel._induction_form.isRowVisible(panel.compressor_flow_spin) is True
    assert panel._induction_form.isRowVisible(panel.compressor_ar_spin) is True


def test_engine_setup_panel_updates_tier2_compressor_context_fields() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    panel.advanced_mode_check.setChecked(True)
    turbo_index = next(
        i
        for i in range(panel.topology_combo.count())
        if panel.topology_combo.itemData(i) == ForcedInductionTopology.SINGLE_TURBO
    )
    panel.topology_combo.setCurrentIndex(turbo_index)
    app.processEvents()

    panel.compressor_flow_spin.setValue(52.0)
    panel.compressor_pr_spin.setValue(2.2)
    panel.compressor_inducer_spin.setValue(54.0)
    panel.compressor_exducer_spin.setValue(71.0)
    panel.compressor_ar_spin.setValue(0.82)
    app.processEvents()

    context = presenter.operator_engine_context_service.get()
    assert context.compressor_corrected_flow_lbmin == 52.0
    assert context.compressor_pressure_ratio == 2.2
    assert context.compressor_inducer_mm == 54.0
    assert context.compressor_exducer_mm == 71.0
    assert context.compressor_ar == 0.82


def test_generate_ve_status_reports_tier1_and_tier2_assumptions() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter_with_tables()
    presenter.update_operator_engine_context(
        displacement_cc=1998.0,
        cylinder_count=4,
        compression_ratio=9.5,
        forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
        boost_target_kpa=180.0,
        supercharger_type=SuperchargerType.CENTRIFUGAL,
        cam_duration_deg=228.0,
        head_flow_class="mild_ported",
        intake_manifold_style="itb",
        injector_pressure_model="fixed_pressure",
        secondary_injector_reference_pressure_psi=58.0,
        injector_characterization="full_characterization",
        compressor_corrected_flow_lbmin=52.0,
        compressor_ar=0.82,
    )

    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    panel._on_generate_ve()
    app.processEvents()

    status = panel.gen_status_label.text().lower()
    assert "tier 1" in status
    assert "tier 2" in status
    assert "cam duration" in status
    assert "head flow class" in status
    assert "manifold style" in status
    assert "injector pressure model" in status
    assert "secondary injector pressure" in status
    assert "injector data depth" in status
    assert "supercharger type" in status
    assert "compressor flow" in status


def test_engine_setup_panel_refresh_restores_hardware_profile_selection() -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter_with_wideband_reference_table()
    presenter.update_operator_engine_context(
        injector_preset_key="id1050x_xds",
        base_fuel_pressure_psi=58.0,
        ignition_preset_key="gm_ls_19005218",
        wideband_preset_key="aem_x_series",
        wideband_reference_table_label="AEM Linear AEM-30-42xx",
        turbo_preset_key="maxpeedingrods_gt2871",
        head_flow_class="mild_ported",
        intake_manifold_style="itb",
        injector_pressure_model="vacuum_referenced",
        secondary_injector_reference_pressure_psi=52.0,
        injector_characterization="full_characterization",
        compressor_corrected_flow_lbmin=35.0,
        compressor_inducer_mm=49.2,
        compressor_exducer_mm=71.0,
        compressor_ar=0.64,
    )

    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    assert panel.injector_profile_combo.currentText() == "Injector Dynamics ID1050x / XDS"
    assert panel.base_fuel_pressure_spin.value() == 58.0
    assert panel.ignition_profile_combo.currentText() == "GM LS Coil PN 19005218"
    assert panel.wideband_profile_combo.currentText() == "AEM UEGO X-Series"
    assert panel.wideband_reference_combo.currentText() == "AEM Linear AEM-30-42xx"
    assert panel.turbo_profile_combo.currentText() == "Maxpeedingrods GT2871"
    assert panel.advanced_mode_check.isChecked() is True
    assert panel.head_flow_combo.currentText() == "Mild ported"
    assert panel.manifold_style_combo.currentText() == "ITB / individual runners"
    assert panel.injector_pressure_model_combo.currentText() == "Vacuum referenced (rising-rate FPR)"
    assert panel.secondary_injector_pressure_spin.value() == 52.0
    assert panel.injector_characterization_combo.currentText() == "Full pressure + voltage characterization"
    assert "1230 cc/min" in panel.injector_profile_summary.text()
    assert "AEM Linear AEM-30-42xx" in panel.wideband_profile_summary.text()


def test_open_hardware_setup_wizard_targets_engine_tab_when_core_engine_facts_missing(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    seen: list[int] = []

    class _Tabs:
        def setCurrentIndex(self, index: int) -> None:
            seen.append(index)

    class _Wizard:
        def __init__(self, presenter, parent=None) -> None:
            del presenter, parent
            self._tabs = _Tabs()
            self.status_message = type("_Signal", (), {"connect": staticmethod(lambda _fn: None)})()
            self.workspace_state_changed = type("_Signal", (), {"connect": staticmethod(lambda _fn: None)})()

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

        def isVisible(self) -> bool:
            return False

    monkeypatch.setattr(hardware_setup_wizard_module, "HardwareSetupWizard", _Wizard)

    panel.open_hardware_setup_wizard()

    assert seen == [1]


def test_open_hardware_setup_wizard_targets_injectors_when_injector_flow_missing(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    presenter.update_operator_engine_context(
        displacement_cc=2000.0,
        cylinder_count=4,
        compression_ratio=9.5,
    )
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    seen: list[int] = []

    class _Tabs:
        def setCurrentIndex(self, index: int) -> None:
            seen.append(index)

    class _Wizard:
        def __init__(self, presenter, parent=None) -> None:
            del presenter, parent
            self._tabs = _Tabs()
            self.status_message = type("_Signal", (), {"connect": staticmethod(lambda _fn: None)})()
            self.workspace_state_changed = type("_Signal", (), {"connect": staticmethod(lambda _fn: None)})()

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

        def isVisible(self) -> bool:
            return False

    monkeypatch.setattr(hardware_setup_wizard_module, "HardwareSetupWizard", _Wizard)

    panel.open_hardware_setup_wizard()

    assert seen == [3]


def test_open_hardware_setup_wizard_targets_induction_for_forced_induction(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter_with_fuel_constants_page()
    presenter.update_operator_engine_context(
        displacement_cc=2000.0,
        cylinder_count=4,
        compression_ratio=9.5,
        forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
    )
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    seen: list[int] = []

    class _Tabs:
        def setCurrentIndex(self, index: int) -> None:
            seen.append(index)

    class _Wizard:
        def __init__(self, presenter, parent=None) -> None:
            del presenter, parent
            self._tabs = _Tabs()
            self.status_message = type("_Signal", (), {"connect": staticmethod(lambda _fn: None)})()
            self.workspace_state_changed = type("_Signal", (), {"connect": staticmethod(lambda _fn: None)})()

        def show(self) -> None:
            return None

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

        def isVisible(self) -> bool:
            return False

    monkeypatch.setattr(hardware_setup_wizard_module, "HardwareSetupWizard", _Wizard)

    panel.open_hardware_setup_wizard()

    assert seen == [2]


def test_open_hardware_setup_wizard_reuses_visible_instance(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    presenter = _presenter()
    panel = EngineSetupPanel()
    panel.set_presenter(presenter)
    panel.show()
    app.processEvents()

    created: list[object] = []

    class _Tabs:
        def __init__(self) -> None:
            self.indexes: list[int] = []

        def setCurrentIndex(self, index: int) -> None:
            self.indexes.append(index)

    class _Wizard:
        def __init__(self, presenter, parent=None) -> None:
            del presenter, parent
            self._tabs = _Tabs()
            self.status_message = type("_Signal", (), {"connect": staticmethod(lambda _fn: None)})()
            self.workspace_state_changed = type("_Signal", (), {"connect": staticmethod(lambda _fn: None)})()
            self.visible = False
            created.append(self)

        def show(self) -> None:
            self.visible = True

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:
            return None

        def isVisible(self) -> bool:
            return self.visible

    monkeypatch.setattr(hardware_setup_wizard_module, "HardwareSetupWizard", _Wizard)

    first = panel.open_hardware_setup_wizard(tab_index=3)
    second = panel.open_hardware_setup_wizard(tab_index=2)

    assert first is second
    assert len(created) == 1
    assert created[0]._tabs.indexes == [3, 2]


def _presenter() -> TuningWorkspacePresenter:
    definition = EcuDefinition(name="Speeduino")
    tune_file = TuneFile(constants=[])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


def _presenter_with_wideband_reference_table() -> TuningWorkspacePresenter:
    definition = EcuDefinition(
        name="Speeduino",
        reference_tables=[
            ReferenceTableDefinition(
                table_id="genO2",
                label="O2 Sensor Calibration",
                solutions=[
                    ReferenceTableSolution(label="14point7 Spartan 2", expression="{ 10 + (adcValue * 0.009765625 * 2) }"),
                    ReferenceTableSolution(label="AEM Linear AEM-30-42xx", expression="{ 9.72 + (adcValue * 0.0096665) }"),
                    ReferenceTableSolution(label="Innovate LC-1 / LC-2 Default", expression="{ 7.35 + (adcValue * 0.01470186 ) }"),
                ],
            )
        ],
    )
    tune_file = TuneFile(constants=[])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


def _select_combo_item_by_text(combo, text: str) -> None:
    for index in range(combo.count()):
        if combo.itemText(index) == text:
            combo.setCurrentIndex(index)
            return
    raise AssertionError(f"Combo item not found: {text}")


def _presenter_with_tables() -> TuningWorkspacePresenter:
    from tuner.domain.ecu_definition import TableDefinition, TableEditorDefinition

    definition = EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="ve1Table", rows=2, columns=2, page=1, offset=0, units="%"),
            TableDefinition(name="ve1Rpm", rows=1, columns=2, page=1, offset=16, units="rpm"),
            TableDefinition(name="ve1Load", rows=2, columns=1, page=1, offset=20, units="kPa"),
            TableDefinition(name="ve2Table", rows=2, columns=2, page=2, offset=0, units="%"),
            TableDefinition(name="ve2Rpm", rows=1, columns=2, page=2, offset=16, units="rpm"),
            TableDefinition(name="ve2Load", rows=2, columns=1, page=2, offset=20, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="ve1Table",
                map_id="ve1Map",
                title="VE Table 1",
                page=1,
                x_bins="ve1Rpm",
                y_bins="ve1Load",
                z_bins="ve1Table",
            ),
            TableEditorDefinition(
                table_id="ve2Table",
                map_id="ve2Map",
                title="VE Table 2",
                page=2,
                x_bins="ve2Rpm",
                y_bins="ve2Load",
                z_bins="ve2Table",
            ),
        ],
    )
    tune_file = TuneFile(constants=[])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


def _presenter_with_fuel_constants_page() -> TuningWorkspacePresenter:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="injectorFlow", data_type="U16", page=1, offset=0, units="cc/min"),
        ],
        dialogs=[
            DialogDefinition(
                dialog_id="fuelConstants",
                title="Fuel Constants",
                fields=[DialogFieldDefinition(label="Injector Flow", parameter_name="injectorFlow")],
            )
        ],
        menus=[MenuDefinition(title="Fuel", items=[MenuItemDefinition(target="fuelConstants", label="Fuel Constants")])],
    )
    tune_file = TuneFile(constants=[TuneValue(name="injectorFlow", value=650.0, units="cc/min")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter
