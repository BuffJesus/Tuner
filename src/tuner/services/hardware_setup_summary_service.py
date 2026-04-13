from __future__ import annotations

from dataclasses import dataclass
import re

from tuner.domain.generator_context import GeneratorInputContext
from tuner.domain.hardware_setup import HardwareIssueSeverity, HardwareSetupIssue
from tuner.domain.setup_checklist import ChecklistItemStatus, SetupChecklistItem
from tuner.domain.tuning_pages import TuningPage, TuningPageParameter
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.visibility_expression_service import VisibilityExpressionService


@dataclass(slots=True, frozen=True)
class HardwareSetupCardSnapshot:
    key: str
    title: str
    summary: str
    detail_lines: tuple[str, ...]
    links: tuple[tuple[str, str], ...] = ()
    severity: str = "info"


class HardwareSetupSummaryService:
    def __init__(
        self,
        visibility_expression_service: VisibilityExpressionService | None = None,
    ) -> None:
        self._visibility = visibility_expression_service or VisibilityExpressionService()

    def build_page_cards(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        issues: tuple[HardwareSetupIssue, ...] = (),
        available_pages: tuple[TuningPage, ...] = (),
        generator_context: GeneratorInputContext | None = None,
        cross_validation_items: tuple[SetupChecklistItem, ...] = (),
    ) -> tuple[HardwareSetupCardSnapshot, ...]:
        page_kind = self._page_kind(page)
        if page.group_id != "hardware_setup" and page_kind is None:
            return ()

        page_issues = tuple(
            issue
            for issue in issues
            if issue.parameter_name is None or issue.parameter_name in set(page.parameter_names)
        )
        cards: list[HardwareSetupCardSnapshot] = []

        primary = self._build_primary_card(
            page_kind,
            page,
            local_tune_edit_service,
            available_pages=available_pages,
        )
        if primary is not None:
            cards.append(primary)

        safety = self._build_safety_card(page, page_issues)
        if safety is not None:
            cards.append(safety)

        guidance = self._build_guidance_card(
            page_kind,
            page,
            local_tune_edit_service,
            page_issues,
            available_pages=available_pages,
        )
        if guidance is not None:
            cards.append(guidance)

        gated = self._build_gated_followups_card(
            page_kind,
            page,
            local_tune_edit_service,
            available_pages=available_pages,
        )
        if gated is not None:
            cards.append(gated)

        if generator_context is not None and page_kind is not None:
            readiness = self._build_readiness_card(page_kind, generator_context)
            if readiness is not None:
                cards.append(readiness)

        if cross_validation_items:
            xval = self._build_cross_validation_card(cross_validation_items)
            if xval is not None:
                cards.append(xval)

        return tuple(cards)

    def _build_primary_card(
        self,
        page_kind: str | None,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> HardwareSetupCardSnapshot | None:
        if page_kind == "injector":
            return self._build_injector_card(page, local_tune_edit_service, available_pages=available_pages)
        if page_kind == "trigger":
            return self._build_trigger_card(page, local_tune_edit_service, available_pages=available_pages)
        if page_kind == "ignition":
            return self._build_ignition_card(page, local_tune_edit_service, available_pages=available_pages)
        if page_kind == "sensor":
            return self._build_sensor_card(page, local_tune_edit_service, available_pages=available_pages)
        return None

    def _build_guidance_card(
        self,
        page_kind: str | None,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        page_issues: tuple[HardwareSetupIssue, ...],
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> HardwareSetupCardSnapshot | None:
        if page_kind is None:
            return None
        builders = {
            "injector": self._injector_guidance_lines,
            "ignition": self._ignition_guidance_lines,
            "trigger": self._trigger_guidance_lines,
            "sensor": self._sensor_guidance_lines,
        }
        details = list(builders[page_kind](page, local_tune_edit_service, available_pages=available_pages))
        if page_issues:
            details.insert(0, "Resolve current warnings and errors on this page before write or burn.")
        if not details:
            return None
        titles = {
            "injector": "Injector Checklist",
            "ignition": "Ignition Checklist",
            "trigger": "Trigger Checklist",
            "sensor": "Sensor Checklist",
        }
        summaries = {
            "injector": "Verify injector data against the actual fuel system before first start.",
            "ignition": "Confirm ignition wiring, dwell, and timing checks before powering coils.",
            "trigger": "Confirm wheel geometry and timing references before running under load.",
            "sensor": "Confirm sensor types and calibrations before trusting logs or autotune.",
        }
        severity = "warning" if page_issues else "info"
        return HardwareSetupCardSnapshot(
            key=f"{page_kind}_checklist",
            title=titles[page_kind],
            summary=summaries[page_kind],
            detail_lines=tuple(details),
            links=self._card_links(page_kind, page, local_tune_edit_service, available_pages=available_pages),
            severity=severity,
        )

    def _build_gated_followups_card(
        self,
        page_kind: str | None,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> HardwareSetupCardSnapshot | None:
        if page_kind is None:
            return None
        details = self._gated_followup_lines(page_kind, page, local_tune_edit_service, available_pages=available_pages)
        if not details:
            return None
        return HardwareSetupCardSnapshot(
            key=f"{page_kind}_gated_followups",
            title="Hidden Follow-Ups",
            summary="Some related settings exist but may still be hidden until prerequisite options are enabled.",
            detail_lines=details,
            links=self._card_links(page_kind, page, local_tune_edit_service, available_pages=available_pages, gated_only=True),
            severity="info",
        )

    def _build_injector_card(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> HardwareSetupCardSnapshot:
        flow = self._line_for(page, local_tune_edit_service, ("injectorflow", "injflow", "flow"))
        dead_time = self._line_for(page, local_tune_edit_service, ("deadtime", "injopen", "opentime"))
        req_fuel = self._line_for(page, local_tune_edit_service, ("reqfuel",))
        staging = self._line_for(page, local_tune_edit_service, ("staging", "injectorcount", "injcount"))
        companion_lines = tuple(
            line
            for line in (
                self._companion_status_line(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("deadtime", "injopen", "opentime"),
                    "Injector dead time",
                ),
                self._companion_status_line(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("reqfuel",),
                    "Required fuel",
                ),
                self._companion_status_line(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("staging", "injectorcount", "injcount"),
                    "Injector count / staging",
                ),
            )
            if line
        )
        details = tuple(line for line in (flow, dead_time, req_fuel, staging, *companion_lines) if line)
        summary = " | ".join(details[:3]) if details else "Review injector flow, dead time, and required fuel before first start."
        return HardwareSetupCardSnapshot(
            key="injector",
            title="Injector Setup",
            summary=summary,
            detail_lines=details or ("No injector-specific scalar summary available on this page.",),
            links=self._card_links("injector", page, local_tune_edit_service, available_pages=available_pages),
        )

    def _build_ignition_card(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> HardwareSetupCardSnapshot:
        mode = self._line_for(page, local_tune_edit_service, ("sparkmode", "ignitionmode", "outputmode", "coil"))
        dwell = self._line_for(page, local_tune_edit_service, ("dwell", "sparkdur"))
        angle = self._line_for(page, local_tune_edit_service, ("timing", "advance", "fixang", "triggerangle"))
        companion_lines: list[str] = []
        reference_angle = self._companion_status_line(
            page,
            available_pages,
            local_tune_edit_service,
            ("timing", "advance", "fixang", "triggerangle"),
            "Reference angle / timing check",
        )
        if reference_angle:
            companion_lines.append(reference_angle)
        if self._feature_enabled(page, local_tune_edit_service, ("knock",)):
            knock_pin = self._companion_status_line(
                page,
                available_pages,
                local_tune_edit_service,
                ("knockpin", "knock_digital", "knock_analog", "knockinput", "knocksensorpin"),
                "Knock input pin",
            )
            if knock_pin:
                companion_lines.append(knock_pin)
        details = tuple(line for line in (mode, dwell, angle, *companion_lines) if line)
        summary = " | ".join(details[:2]) if details else "Verify coil mode, dwell, and timing references before writing."
        return HardwareSetupCardSnapshot(
            key="ignition",
            title="Ignition Setup",
            summary=summary,
            detail_lines=details or ("No ignition-specific scalar summary available on this page.",),
            links=self._card_links("ignition", page, local_tune_edit_service, available_pages=available_pages),
        )

    def _build_trigger_card(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> HardwareSetupCardSnapshot:
        trigger_type = self._line_for(page, local_tune_edit_service, ("triggertype", "decoder", "pattern"))
        teeth_param = self._find_parameter(page, ("nteeth", "toothcount", "triggerteeth", "crankteeth"))
        missing_param = self._find_parameter(page, ("missingteeth", "missingtooth"))
        angle = self._line_for(page, local_tune_edit_service, ("triggerangle", "fixang", "crankangle", "tdcangle"))
        geometry_line = self._trigger_geometry_line(teeth_param, missing_param, local_tune_edit_service)
        companion_lines = tuple(
            line
            for line in (
                self._companion_status_line(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("caminput", "secondtrigger", "cam", "sync"),
                    "Cam / secondary trigger input",
                ),
                self._companion_status_line(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("triggerangle", "fixang", "crankangle", "tdcangle"),
                    "Reference angle",
                ),
            )
            if line
        )
        details = tuple(line for line in (trigger_type, geometry_line, angle, *companion_lines) if line)
        summary = " | ".join(details[:2]) if details else "Verify trigger type, wheel pattern, and reference angle."
        return HardwareSetupCardSnapshot(
            key="trigger",
            title="Trigger Pattern",
            summary=summary,
            detail_lines=details or ("No trigger-specific scalar summary available on this page.",),
            links=self._card_links("trigger", page, local_tune_edit_service, available_pages=available_pages),
        )

    def _build_sensor_card(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> HardwareSetupCardSnapshot:
        ego = self._line_for(page, local_tune_edit_service, ("egotype", "afrsensortype", "o2sensortype", "lambdatype"))
        stoich = self._line_for(page, local_tune_edit_service, ("stoich",))
        count = self._line_for(page, local_tune_edit_service, ("egocount", "sensorcount"))
        calibration = self._line_for(page, local_tune_edit_service, ("afrcal", "widebandcal", "lambdacal", "thermistor", "calibration"))
        companion_lines: list[str] = []
        if self._feature_enabled(
            page,
            local_tune_edit_service,
            ("egotype", "afrsensortype", "o2sensortype", "lambdatype"),
            min_numeric=2.0,
        ):
            wideband_cal = self._companion_status_line(
                page,
                available_pages,
                local_tune_edit_service,
                ("afrcal", "widebandcal", "lambdacal"),
                "Wideband calibration",
            )
            if wideband_cal:
                companion_lines.append(wideband_cal)
        if self._feature_enabled(page, local_tune_edit_service, ("oilpressureenable", "oilpressure", "oilpressuresensor")):
            oil_pin = self._companion_status_line(
                page,
                available_pages,
                local_tune_edit_service,
                ("oilpressurepin", "oilpin", "oilpressuresensorpin"),
                "Oil pressure sensor input pin",
            )
            if oil_pin:
                companion_lines.append(oil_pin)
        if self._feature_enabled(page, local_tune_edit_service, ("useextbaro", "extbaro", "baroenable")):
            baro_pin = self._companion_status_line(
                page,
                available_pages,
                local_tune_edit_service,
                ("baropin", "extbaropin", "externalbaropin", "barosensorpin"),
                "External baro input pin",
            )
            if baro_pin:
                companion_lines.append(baro_pin)
        if self._feature_enabled(page, local_tune_edit_service, ("map", "baro")):
            map_cal = self._companion_status_line(
                page,
                available_pages,
                local_tune_edit_service,
                ("barocal", "mapcal", "calibration", "thermistor"),
                "MAP / baro calibration",
            )
            if map_cal:
                companion_lines.append(map_cal)
        stoich_basis = self._companion_status_line(
            page,
            available_pages,
            local_tune_edit_service,
            ("stoich", "fuel", "ethanol", "flex"),
            "Stoich / fuel basis",
        )
        if stoich_basis:
            companion_lines.append(stoich_basis)
        details = tuple(line for line in (ego, stoich, count, calibration, *companion_lines) if line)
        summary = " | ".join(details[:3]) if details else "Confirm sensor type and calibration before trusting logs or autotune."
        return HardwareSetupCardSnapshot(
            key="sensor",
            title="Sensor Calibration",
            summary=summary,
            detail_lines=details or ("No sensor-specific scalar summary available on this page.",),
            links=self._card_links("sensor", page, local_tune_edit_service, available_pages=available_pages),
        )

    def _build_safety_card(
        self,
        page: TuningPage,
        page_issues: tuple[HardwareSetupIssue, ...],
    ) -> HardwareSetupCardSnapshot | None:
        warning_count = sum(1 for issue in page_issues if issue.severity == HardwareIssueSeverity.WARNING)
        error_count = sum(1 for issue in page_issues if issue.severity == HardwareIssueSeverity.ERROR)
        requires_power_cycle = any(parameter.requires_power_cycle for parameter in page.parameters)
        if not page_issues and not requires_power_cycle:
            return None

        details = [issue.message for issue in page_issues[:3]]
        if requires_power_cycle:
            details.append("Power cycle required after changes on this page.")
        summary_parts: list[str] = []
        if error_count:
            summary_parts.append(f"{error_count} error{'s' if error_count != 1 else ''}")
        if warning_count:
            summary_parts.append(f"{warning_count} warning{'s' if warning_count != 1 else ''}")
        if requires_power_cycle:
            summary_parts.append("restart required")
        severity = "warning" if error_count or warning_count else "info"
        return HardwareSetupCardSnapshot(
            key="safety",
            title="Change Safety",
            summary=", ".join(summary_parts) if summary_parts else "Review restart requirements before applying changes.",
            detail_lines=tuple(details),
            severity=severity,
        )

    @staticmethod
    def _build_readiness_card(
        page_kind: str,
        generator_context: GeneratorInputContext,
    ) -> HardwareSetupCardSnapshot | None:
        """Build a card showing which generator inputs have been captured and what is still needed."""
        if page_kind == "injector":
            return _injector_readiness_card(generator_context)
        if page_kind == "ignition":
            return _ignition_readiness_card(generator_context)
        if page_kind == "trigger":
            return _trigger_readiness_card(generator_context)
        if page_kind == "sensor":
            return _sensor_readiness_card(generator_context)
        return None

    @staticmethod
    def _build_cross_validation_card(
        items: tuple[SetupChecklistItem, ...],
    ) -> HardwareSetupCardSnapshot | None:
        """Convert structured cross-validation checklist items into a summary card."""
        if not items:
            return None

        status_prefix = {
            ChecklistItemStatus.OK: "[OK]",
            ChecklistItemStatus.INFO: "[Info]",
            ChecklistItemStatus.WARNING: "[Warning]",
            ChecklistItemStatus.ERROR: "[Error]",
            ChecklistItemStatus.NEEDED: "[Needed]",
        }
        unresolved_statuses = (
            ChecklistItemStatus.ERROR,
            ChecklistItemStatus.NEEDED,
            ChecklistItemStatus.WARNING,
        )
        unresolved_items = tuple(item for item in items if item.status in unresolved_statuses)
        configured_items = tuple(item for item in items if item.status not in unresolved_statuses)

        def format_item(item: SetupChecklistItem) -> str:
            cross_page = " (other page)" if item.cross_page else ""
            return f"{status_prefix.get(item.status, '[ ]')} {item.title}{cross_page}: {item.detail}"

        detail_lines_list: list[str] = []
        if unresolved_items:
            detail_lines_list.append("Still needed:")
            detail_lines_list.extend(format_item(item) for item in unresolved_items)
        if configured_items:
            detail_lines_list.append("Configured now:")
            detail_lines_list.extend(format_item(item) for item in configured_items)
        detail_lines = tuple(detail_lines_list)

        has_error = any(item.status == ChecklistItemStatus.ERROR for item in items)
        has_warning = any(item.status in (ChecklistItemStatus.WARNING, ChecklistItemStatus.NEEDED) for item in items)
        severity = "warning" if has_error or has_warning else "info"

        unresolved = len(unresolved_items)
        configured = len(configured_items)
        if unresolved:
            summary = (
                f"{unresolved} item{'s' if unresolved != 1 else ''} still need attention before first start; "
                f"{configured} already configured."
            )
        else:
            summary = f"All cross-setup checks passed ({configured} configured)."

        return HardwareSetupCardSnapshot(
            key="ignition_trigger_cross_check",
            title="Ignition / Trigger Cross-Check",
            summary=summary,
            detail_lines=detail_lines,
            severity=severity,
        )

    def _line_for(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        keywords: tuple[str, ...],
    ) -> str | None:
        parameter = self._find_parameter(page, keywords)
        if parameter is None:
            return None
        value = self._display_value(parameter, local_tune_edit_service)
        if not value:
            return None
        return f"{self._friendly_label(parameter)}: {value}"

    @staticmethod
    def _trigger_geometry_line(
        teeth_param: TuningPageParameter | None,
        missing_param: TuningPageParameter | None,
        local_tune_edit_service: LocalTuneEditService,
    ) -> str | None:
        if teeth_param is None or missing_param is None:
            return None
        teeth = local_tune_edit_service.get_value(teeth_param.name)
        missing = local_tune_edit_service.get_value(missing_param.name)
        if teeth is None or missing is None:
            return None
        if not isinstance(teeth.value, (int, float)) or not isinstance(missing.value, (int, float)):
            return None
        return f"Wheel: {int(teeth.value)}-{int(missing.value)}"

    @staticmethod
    def _find_parameter(page: TuningPage, keywords: tuple[str, ...]) -> TuningPageParameter | None:
        lowered = tuple(keyword.lower() for keyword in keywords)
        for parameter in page.parameters:
            haystack = f"{parameter.name} {parameter.label}".lower()
            if any(keyword in haystack for keyword in lowered):
                return parameter
        return None

    @staticmethod
    def _display_value(
        parameter: TuningPageParameter,
        local_tune_edit_service: LocalTuneEditService,
    ) -> str | None:
        tune_value = local_tune_edit_service.get_value(parameter.name)
        if tune_value is None:
            return None
        value = tune_value.value
        if isinstance(value, list):
            return f"{len(value)} values"
        if parameter.options and isinstance(value, (int, float)):
            value_text = str(int(value)) if float(value).is_integer() else str(value)
            option_values = parameter.option_values or tuple(str(index) for index, _ in enumerate(parameter.options))
            for label, option_value in zip(parameter.options, option_values):
                if option_value == value_text:
                    return label
            option_index = int(value)
            if 0 <= option_index < len(parameter.options):
                return parameter.options[option_index]
        if isinstance(value, float):
            text = f"{value:.3f}".rstrip("0").rstrip(".")
        else:
            text = str(value)
        if parameter.units:
            return f"{text} {parameter.units}"
        return text

    @staticmethod
    def _page_haystack(page: TuningPage) -> str:
        return " ".join(
            [page.title, page.summary, *(parameter.name for parameter in page.parameters), *(parameter.label for parameter in page.parameters)]
        ).lower()

    @staticmethod
    def _friendly_label(parameter: TuningPageParameter) -> str:
        raw = parameter.label or parameter.name
        if raw and raw != parameter.name:
            return raw
        known = {
            "injectorflow": "Injector Flow Rate",
            "injflow": "Injector Flow Rate",
            "deadtime": "Dead Time",
            "injopen": "Injector Dead Time",
            "opentime": "Injector Open Time",
            "reqfuel": "Required Fuel",
            "sparkmode": "Spark Mode",
            "ignitionmode": "Ignition Mode",
            "sparkdur": "Spark Duration",
            "triggertype": "Trigger Type",
            "fixang": "Trigger Angle",
            "egoType": "EGO sensor type",
            "egotype": "EGO sensor type",
            "afrsensortype": "AFR sensor type",
            "o2sensortype": "O2 sensor type",
            "lambdatype": "Lambda sensor type",
            "stoich": "Stoich",
        }
        lowered = parameter.name.lower()
        if lowered in known:
            return known[lowered]
        spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", parameter.name.replace("_", " "))
        return spaced[:1].upper() + spaced[1:]

    def _page_kind(self, page: TuningPage) -> str | None:
        haystack = self._page_haystack(page)
        if any(keyword in haystack for keyword in ("injector", "reqfuel", "deadtime", "injopen")):
            return "injector"
        if any(keyword in haystack for keyword in ("trigger", "decoder", "tooth", "sync")):
            return "trigger"
        if any(keyword in haystack for keyword in ("spark", "ignition", "coil", "dwell", "timing")):
            return "ignition"
        if any(keyword in haystack for keyword in ("sensor", "thermistor", "ego", "lambda", "afr", "map", "clt", "iat", "baro")):
            return "sensor"
        return None

    def _injector_guidance_lines(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> tuple[str, ...]:
        lines = [self._guidance_review("Confirm injector flow matches rated pressure and injector size.")]
        if self._find_parameter(page, ("deadtime", "injopen", "opentime")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("deadtime", "injopen", "opentime"),
                    "Find injector dead time/open time before first start.",
                )
            )
        else:
            lines.append(self._guidance_review("Recheck injector dead time whenever injector hardware or voltage compensation data changes."))
        if self._find_parameter(page, ("reqfuel",)) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("reqfuel",),
                    "Verify required fuel before writing changes.",
                )
            )
        else:
            lines.append(self._guidance_action("Recalculate required fuel after engine-size, injector, or fuel changes."))
        if self._find_parameter(page, ("staging", "injectorcount", "injcount")) is not None:
            lines.append(self._guidance_review("Confirm injector count or staging matches the installed wiring strategy."))
        dead_time = self._find_parameter(page, ("deadtime", "injopen", "opentime"))
        if dead_time is not None:
            dead_time_value = self._numeric_value(dead_time, local_tune_edit_service)
            if dead_time_value == 0.0:
                lines.append(self._guidance_caution("Dead time is currently zero; verify injector latency data before relying on fueling."))
        return tuple(lines)

    def _ignition_guidance_lines(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> tuple[str, ...]:
        lines = [self._guidance_review("Confirm spark output mode matches the actual coil driver wiring.")]
        if self._find_parameter(page, ("dwell", "sparkdur")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("dwell", "sparkdur"),
                    "Review dwell or spark duration before enabling coils.",
                )
            )
        else:
            lines.append(self._guidance_review("Verify dwell against the coil datasheet before long key-on testing."))
        if self._find_parameter(page, ("timing", "advance", "fixang", "triggerangle")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("timing", "advance", "fixang", "triggerangle"),
                    "Check the trigger/reference-angle settings before timing verification.",
                )
            )
        if self._feature_enabled(page, local_tune_edit_service, ("knock",)):
            if self._find_parameter(page, ("knockpin", "knockinput", "knocksensorpin")) is None:
                lines.append(
                    self._cross_page_prompt(
                        page,
                        available_pages,
                        local_tune_edit_service,
                        ("knockpin", "knockinput", "knocksensorpin"),
                        "Knock-related settings are enabled; verify knock input pin and sensor wiring.",
                    )
                )
        lines.append(self._guidance_action("Use a timing light after changes before running the engine under load."))
        return tuple(lines)

    def _trigger_guidance_lines(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> tuple[str, ...]:
        lines = [self._guidance_review("Confirm wheel tooth count and missing-tooth pattern match the physical trigger wheel.")]
        if self._find_parameter(page, ("triggertype", "decoder", "pattern")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("triggertype", "decoder", "pattern"),
                    "Review decoder or trigger type before burning changes.",
                )
            )
        if self._find_parameter(page, ("missingteeth", "missingtooth")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("missingteeth", "missingtooth", "caminput", "secondtrigger"),
                    "Review missing-tooth or secondary-trigger settings if this page does not expose them directly.",
                )
            )
        if self._find_parameter(page, ("triggerangle", "fixang", "crankangle", "tdcangle")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("triggerangle", "fixang", "crankangle", "tdcangle"),
                    "Find the reference-angle setting before doing timing-light verification.",
                )
            )
        elif self._numeric_value(
            self._find_parameter(page, ("triggerangle", "fixang", "crankangle", "tdcangle")),
            local_tune_edit_service,
        ) == 0.0:
            lines.append(self._guidance_caution("Reference angle is currently zero; confirm that is intentional with a timing light."))
        lines.append(self._guidance_action("Use a timing light to confirm reference angle before any loaded pulls."))
        return tuple(lines)

    def _sensor_guidance_lines(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> tuple[str, ...]:
        lines = [self._guidance_review("Confirm each sensor type matches the installed hardware, not just the default tune.")]
        calibration = self._find_parameter(page, ("afrcal", "widebandcal", "lambdacal", "thermistor", "calibration"))
        if calibration is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("afrcal", "widebandcal", "lambdacal", "thermistor", "calibration"),
                    "Find the AFR or thermistor calibration settings before trusting logs or autotune.",
                )
            )
        else:
            lines.append(self._guidance_review("Recheck calibration tables after sensor or wiring changes."))
        if self._feature_enabled(page, local_tune_edit_service, ("egotype", "afrsensortype", "o2sensortype", "lambdatype"), min_numeric=2.0) and calibration is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("afrcal", "widebandcal", "lambdacal"),
                    "Wideband is enabled here, but no calibration setting is visible on this page.",
                )
            )
        if self._feature_enabled(page, local_tune_edit_service, ("map", "baro")) and self._find_parameter(page, ("calibration", "thermistor", "barocal", "mapcal")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("barocal", "mapcal", "calibration", "thermistor"),
                    "MAP or baro-related settings are present; verify sensor calibration and range.",
                )
            )
        if self._feature_enabled(page, local_tune_edit_service, ("oilpressureenable", "oilpressure", "oilpressuresensor")) and self._find_parameter(page, ("oilpressurepin", "oilpin", "oilpressuresensorpin")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("oilpressurepin", "oilpin", "oilpressuresensorpin"),
                    "Oil pressure sensing is enabled; verify the analog input pin assignment.",
                )
            )
        if self._feature_enabled(page, local_tune_edit_service, ("useextbaro", "extbaro", "baroenable")) and self._find_parameter(page, ("baropin", "extbaropin", "externalbaropin", "barosensorpin")) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("baropin", "extbaropin", "externalbaropin", "barosensorpin"),
                    "External baro sensing is enabled; verify the baro input pin assignment.",
                )
            )
        if self._find_parameter(page, ("stoich",)) is None:
            lines.append(
                self._cross_page_prompt(
                    page,
                    available_pages,
                    local_tune_edit_service,
                    ("stoich", "fuel", "ethanol", "flex"),
                    "Verify stoich or fuel-type assumptions when changing fuels.",
                )
            )
        return tuple(lines)

    def _gated_followup_lines(
        self,
        page_kind: str,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
    ) -> tuple[str, ...]:
        checks: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
            "injector": (
                (("deadtime", "injopen", "opentime"), "Injector dead time/open time"),
                (("reqfuel",), "Required fuel"),
            ),
            "ignition": (
                (("knockpin", "knock_digital", "knock_analog", "knockinput", "knocksensorpin"), "Knock input pin"),
                (("timing", "advance", "fixang", "triggerangle"), "Reference angle / timing verification setting"),
            ),
            "trigger": (
                (("missingteeth", "missingtooth", "caminput", "secondtrigger"), "Missing-tooth or secondary-trigger setting"),
                (("triggerangle", "fixang", "crankangle", "tdcangle"), "Reference angle setting"),
            ),
            "sensor": (
                (("afrcal", "widebandcal", "lambdacal"), "Wideband calibration"),
                (("barocal", "mapcal", "calibration", "thermistor"), "Sensor calibration / range setting"),
                (("oilpressurepin", "oilpin", "oilpressuresensorpin"), "Oil pressure sensor input pin"),
                (("baropin", "extbaropin", "externalbaropin", "barosensorpin"), "External baro input pin"),
                (("stoich", "fuel", "ethanol", "flex"), "Stoich or fuel-type assumption"),
            ),
        }
        lines: list[str] = []
        for keywords, label in checks.get(page_kind, ()):
            if page_kind == "ignition" and "knock" in label.lower() and not self._feature_enabled(page, local_tune_edit_service, ("knock",)):
                continue
            if page_kind == "sensor" and "oil pressure" in label.lower() and not self._feature_enabled(page, local_tune_edit_service, ("oilpressureenable", "oilpressure", "oilpressuresensor")):
                continue
            if page_kind == "sensor" and "external baro" in label.lower() and not self._feature_enabled(page, local_tune_edit_service, ("useextbaro", "extbaro", "baroenable")):
                continue
            related = self._parameter_location(page, available_pages, local_tune_edit_service, keywords)
            if related is None:
                continue
            related_page, _parameter, is_visible = related
            if is_visible:
                continue
            if related_page.page_id == page.page_id:
                lines.append(f"{label} exists on this page but is currently hidden until prerequisite options are enabled.")
            else:
                lines.append(f"{label} exists on '{related_page.title}' but may remain hidden until prerequisite options are enabled.")
        return tuple(lines)

    def _cross_page_prompt(
        self,
        current_page: TuningPage,
        available_pages: tuple[TuningPage, ...],
        local_tune_edit_service: LocalTuneEditService,
        keywords: tuple[str, ...],
        fallback: str,
    ) -> str:
        related = self._parameter_location(current_page, available_pages, local_tune_edit_service, keywords)
        if related is None:
            return self._guidance_action(fallback)
        related_page, _parameter, is_visible = related
        prefix = "[Action]"
        suffix = f" See '{related_page.title}'."
        if not is_visible:
            prefix = "[Gated]"
            if related_page.page_id == current_page.page_id:
                suffix = " It exists on this page but may still be hidden until prerequisite options are enabled."
            else:
                suffix = f" See '{related_page.title}'; the setting may still be hidden until prerequisite options are enabled."
        return f"{prefix} {fallback}{suffix}"

    @staticmethod
    def _guidance_review(text: str) -> str:
        return f"[Review] {text}"

    @staticmethod
    def _guidance_action(text: str) -> str:
        return f"[Action] {text}"

    @staticmethod
    def _guidance_caution(text: str) -> str:
        return f"[Caution] {text}"

    def _companion_status_line(
        self,
        current_page: TuningPage,
        available_pages: tuple[TuningPage, ...],
        local_tune_edit_service: LocalTuneEditService,
        keywords: tuple[str, ...],
        label: str,
    ) -> str | None:
        current_parameter = self._find_parameter(current_page, keywords)
        if current_parameter is not None:
            values = local_tune_edit_service.get_scalar_values_dict()
            if self._visibility.evaluate(current_parameter.visibility_expression, values):
                return None
            return f"[Gated] {label}: available on this page but currently hidden until prerequisite options are enabled."
        related = self._related_parameter_location(current_page, available_pages, local_tune_edit_service, keywords)
        if related is None:
            return f"[Missing] {label}: not found on known setup pages."
        related_page, _parameter, is_visible = related
        if is_visible:
            return f"[OK] {label}: configured on '{related_page.title}'."
        return f"[Gated] {label}: exists on '{related_page.title}' but is currently gated by prerequisite options."

    def _parameter_location(
        self,
        current_page: TuningPage,
        available_pages: tuple[TuningPage, ...],
        local_tune_edit_service: LocalTuneEditService,
        keywords: tuple[str, ...],
    ) -> tuple[TuningPage, TuningPageParameter, bool] | None:
        current_parameter = self._find_parameter(current_page, keywords)
        if current_parameter is not None:
            values = local_tune_edit_service.get_scalar_values_dict()
            is_visible = self._visibility.evaluate(current_parameter.visibility_expression, values)
            return current_page, current_parameter, is_visible
        return self._related_parameter_location(current_page, available_pages, local_tune_edit_service, keywords)

    def _related_parameter_location(
        self,
        current_page: TuningPage,
        available_pages: tuple[TuningPage, ...],
        local_tune_edit_service: LocalTuneEditService,
        keywords: tuple[str, ...],
    ) -> tuple[TuningPage, TuningPageParameter, bool] | None:
        lowered = tuple(keyword.lower() for keyword in keywords)
        values = local_tune_edit_service.get_scalar_values_dict()
        for candidate in available_pages:
            if candidate.page_id == current_page.page_id and candidate.title == current_page.title:
                continue
            for parameter in candidate.parameters:
                haystack = f"{parameter.name} {parameter.label}".lower()
                if any(keyword in haystack for keyword in lowered):
                    is_visible = self._visibility.evaluate(parameter.visibility_expression, values)
                    return candidate, parameter, is_visible
        return None

    def _feature_enabled(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        keywords: tuple[str, ...],
        *,
        min_numeric: float = 0.5,
    ) -> bool:
        parameter = self._find_parameter(page, keywords)
        if parameter is None:
            return False
        tune_value = local_tune_edit_service.get_value(parameter.name)
        if tune_value is None:
            return False
        value = tune_value.value
        if isinstance(value, (int, float)):
            return float(value) >= min_numeric
        text = str(value).strip().lower()
        return text not in {"", "0", "off", "disabled", "false", "none"}

    def _card_links(
        self,
        page_kind: str,
        current_page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
        *,
        available_pages: tuple[TuningPage, ...],
        gated_only: bool = False,
    ) -> tuple[tuple[str, str], ...]:
        checks: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
            "injector": (
                (("deadtime", "injopen", "opentime"), "Injector Dead Time"),
                (("reqfuel",), "Required Fuel"),
                (("staging", "injectorcount", "injcount"), "Injector Count / Staging"),
            ),
            "ignition": (
                (("dwell", "sparkdur"), "Dwell / Spark Duration"),
                (("timing", "advance", "fixang", "triggerangle"), "Reference Angle"),
                (("knockpin", "knock_digital", "knock_analog", "knockinput", "knocksensorpin"), "Knock Input"),
            ),
            "trigger": (
                (("triggertype", "decoder", "pattern"), "Trigger Decoder"),
                (("missingteeth", "missingtooth", "caminput", "secondtrigger"), "Secondary Trigger"),
                (("triggerangle", "fixang", "crankangle", "tdcangle"), "Reference Angle"),
            ),
            "sensor": (
                (("afrcal", "widebandcal", "lambdacal"), "Wideband Calibration"),
                (("barocal", "mapcal", "calibration", "thermistor"), "Sensor Calibration"),
                (("oilpressurepin", "oilpin", "oilpressuresensorpin"), "Oil Pressure Input"),
                (("baropin", "extbaropin", "externalbaropin", "barosensorpin"), "Baro Input"),
                (("stoich", "fuel", "ethanol", "flex"), "Fuel Basis"),
            ),
        }
        links: list[tuple[str, str]] = []
        seen_page_ids: set[str] = set()
        for keywords, label in checks.get(page_kind, ()):
            if page_kind == "ignition" and "knock" in label.lower() and not self._feature_enabled(current_page, local_tune_edit_service, ("knock",)):
                continue
            if page_kind == "sensor" and "oil pressure" in label.lower() and not self._feature_enabled(current_page, local_tune_edit_service, ("oilpressureenable", "oilpressure", "oilpressuresensor")):
                continue
            if page_kind == "sensor" and "baro" in label.lower() and not self._feature_enabled(current_page, local_tune_edit_service, ("useextbaro", "extbaro", "baroenable")):
                continue
            related = self._related_parameter_location(current_page, available_pages, local_tune_edit_service, keywords)
            if related is None:
                continue
            related_page, _parameter, is_visible = related
            if related_page.page_id == current_page.page_id:
                continue
            if gated_only and is_visible:
                continue
            if not gated_only and not is_visible:
                pass
            if related_page.page_id in seen_page_ids:
                continue
            seen_page_ids.add(related_page.page_id)
            links.append((f"Open {label}", f"{related_page.page_id}#{_parameter.name}"))
        return tuple(links)

    @staticmethod
    def _numeric_value(
        parameter: TuningPageParameter | None,
        local_tune_edit_service: LocalTuneEditService,
    ) -> float | None:
        if parameter is None:
            return None
        tune_value = local_tune_edit_service.get_value(parameter.name)
        if tune_value is None or not isinstance(tune_value.value, (int, float)):
            return None
        return float(tune_value.value)


