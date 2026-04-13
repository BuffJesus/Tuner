from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tuner.comms.interfaces import ControllerClient
from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.firmware_capabilities import FirmwareCapabilities
from tuner.domain.generator_context import GeneratorInputContext
from tuner.domain.hardware_setup import HardwareSetupIssue
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.domain.parameters import ParameterValue
from tuner.domain.session import SessionState
from tuner.domain.sync_state import SyncState
from tuner.domain.tune import TuneFile, TuneValue
from tuner.domain.tuning_pages import (
    TuningPage,
    TuningPageGroup,
    TuningPageKind,
    TuningPageParameter,
    TuningPageState,
    TuningPageStateKind,
)
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.operation_log_service import OperationLogService
from tuner.services.operation_evidence_service import OperationEvidenceService
from tuner.services.parameter_catalog_service import ParameterCatalogEntry, ParameterCatalogService
from tuner.services.scalar_page_editor_service import ScalarPageEditorService, ScalarSectionEditorSnapshot
from tuner.services.staged_change_service import StagedChangeEntry, StagedChangeService
from tuner.services.table_edit_service import TableEditService, TableSelection
from tuner.services.table_view_service import TableViewModel, TableViewService
from tuner.domain.generator_context import ForcedInductionTopology, SuperchargerType
from tuner.domain.operator_engine_context import CalibrationIntent, OperatorEngineContext
from tuner.services.hardware_setup_generator_context_service import HardwareSetupGeneratorContextService
from tuner.services.operator_engine_context_service import OperatorEngineContextService
from tuner.services.required_fuel_calculator_service import RequiredFuelCalculatorService, RequiredFuelResult
from tuner.services.ve_table_generator_service import VeTableGeneratorResult, VeTableGeneratorService
from tuner.services.spark_table_generator_service import SparkTableGeneratorResult, SparkTableGeneratorService
from tuner.services.afr_target_generator_service import AfrTargetGeneratorResult, AfrTargetGeneratorService
from tuner.services.startup_enrichment_generator_service import (
    AfterStartEnrichmentGeneratorResult,
    CrankingEnrichmentGeneratorResult,
    StartupEnrichmentGeneratorService,
    WarmupEnrichmentGeneratorResult,
)
from tuner.services.idle_rpm_target_generator_service import (
    IdleRpmTargetGeneratorResult,
    IdleRpmTargetGeneratorService,
)
from tuner.services.thermistor_calibration_service import (
    CalibrationSensor,
    ThermistorCalibrationService,
    ThermistorPreset,
)
from tuner.services.hardware_setup_validation_service import HardwareSetupValidationService
from tuner.services.hardware_setup_summary_service import HardwareSetupCardSnapshot, HardwareSetupSummaryService
from tuner.services.ignition_trigger_cross_validation_service import IgnitionTriggerCrossValidationService
from tuner.services.speeduino_runtime_telemetry_service import SpeeduinoRuntimeTelemetryService
from tuner.services.sync_state_service import SyncStateService
from tuner.services.tuning_page_diff_service import TuningPageDiffEntry, TuningPageDiffResult, TuningPageDiffService
from tuner.services.page_family_service import PageFamily, PageFamilyService
from tuner.services.curve_page_service import CurvePageService
from tuner.services.tuning_page_service import TuningPageService
from tuner.services.tuning_page_validation_service import TuningPageValidationResult, TuningPageValidationService
from tuner.services.visibility_expression_service import VisibilityExpressionService


@dataclass(slots=True, frozen=True)
class VeAnalyzeSnapshot:
    """Lightweight VE Analyze status for the workspace UI."""

    is_running: bool
    has_data: bool                  # session is active (has accumulated data)
    status_text: str
    accepted_count: int
    rejected_count: int
    cells_with_proposals: int
    summary_text: str               # one-line review
    detail_text: str                # multi-line review
    can_start: bool
    can_stop: bool
    can_reset: bool
    can_apply: bool


@dataclass(slots=True, frozen=True)
class WueAnalyzeSnapshot:
    """Lightweight WUE Analyze status for the workspace UI."""

    is_running: bool
    has_data: bool
    status_text: str
    accepted_count: int
    rejected_count: int
    rows_with_proposals: int
    summary_text: str
    detail_text: str
    can_start: bool
    can_stop: bool
    can_reset: bool
    can_apply: bool


@dataclass(slots=True, frozen=True)
class NavigationPageSnapshot:
    page_id: str
    title: str
    kind: TuningPageKind
    summary: str
    state: TuningPageState
    is_active: bool


@dataclass(slots=True, frozen=True)
class NavigationGroupSnapshot:
    title: str
    pages: tuple[NavigationPageSnapshot, ...]


@dataclass(slots=True, frozen=True)
class TablePageSnapshot:
    page_id: str
    group_id: str
    title: str
    state: TuningPageState
    summary: str
    validation_summary: str
    diff_summary: str
    diff_text: str
    diff_entries: tuple[TuningPageDiffEntry, ...]
    axis_summary: str
    details_text: str
    help_topic: str | None
    x_parameter_name: str | None
    y_parameter_name: str | None
    x_labels: tuple[str, ...]
    y_labels: tuple[str, ...]
    table_model: TableViewModel | None
    auxiliary_sections: tuple[ScalarSectionEditorSnapshot, ...]
    can_undo: bool
    can_redo: bool
    # Table context — axis ranges, help, power-cycle warnings
    z_help: str | None = None
    x_help: str | None = None
    y_help: str | None = None
    z_range: tuple[float, float] | None = None
    x_range: tuple[float, float] | None = None
    y_range: tuple[float, float] | None = None
    any_requires_power_cycle: bool = False
    message: str | None = None
    page_family_id: str | None = None
    page_family_title: str | None = None
    related_pages_title: str | None = None
    related_pages: tuple["RelatedPageSnapshot", ...] = ()
    evidence_hints: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class CurveRowSnapshot:
    """One row in the curve editor: a fixed x-axis position with one or more editable y-values."""
    index: int
    x_display: str
    y_displays: tuple[str, ...]
    is_staged: tuple[bool, ...]  # per y-param column


@dataclass(slots=True, frozen=True)
class CurvePageSnapshot:
    """View-model for a 1D curve editing surface."""
    page_id: str
    title: str
    state: TuningPageState
    summary: str
    help_topic: str | None
    x_param_name: str | None
    x_label: str
    x_units: str
    x_channel: str | None
    y_param_names: tuple[str, ...]
    y_labels: tuple[str, ...]
    y_units: tuple[str, ...]
    rows: tuple[CurveRowSnapshot, ...]
    can_undo: bool
    can_redo: bool
    diff_entries: tuple[TuningPageDiffEntry, ...]
    diff_summary: str


@dataclass(slots=True, frozen=True)
class ParameterPageRowSnapshot:
    name: str
    label: str
    kind: str
    role: str
    units: str | None
    data_type: str
    shape: str
    preview: str
    is_staged: bool
    is_editable: bool
    min_value: float | None
    max_value: float | None


@dataclass(slots=True, frozen=True)
class RequiredFuelCalculatorSnapshot:
    """View-model for the interactive required fuel calculator panel on injector pages.

    Exposes the current input values (from ECU tune + operator context), the
    computed result, and a flag indicating whether the result can be applied as a
    staged edit.  UI widgets must never write directly; they call the presenter
    which stages the change through the normal staged edit flow.
    """

    displacement_cc: float | None
    cylinder_count: int | None
    injector_flow_ccmin: float | None
    target_afr: float

    result: RequiredFuelResult | None
    """Populated when all inputs are present and valid; None otherwise."""

    missing_inputs: tuple[str, ...]
    """Human-readable labels for inputs still needed before the calculation is possible."""

    can_apply: bool
    """True when result is valid and a reqFuel parameter exists on the page to stage."""


@dataclass(slots=True, frozen=True)
class ParameterPageSnapshot:
    page_id: str
    group_id: str
    title: str
    state: TuningPageState
    summary: str
    validation_summary: str
    diff_summary: str
    diff_text: str
    diff_entries: tuple[TuningPageDiffEntry, ...]
    help_topic: str | None
    rows: tuple[ParameterPageRowSnapshot, ...]
    sections: tuple[ScalarSectionEditorSnapshot, ...]
    selected_name: str | None
    details_text: str
    can_undo: bool = False
    can_redo: bool = False
    written_values: tuple[tuple[str, str], ...] = ()  # (name, value_text) pairs last written to RAM
    hardware_issues: tuple[HardwareSetupIssue, ...] = ()
    hardware_cards: tuple[HardwareSetupCardSnapshot, ...] = ()
    any_requires_power_cycle: bool = False
    generator_context: GeneratorInputContext | None = None
    calculator_snapshot: RequiredFuelCalculatorSnapshot | None = None
    page_family_id: str | None = None
    page_family_title: str | None = None
    related_pages_title: str | None = None
    related_pages: tuple["RelatedPageSnapshot", ...] = ()
    evidence_hints: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class RelatedPageSnapshot:
    page_id: str
    title: str
    is_active: bool
    state_label: str


@dataclass(slots=True, frozen=True)
class CatalogSnapshot:
    entries: tuple[ParameterCatalogEntry, ...]
    selected_name: str | None
    details_text: str


@dataclass(slots=True, frozen=True)
class OperationLogSnapshot:
    summary_text: str
    entry_count: int
    has_unwritten: bool
    session_count: int = 0
    latest_write_text: str | None = None
    latest_burn_text: str | None = None


@dataclass(slots=True, frozen=True)
class WorkspaceReviewSnapshot:
    summary_text: str
    entries: tuple[StagedChangeEntry, ...]


@dataclass(slots=True, frozen=True)
class TuningWorkspaceSnapshot:
    navigation: tuple[NavigationGroupSnapshot, ...]
    active_page_kind: str
    table_page: TablePageSnapshot | None
    parameter_page: ParameterPageSnapshot | None
    catalog: CatalogSnapshot
    operation_log: OperationLogSnapshot
    workspace_review: WorkspaceReviewSnapshot
    sync_state: SyncState | None = None
    curve_page: CurvePageSnapshot | None = None
    hardware_issues: tuple[HardwareSetupIssue, ...] = ()  # workspace-wide hardware warnings/errors
    post_burn_verification_text: str | None = None
    ve_analyze: VeAnalyzeSnapshot | None = None
    wue_analyze: WueAnalyzeSnapshot | None = None


