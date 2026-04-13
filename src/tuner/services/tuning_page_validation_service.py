from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.tuning_pages import TuningPage, TuningPageKind
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.visibility_expression_service import VisibilityExpressionService


@dataclass(slots=True, frozen=True)
class TuningPageValidationResult:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def summary(self) -> str:
        parts: list[str] = []
        if self.errors:
            parts.append(f"{len(self.errors)} error{'s' if len(self.errors) != 1 else ''}")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning{'s' if len(self.warnings) != 1 else ''}")
        return ", ".join(parts) if parts else "No validation issues."


class TuningPageValidationService:
    def __init__(
        self,
        visibility_expression_service: VisibilityExpressionService | None = None,
    ) -> None:
        self._visibility = visibility_expression_service or VisibilityExpressionService()

    def validate_page(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
    ) -> TuningPageValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        values_dict = local_tune_edit_service.get_scalar_values_dict()

        available_values: dict[str, object | None] = {}
        for parameter in page.parameters:
            if not self._visibility.evaluate(parameter.visibility_expression, values_dict):
                continue
            tune_value = local_tune_edit_service.get_value(parameter.name)
            available_values[parameter.name] = tune_value
            if tune_value is None and self._expects_tune_value(parameter.page, parameter.offset):
                errors.append(f"Missing tune value for '{parameter.name}'.")

        if page.kind == TuningPageKind.TABLE:
            if page.table_name:
                table_value = local_tune_edit_service.get_value(page.table_name)
                if table_value is None:
                    errors.append(f"Main table '{page.table_name}' is unavailable.")
                elif not isinstance(table_value.value, list):
                    errors.append(f"Main table '{page.table_name}' is not list-backed.")
            else:
                errors.append("This table page does not define a main table name.")

            for axis_name, axis_label in ((page.x_axis_name, "X axis"), (page.y_axis_name, "Y axis")):
                if not axis_name:
                    continue
                axis_value = local_tune_edit_service.get_value(axis_name)
                if axis_value is None:
                    errors.append(f"{axis_label} '{axis_name}' is unavailable.")
                    continue
                if not isinstance(axis_value.value, list):
                    errors.append(f"{axis_label} '{axis_name}' is not list-backed.")
                    continue
                if not axis_value.value:
                    warnings.append(f"{axis_label} '{axis_name}' has no labels.")
        else:
            scalar_count = 0
            table_count = 0
            for parameter in page.parameters:
                tune_value = available_values.get(parameter.name)
                if parameter.kind == "scalar":
                    scalar_count += 1
                    if tune_value is not None and isinstance(tune_value.value, float):
                        v = tune_value.value
                        if parameter.min_value is not None and v < parameter.min_value:
                            warnings.append(
                                f"'{parameter.name}' value {v} is below minimum {parameter.min_value}."
                            )
                        elif parameter.max_value is not None and v > parameter.max_value:
                            warnings.append(
                                f"'{parameter.name}' value {v} exceeds maximum {parameter.max_value}."
                            )
                elif parameter.kind == "table":
                    table_count += 1
                    if tune_value is not None and not isinstance(getattr(tune_value, "value", None), list):
                        warnings.append(f"Fallback table '{parameter.name}' is not list-backed in the tune.")
            if scalar_count == 0 and table_count > 0:
                warnings.append("This fallback page has only table content and no direct scalar edits.")

        return TuningPageValidationResult(errors=tuple(dict.fromkeys(errors)), warnings=tuple(dict.fromkeys(warnings)))

    @staticmethod
    def _expects_tune_value(page: int | None, offset: int | None) -> bool:
        return page is not None or offset is not None