# ---------------------------------------------------------------------------
# Readiness card builders (module-level helpers)
# ---------------------------------------------------------------------------

def _fmt(value: float | None, units: str = "") -> str:
    """Format a numeric value for display in a readiness card line."""
    if value is None:
        return ""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{text} {units}".strip() if units else text


def _captured_line(label: str, value: str) -> str:
    return f"OK  {label}: {value}"


def _missing_line(label: str, note: str = "") -> str:
    return f"--  {label}: not set{(' — ' + note) if note else ''}"


def _injector_readiness_card(ctx: GeneratorInputContext) -> HardwareSetupCardSnapshot:
    detail: list[str] = ["Inputs needed for VE table and injector baseline generation:"]
    captured: list[str] = []

    # Injector flow — prefer primary staging value; note if secondary is also set
    if ctx.injector_flow_ccmin:
        flow_label = "Primary injector flow" if ctx.injector_flow_secondary_ccmin else "Injector flow"
        captured.append(_captured_line(flow_label, _fmt(ctx.injector_flow_ccmin, "cc/min")))
    if ctx.injector_flow_secondary_ccmin:
        captured.append(_captured_line("Secondary injector flow", _fmt(ctx.injector_flow_secondary_ccmin, "cc/min")))
    if ctx.injector_dead_time_ms:
        captured.append(_captured_line("Dead time", _fmt(ctx.injector_dead_time_ms, "ms")))

    # reqFuel: show current ECU value, computed suggestion, and readiness
    if ctx.required_fuel_ms:
        req_fuel_note = _fmt(ctx.required_fuel_ms, "ms")
        if ctx.computed_req_fuel_ms is not None:
            req_fuel_note += f" — calculated: {_fmt(ctx.computed_req_fuel_ms, 'ms')}"
        captured.append(_captured_line("Required fuel", req_fuel_note))
    elif ctx.computed_req_fuel_ms is not None:
        captured.append(
            _captured_line(
                "Required fuel (computed)",
                f"{_fmt(ctx.computed_req_fuel_ms, 'ms')} — apply via staged edit before writing",
            )
        )
    if ctx.injector_count:
        captured.append(_captured_line("Injector count", str(ctx.injector_count)))

    if captured:
        detail.extend(captured)

    # Calculator readiness note when reqFuel is absent and computed value is not yet available
    if not ctx.required_fuel_ms and ctx.computed_req_fuel_ms is None:
        if ctx.injector_flow_ccmin and ctx.cylinder_count:
            detail.append(
                "reqFuel calculator: injector flow and cylinder count are available — "
                "enter engine displacement to calculate required fuel."
            )

    missing_labels = {label for label in ctx.missing_for_ve_generation + ctx.missing_for_injector_helper}
    missing_lines: list[str] = []
    if "Engine displacement" in missing_labels:
        missing_lines.append(_missing_line("Displacement", "needed for required-fuel calculation — not stored in ECU"))
    if "Cylinder count" in missing_labels:
        missing_lines.append(_missing_line("Cylinder count", "needed for required-fuel calculation"))
    if "Injector flow rate" in missing_labels:
        missing_lines.append(_missing_line("Injector flow", "enter rated flow from datasheet"))
    if "Required fuel (ms)" in missing_labels:
        missing_lines.append(_missing_line("Required fuel", "use reqFuel calculator before writing"))
    if "Stoich ratio" in missing_labels:
        missing_lines.append(_missing_line("Stoich ratio", "check Sensor / Fuel settings"))
    if "RPM limit / redline" in missing_labels:
        missing_lines.append(_missing_line("RPM limit", "check Engine Setup"))
    if missing_lines:
        detail.append("Still needed:")
        detail.extend(missing_lines)

    n_captured = len(captured)
    n_total = n_captured + len(missing_lines)
    if missing_lines:
        summary = f"{n_captured} of {n_total} injector/VE inputs captured — {len(missing_lines)} still needed."
        severity = "warning"
    else:
        summary = "All required injector and VE generation inputs are captured."
        severity = "info"
    return HardwareSetupCardSnapshot(
        key="injector_readiness",
        title="Base Tune Readiness — Injector",
        summary=summary,
        detail_lines=tuple(detail),
        severity=severity,
    )


