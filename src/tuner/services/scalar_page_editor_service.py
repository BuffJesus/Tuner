from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.tuning_pages import TuningPage, TuningPageParameter, TuningPageSection
from tuner.domain.tune import TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.visibility_expression_service import VisibilityExpressionService


@dataclass(slots=True, frozen=True)
class ScalarFieldEditorSnapshot:
    name: str
    label: str
    value_text: str
    base_value_text: str
    units: str | None
    help_text: str | None
    min_value: float | None
    max_value: float | None
    digits: int | None
    options: tuple[str, ...]
    option_values: tuple[str, ...]
    is_dirty: bool
    requires_power_cycle: bool
    visibility_expression: str | None


@dataclass(slots=True, frozen=True)
class ScalarSectionEditorSnapshot:
    title: str
    notes: tuple[str, ...]
    fields: tuple[ScalarFieldEditorSnapshot, ...]
    visibility_expression: str | None


class ScalarPageEditorService:
    def __init__(
        self,
        visibility_expression_service: VisibilityExpressionService | None = None,
    ) -> None:
        self._visibility = visibility_expression_service or VisibilityExpressionService()

    def build_sections(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
    ) -> tuple[ScalarSectionEditorSnapshot, ...]:
        parameters_by_name = {parameter.name: parameter for parameter in page.parameters}
        values_dict = local_tune_edit_service.get_scalar_values_dict()
        sections: list[ScalarSectionEditorSnapshot] = []
        for section in page.sections:
            all_fields = tuple(
                self._field_snapshot(parameters_by_name[name], local_tune_edit_service)
                for name in section.parameter_names
                if name in parameters_by_name and parameters_by_name[name].kind == "scalar"
            )
            visible_fields = tuple(
                f for f in all_fields
                if self._visibility.evaluate(f.visibility_expression, values_dict)
            )
            candidate = ScalarSectionEditorSnapshot(
                title=section.title,
                notes=section.notes,
                fields=visible_fields,
                visibility_expression=section.visibility_expression,
            )
            if (visible_fields or section.notes) and self._visibility.evaluate(section.visibility_expression, values_dict):
                sections.append(candidate)
        if sections:
            return tuple(sections)
        fallback_fields = tuple(
            self._field_snapshot(parameter, local_tune_edit_service)
            for parameter in page.parameters
            if parameter.kind == "scalar"
            if self._visibility.evaluate(parameter.visibility_expression, values_dict)
        )
        return (
            ScalarSectionEditorSnapshot(
                title=page.title,
                notes=(),
                fields=fallback_fields,
                visibility_expression=None,
            ),
        )

    def _field_snapshot(
        self,
        parameter: TuningPageParameter,
        local_tune_edit_service: LocalTuneEditService,
    ) -> ScalarFieldEditorSnapshot:
        current_value = local_tune_edit_service.get_value(parameter.name)
        base_value = local_tune_edit_service.get_base_value(parameter.name)
        return ScalarFieldEditorSnapshot(
            name=parameter.name,
            label=parameter.label,
            value_text=self._value_text(current_value),
            base_value_text=self._value_text(base_value),
            units=parameter.units,
            help_text=parameter.help_text,
            min_value=parameter.min_value,
            max_value=parameter.max_value,
            digits=parameter.digits,
            options=parameter.options,
            option_values=parameter.option_values,
            is_dirty=local_tune_edit_service.is_dirty(parameter.name),
            requires_power_cycle=parameter.requires_power_cycle,
            visibility_expression=parameter.visibility_expression,
        )

    @staticmethod
    def _value_text(tune_value: TuneValue | None) -> str:
        if tune_value is None:
            return ""
        if isinstance(tune_value.value, list):
            return ", ".join(str(item) for item in tune_value.value[:4])
        return str(tune_value.value)