class TuningWorkspacePresenter:
    def __init__(
        self,
        local_tune_edit_service: LocalTuneEditService,
        tuning_page_service: TuningPageService | None = None,
        parameter_catalog_service: ParameterCatalogService | None = None,
        table_view_service: TableViewService | None = None,
        tuning_page_diff_service: TuningPageDiffService | None = None,
        tuning_page_validation_service: TuningPageValidationService | None = None,
        scalar_page_editor_service: ScalarPageEditorService | None = None,
        table_edit_service: TableEditService | None = None,
        operation_log_service: OperationLogService | None = None,
        staged_change_service: StagedChangeService | None = None,
        sync_state_service: SyncStateService | None = None,
        hardware_setup_validation_service: HardwareSetupValidationService | None = None,
        hardware_setup_summary_service: HardwareSetupSummaryService | None = None,
        hardware_setup_generator_context_service: HardwareSetupGeneratorContextService | None = None,
        operator_engine_context_service: OperatorEngineContextService | None = None,
        ve_table_generator_service: VeTableGeneratorService | None = None,
        spark_table_generator_service: SparkTableGeneratorService | None = None,
        ignition_trigger_cross_validation_service: IgnitionTriggerCrossValidationService | None = None,
        afr_target_generator_service: AfrTargetGeneratorService | None = None,
        startup_enrichment_generator_service: StartupEnrichmentGeneratorService | None = None,
        idle_rpm_target_generator_service: IdleRpmTargetGeneratorService | None = None,
        page_family_service: PageFamilyService | None = None,
        visibility_expression_service: VisibilityExpressionService | None = None,
    ) -> None:
        self.local_tune_edit_service = local_tune_edit_service
        self.tuning_page_service = tuning_page_service or TuningPageService()
        self.parameter_catalog_service = parameter_catalog_service or ParameterCatalogService()
        self.table_view_service = table_view_service or TableViewService()
        self.tuning_page_diff_service = tuning_page_diff_service or TuningPageDiffService()
        self.tuning_page_validation_service = tuning_page_validation_service or TuningPageValidationService()
        self.scalar_page_editor_service = scalar_page_editor_service or ScalarPageEditorService()
        self.table_edit_service = table_edit_service or TableEditService()
        self.operation_log_service = operation_log_service or OperationLogService()
        self.operation_evidence_service = OperationEvidenceService()
        self.staged_change_service = staged_change_service or StagedChangeService()
        self.sync_state_service = sync_state_service or SyncStateService()
        self.hardware_setup_validation_service = hardware_setup_validation_service or HardwareSetupValidationService()
        self.hardware_setup_summary_service = hardware_setup_summary_service or HardwareSetupSummaryService()
        self.hardware_setup_generator_context_service = (
            hardware_setup_generator_context_service or HardwareSetupGeneratorContextService()
        )
        self.operator_engine_context_service = (
            operator_engine_context_service or OperatorEngineContextService()
        )
        self.ve_table_generator_service = ve_table_generator_service or VeTableGeneratorService()
        self.spark_table_generator_service = spark_table_generator_service or SparkTableGeneratorService()
        self.ignition_trigger_cross_validation_service = (
            ignition_trigger_cross_validation_service or IgnitionTriggerCrossValidationService()
        )
        self.afr_target_generator_service = afr_target_generator_service or AfrTargetGeneratorService()
        self.startup_enrichment_generator_service = (
            startup_enrichment_generator_service or StartupEnrichmentGeneratorService()
        )
        self.idle_rpm_target_generator_service = (
            idle_rpm_target_generator_service or IdleRpmTargetGeneratorService()
        )
        self.page_family_service = page_family_service or PageFamilyService()
        self.curve_page_service = CurvePageService()
        self.visibility_expression_service = visibility_expression_service or VisibilityExpressionService()
        # Deferred imports to break circular dependency:
        # live_ve_analyze_session_service → table_replay_context_service → this module
        from tuner.services.live_ve_analyze_session_service import LiveVeAnalyzeSessionService  # noqa: PLC0415
        from tuner.services.ve_analyze_review_service import VeAnalyzeReviewService  # noqa: PLC0415
        self._ve_analyze_session = LiveVeAnalyzeSessionService()
        self._ve_analyze_review_service = VeAnalyzeReviewService()
        self._ve_analyze_running = False
        from tuner.services.live_wue_analyze_session_service import LiveWueAnalyzeSessionService  # noqa: PLC0415
        from tuner.services.wue_analyze_review_service import WueAnalyzeReviewService  # noqa: PLC0415
        self._wue_analyze_session = LiveWueAnalyzeSessionService()
        self._wue_analyze_review_service = WueAnalyzeReviewService()
        self._wue_analyze_running = False
        self._written_values: dict[str, str] = {}   # name → value text last written to ECU RAM
        self._ecu_client: ControllerClient | None = None
        self._ecu_ram: dict[str, ParameterValue] | None = None
        self.current_runtime_snapshot: OutputChannelSnapshot | None = None
        self.current_firmware_capabilities: FirmwareCapabilities | None = None
        self._session_state: SessionState = SessionState.OFFLINE
        self.definition: EcuDefinition | None = None
        self.tune_file: TuneFile | None = None
        self.page_groups: list[TuningPageGroup] = []
        self.pages_by_id: dict[str, TuningPage] = {}
        self.parameter_catalog_entries: list[ParameterCatalogEntry] = []
        self.active_page_id: str | None = None
        self.active_page_parameter_name: str | None = None
        self.catalog_query = ""
        self.catalog_kind = "All"
        self.catalog_selected_name: str | None = None
        self.page_errors: dict[str, str] = {}
        self._message: str | None = None
        self._post_burn_verification_text: str | None = None
        self._clipboard_text = ""
        self._context_sidecar_path: Path | None = None
        self._page_families_by_page_id: dict[str, PageFamily] = {}
        self._speeduino_runtime_telemetry_service = SpeeduinoRuntimeTelemetryService()

    def set_context_sidecar_path(self, path: Path | None) -> None:
        """Set the path to the engine-context JSON sidecar file.

        When set, :meth:`load` will attempt to restore the operator engine
        context from this file, and :meth:`update_operator_engine_context`
        will persist changes back to it automatically.
        """
        self._context_sidecar_path = path

    def load(self, definition: EcuDefinition | None, tune_file: TuneFile | None) -> TuningWorkspaceSnapshot:
        self.definition = definition
        self.tune_file = tune_file
        table_groups = self.tuning_page_service.build_pages(definition)
        curve_groups = self.curve_page_service.build_curve_pages(definition) if definition else []
        self.page_groups = list(table_groups) + list(curve_groups)
        self._page_families_by_page_id = self.page_family_service.build_index(self.page_groups)
        self.pages_by_id = {
            page.page_id: page
            for group in self.page_groups
            for page in group.pages
        }
        self.active_page_id = self._default_page_id()
        self.active_page_parameter_name = self._default_page_parameter_name(self._active_page())
        self.page_errors.clear()
        self.catalog_selected_name = None
        self.operation_log_service.clear()
        self._written_values.clear()
        self._reload_catalog()
        self._sync_catalog_selection()
        self._message = None
        self._post_burn_verification_text = None
        if self._context_sidecar_path is not None:
            self.operator_engine_context_service.load_from(self._context_sidecar_path)
        return self.snapshot()

    def select_page(self, page_id: str | None) -> TuningWorkspaceSnapshot:
        if page_id not in self.pages_by_id:
            return self.snapshot()
        if page_id != self.active_page_id:
            self._reset_ve_analyze_state()
            self._reset_wue_analyze_state()
        self.active_page_id = page_id
        page = self._active_page()
        self.active_page_parameter_name = self._default_page_parameter_name(page)
        self.catalog_selected_name = page.table_name if page is not None and page.table_name else self.active_page_parameter_name
        self._sync_catalog_selection()
        self._message = None
        return self.snapshot()

    def select_active_page_parameter(self, name: str | None) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None or name not in page.parameter_names:
            return self.snapshot()
        self.active_page_parameter_name = name
        return self.snapshot()

    def stage_active_page_parameter(self, raw_value: str) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        name = self.active_page_parameter_name
        if page is None or name is None:
            return self.snapshot()
        parameter = next((item for item in page.parameters if item.name == name), None)
        if parameter is None or parameter.kind != "scalar":
            return self.snapshot()
        old_value = self._value_text(name)
        try:
            self.local_tune_edit_service.stage_scalar_value(name, raw_value)
        except Exception as exc:
            self.page_errors[page.page_id] = str(exc)
            self._message = str(exc)
            return self.snapshot()
        # Bounds check — reject if outside declared limits.
        if parameter.options:
            pass  # enum index — no float bounds apply
        elif not isinstance(self.local_tune_edit_service.get_value(name).value, str):  # type: ignore[union-attr]
            staged_float = self.local_tune_edit_service.get_value(name).value  # type: ignore[union-attr]
            if parameter.min_value is not None and staged_float < parameter.min_value:
                self.local_tune_edit_service.revert(name)
                error = f"{name}: value {staged_float} is below minimum {parameter.min_value}."
                self.page_errors[page.page_id] = error
                self._message = error
                return self.snapshot()
            if parameter.max_value is not None and staged_float > parameter.max_value:
                self.local_tune_edit_service.revert(name)
                error = f"{name}: value {staged_float} exceeds maximum {parameter.max_value}."
                self.page_errors[page.page_id] = error
                self._message = error
                return self.snapshot()
        self.page_errors.pop(page.page_id, None)
        self.operation_log_service.record_staged(name, old_value, self._value_text(name), page.title)
        self._written_values.pop(name, None)
        self._reload_catalog()
        self.catalog_selected_name = name
        self._sync_catalog_selection()
        self._message = f"Staged change: {name}"
        return self.snapshot()

    def set_catalog_query(self, query: str) -> TuningWorkspaceSnapshot:
        self.catalog_query = query
        self._sync_catalog_selection()
        return self.snapshot()

    def set_catalog_kind(self, kind: str) -> TuningWorkspaceSnapshot:
        self.catalog_kind = kind
        self._sync_catalog_selection()
        return self.snapshot()

    def select_catalog_entry(self, name: str | None) -> TuningWorkspaceSnapshot:
        self.catalog_selected_name = name
        return self.snapshot()

    def revert_active_page(self) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None:
            return self.snapshot()
        for name in page.parameter_names:
            if self.local_tune_edit_service.is_dirty(name):
                old_value = self._value_text(name)
                self.local_tune_edit_service.revert(name)
                self.operation_log_service.record_reverted(name, old_value, self._value_text(name), page.title)
                self._written_values.pop(name, None)
            else:
                self.local_tune_edit_service.revert(name)
        self.page_errors.pop(page.page_id, None)
        self._reload_catalog()
        self._sync_catalog_selection()
        self._message = f"Reverted page: {page.title}"
        return self.snapshot()

    def stage_table_cell(self, row: int, column: int, raw_value: str) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None or page.kind != TuningPageKind.TABLE or not page.table_name:
            return self.snapshot()
        model = self._active_table_model(page)
        if model is None:
            return self.snapshot()
        return self._stage_list_cell(page, page.table_name, row * model.columns + column, raw_value)

    def stage_x_axis_cell(self, column: int, raw_value: str) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None or page.kind != TuningPageKind.TABLE or not page.x_axis_name:
            return self.snapshot()
        return self._stage_list_cell(page, page.x_axis_name, column, raw_value)

    def stage_y_axis_cell(self, row: int, raw_value: str) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None or page.kind != TuningPageKind.TABLE or not page.y_axis_name:
            return self.snapshot()
        return self._stage_list_cell(page, page.y_axis_name, row, raw_value)

    def stage_curve_cell(self, param_name: str, index: int, raw_value: str) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None or page.kind != TuningPageKind.CURVE:
            return self.snapshot()
        return self._stage_list_cell(page, param_name, index, raw_value)

    def undo_curve_param(self, param_name: str) -> TuningWorkspaceSnapshot:
        self.local_tune_edit_service.undo(param_name)
        return self.snapshot()

    def redo_curve_param(self, param_name: str) -> TuningWorkspaceSnapshot:
        self.local_tune_edit_service.redo(param_name)
        return self.snapshot()

    def copy_table_selection(self, selection: TableSelection) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        model = self._active_table_model(page)
        if page is None or model is None or not page.table_name:
            return self.snapshot()
        tune_value = self.local_tune_edit_service.get_value(page.table_name)
        if tune_value is None or not isinstance(tune_value.value, list):
            return self.snapshot()
        self._clipboard_text = self.table_edit_service.copy_region(tune_value.value, model.columns, selection)
        self._message = "Copied table selection"
        return self.snapshot()

    def paste_table_selection(self, selection: TableSelection, clipboard_text: str | None = None) -> TuningWorkspaceSnapshot:
        text = clipboard_text if clipboard_text is not None else self._clipboard_text
        return self._apply_table_edit(selection, "Pasted table selection", lambda values, columns: self.table_edit_service.paste_region(values, columns, selection, text))

    def fill_table_selection(self, selection: TableSelection, raw_value: str) -> TuningWorkspaceSnapshot:
        return self._apply_table_edit(selection, "Filled table selection", lambda values, columns: self.table_edit_service.fill_region(values, columns, selection, float(raw_value)))

    def fill_down_table_selection(self, selection: TableSelection) -> TuningWorkspaceSnapshot:
        return self._apply_table_edit(
            selection,
            "Filled table selection down",
            lambda values, columns: self.table_edit_service.fill_down_region(values, columns, selection),
        )

    def fill_right_table_selection(self, selection: TableSelection) -> TuningWorkspaceSnapshot:
        return self._apply_table_edit(
            selection,
            "Filled table selection right",
            lambda values, columns: self.table_edit_service.fill_right_region(values, columns, selection),
        )

    def interpolate_table_selection(self, selection: TableSelection) -> TuningWorkspaceSnapshot:
        return self._apply_table_edit(selection, "Interpolated table selection", lambda values, columns: self.table_edit_service.interpolate_region(values, columns, selection))

    def smooth_table_selection(self, selection: TableSelection) -> TuningWorkspaceSnapshot:
        return self._apply_table_edit(selection, "Smoothed table selection", lambda values, columns: self.table_edit_service.smooth_region(values, columns, selection))

    def undo_active_table(self) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None or not page.table_name:
            return self.snapshot()
        old_value = self._value_text(page.table_name)
        self.local_tune_edit_service.undo(page.table_name)
        self.operation_log_service.record_reverted(
            page.table_name, old_value, self._value_text(page.table_name), page.title
        )
        self._written_values.pop(page.table_name, None)
        self._reload_catalog()
        self._message = "Undid table change"
        return self.snapshot()

    def redo_active_table(self) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None or not page.table_name:
            return self.snapshot()
        old_value = self._value_text(page.table_name)
        self.local_tune_edit_service.redo(page.table_name)
        self.operation_log_service.record_staged(
            page.table_name, old_value, self._value_text(page.table_name), page.title
        )
        self._written_values.pop(page.table_name, None)
        self._reload_catalog()
        self._message = "Redid table change"
        return self.snapshot()

    def undo_active_page_parameter(self) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None:
            return self.snapshot()
        for p in page.parameters:
            if p.kind == "scalar" and self.local_tune_edit_service.can_undo(p.name):
                self.local_tune_edit_service.undo(p.name)
                self._reload_catalog()
                self._message = f"Undid change: {p.name}"
                return self.snapshot()
        return self.snapshot()

    def redo_active_page_parameter(self) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        if page is None:
            return self.snapshot()
        for p in page.parameters:
            if p.kind == "scalar" and self.local_tune_edit_service.can_redo(p.name):
                self.local_tune_edit_service.redo(p.name)
                self._reload_catalog()
                self._message = f"Redid change: {p.name}"
                return self.snapshot()
        return self.snapshot()

    def write_active_page(self) -> TuningWorkspaceSnapshot:
        """Mark all staged changes on the active page as written to ECU RAM.

        In offline mode this is a logical marker only — no data is transmitted.
        When a live ``ControllerClient`` is present (future Phase 3 integration),
        this is where the actual write calls go.
        """
        page = self._active_page()
        if page is None:
            return self.snapshot()
        written: list[str] = []
        for name in page.parameter_names:
            if self.local_tune_edit_service.is_dirty(name):
                tune_value = self.local_tune_edit_service.get_value(name)
                if tune_value is None:
                    continue
                if self._ecu_client is not None:
                    try:
                        self._ecu_client.write_parameter(name, tune_value.value)
                    except Exception as exc:
                        self._message = f"Failed to write {name}: {exc}"
                        return self.snapshot()
                    if self._ecu_ram is not None:
                        self._ecu_ram[name] = tune_value.value
                value = self._value_text(name)
                self.operation_log_service.record_written(name, value, page.title)
                self._written_values[name] = value
                written.append(name)
        if written:
            self._message = f"Written to RAM: {', '.join(written)}"
        else:
            self._message = "No staged changes to write on this page."
        return self.snapshot()

    def burn_active_page(self) -> TuningWorkspaceSnapshot:
        """Mark all written parameters on the active page as burned to flash.

        In offline mode this is a logical marker only.  A live integration
        would call ``ControllerClient.burn()`` here.
        """
        page = self._active_page()
        if page is None:
            return self.snapshot()
        burned: list[str] = []
        freshly_written: list[str] = []
        if self._ecu_client is not None:
            for name in page.parameter_names:
                if not self.local_tune_edit_service.is_dirty(name):
                    continue
                if name in self._written_values:
                    continue
                tune_value = self.local_tune_edit_service.get_value(name)
                if tune_value is None:
                    continue
                try:
                    self._ecu_client.write_parameter(name, tune_value.value)
                except Exception as exc:
                    self._message = f"Failed to write {name} before burn: {exc}"
                    return self.snapshot()
                if self._ecu_ram is not None:
                    self._ecu_ram[name] = tune_value.value
                value = self._value_text(name)
                self.operation_log_service.record_written(name, value, page.title)
                self._written_values[name] = value
                freshly_written.append(name)
            pending = [name for name in page.parameter_names if name in self._written_values]
            if pending:
                try:
                    self._ecu_client.burn()
                except Exception as exc:
                    self._message = f"Failed to burn page: {exc}"
                    return self.snapshot()
        for name in page.parameter_names:
            if name in self._written_values or (self._ecu_client is None and self.local_tune_edit_service.is_dirty(name)):
                value = self._value_text(name)
                self.operation_log_service.record_burned(name, value, page.title)
                burned.append(name)
        for name in burned:
            tune_value = self.local_tune_edit_service.get_value(name)
            if tune_value is None:
                continue
            self.local_tune_edit_service.set_base_value(name, tune_value.value)
            self._written_values.pop(name, None)
        bootstrapped = 0
        if burned:
            bootstrapped = self._materialize_missing_visible_tune_values()
        if burned or bootstrapped:
            self._reload_catalog()
            self._post_burn_verification_text = self._build_post_burn_verification_text()
        if burned:
            if freshly_written:
                self._message = f"Written and burned: {', '.join(burned)}"
            else:
                self._message = f"Burned to flash: {', '.join(burned)}"
            if self._post_burn_verification_text is not None:
                self._message = f"{self._message} {self._post_burn_verification_text}"
        else:
            self._message = "No written changes to burn on this page."
        return self.snapshot()

    # ------------------------------------------------------------------
    # Phase 3 — connection and sync state management
    # ------------------------------------------------------------------

    def set_client(self, client: ControllerClient | None, state: SessionState = SessionState.CONNECTED) -> TuningWorkspaceSnapshot:
        """Attach or detach a live controller client and update session state."""
        self._ecu_client = client
        self._session_state = state if client is not None else SessionState.DISCONNECTED
        self.current_firmware_capabilities = getattr(client, "capabilities", None) if client is not None else None
        if client is None:
            self._ecu_ram = None
            self.current_runtime_snapshot = None
        self._post_burn_verification_text = None
        self._message = f"Session: {self._session_state.value}"
        return self.snapshot()

    def go_offline(self) -> TuningWorkspaceSnapshot:
        """Drop the live client but keep the loaded tune and all staged edits."""
        self._ecu_client = None
        self.current_firmware_capabilities = None
        self.current_runtime_snapshot = None
        self._session_state = SessionState.OFFLINE
        self._post_burn_verification_text = None
        self._message = "Went offline — local tune preserved."
        return self.snapshot()

    def set_runtime_snapshot(self, snapshot: OutputChannelSnapshot | None) -> None:
        self.current_runtime_snapshot = snapshot
        if snapshot is not None and self._ve_analyze_running and self._ve_analyze_session.is_active:
            self._ve_analyze_session.feed_runtime(snapshot)
        if snapshot is not None and self._wue_analyze_running and self._wue_analyze_session.is_active:
            self._wue_analyze_session.feed_runtime(snapshot)

    # ------------------------------------------------------------------
    # VE Analyze session lifecycle
    # ------------------------------------------------------------------

    def start_ve_analyze(self) -> TuningWorkspaceSnapshot:
        """Start (or restart) a live VE Analyze session on the current table page.

        Snapshots the current table state and begins accumulating runtime samples.
        All proposed edits remain output-only until the operator calls
        ``apply_ve_analyze_proposals()``.
        """
        page = self._active_page()
        if page is None or page.kind != TuningPageKind.TABLE:
            self._message = "VE Analyze requires an active table page."
            return self.snapshot()
        table_snapshot = self._table_page_snapshot(page)
        if table_snapshot is None or table_snapshot.table_model is None:
            self._message = "VE Analyze: no table data available."
            return self.snapshot()
        self._ve_analyze_session.start(ve_table_snapshot=table_snapshot)
        self._ve_analyze_running = True
        self._message = "VE Analyze started. Feed runtime samples to begin accumulating."
        return self.snapshot()

    def stop_ve_analyze(self) -> TuningWorkspaceSnapshot:
        """Stop feeding runtime samples; preserve accumulated data for review/apply."""
        if not self._ve_analyze_running:
            return self.snapshot()
        self._ve_analyze_running = False
        status = self._ve_analyze_session.status_snapshot()
        self._message = f"VE Analyze stopped. {status.accepted_count} sample(s) accepted."
        return self.snapshot()

    def reset_ve_analyze(self) -> TuningWorkspaceSnapshot:
        """Reset and clear all VE Analyze data for the current session."""
        self._reset_ve_analyze_state()
        self._message = "VE Analyze reset."
        return self.snapshot()

    def apply_ve_analyze_proposals(self) -> TuningWorkspaceSnapshot:
        """Stage all current VE Analyze proposals as table cell edits.

        Only proposals that pass the minimum sample threshold are staged.
        The operator can then review, undo, or revert before writing to RAM.
        """
        page = self._active_page()
        if page is None or page.kind != TuningPageKind.TABLE or not page.table_name:
            self._message = "VE Analyze: no active table page."
            return self.snapshot()
        summary = self._ve_analyze_session.get_summary()
        if summary is None or not summary.proposals:
            self._message = "VE Analyze: no proposals to apply."
            return self.snapshot()
        model = self._active_table_model(page)
        if model is None:
            self._message = "VE Analyze: no table model available."
            return self.snapshot()
        tune_value = self.local_tune_edit_service.get_value(page.table_name)
        if tune_value is None or not isinstance(tune_value.value, list):
            self._message = "VE Analyze: cannot read current table values."
            return self.snapshot()
        old_value = self._value_text(page.table_name)
        new_values = list(tune_value.value)
        applied = 0
        for proposal in summary.proposals:
            index = proposal.row_index * model.columns + proposal.col_index
            if 0 <= index < len(new_values):
                new_values[index] = proposal.proposed_ve
                applied += 1
        if applied == 0:
            self._message = "VE Analyze: no proposals within table bounds."
            return self.snapshot()
        try:
            self.local_tune_edit_service.replace_list(page.table_name, new_values)
        except Exception as exc:
            self._message = f"VE Analyze apply failed: {exc}"
            return self.snapshot()
        self.page_errors.pop(page.page_id, None)
        self.operation_log_service.record_staged(
            page.table_name, old_value, self._value_text(page.table_name), page.title
        )
        self._written_values.pop(page.table_name, None)
        self._reload_catalog()
        self._message = f"VE Analyze: staged {applied} proposal(s) on {page.title}."
        return self.snapshot()

    def _reset_ve_analyze_state(self) -> None:
        self._ve_analyze_session.reset()
        self._ve_analyze_running = False

    def _ve_analyze_snapshot(self, active_page: "TuningPage | None") -> "VeAnalyzeSnapshot | None":
        """Build VeAnalyzeSnapshot; only populated when the active page is a TABLE."""
        if active_page is None or active_page.kind != TuningPageKind.TABLE:
            return None
        is_running = self._ve_analyze_running
        has_data = self._ve_analyze_session.is_active
        status = self._ve_analyze_session.status_snapshot()
        accepted = status.accepted_count
        rejected = status.rejected_count
        summary = self._ve_analyze_session.get_summary() if has_data else None
        cells_with_proposals = summary.cells_with_proposals if summary is not None else 0
        if summary is not None:
            review = self._ve_analyze_review_service.build(summary)
            summary_text = review.summary_text
            detail_text = review.detail_text
        else:
            summary_text = "VE Analyze: not started."
            detail_text = ""
        can_start = not is_running
        can_stop = is_running
        can_reset = has_data or is_running
        can_apply = has_data and not is_running and cells_with_proposals > 0
        return VeAnalyzeSnapshot(
            is_running=is_running,
            has_data=has_data,
            status_text=status.status_text,
            accepted_count=accepted,
            rejected_count=rejected,
            cells_with_proposals=cells_with_proposals,
            summary_text=summary_text,
            detail_text=detail_text,
            can_start=can_start,
            can_stop=can_stop,
            can_reset=can_reset,
            can_apply=can_apply,
        )

    # ------------------------------------------------------------------
    # WUE Analyze session lifecycle
    # ------------------------------------------------------------------

    def start_wue_analyze(self) -> TuningWorkspaceSnapshot:
        """Start (or restart) a live WUE Analyze session on the current table page."""
        page = self._active_page()
        if page is None or page.kind != TuningPageKind.TABLE:
            self._message = "WUE Analyze requires an active table page."
            return self.snapshot()
        table_snapshot = self._table_page_snapshot(page)
        if table_snapshot is None or table_snapshot.table_model is None:
            self._message = "WUE Analyze: no table data available."
            return self.snapshot()
        self._wue_analyze_session.start(wue_table_snapshot=table_snapshot)
        self._wue_analyze_running = True
        self._message = "WUE Analyze started."
        return self.snapshot()

    def stop_wue_analyze(self) -> TuningWorkspaceSnapshot:
        """Stop feeding runtime samples; preserve accumulated data for review/apply."""
        if not self._wue_analyze_running:
            return self.snapshot()
        self._wue_analyze_running = False
        status = self._wue_analyze_session.status_snapshot()
        self._message = f"WUE Analyze stopped. {status.accepted_count} sample(s) accepted."
        return self.snapshot()

    def reset_wue_analyze(self) -> TuningWorkspaceSnapshot:
        """Reset and clear all WUE Analyze data."""
        self._reset_wue_analyze_state()
        self._message = "WUE Analyze reset."
        return self.snapshot()

    def apply_wue_analyze_proposals(self) -> TuningWorkspaceSnapshot:
        """Stage all current WUE Analyze proposals as table cell edits."""
        page = self._active_page()
        if page is None or page.kind != TuningPageKind.TABLE or not page.table_name:
            self._message = "WUE Analyze: no active table page."
            return self.snapshot()
        summary = self._wue_analyze_session.get_summary()
        if summary is None or not summary.proposals:
            self._message = "WUE Analyze: no proposals to apply."
            return self.snapshot()
        model = self._active_table_model(page)
        if model is None:
            self._message = "WUE Analyze: no table model available."
            return self.snapshot()
        tune_value = self.local_tune_edit_service.get_value(page.table_name)
        if tune_value is None or not isinstance(tune_value.value, list):
            self._message = "WUE Analyze: cannot read current table values."
            return self.snapshot()
        # Resolve table orientation to map logical row → flat index
        from tuner.services.wue_analyze_service import _TableOrientation  # noqa: PLC0415
        table_snapshot = self._table_page_snapshot(page)
        orientation = _TableOrientation.detect(table_snapshot) if table_snapshot is not None else None
        old_value = self._value_text(page.table_name)
        new_values = list(tune_value.value)
        applied = 0
        for proposal in summary.proposals:
            if orientation is not None:
                flat_idx = orientation.flat_index(proposal.row_index, model.columns)
            else:
                # Fallback: treat as N×1, logical row maps to row*columns
                flat_idx = proposal.row_index * model.columns
            if 0 <= flat_idx < len(new_values):
                new_values[flat_idx] = proposal.proposed_enrichment
                applied += 1
        if applied == 0:
            self._message = "WUE Analyze: no proposals within table bounds."
            return self.snapshot()
        try:
            self.local_tune_edit_service.replace_list(page.table_name, new_values)
        except Exception as exc:
            self._message = f"WUE Analyze apply failed: {exc}"
            return self.snapshot()
        self.page_errors.pop(page.page_id, None)
        self.operation_log_service.record_staged(
            page.table_name, old_value, self._value_text(page.table_name), page.title
        )
        self._written_values.pop(page.table_name, None)
        self._reload_catalog()
        self._message = f"WUE Analyze: staged {applied} proposal(s) on {page.title}."
        return self.snapshot()

    def _reset_wue_analyze_state(self) -> None:
        self._wue_analyze_session.reset()
        self._wue_analyze_running = False

    def _wue_analyze_snapshot(self, active_page: "TuningPage | None") -> "WueAnalyzeSnapshot | None":
        if active_page is None or active_page.kind != TuningPageKind.TABLE:
            return None
        is_running = self._wue_analyze_running
        has_data = self._wue_analyze_session.is_active
        status = self._wue_analyze_session.status_snapshot()
        summary = self._wue_analyze_session.get_summary() if has_data else None
        rows_with_proposals = summary.rows_with_proposals if summary is not None else 0
        if summary is not None:
            review = self._wue_analyze_review_service.build(summary)
            summary_text = review.summary_text
            detail_text = review.detail_text
        else:
            summary_text = "WUE Analyze: not started."
            detail_text = ""
        can_start = not is_running
        can_stop = is_running
        can_reset = has_data or is_running
        can_apply = has_data and not is_running and rows_with_proposals > 0
        return WueAnalyzeSnapshot(
            is_running=is_running,
            has_data=has_data,
            status_text=status.status_text,
            accepted_count=status.accepted_count,
            rejected_count=status.rejected_count,
            rows_with_proposals=rows_with_proposals,
            summary_text=summary_text,
            detail_text=detail_text,
            can_start=can_start,
            can_stop=can_stop,
            can_reset=can_reset,
            can_apply=can_apply,
        )

    def read_from_ecu(self) -> TuningWorkspaceSnapshot:
        """Read all page parameters from the ECU and store as an ECU RAM snapshot.

        Invalidates the page cache so every read goes to the controller rather
        than returning stale cached data.  Detects mismatches between the ECU
        state and the local tune.  Staged (unwritten) changes are preserved —
        use revert_from_ecu() to replace local values with ECU values.
        """
        if self._ecu_client is None:
            self._message = "No active connection — cannot read from ECU."
            return self.snapshot()
        # Force fresh reads from the controller — don't return stale page cache.
        if hasattr(self._ecu_client, "invalidate_page_cache"):
            self._ecu_client.invalidate_page_cache()
        names: list[str] = []
        for group in self.page_groups:
            for page in group.pages:
                for name in page.parameter_names:
                    if name not in names:
                        names.append(name)
        ram: dict[str, ParameterValue] = {}
        for name in names:
            try:
                ram[name] = self._ecu_client.read_parameter(name)
            except Exception:
                pass
        self._ecu_ram = ram
        self._materialize_missing_visible_tune_values(ram)
        self._reload_catalog()
        self._post_burn_verification_text = None
        self._message = f"Read {len(ram)} parameter(s) from ECU."
        return self.snapshot()

    def revert_from_ecu(self) -> TuningWorkspaceSnapshot:
        """Replace local tune values with ECU RAM values.

        Accepts the ECU RAM snapshot as the new source of truth: updates the
        base tune values and clears all staged overrides for the affected
        parameters.  Requires a prior read_from_ecu() call.
        """
        if self._ecu_ram is None:
            self._message = "No ECU RAM snapshot — run read_from_ecu() first."
            return self.snapshot()
        applied = 0
        for name, value in self._ecu_ram.items():
            self.local_tune_edit_service.set_base_value(name, value)
            applied += 1
        self.operation_log_service.record_written("(all)", f"{applied} values from ECU RAM", "ECU Sync")
        self._written_values.clear()
        self._reload_catalog()
        self._message = f"Reverted {applied} parameter(s) to ECU RAM values."
        return self.snapshot()

    def revert_all_to_baseline(self) -> TuningWorkspaceSnapshot:
        """Clear all staged changes across all pages, returning to the loaded file state."""
        if not self.local_tune_edit_service.is_dirty():
            self._message = "No staged changes to revert."
            return self.snapshot()
        self.local_tune_edit_service.revert()
        self.page_errors.clear()
        self._written_values.clear()
        self._reload_catalog()
        self._message = "Reverted all staged changes to baseline."
        return self.snapshot()

    def consume_message(self) -> str | None:
        message = self._message
        self._message = None
        return message

    # ------------------------------------------------------------------
    # Operator engine context — user-supplied facts not in the ECU
    # ------------------------------------------------------------------

    def update_operator_engine_context(  # noqa: PLR0913
        self,
        *,
        displacement_cc: float | None = ...,  # type: ignore[assignment]
        cylinder_count: int | None = ...,  # type: ignore[assignment]
        compression_ratio: float | None = ...,  # type: ignore[assignment]
        cam_duration_deg: float | None = ...,  # type: ignore[assignment]
        head_flow_class: str | None = ...,  # type: ignore[assignment]
        intake_manifold_style: str | None = ...,  # type: ignore[assignment]
        base_fuel_pressure_psi: float | None = ...,  # type: ignore[assignment]
        injector_pressure_model: str | None = ...,  # type: ignore[assignment]
        secondary_injector_reference_pressure_psi: float | None = ...,  # type: ignore[assignment]
        injector_preset_key: str | None = ...,  # type: ignore[assignment]
        ignition_preset_key: str | None = ...,  # type: ignore[assignment]
        wideband_preset_key: str | None = ...,  # type: ignore[assignment]
        wideband_reference_table_label: str | None = ...,  # type: ignore[assignment]
        turbo_preset_key: str | None = ...,  # type: ignore[assignment]
        injector_characterization: str | None = ...,  # type: ignore[assignment]
        calibration_intent: CalibrationIntent | None = ...,  # type: ignore[assignment]
        # Induction
        forced_induction_topology: ForcedInductionTopology | None = ...,  # type: ignore[assignment]
        supercharger_type: SuperchargerType | None = ...,  # type: ignore[assignment]
        boost_target_kpa: float | None = ...,  # type: ignore[assignment]
        intercooler_present: bool | None = ...,  # type: ignore[assignment]
        # Compressor data
        compressor_corrected_flow_lbmin: float | None = ...,  # type: ignore[assignment]
        compressor_pressure_ratio: float | None = ...,  # type: ignore[assignment]
        compressor_inducer_mm: float | None = ...,  # type: ignore[assignment]
        compressor_exducer_mm: float | None = ...,  # type: ignore[assignment]
        compressor_ar: float | None = ...,  # type: ignore[assignment]
    ) -> TuningWorkspaceSnapshot:
        """Update one or more operator-supplied engine context fields.

        Accepts the same keyword-only sentinel interface as
        :meth:`OperatorEngineContextService.update`.  Passing ``...`` (the
        default) leaves the corresponding field unchanged.  The snapshot is
        regenerated so that the reqFuel calculator and readiness cards reflect
        the new values immediately.
        """
        self.operator_engine_context_service.update(
            displacement_cc=displacement_cc,
            cylinder_count=cylinder_count,
            compression_ratio=compression_ratio,
            cam_duration_deg=cam_duration_deg,
            head_flow_class=head_flow_class,
            intake_manifold_style=intake_manifold_style,
            base_fuel_pressure_psi=base_fuel_pressure_psi,
            injector_pressure_model=injector_pressure_model,
            secondary_injector_reference_pressure_psi=secondary_injector_reference_pressure_psi,
            injector_preset_key=injector_preset_key,
            ignition_preset_key=ignition_preset_key,
            wideband_preset_key=wideband_preset_key,
            wideband_reference_table_label=wideband_reference_table_label,
            turbo_preset_key=turbo_preset_key,
            injector_characterization=injector_characterization,
            calibration_intent=calibration_intent,
            forced_induction_topology=forced_induction_topology,
            supercharger_type=supercharger_type,
            boost_target_kpa=boost_target_kpa,
            intercooler_present=intercooler_present,
            compressor_corrected_flow_lbmin=compressor_corrected_flow_lbmin,
            compressor_pressure_ratio=compressor_pressure_ratio,
            compressor_inducer_mm=compressor_inducer_mm,
            compressor_exducer_mm=compressor_exducer_mm,
            compressor_ar=compressor_ar,
        )
        if self._context_sidecar_path is not None:
            self.operator_engine_context_service.save(self._context_sidecar_path)
        self._message = "Operator engine context updated."
        return self.snapshot()

    # ------------------------------------------------------------------
    # Required fuel calculator — apply computed result as staged edit
    # ------------------------------------------------------------------

    def apply_req_fuel_result(self) -> TuningWorkspaceSnapshot:
        """Stage the computed reqFuel value on the first available reqFuel parameter.

        Unlike the page-local injector calculator, this action is global: it
        computes reqFuel from the current operator context plus discovered tune
        inputs, then stages the value on the first matching scalar parameter
        named/labeled like ``reqFuel`` anywhere in the loaded pages.
        """
        req_fuel_param_name = next(
            (
                parameter.name
                for group in self.page_groups
                for page in group.pages
                for parameter in page.parameters
                if parameter.kind == "scalar" and "reqfuel" in f"{parameter.name} {parameter.label}".lower()
            ),
            None,
        )
        if req_fuel_param_name is None:
            self._message = "No reqFuel scalar parameter found in the loaded tune definition."
            return self.snapshot()

        all_pages = tuple(
            page
            for group in self.page_groups
            for page in group.pages
        )
        ctx = self.hardware_setup_generator_context_service.build(
            all_pages,
            self.local_tune_edit_service,
            operator_context=self.operator_engine_context_service.get(),
        )

        displacement = ctx.displacement_cc
        cylinder_count = ctx.cylinder_count
        injector_flow = ctx.injector_flow_ccmin
        target_afr = ctx.stoich_ratio or 14.7
        if not displacement or not cylinder_count or not injector_flow:
            self._message = "reqFuel calculator result is not available or cannot be applied."
            return self.snapshot()

        calc = RequiredFuelCalculatorService().calculate(
            displacement_cc=displacement,
            cylinder_count=cylinder_count,
            injector_flow_ccmin=injector_flow,
            target_afr=target_afr,
        )
        if not calc.is_valid:
            self._message = "reqFuel calculator result is not available or cannot be applied."
            return self.snapshot()

        result = self.stage_named_parameter(req_fuel_param_name, str(calc.req_fuel_ms))
        if self._message and self._message.startswith("Staged change:"):
            self._message = f"Calculated reqFuel staged on '{req_fuel_param_name}'."
        return result

    # ------------------------------------------------------------------
    # VE table generator — produce and stage a conservative starter table
    # ------------------------------------------------------------------

    def stage_generated_ve_table(
        self, table_name: str, result: VeTableGeneratorResult
    ) -> TuningWorkspaceSnapshot:
        """Stage a generated VE table as a reviewable edit.

        The values from ``result`` are staged via the normal
        :meth:`LocalTuneEditService.replace_list` path so they appear in the
        workspace diff and follow the standard write/burn flow.

        Parameters
        ----------
        table_name:
            Name of the table parameter to stage (typically ``"veTable"``).
        result:
            The generator result returned by
            :class:`VeTableGeneratorService.generate`.
        """
        self._ensure_table_page_materialized(table_name)
        tune_value = self.local_tune_edit_service.get_value(table_name)
        if tune_value is None:
            if self.local_tune_edit_service.base_tune_file is None:
                self._message = "No tune file loaded. Open a tune (.msq) before generating a VE table."
            else:
                self._message = f"Table '{table_name}' not found in loaded tune."
            return self.snapshot()
        if not isinstance(tune_value.value, list):
            self._message = f"Parameter '{table_name}' is not a table."
            return self.snapshot()

        old_value = self._value_text(table_name)
        try:
            self.local_tune_edit_service.replace_list(table_name, result.as_list())
        except Exception as exc:
            self._message = str(exc)
            return self.snapshot()

        # Find a page containing this table to attach the operation log entry
        page_title = next(
            (
                page.title
                for group in self.page_groups
                for page in group.pages
                if table_name in page.parameter_names
            ),
            "VE Table",
        )
        self.operation_log_service.record_staged(
            table_name, old_value, self._value_text(table_name), page_title
        )
        self._written_values.pop(table_name, None)
        self._reload_catalog()
        self._message = (
            f"Generated VE table staged for '{table_name}'. "
            f"Topology: {result.topology.value}. Review and write when ready."
        )
        return self.snapshot()

    def generate_and_stage_ve_table(
        self,
        table_name: str,
        *,
        operator_context: OperatorEngineContext | None = None,
    ) -> TuningWorkspaceSnapshot:
        """Generate a conservative VE table from current context and stage it.

        Convenience method that calls :class:`VeTableGeneratorService` with
        the generator context from the current hardware setup pages and then
        immediately stages the result on ``table_name``.

        Requires that the tune is loaded and that hardware setup pages are
        present to supply injector/engine geometry inputs.
        """
        # Build generator context from all hardware_setup pages
        hw_pages = tuple(
            page
            for group in self.page_groups
            if group.group_id == "hardware_setup"
            for page in group.pages
        )
        if not hw_pages:
            hw_pages = tuple(
                page
                for group in self.page_groups
                for page in group.pages
            )
        resolved_operator_context = operator_context or self.operator_engine_context_service.get()
        ctx = self.hardware_setup_generator_context_service.build(
            hw_pages,
            self.local_tune_edit_service,
            operator_context=resolved_operator_context,
        )

        result = self.ve_table_generator_service.generate(ctx)
        return self.stage_generated_ve_table(table_name, result)

    # ------------------------------------------------------------------
    # Spark table generator — produce and stage a conservative timing table
    # ------------------------------------------------------------------

    def stage_generated_spark_table(
        self, table_name: str, result: SparkTableGeneratorResult
    ) -> TuningWorkspaceSnapshot:
        """Stage a generated spark advance table as a reviewable edit.

        Parallel to :meth:`stage_generated_ve_table` — values are staged via
        the normal :meth:`LocalTuneEditService.replace_list` path.

        Parameters
        ----------
        table_name:
            Name of the table parameter to stage (typically ``"ignitionTable"``).
        result:
            The generator result returned by
            :class:`SparkTableGeneratorService.generate`.
        """
        self._ensure_table_page_materialized(table_name)
        tune_value = self.local_tune_edit_service.get_value(table_name)
        if tune_value is None:
            if self.local_tune_edit_service.base_tune_file is None:
                self._message = "No tune file loaded. Open a tune (.msq) before generating a spark table."
            else:
                self._message = f"Table '{table_name}' not found in loaded tune."
            return self.snapshot()
        if not isinstance(tune_value.value, list):
            self._message = f"Parameter '{table_name}' is not a table."
            return self.snapshot()

        old_value = self._value_text(table_name)
        try:
            self.local_tune_edit_service.replace_list(table_name, result.as_list())
        except Exception as exc:
            self._message = str(exc)
            return self.snapshot()

        page_title = next(
            (
                page.title
                for group in self.page_groups
                for page in group.pages
                if table_name in page.parameter_names
            ),
            "Ignition Table",
        )
        self.operation_log_service.record_staged(
            table_name, old_value, self._value_text(table_name), page_title
        )
        self._written_values.pop(table_name, None)
        self._reload_catalog()
        topology_text = result.topology.value if hasattr(result.topology, "value") else str(result.topology)
        self._message = (
            f"Generated spark table staged for '{table_name}'. "
            f"Topology: {topology_text}. Review and write when ready."
        )
        return self.snapshot()

    def generate_and_stage_spark_table(
        self,
        table_name: str,
        *,
        operator_context: OperatorEngineContext | None = None,
    ) -> TuningWorkspaceSnapshot:
        """Generate a conservative spark advance table from current context and stage it.

        Uses operator engine context (compression ratio, cylinder count,
        calibration intent) and hardware setup generator context (topology).
        """
        hw_pages = tuple(
            page
            for group in self.page_groups
            if group.group_id == "hardware_setup"
            for page in group.pages
        )
        if not hw_pages:
            hw_pages = tuple(
                page
                for group in self.page_groups
                for page in group.pages
            )
        resolved_operator_context = operator_context or self.operator_engine_context_service.get()
        ctx = self.hardware_setup_generator_context_service.build(
            hw_pages,
            self.local_tune_edit_service,
            operator_context=resolved_operator_context,
        )

        calibration_intent = (
            resolved_operator_context.calibration_intent
            if resolved_operator_context
            else CalibrationIntent.FIRST_START
        )
        result = self.spark_table_generator_service.generate(ctx, calibration_intent)
        return self.stage_generated_spark_table(table_name, result)

    def stage_generated_afr_table(
        self, table_name: str, result: AfrTargetGeneratorResult
    ) -> TuningWorkspaceSnapshot:
        """Stage a generated AFR target table as a reviewable edit.

        Values are staged via the normal :meth:`LocalTuneEditService.replace_list`
        path.  The operator must review and explicitly write/burn the result.

        Parameters
        ----------
        table_name:
            Name of the table parameter to stage (typically ``"afrTable"`` or
            ``"targetAfr"``).
        result:
            The generator result returned by
            :class:`AfrTargetGeneratorService.generate`.
        """
        self._ensure_table_page_materialized(table_name)
        tune_value = self.local_tune_edit_service.get_value(table_name)
        if tune_value is None:
            if self.local_tune_edit_service.base_tune_file is None:
                self._message = "No tune file loaded. Open a tune (.msq) before generating an AFR table."
            else:
                self._message = f"Table '{table_name}' not found in loaded tune."
            return self.snapshot()
        if not isinstance(tune_value.value, list):
            self._message = f"Parameter '{table_name}' is not a table."
            return self.snapshot()

        old_value = self._value_text(table_name)
        try:
            self.local_tune_edit_service.replace_list(table_name, result.as_list())
        except Exception as exc:
            self._message = str(exc)
            return self.snapshot()

        page_title = next(
            (
                page.title
                for group in self.page_groups
                for page in group.pages
                if table_name in page.parameter_names
            ),
            "AFR Target",
        )
        self.operation_log_service.record_staged(
            table_name, old_value, self._value_text(table_name), page_title
        )
        self._written_values.pop(table_name, None)
        self._reload_catalog()
        self._message = (
            f"Generated AFR target table staged for '{table_name}'. "
            f"Topology: {result.topology.value}. Stoich: {result.stoich:.1f}. "
            "Review WOT cells before first run under load."
        )
        return self.snapshot()

    def _ensure_table_page_materialized(self, table_name: str) -> None:
        """Bootstrap a definition-backed table and its axes into the tune when absent."""
        if self.local_tune_edit_service.get_value(table_name) is not None:
            return
        if self.definition is None or self.local_tune_edit_service.base_tune_file is None:
            return

        materialized = self._materialize_missing_tune_value(table_name)
        page = next(
            (
                page
                for group in self.page_groups
                for page in group.pages
                if page.table_name == table_name or table_name in page.parameter_names
            ),
            None,
        )
        if page is not None:
            for axis_name in (page.x_axis_name, page.y_axis_name):
                if axis_name and self.local_tune_edit_service.get_value(axis_name) is None:
                    materialized = self._materialize_missing_tune_value(axis_name) or materialized
        if materialized:
            self._reload_catalog()

    def generate_and_stage_afr_table(
        self,
        table_name: str,
        *,
        operator_context: OperatorEngineContext | None = None,
    ) -> TuningWorkspaceSnapshot:
        """Generate a conservative AFR target table from current context and stage it.

        Uses operator engine context (calibration intent, induction topology)
        and hardware setup generator context.
        """
        resolved_operator_context = operator_context or self.operator_engine_context_service.get()
        hw_pages = tuple(
            page
            for group in self.page_groups
            if group.group_id == "hardware_setup"
            for page in group.pages
        )
        if not hw_pages:
            from tuner.domain.generator_context import GeneratorInputContext
            ctx = GeneratorInputContext()
        else:
            ctx = self.hardware_setup_generator_context_service.build(
                hw_pages,
                self.local_tune_edit_service,
                operator_context=resolved_operator_context,
            )

        calibration_intent = (
            resolved_operator_context.calibration_intent
            if resolved_operator_context
            else CalibrationIntent.FIRST_START
        )
        result = self.afr_target_generator_service.generate(ctx, calibration_intent)
        return self.stage_generated_afr_table(table_name, result)

    # ------------------------------------------------------------------
    # Startup enrichment generators — WUE, cranking, ASE
    # ------------------------------------------------------------------

    def _stage_named_array(
        self, name: str, values: list[float], fallback_title: str
    ) -> str | None:
        """Stage a named 1-D array parameter via replace_list.

        Returns an error message string on failure, or ``None`` on success.
        The operation is recorded in the operation log.
        """
        tv = self.local_tune_edit_service.get_value(name)
        if tv is None:
            return f"Parameter '{name}' not found in loaded tune."
        if not isinstance(tv.value, list):
            return f"Parameter '{name}' is not an array parameter."
        old_value = self._value_text(name)
        try:
            self.local_tune_edit_service.replace_list(name, values)
        except Exception as exc:
            return str(exc)
        page_title = next(
            (
                page.title
                for group in self.page_groups
                for page in group.pages
                if name in page.parameter_names
            ),
            fallback_title,
        )
        self.operation_log_service.record_staged(
            name, old_value, self._value_text(name), page_title
        )
        self._written_values.pop(name, None)
        self._reload_catalog()
        return None

    def stage_generated_wue(
        self,
        bins_name: str,
        rates_name: str,
        result: WarmupEnrichmentGeneratorResult,
    ) -> TuningWorkspaceSnapshot:
        """Stage generated WUE bins and rates as reviewable edits.

        Both ``bins_name`` (typically ``"wueBins"``) and ``rates_name``
        (typically ``"wueRates"``) must exist as list parameters in the
        loaded tune.  The operator must review and explicitly write/burn.
        """
        err = self._stage_named_array(bins_name, result.as_bins_list(), "Warmup Enrichment")
        if err:
            self._message = err
            return self.snapshot()
        err = self._stage_named_array(rates_name, result.as_rates_list(), "Warmup Enrichment")
        if err:
            self._message = err
            return self.snapshot()
        self._message = (
            f"WUE staged for '{rates_name}'. {result.summary} "
            "Review before first cold start."
        )
        return self.snapshot()

    def generate_and_stage_wue(
        self,
        bins_name: str = "wueBins",
        rates_name: str = "wueRates",
        *,
        operator_context: OperatorEngineContext | None = None,
    ) -> TuningWorkspaceSnapshot:
        """Generate conservative WUE from current context and stage it."""
        op_ctx = operator_context or self.operator_engine_context_service.get()
        calibration_intent = (
            op_ctx.calibration_intent if op_ctx else CalibrationIntent.FIRST_START
        )
        hw_pages = tuple(
            page
            for group in self.page_groups
            if group.group_id == "hardware_setup"
            for page in group.pages
        )
        if hw_pages:
            ctx = self.hardware_setup_generator_context_service.build(
                hw_pages,
                self.local_tune_edit_service,
                operator_context=op_ctx,
            )
        else:
            from tuner.domain.generator_context import GeneratorInputContext
            ctx = GeneratorInputContext()

        result = self.startup_enrichment_generator_service.generate_wue(ctx, calibration_intent)
        return self.stage_generated_wue(bins_name, rates_name, result)

    def stage_generated_cranking_enrichment(
        self,
        bins_name: str,
        values_name: str,
        result: CrankingEnrichmentGeneratorResult,
    ) -> TuningWorkspaceSnapshot:
        """Stage generated cranking enrichment bins and values as reviewable edits."""
        err = self._stage_named_array(bins_name, result.as_bins_list(), "Cranking Enrichment")
        if err:
            self._message = err
            return self.snapshot()
        err = self._stage_named_array(values_name, result.as_values_list(), "Cranking Enrichment")
        if err:
            self._message = err
            return self.snapshot()
        self._message = (
            f"Cranking enrichment staged for '{values_name}'. {result.summary} "
            "Review against cold-start fueling behavior."
        )
        return self.snapshot()

    def generate_and_stage_cranking_enrichment(
        self,
        bins_name: str = "crankingEnrichBins",
        values_name: str = "crankingEnrichValues",
        *,
        operator_context: OperatorEngineContext | None = None,
    ) -> TuningWorkspaceSnapshot:
        """Generate conservative cranking enrichment from current context and stage it."""
        op_ctx = operator_context or self.operator_engine_context_service.get()
        calibration_intent = (
            op_ctx.calibration_intent if op_ctx else CalibrationIntent.FIRST_START
        )
        hw_pages = tuple(
            page
            for group in self.page_groups
            if group.group_id == "hardware_setup"
            for page in group.pages
        )
        if hw_pages:
            ctx = self.hardware_setup_generator_context_service.build(
                hw_pages,
                self.local_tune_edit_service,
                operator_context=op_ctx,
            )
        else:
            from tuner.domain.generator_context import GeneratorInputContext
            ctx = GeneratorInputContext()

        result = self.startup_enrichment_generator_service.generate_cranking(
            ctx, calibration_intent
        )
        return self.stage_generated_cranking_enrichment(bins_name, values_name, result)

    def stage_generated_ase(
        self,
        bins_name: str,
        pct_name: str,
        count_name: str,
        result: AfterStartEnrichmentGeneratorResult,
    ) -> TuningWorkspaceSnapshot:
        """Stage generated ASE bins, enrichment %, and durations as reviewable edits."""
        err = self._stage_named_array(bins_name, result.as_bins_list(), "After-Start Enrichment")
        if err:
            self._message = err
            return self.snapshot()
        err = self._stage_named_array(pct_name, result.as_pct_list(), "After-Start Enrichment")
        if err:
            self._message = err
            return self.snapshot()
        err = self._stage_named_array(count_name, result.as_count_list(), "After-Start Enrichment")
        if err:
            self._message = err
            return self.snapshot()
        self._message = (
            f"ASE staged for '{pct_name}' / '{count_name}'. {result.summary} "
            "Review enrichment and duration against post-start idle stability."
        )
        return self.snapshot()

    def generate_and_stage_ase(
        self,
        bins_name: str = "aseBins",
        pct_name: str = "asePct",
        count_name: str = "aseCount",
        *,
        operator_context: OperatorEngineContext | None = None,
    ) -> TuningWorkspaceSnapshot:
        """Generate conservative ASE from current context and stage it."""
        op_ctx = operator_context or self.operator_engine_context_service.get()
        calibration_intent = (
            op_ctx.calibration_intent if op_ctx else CalibrationIntent.FIRST_START
        )
        hw_pages = tuple(
            page
            for group in self.page_groups
            if group.group_id == "hardware_setup"
            for page in group.pages
        )
        if hw_pages:
            ctx = self.hardware_setup_generator_context_service.build(
                hw_pages,
                self.local_tune_edit_service,
                operator_context=op_ctx,
            )
        else:
            from tuner.domain.generator_context import GeneratorInputContext
            ctx = GeneratorInputContext()

        result = self.startup_enrichment_generator_service.generate_ase(
            ctx, calibration_intent
        )
        return self.stage_generated_ase(bins_name, pct_name, count_name, result)

    def stage_generated_idle_rpm_targets(
        self,
        bins_name: str,
        values_name: str,
        result: IdleRpmTargetGeneratorResult,
    ) -> TuningWorkspaceSnapshot:
        """Stage generated idle RPM target bins and values as reviewable edits.

        ``bins_name`` (typically ``"iacBins"``) and ``values_name``
        (typically ``"iacCLValues"``) must exist as list parameters in the
        loaded tune.  The operator must review and explicitly write/burn.
        """
        err = self._stage_named_array(bins_name, result.as_bins_list(), "Idle RPM Targets")
        if err:
            self._message = err
            return self.snapshot()
        err = self._stage_named_array(values_name, result.as_targets_list(), "Idle RPM Targets")
        if err:
            self._message = err
            return self.snapshot()
        self._message = (
            f"Idle RPM targets staged for '{values_name}'. {result.summary}"
        )
        return self.snapshot()

    def generate_and_stage_idle_rpm_targets(
        self,
        bins_name: str = "iacBins",
        values_name: str = "iacCLValues",
        *,
        operator_context: OperatorEngineContext | None = None,
    ) -> TuningWorkspaceSnapshot:
        """Generate conservative idle RPM targets from current context and stage them."""
        op_ctx = operator_context or self.operator_engine_context_service.get()
        calibration_intent = (
            op_ctx.calibration_intent if op_ctx else CalibrationIntent.FIRST_START
        )
        hw_pages = tuple(
            page
            for group in self.page_groups
            if group.group_id == "hardware_setup"
            for page in group.pages
        )
        if hw_pages:
            ctx = self.hardware_setup_generator_context_service.build(
                hw_pages,
                self.local_tune_edit_service,
                operator_context=op_ctx,
            )
        else:
            from tuner.domain.generator_context import GeneratorInputContext
            ctx = GeneratorInputContext()

        result = self.idle_rpm_target_generator_service.generate(ctx, calibration_intent)
        return self.stage_generated_idle_rpm_targets(bins_name, values_name, result)

    # ------------------------------------------------------------------
    # Thermistor calibration — write CLT/IAT tables directly to the ECU
    # ------------------------------------------------------------------

    def write_thermistor_calibration(
        self,
        sensor: CalibrationSensor,
        preset: ThermistorPreset,
    ) -> TuningWorkspaceSnapshot:
        """Generate a calibration table from *preset* and write it to the ECU.

        Unlike tune-file edits, thermistor calibration tables are not stored
        in the MSQ page structure — they live in a dedicated EEPROM region and
        are written via the Speeduino ``'t'`` serial command.  A live ECU
        connection is required; the call has no effect in offline mode.

        Parameters
        ----------
        sensor:
            ``CalibrationSensor.CLT`` (coolant) or ``CalibrationSensor.IAT``
            (intake air temperature).
        preset:
            Thermistor definition to generate from.  Use
            :class:`ThermistorCalibrationService` to look up built-in presets
            or construct a custom one.
        """
        sensor_label = "CLT" if sensor == CalibrationSensor.CLT else "IAT"

        if self._ecu_client is None or self._session_state.name == "OFFLINE":
            self._message = (
                f"{sensor_label} calibration requires a live ECU connection. "
                "Connect to the ECU, then try again."
            )
            return self.snapshot()

        svc = ThermistorCalibrationService()
        result = svc.generate(preset, sensor)
        payload = result.encode_payload()

        try:
            write_fn = getattr(self._ecu_client, "write_calibration_table", None)
            if write_fn is None:
                raise NotImplementedError(
                    "The connected client does not support calibration table writes."
                )
            write_fn(int(sensor), payload)
        except Exception as exc:
            self._message = f"{sensor_label} calibration write failed: {exc}"
            return self.snapshot()

        self._message = (
            f"{sensor_label} calibration written to ECU — preset: {preset.name}. "
            "The table is stored in ECU EEPROM immediately and does not require a burn."
        )
        return self.snapshot()

    # ------------------------------------------------------------------
    # Generic staged-parameter helper (used by wizard surfaces)
    # ------------------------------------------------------------------

    def stage_named_parameter(self, name: str, value: str) -> TuningWorkspaceSnapshot:
        """Stage a scalar parameter value by name without requiring it to be on
        the active page.

        This is used by wizard surfaces (e.g. :class:`HardwareSetupWizard`)
        that need to stage individual parameters regardless of which tuning
        page is currently selected in the main editor.

        Parameters
        ----------
        name:
            The parameter name as it appears in the tune / definition.
        value:
            The new value as a string (will be stored verbatim in the staged
            edit, matching the normal scalar-edit path).
        """
        tune_value = self.local_tune_edit_service.get_value(name)
        if tune_value is None:
            tune_value = self._bootstrap_missing_scalar_tune_value(name, value)
            if tune_value is None:
                self._message = f"Parameter '{name}' not found in loaded tune."
                return self.snapshot()

        old_value = self._value_text(name)
        try:
            self.local_tune_edit_service.stage_scalar_value(name, value)
        except Exception as exc:
            self._message = str(exc)
            return self.snapshot()

        new_value = self._value_text(name)
        page_title = next(
            (
                page.title
                for group in self.page_groups
                for page in group.pages
                if name in page.parameter_names
            ),
            "Wizard",
        )
        self.operation_log_service.record_staged(name, old_value, new_value, page_title)
        self._written_values.pop(name, None)
        self._reload_catalog()
        self._message = f"Staged '{name}' = {value}."
        return self.snapshot()

    def stage_named_array(self, name: str, values: list[float]) -> TuningWorkspaceSnapshot:
        message = self._stage_named_array(name, values, "Wizard")
        self._message = message or f"Staged '{name}' array."
        return self.snapshot()

    def _bootstrap_missing_scalar_tune_value(self, name: str, raw_value: str) -> TuneValue | None:
        if self.tune_file is None or self.definition is None:
            return None
        scalar = next((item for item in self.definition.scalars if item.name == name), None)
        if scalar is None:
            return None
        try:
            value: str | float
            value = float(raw_value)
        except ValueError:
            value = raw_value
        tune_value = TuneValue(
            name=name,
            value=value,
            units=scalar.units,
            digits=scalar.digits,
        )
        self.tune_file.constants.append(tune_value)
        return tune_value

    def _materialize_missing_visible_tune_values(self, ecu_values: dict[str, ParameterValue] | None = None) -> int:
        if self.tune_file is None or self.definition is None:
            return 0
        added = 0
        seen_names: set[str] = set()
        for group in self.page_groups:
            for page in group.pages:
                values = self.local_tune_edit_service.get_scalar_values_dict()
                if not self.visibility_expression_service.evaluate(page.visibility_expression, values):
                    continue
                for parameter in page.parameters:
                    if parameter.name in seen_names:
                        continue
                    seen_names.add(parameter.name)
                    values = self.local_tune_edit_service.get_scalar_values_dict()
                    if not self.visibility_expression_service.evaluate(parameter.visibility_expression, values):
                        continue
                    if not self.tuning_page_validation_service._expects_tune_value(parameter.page, parameter.offset):
                        continue
                    if self.local_tune_edit_service.get_value(parameter.name) is not None:
                        continue
                    if self._materialize_missing_tune_value(parameter.name, ecu_values):
                        added += 1
        return added

    def _materialize_missing_tune_value(
        self,
        name: str,
        ecu_values: dict[str, ParameterValue] | None = None,
    ) -> bool:
        scalar = next((item for item in self.definition.scalars if item.name == name), None) if self.definition else None
        table = next((item for item in self.definition.tables if item.name == name), None) if self.definition else None
        ecu_value = ecu_values.get(name) if ecu_values is not None and name in ecu_values else None
        if table is not None:
            value = ecu_value if isinstance(ecu_value, list) else [0.0] * (table.rows * table.columns)
            self.local_tune_edit_service.set_or_add_base_value(
                name,
                value,
                units=table.units,
                digits=table.digits,
                rows=table.rows,
                cols=table.columns,
            )
            return True
        if scalar is not None:
            value = ecu_value if isinstance(ecu_value, (float, str)) else 0.0
            self.local_tune_edit_service.set_or_add_base_value(
                name,
                value,
                units=scalar.units,
                digits=scalar.digits,
            )
            return True
        return False

    def snapshot(self) -> TuningWorkspaceSnapshot:
        active_page = self._active_page()
        return TuningWorkspaceSnapshot(
            navigation=tuple(self._navigation_snapshot()),
            active_page_kind=active_page.kind.value if active_page is not None else "empty",
            table_page=self._table_page_snapshot(active_page) if active_page is not None and active_page.kind == TuningPageKind.TABLE else None,
            curve_page=self._curve_page_snapshot(active_page) if active_page is not None and active_page.kind == TuningPageKind.CURVE else None,
            parameter_page=self._parameter_page_snapshot(active_page) if active_page is not None and active_page.kind == TuningPageKind.PARAMETER_LIST else None,
            catalog=self._catalog_snapshot(),
            operation_log=self._operation_log_snapshot(),
            workspace_review=self._workspace_review_snapshot(),
            sync_state=self.sync_state_service.build(
                self.definition,
                self.tune_file,
                self._ecu_ram,
                self.local_tune_edit_service.is_dirty(),
                self._session_state.value,
            ),
            hardware_issues=tuple(self._hardware_issues()),
            post_burn_verification_text=self._post_burn_verification_text,
            ve_analyze=self._ve_analyze_snapshot(active_page),
            wue_analyze=self._wue_analyze_snapshot(active_page),
        )

    def _build_post_burn_verification_text(self) -> str:
        if self._ecu_client is None:
            return "Reconnect to the controller and verify persisted values before trusting the burn."
        telemetry = self._speeduino_runtime_telemetry_service.decode(self.current_runtime_snapshot)
        if telemetry.board_capabilities.spi_flash and telemetry.spi_flash_health is False:
            return "Runtime storage health is bad; power-cycle or reconnect and verify persisted values before trusting the burn."
        if telemetry.spi_flash_health is False:
            return "Runtime reports storage unavailable; reconnect and verify persisted values before trusting the burn."
        return "Reconnect or read back from ECU and verify persisted values before trusting the burn."

    def _actual_group_id(self, page_id: str) -> str:
        """Return the group_id of the TuningPageGroup that contains the given page."""
        for group in self.page_groups:
            for page in group.pages:
                if page.page_id == page_id:
                    return group.group_id
        return ""

    def _cross_validate_ignition_trigger(
        self,
        active_page: "TuningPage",
        hardware_pages: tuple["TuningPage", ...],
    ) -> "tuple":
        """Run ignition/trigger cross-validation when the active page is ignition or trigger.

        Returns an empty tuple for all other page kinds.
        """
        from tuner.domain.setup_checklist import SetupChecklistItem

        page_kind = self.hardware_setup_summary_service._page_kind(active_page)  # noqa: SLF001
        if page_kind not in ("ignition", "trigger"):
            return ()

        # Find the companion page: if active is ignition, look for trigger and vice versa.
        companion_kind = "trigger" if page_kind == "ignition" else "ignition"
        companion_page = next(
            (
                p for p in hardware_pages
                if p is not active_page
                and self.hardware_setup_summary_service._page_kind(p) == companion_kind  # noqa: SLF001
            ),
            None,
        )

        ign = active_page if page_kind == "ignition" else companion_page
        trig = active_page if page_kind == "trigger" else companion_page

        return self.ignition_trigger_cross_validation_service.validate(
            ignition_page=ign,
            trigger_page=trig,
            edits=self.local_tune_edit_service,
        )

    def _cross_validate_sensor(
        self,
        active_page: "TuningPage",
        hardware_pages: tuple["TuningPage", ...],
    ) -> "tuple":
        """Run sensor checklist when the active page is a sensor page.

        Returns an empty tuple for all other page kinds.
        """
        page_kind = self.hardware_setup_summary_service._page_kind(active_page)  # noqa: SLF001
        if page_kind != "sensor":
            return ()

        from tuner.services.sensor_setup_checklist_service import SensorSetupChecklistService

        sensor_pages = tuple(
            p for p in hardware_pages
            if self.hardware_setup_summary_service._page_kind(p) == "sensor"  # noqa: SLF001
        )
        if not sensor_pages:
            sensor_pages = (active_page,)

        return SensorSetupChecklistService().validate(
            sensor_pages=sensor_pages,
            edits=self.local_tune_edit_service,
        )

    def _hardware_issues(self) -> list[HardwareSetupIssue]:
        """Run hardware setup validation across all hardware_setup group pages."""
        hw_names: list[str] = []
        for group in self.page_groups:
            if group.group_id == "hardware_setup":
                for page in group.pages:
                    for name in page.parameter_names:
                        if name not in hw_names:
                            hw_names.append(name)
        if not hw_names:
            return []

        def _get(name: str) -> float | None:
            tv = self.local_tune_edit_service.get_value(name)
            if tv is None:
                return None
            val = tv.value
            if isinstance(val, (int, float)):
                return float(val)
            return None

        return self.hardware_setup_validation_service.validate(hw_names, _get)

    def _apply_table_edit(self, selection: TableSelection, message: str, transform: callable) -> TuningWorkspaceSnapshot:
        page = self._active_page()
        model = self._active_table_model(page)
        if page is None or model is None or not page.table_name:
            return self.snapshot()
        tune_value = self.local_tune_edit_service.get_value(page.table_name)
        if tune_value is None or not isinstance(tune_value.value, list):
            return self.snapshot()
        old_value = self._value_text(page.table_name)
        try:
            new_values = transform(list(tune_value.value), model.columns)
            self.local_tune_edit_service.replace_list(page.table_name, new_values)
        except Exception as exc:
            self.page_errors[page.page_id] = str(exc)
            self._message = str(exc)
            return self.snapshot()
        self.page_errors.pop(page.page_id, None)
        self.operation_log_service.record_staged(
            page.table_name, old_value, self._value_text(page.table_name), page.title
        )
        self._written_values.pop(page.table_name, None)
        self._reload_catalog()
        self._message = message
        return self.snapshot()

    def _stage_list_cell(self, page: TuningPage, name: str, index: int, raw_value: str) -> TuningWorkspaceSnapshot:
        try:
            self.local_tune_edit_service.stage_list_cell(name, index, raw_value)
        except Exception as exc:
            self.page_errors[page.page_id] = str(exc)
            self._message = str(exc)
            return self.snapshot()
        self.page_errors.pop(page.page_id, None)
        self._reload_catalog()
        self._sync_catalog_selection()
        self._message = f"Staged change: {name}"
        return self.snapshot()

    def _navigation_snapshot(self) -> list[NavigationGroupSnapshot]:
        groups: list[NavigationGroupSnapshot] = []
        seen_family_ids: set[str] = set()
        for group in self.page_groups:
            pages: list[NavigationPageSnapshot] = []
            for page in group.pages:
                if not self._is_page_visible(page):
                    continue
                family = self._page_families_by_page_id.get(page.page_id)
                if family is None:
                    pages.append(
                        NavigationPageSnapshot(
                            page_id=page.page_id,
                            title=page.title,
                            kind=page.kind,
                            summary=page.summary,
                            state=self._page_state(page),
                            is_active=page.page_id == self.active_page_id,
                        )
                    )
                    continue
                if family.family_id in seen_family_ids:
                    continue
                family_tabs = self._visible_family_related_pages(family)
                if not family_tabs:
                    continue
                seen_family_ids.add(family.family_id)
                active_tab = next((tab for tab in family_tabs if tab.is_active), family_tabs[0])
                family_pages = [self.pages_by_id[tab.page_id] for tab in family_tabs if tab.page_id in self.pages_by_id]
                pages.append(
                    NavigationPageSnapshot(
                        page_id=active_tab.page_id,
                        title=family.title,
                        kind=family_pages[0].kind if family_pages else page.kind,
                        summary=", ".join(tab.title for tab in family_tabs),
                        state=self._aggregate_page_state(tuple(family_pages)),
                        is_active=any(tab.is_active for tab in family_tabs),
                    )
                )
            if pages:
                groups.append(NavigationGroupSnapshot(title=group.title, pages=tuple(pages)))
        return groups

    def _aggregate_page_state(self, pages: tuple[TuningPage, ...]) -> TuningPageState:
        if not pages:
            return TuningPageState(kind=TuningPageStateKind.CLEAN)
        states = [self._page_state(page) for page in pages]
        for kind in (TuningPageStateKind.INVALID, TuningPageStateKind.STAGED, TuningPageStateKind.WRITTEN):
            match = next((state for state in states if state.kind == kind), None)
            if match is not None:
                return match
        return states[0]

    def _visible_family_related_pages(self, family: PageFamily) -> tuple[RelatedPageSnapshot, ...]:
        visible: list[RelatedPageSnapshot] = []
        for tab in family.tabs:
            page = self.pages_by_id.get(tab.page_id)
            if page is None or not self._is_page_visible(page):
                continue
            visible.append(
                RelatedPageSnapshot(
                    page_id=tab.page_id,
                    title=tab.title,
                    is_active=tab.page_id == self.active_page_id,
                    state_label=self._page_state(page).label,
                )
            )
        return tuple(visible)

    def _is_page_visible(self, page: TuningPage) -> bool:
        values = self.local_tune_edit_service.get_scalar_values_dict()
        arrays = self.definition.output_channel_arrays if self.definition is not None else None
        if not self.visibility_expression_service.evaluate(page.visibility_expression, values, arrays):
            return False
        return self._is_page_family_relevant(page, values)

    @staticmethod
    def _scalar_value(values: dict[str, float], name: str) -> int:
        return int(values.get(name, 0.0))

    def _is_page_family_relevant(self, page: TuningPage, values: dict[str, float]) -> bool:
        family = self._page_families_by_page_id.get(page.page_id)
        if family is None:
            return True
        title = page.title.lower()
        if family.family_id != "fuel-trims":
            return True
        inj_layout = self._scalar_value(values, "injLayout")
        n_cylinders = self._scalar_value(values, "nCylinders")
        n_fuel_channels = self._scalar_value(values, "nFuelChannels")
        fuel_trim_enabled = self._scalar_value(values, "fuelTrimEnabled")
        sequential_available = inj_layout == 3 and n_cylinders > 0 and n_cylinders <= max(n_fuel_channels, 0)
        if not sequential_available:
            return False
        if "settings" in title:
            return True
        if not fuel_trim_enabled:
            return False
        if "seq 1-4" in title or "sequential fuel trim (1-4)" in title:
            return n_cylinders >= 2
        if "seq 5-8" in title or "sequential fuel trim (5-8)" in title:
            return n_fuel_channels >= 5 and n_cylinders >= 5
        if "fuel trim table" in title:
            suffix = title.rsplit(" ", 1)[-1]
            try:
                channel = int(suffix)
            except ValueError:
                return False
            return n_cylinders >= max(2, channel) and n_fuel_channels >= channel
        return True

    def _related_pages_snapshot(self, page: TuningPage) -> dict[str, object]:
        family = self._page_families_by_page_id.get(page.page_id)
        if family is None:
            return {
                "page_family_id": None,
                "page_family_title": None,
                "related_pages_title": None,
                "related_pages": (),
            }
        return {
            "page_family_id": family.family_id,
            "page_family_title": family.title,
            "related_pages_title": family.title,
            "related_pages": self._visible_family_related_pages(family),
        }

    def _table_page_snapshot(self, page: TuningPage) -> TablePageSnapshot:
        validation = self._validation(page)
        diff = self._diff(page)
        state = self._page_state(page, validation)
        auxiliary_sections = self.scalar_page_editor_service.build_sections(page, self.local_tune_edit_service)
        details = list(self._validation_lines(validation))
        if not details and state.kind.value == "invalid":
            details.append(f"Page: {page.page_number if page.page_number is not None else 'n/a'}")
            details.append(f"Source: {page.source}")
        model = self._active_table_model(page)
        ctx = self._table_context(page)
        if model is None:
            return TablePageSnapshot(
                page_id=page.page_id,
                group_id=page.group_id,
                title=page.title,
                state=state,
                summary=page.summary,
                validation_summary=validation.summary,
                diff_summary=diff.summary,
                diff_text=diff.detail_text,
                diff_entries=diff.entries,
                axis_summary=self._axis_summary(page),
                details_text="\n".join(details),
                help_topic=page.help_topic,
                x_parameter_name=page.x_axis_name,
                y_parameter_name=page.y_axis_name,
                x_labels=tuple(),
                y_labels=tuple(),
                table_model=None,
                auxiliary_sections=auxiliary_sections,
                can_undo=False,
                can_redo=False,
                **ctx,
                message="No tune values available for this page table.",
                **self._related_pages_snapshot(page),
                evidence_hints=tuple(name for name in page.parameter_names if name),
            )

        x_labels = tuple(self._axis_labels(page.x_axis_name, model.columns))
        y_labels = tuple(self._axis_labels(page.y_axis_name, model.rows))
        return TablePageSnapshot(
            page_id=page.page_id,
            group_id=page.group_id,
            title=page.title,
            state=state,
            summary=page.summary,
            validation_summary=validation.summary,
            diff_summary=diff.summary,
            diff_text=diff.detail_text,
            diff_entries=diff.entries,
            axis_summary=self._axis_summary(page),
            details_text="\n".join(details),
            help_topic=page.help_topic,
            x_parameter_name=page.x_axis_name,
            y_parameter_name=page.y_axis_name,
            x_labels=x_labels,
            y_labels=y_labels,
            table_model=model,
            auxiliary_sections=auxiliary_sections,
            can_undo=bool(page.table_name and self.local_tune_edit_service.can_undo(page.table_name)),
            can_redo=bool(page.table_name and self.local_tune_edit_service.can_redo(page.table_name)),
            **ctx,
            **self._related_pages_snapshot(page),
            evidence_hints=tuple(name for name in page.parameter_names if name),
        )

    def _curve_page_snapshot(self, page: TuningPage) -> CurvePageSnapshot:
        from tuner.domain.tuning_pages import TuningPageParameterRole
        x_params = [p for p in page.parameters if p.role == TuningPageParameterRole.X_AXIS]
        y_params = [p for p in page.parameters if p.role == TuningPageParameterRole.Y_AXIS]

        x_param = x_params[0] if x_params else None
        x_values: list[float] = []
        if x_param is not None:
            tv = self.local_tune_edit_service.get_value(x_param.name)
            if tv is not None and isinstance(tv.value, list):
                x_values = [float(v) for v in tv.value]

        y_values: list[list[float]] = []
        for yp in y_params:
            tv = self.local_tune_edit_service.get_value(yp.name)
            if tv is not None and isinstance(tv.value, list):
                y_values.append([float(v) for v in tv.value])
            else:
                y_values.append([])

        n_rows = len(x_values)
        rows: list[CurveRowSnapshot] = []
        for i in range(n_rows):
            x_display = self._curve_format(x_values[i], x_param.digits if x_param else None)
            y_displays = tuple(
                self._curve_format(yv[i] if i < len(yv) else 0.0, yp.digits)
                for yp, yv in zip(y_params, y_values)
            )
            is_staged = tuple(
                yp.name in self.local_tune_edit_service.staged_values
                for yp in y_params
            )
            rows.append(CurveRowSnapshot(index=i, x_display=x_display, y_displays=y_displays, is_staged=is_staged))

        diff = self._diff(page)
        can_undo = any(self.local_tune_edit_service.can_undo(yp.name) for yp in y_params)
        can_redo = any(self.local_tune_edit_service.can_redo(yp.name) for yp in y_params)

        return CurvePageSnapshot(
            page_id=page.page_id,
            title=page.title,
            state=self._page_state(page),
            summary=page.summary,
            help_topic=page.help_topic,
            x_param_name=x_param.name if x_param else None,
            x_label=page.x_axis_label or (x_param.label if x_param else "X"),
            x_units=x_param.units or "" if x_param else "",
            x_channel=page.curve_x_channel,
            y_param_names=tuple(p.name for p in y_params),
            y_labels=tuple(p.label for p in y_params),
            y_units=tuple(p.units or "" for p in y_params),
            rows=tuple(rows),
            can_undo=can_undo,
            can_redo=can_redo,
            diff_entries=diff.entries,
            diff_summary=diff.summary,
        )

    @staticmethod
    def _curve_format(value: float, digits: int | None) -> str:
        if digits is not None and digits >= 0:
            return f"{value:.{digits}f}"
        # Trim unnecessary trailing zeros for a clean display
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return text if text else "0"

    def _parameter_page_snapshot(self, page: TuningPage) -> ParameterPageSnapshot:
        validation = self._validation(page)
        diff = self._diff(page)
        rows = tuple(self._parameter_row(parameter) for parameter in page.parameters)
        sections = self.scalar_page_editor_service.build_sections(page, self.local_tune_edit_service)
        selected_name = self.active_page_parameter_name
        if selected_name not in {row.name for row in rows}:
            selected_name = rows[0].name if rows else None
            self.active_page_parameter_name = selected_name
        details_text = self._parameter_details_text(page, selected_name, validation)
        scalar_names = [p.name for p in page.parameters if p.kind == "scalar"]
        can_undo = any(self.local_tune_edit_service.can_undo(n) for n in scalar_names)
        can_redo = any(self.local_tune_edit_service.can_redo(n) for n in scalar_names)
        page_written = tuple(
            (name, val)
            for name, val in self._written_values.items()
            if name in {p.name for p in page.parameters}
        )
        any_power_cycle = any(p.requires_power_cycle for p in page.parameters)
        actual_group_id = self._actual_group_id(page.page_id)
        page_hw_issues = tuple(
            issue for issue in self._hardware_issues()
            if issue.parameter_name is None or issue.parameter_name in {p.name for p in page.parameters}
        ) if actual_group_id == "hardware_setup" else ()
        hardware_pages = tuple(
            candidate
            for group in self.page_groups
            if group.group_id == "hardware_setup" or any(
                self.hardware_setup_summary_service.build_page_cards(
                    group_page,
                    self.local_tune_edit_service,
                )
                for group_page in group.pages
            )
            for candidate in group.pages
        )
        generator_context: GeneratorInputContext | None = None
        if actual_group_id == "hardware_setup" and hardware_pages:
            generator_context = self.hardware_setup_generator_context_service.build(
                hardware_pages,
                self.local_tune_edit_service,
                operator_context=self.operator_engine_context_service.get(),
            )
        cross_validation_items = (
            self._cross_validate_ignition_trigger(page, hardware_pages)
            or self._cross_validate_sensor(page, hardware_pages)
        )
        hardware_cards = self.hardware_setup_summary_service.build_page_cards(
            page,
            self.local_tune_edit_service,
            issues=page_hw_issues,
            available_pages=hardware_pages,
            generator_context=generator_context,
            cross_validation_items=cross_validation_items,
        )
        return ParameterPageSnapshot(
            page_id=page.page_id,
            group_id=page.group_id,
            title=page.title,
            state=self._page_state(page, validation),
            summary=page.summary,
            validation_summary=validation.summary,
            diff_summary=diff.summary,
            diff_text=diff.detail_text,
            diff_entries=diff.entries,
            help_topic=page.help_topic,
            rows=rows,
            sections=sections,
            selected_name=selected_name,
            details_text=details_text,
            can_undo=can_undo,
            can_redo=can_redo,
            written_values=page_written,
            hardware_issues=page_hw_issues,
            hardware_cards=hardware_cards,
            any_requires_power_cycle=any_power_cycle,
            generator_context=generator_context,
            calculator_snapshot=self._req_fuel_calculator_snapshot(page, generator_context),
            **self._related_pages_snapshot(page),
            evidence_hints=tuple(name for name in page.parameter_names if name),
        )

    def _req_fuel_calculator_snapshot(
        self,
        page: TuningPage,
        generator_context: GeneratorInputContext | None,
    ) -> RequiredFuelCalculatorSnapshot | None:
        """Build a reqFuel calculator snapshot for injector pages; None for all others."""
        if generator_context is None:
            return None
        # Only produce the snapshot on injector pages.
        page_haystack = " ".join(
            f"{p.name} {p.label}".lower() for p in page.parameters
        )
        is_injector_page = any(
            kw in page_haystack for kw in ("injector", "reqfuel", "deadtime", "injopen")
        )
        if not is_injector_page:
            return None

        operator_ctx = self.operator_engine_context_service.get()
        displacement = generator_context.displacement_cc
        cylinder_count = generator_context.cylinder_count
        injector_flow = generator_context.injector_flow_ccmin
        target_afr = generator_context.stoich_ratio or 14.7

        missing: list[str] = []
        if not displacement:
            missing.append("Engine displacement (enter in operator context)")
        if not cylinder_count:
            missing.append("Cylinder count")
        if not injector_flow:
            missing.append("Injector flow rate")

        result: RequiredFuelResult | None = None
        if not missing:
            result = RequiredFuelCalculatorService().calculate(
                displacement_cc=displacement,  # type: ignore[arg-type]
                cylinder_count=cylinder_count,  # type: ignore[arg-type]
                injector_flow_ccmin=injector_flow,  # type: ignore[arg-type]
                target_afr=target_afr,
            )
            if not result.is_valid:
                result = None

        req_fuel_param_exists = any(
            "reqfuel" in f"{p.name} {p.label}".lower() for p in page.parameters
        )
        can_apply = result is not None and req_fuel_param_exists

        return RequiredFuelCalculatorSnapshot(
            displacement_cc=displacement,
            cylinder_count=cylinder_count,
            injector_flow_ccmin=injector_flow,
            target_afr=target_afr,
            result=result,
            missing_inputs=tuple(missing),
            can_apply=can_apply,
        )

    def _catalog_snapshot(self) -> CatalogSnapshot:
        filtered = self.parameter_catalog_service.filter_catalog(self.parameter_catalog_entries, self.catalog_query)
        if self.catalog_kind == "Scalars":
            filtered = [entry for entry in filtered if entry.kind == "scalar"]
        elif self.catalog_kind == "Tables / Maps":
            filtered = [entry for entry in filtered if entry.kind == "table"]
        elif self.catalog_kind == "Tune Only":
            filtered = [entry for entry in filtered if entry.data_type == "tune-only"]

        selected_name = self.catalog_selected_name
        if selected_name not in {entry.name for entry in filtered}:
            selected_name = filtered[0].name if filtered else None
            self.catalog_selected_name = selected_name
        return CatalogSnapshot(
            entries=tuple(filtered),
            selected_name=selected_name,
            details_text=self._catalog_details_text(selected_name),
        )

    def _catalog_details_text(self, name: str | None) -> str:
        if not name:
            return "No parameters loaded."
        entry = next((entry for entry in self.parameter_catalog_entries if entry.name == name), None)
        if entry is None:
            return "No parameters loaded."
        return "\n".join(
            [
                f"Name: {entry.name}",
                f"Kind: {entry.kind}",
                f"Page: {entry.page if entry.page is not None else 'n/a'}",
                f"Offset: {entry.offset if entry.offset is not None else 'n/a'}",
                f"Units: {entry.units or 'n/a'}",
                f"Data Type: {entry.data_type}",
                f"Shape: {entry.shape}",
                f"Tune Present: {'yes' if entry.tune_present else 'no'}",
                f"Tune Preview: {entry.tune_preview or 'n/a'}",
            ]
        )

    def _parameter_row(self, parameter: TuningPageParameter) -> ParameterPageRowSnapshot:
        value = self.local_tune_edit_service.get_value(parameter.name)
        preview = self.parameter_catalog_service._preview_value(value.value if value is not None else None)
        return ParameterPageRowSnapshot(
            name=parameter.name,
            label=parameter.label,
            kind=parameter.kind,
            role=parameter.role.value,
            units=parameter.units,
            data_type=parameter.data_type,
            shape=parameter.shape,
            preview=preview,
            is_staged=self.local_tune_edit_service.is_dirty(parameter.name),
            is_editable=parameter.kind == "scalar",
            min_value=parameter.min_value,
            max_value=parameter.max_value,
        )

    def _parameter_details_text(
        self,
        page: TuningPage,
        selected_name: str | None,
        validation: TuningPageValidationResult,
    ) -> str:
        if not selected_name:
            return "This page has no definition-backed parameters."
        parameter = next((item for item in page.parameters if item.name == selected_name), None)
        if parameter is None:
            return "Select a parameter to inspect it."
        value = self.local_tune_edit_service.get_value(parameter.name)
        lines = [
            f"Name: {parameter.name}",
            f"Label: {parameter.label}",
            f"Kind: {parameter.kind}",
            f"Role: {parameter.role.value}",
            f"Page: {parameter.page if parameter.page is not None else 'n/a'}",
            f"Offset: {parameter.offset if parameter.offset is not None else 'n/a'}",
            f"Units: {parameter.units or 'n/a'}",
            f"Data Type: {parameter.data_type}",
            f"Shape: {parameter.shape}",
            f"Bounds: {parameter.min_value if parameter.min_value is not None else 'n/a'} -> {parameter.max_value if parameter.max_value is not None else 'n/a'}",
            f"Requires Power Cycle: {'yes' if parameter.requires_power_cycle else 'no'}",
            f"Staged: {'yes' if self.local_tune_edit_service.is_dirty(parameter.name) else 'no'}",
            f"Preview: {self.parameter_catalog_service._preview_value(value.value if value is not None else None) or 'n/a'}",
            f"Help: {parameter.help_text or 'n/a'}",
            "",
            f"Page Summary: {page.summary}",
        ]
        lines.extend(self._validation_lines(validation))
        return "\n".join(lines)

    def _page_state(self, page: TuningPage, validation: TuningPageValidationResult | None = None) -> TuningPageState:
        error = self.page_errors.get(page.page_id)
        if error:
            return TuningPageState(kind=TuningPageStateKind.INVALID, detail=error)
        validation = validation or self._validation(page)
        if validation.errors:
            return TuningPageState(kind=TuningPageStateKind.INVALID, detail=validation.errors[0])
        dirty_names = {name for name in page.parameter_names if self.local_tune_edit_service.is_dirty(name)}
        if dirty_names:
            if dirty_names.issubset(self._written_values):
                return TuningPageState(kind=TuningPageStateKind.WRITTEN)
            return TuningPageState(kind=TuningPageStateKind.STAGED)
        return TuningPageState(kind=TuningPageStateKind.CLEAN)

    def _validation(self, page: TuningPage) -> TuningPageValidationResult:
        return self.tuning_page_validation_service.validate_page(page, self.local_tune_edit_service)

    def _diff(self, page: TuningPage) -> TuningPageDiffResult:
        return self.tuning_page_diff_service.build_page_diff(page, self.local_tune_edit_service)

    @staticmethod
    def _validation_lines(validation: TuningPageValidationResult) -> list[str]:
        lines = [f"Validation: {validation.summary}"]
        if validation.errors:
            lines.extend(f"Error: {message}" for message in validation.errors)
        if validation.warnings:
            lines.extend(f"Warning: {message}" for message in validation.warnings)
        return lines

    def _axis_summary(self, page: TuningPage) -> str:
        return (
            f"X Axis: {page.x_axis_label or page.x_axis_name or 'n/a'} | "
            f"Y Axis: {page.y_axis_label or page.y_axis_name or 'n/a'}"
        )

    def _table_context(self, page: TuningPage) -> dict:
        """Extract axis/table context fields for TablePageSnapshot."""
        params_by_name = {p.name: p for p in page.parameters}
        z_param = params_by_name.get(page.table_name) if page.table_name else None
        x_param = params_by_name.get(page.x_axis_name) if page.x_axis_name else None
        y_param = params_by_name.get(page.y_axis_name) if page.y_axis_name else None

        def _range(p: TuningPageParameter | None) -> tuple[float, float] | None:
            if p is None or p.min_value is None or p.max_value is None:
                return None
            return (p.min_value, p.max_value)

        any_rpc = any(
            p.requires_power_cycle
            for p in (z_param, x_param, y_param)
            if p is not None
        )
        return dict(
            z_help=z_param.help_text if z_param else None,
            x_help=x_param.help_text if x_param else None,
            y_help=y_param.help_text if y_param else None,
            z_range=_range(z_param),
            x_range=_range(x_param),
            y_range=_range(y_param),
            any_requires_power_cycle=any_rpc,
        )

    def _axis_labels(self, parameter_name: str | None, expected_count: int) -> list[str]:
        if not parameter_name:
            return [str(index) for index in range(expected_count)]
        tune_value = self.local_tune_edit_service.get_value(parameter_name)
        if tune_value is None or not isinstance(tune_value.value, list):
            return [str(index) for index in range(expected_count)]
        labels = [str(item) for item in tune_value.value[:expected_count]]
        if len(labels) < expected_count:
            labels.extend(str(index) for index in range(len(labels), expected_count))
        return labels

    def _active_table_model(self, page: TuningPage | None) -> TableViewModel | None:
        if page is None or not page.table_name:
            return None
        tune_value = self.local_tune_edit_service.get_value(page.table_name)
        if tune_value is None:
            return None
        table_parameter = next((parameter for parameter in page.parameters if parameter.name == page.table_name), None)
        shape = table_parameter.shape if table_parameter is not None else None
        return self.table_view_service.build_table_model(tune_value, shape)

    def _active_page(self) -> TuningPage | None:
        if self.active_page_id is None:
            return None
        return self.pages_by_id.get(self.active_page_id)

    def _default_page_id(self) -> str | None:
        for group in self.page_groups:
            if group.pages:
                return group.pages[0].page_id
        return None

    @staticmethod
    def _default_page_parameter_name(page: TuningPage | None) -> str | None:
        if page is None or not page.parameter_names:
            return None
        if page.table_name:
            scalar_name = next((parameter.name for parameter in page.parameters if parameter.kind == "scalar"), None)
            return scalar_name or page.table_name
        return page.parameter_names[0]

    def _reload_catalog(self) -> None:
        self.parameter_catalog_entries = self.parameter_catalog_service.build_catalog(
            self.definition,
            self.tune_file,
            staged_values=self.local_tune_edit_service.staged_values,
        )

    def _sync_catalog_selection(self) -> None:
        if self.catalog_selected_name is not None:
            return
        page = self._active_page()
        if page is not None and page.table_name:
            self.catalog_selected_name = page.table_name
        elif self.active_page_parameter_name is not None:
            self.catalog_selected_name = self.active_page_parameter_name

    def _operation_log_snapshot(self) -> OperationLogSnapshot:
        entries = self.operation_log_service.entries()
        staged_names = set(self.local_tune_edit_service.staged_values.keys())
        has_unwritten = bool(staged_names - set(self._written_values))
        evidence = self.operation_evidence_service.build(
            entries=entries,
            has_unwritten=has_unwritten,
        )
        return OperationLogSnapshot(
            summary_text=evidence.summary_text,
            entry_count=len(entries),
            has_unwritten=has_unwritten,
            session_count=evidence.session_count,
            latest_write_text=evidence.latest_write_entry.summary_line() if evidence.latest_write_entry is not None else None,
            latest_burn_text=evidence.latest_burn_entry.summary_line() if evidence.latest_burn_entry is not None else None,
        )

    def _workspace_review_snapshot(self) -> WorkspaceReviewSnapshot:
        page_titles = self._page_titles_by_parameter()
        entries = tuple(
            self.staged_change_service.summarize(
                self.local_tune_edit_service,
                page_titles=page_titles,
                written_names=set(self._written_values),
            )
        )
        if not entries:
            summary = "No staged changes across the workspace."
        else:
            unwritten = sum(1 for entry in entries if not entry.is_written)
            written = len(entries) - unwritten
            summary = f"{len(entries)} staged change{'s' if len(entries) != 1 else ''} across the workspace."
            if unwritten:
                summary += f" {unwritten} not yet written to RAM."
            elif written:
                summary += " All staged values have been written to RAM."
        return WorkspaceReviewSnapshot(summary_text=summary, entries=entries)

    def _page_titles_by_parameter(self) -> dict[str, str]:
        titles: dict[str, str] = {}
        for group in self.page_groups:
            for page in group.pages:
                for name in page.parameter_names:
                    titles.setdefault(name, page.title)
        return titles

    def _value_text(self, name: str) -> str:
        tv = self.local_tune_edit_service.get_value(name)
        if tv is None:
            return ""
        if isinstance(tv.value, list):
            return ", ".join(str(v) for v in tv.value[:4])
        return str(tv.value)