def _ignition_readiness_card(ctx: GeneratorInputContext) -> HardwareSetupCardSnapshot:
    detail: list[str] = ["Inputs needed for conservative spark table generation:"]
    captured: list[str] = []
    if ctx.dwell_ms:
        captured.append(_captured_line("Dwell", _fmt(ctx.dwell_ms, "ms")))
    if ctx.compression_ratio:
        captured.append(_captured_line("Compression ratio", _fmt(ctx.compression_ratio)))
    if ctx.rev_limit_rpm:
        captured.append(_captured_line("RPM limit", _fmt(ctx.rev_limit_rpm, "rpm")))
    if captured:
        detail.extend(captured)

    missing_lines: list[str] = []
    for label in ctx.missing_for_spark_helper:
        if label == "Compression ratio":
            missing_lines.append(_missing_line("Compression ratio", "check Engine Setup"))
        elif label == "RPM limit / redline":
            missing_lines.append(_missing_line("RPM limit", "check Engine Setup"))
    if "Dwell" not in {line.split(":")[0].strip().lstrip("OK ") for line in captured}:
        if ctx.dwell_ms is None:
            missing_lines.append(_missing_line("Dwell", "enter from coil datasheet"))
    if missing_lines:
        detail.append("Still needed:")
        detail.extend(missing_lines)

    n_captured = len(captured)
    n_total = n_captured + len(missing_lines)
    if missing_lines:
        summary = f"{n_captured} of {n_total} ignition inputs captured — {len(missing_lines)} still needed."
        severity = "warning"
    else:
        summary = "All ignition baseline inputs are captured."
        severity = "info"
    return HardwareSetupCardSnapshot(
        key="ignition_readiness",
        title="Base Tune Readiness — Ignition",
        summary=summary,
        detail_lines=tuple(detail),
        severity=severity,
    )


def _trigger_readiness_card(ctx: GeneratorInputContext) -> HardwareSetupCardSnapshot | None:
    # Trigger inputs are primarily for RPM-axis scaling.  Only show a card
    # when something actionable is missing.
    missing_lines: list[str] = []
    if "RPM limit / redline" in ctx.missing_for_ve_generation:
        missing_lines.append(_missing_line("RPM limit", "needed for RPM-axis scaling in VE generation"))
    if not missing_lines:
        return None
    detail = ["Inputs needed for RPM-axis scaling in base tune generation:"] + missing_lines
    return HardwareSetupCardSnapshot(
        key="trigger_readiness",
        title="Base Tune Readiness — Trigger / RPM",
        summary=f"{len(missing_lines)} RPM-axis input(s) still needed for VE generation.",
        detail_lines=tuple(detail),
        severity="warning",
    )


def _sensor_readiness_card(ctx: GeneratorInputContext) -> HardwareSetupCardSnapshot:
    detail: list[str] = ["Inputs needed for load-axis and AFR target generation:"]
    captured: list[str] = []
    if ctx.ego_type_index is not None:
        ego_label = ("Off", "Narrowband", "Wideband")[min(ctx.ego_type_index, 2)]
        captured.append(_captured_line("EGO type", ego_label))
    if ctx.stoich_ratio:
        captured.append(_captured_line("Stoich", _fmt(ctx.stoich_ratio)))
    if ctx.map_range_kpa:
        captured.append(_captured_line("MAP range", _fmt(ctx.map_range_kpa, "kPa")))
    if captured:
        detail.extend(captured)

    missing_lines: list[str] = []
    if ctx.ego_type_index is None:
        missing_lines.append(_missing_line("EGO type", "needed for AFR target generation"))
    if "Stoich ratio" in ctx.missing_for_injector_helper:
        missing_lines.append(_missing_line("Stoich ratio", "needed for injector helper calculation"))
    if ctx.map_range_kpa is None:
        missing_lines.append(_missing_line("MAP range", "needed for load-axis calibration"))
    if missing_lines:
        detail.append("Still needed:")
        detail.extend(missing_lines)

    n_captured = len(captured)
    n_total = n_captured + len(missing_lines)
    if missing_lines:
        summary = f"{n_captured} of {n_total} sensor inputs captured — {len(missing_lines)} still needed."
        severity = "warning"
    else:
        summary = "Sensor inputs for base tune generation are captured."
        severity = "info"
    return HardwareSetupCardSnapshot(
        key="sensor_readiness",
        title="Base Tune Readiness — Sensors",
        summary=summary,
        detail_lines=tuple(detail),
        severity=severity,
    )
