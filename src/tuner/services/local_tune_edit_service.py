from __future__ import annotations

from dataclasses import replace

from tuner.domain.tune import TuneFile, TuneValue


class LocalTuneEditService:
    def __init__(self) -> None:
        self.base_tune_file: TuneFile | None = None
        self.staged_values: dict[str, TuneValue] = {}
        self._history: dict[str, list[str | float | list[float]]] = {}
        self._history_index: dict[str, int] = {}

    def set_tune_file(self, tune_file: TuneFile | None) -> None:
        self.base_tune_file = tune_file
        self.staged_values.clear()
        self._history.clear()
        self._history_index.clear()

    def get_value(self, name: str) -> TuneValue | None:
        if name in self.staged_values:
            return self.staged_values[name]
        return self.get_base_value(name)

    def get_base_value(self, name: str) -> TuneValue | None:
        if self.base_tune_file is None:
            return None
        for item in self.base_tune_file.constants:
            if item.name == name:
                return item
        for item in self.base_tune_file.pc_variables:
            if item.name == name:
                return item
        return None

    def stage_list_cell(self, name: str, index: int, raw_value: str) -> None:
        tune_value = self.get_value(name)
        if tune_value is None or not isinstance(tune_value.value, list):
            raise KeyError(f"Tune value '{name}' is not a list-backed parameter.")
        if index < 0 or index >= len(tune_value.value):
            raise IndexError(f"Cell index {index} is out of range for '{name}'.")
        staged = self._ensure_staged_copy(name, tune_value)
        staged.value[index] = float(raw_value)
        self._commit_history(name, staged.value)

    def stage_scalar_value(self, name: str, raw_value: str) -> None:
        tune_value = self.get_value(name)
        if tune_value is not None and isinstance(tune_value.value, list):
            raise KeyError(f"Tune value '{name}' is not a scalar-backed parameter.")
        if tune_value is None:
            # Parameter is in the definition but absent from the tune (e.g. a knock or
            # advanced sensor field that was never written by the ECU).  Auto-create a
            # base entry so the user can stage an initial value.
            try:
                default: float | str = float(raw_value)
            except (ValueError, TypeError):
                default = raw_value
            self.set_or_add_base_value(name, default)
            tune_value = self.get_value(name)
            if tune_value is None:
                raise KeyError(f"Tune value '{name}' could not be created (no tune file loaded).")
        staged = self._ensure_staged_copy(name, tune_value)
        if isinstance(tune_value.value, str):
            staged.value = raw_value
            self._commit_history(name, staged.value)
            return
        staged.value = float(raw_value)
        self._commit_history(name, staged.value)

    def replace_list(self, name: str, values: list[float]) -> None:
        tune_value = self.get_value(name)
        if tune_value is None or not isinstance(tune_value.value, list):
            raise KeyError(f"Tune value '{name}' is not a list-backed parameter.")
        staged = self._ensure_staged_copy(name, tune_value)
        staged.value = list(values)
        self._commit_history(name, staged.value)

    def can_undo(self, name: str) -> bool:
        return self._history_index.get(name, 0) > 0

    def can_redo(self, name: str) -> bool:
        history = self._history.get(name)
        if not history:
            return False
        return self._history_index.get(name, 0) < len(history) - 1

    def undo(self, name: str) -> None:
        if not self.can_undo(name):
            return
        staged = self.staged_values.get(name)
        if staged is None:
            return
        self._history_index[name] -= 1
        staged.value = self._copy_value(self._history[name][self._history_index[name]])

    def redo(self, name: str) -> None:
        if not self.can_redo(name):
            return
        staged = self.staged_values.get(name)
        if staged is None:
            return
        self._history_index[name] += 1
        staged.value = self._copy_value(self._history[name][self._history_index[name]])

    def revert(self, name: str | None = None) -> None:
        if name is None:
            self.staged_values.clear()
            self._history.clear()
            self._history_index.clear()
            return
        self.staged_values.pop(name, None)
        self._history.pop(name, None)
        self._history_index.pop(name, None)

    def set_base_value(self, name: str, value: str | float | list[float]) -> None:
        """Replace a single base tune value and clear any staged override for it.

        Used by revert_from_ecu to accept ECU RAM as the new source of truth
        without disturbing other parameters.
        """
        if self.base_tune_file is None:
            return
        for tv in self.base_tune_file.constants:
            if tv.name == name:
                tv.value = self._copy_value(value)
                self.staged_values.pop(name, None)
                self._history.pop(name, None)
                self._history_index.pop(name, None)
                return
        for tv in self.base_tune_file.pc_variables:
            if tv.name == name:
                tv.value = self._copy_value(value)
                self.staged_values.pop(name, None)
                self._history.pop(name, None)
                self._history_index.pop(name, None)
                return

    def set_or_add_base_value(
        self,
        name: str,
        value: str | float | list[float],
        *,
        units: str | None = None,
        digits: int | None = None,
        rows: int | None = None,
        cols: int | None = None,
    ) -> None:
        """Replace an existing base tune value or append a new one when absent."""
        if self.base_tune_file is None:
            return
        existing = self.get_base_value(name)
        if existing is not None:
            self.set_base_value(name, value)
            if units is not None:
                existing.units = units
            if digits is not None:
                existing.digits = digits
            if rows is not None:
                existing.rows = rows
            if cols is not None:
                existing.cols = cols
            return
        self.base_tune_file.constants.append(
            TuneValue(
                name=name,
                value=self._copy_value(value),
                units=units,
                digits=digits,
                rows=rows,
                cols=cols,
            )
        )
        self.staged_values.pop(name, None)
        self._history.pop(name, None)
        self._history_index.pop(name, None)
        for tv in self.base_tune_file.pc_variables:
            if tv.name == name:
                tv.value = self._copy_value(value)
                self.staged_values.pop(name, None)
                self._history.pop(name, None)
                self._history_index.pop(name, None)
                return

    def get_scalar_values_dict(self) -> dict[str, float]:
        """Return all current scalar (float) parameter values keyed by name.

        Staged values take precedence over base values.  String-valued and
        list-valued parameters are excluded.  Used by visibility expression
        evaluation to resolve identifier references.
        """
        result: dict[str, float] = {}
        if self.base_tune_file is not None:
            for tv in self.base_tune_file.constants:
                if isinstance(tv.value, float):
                    result[tv.name] = tv.value
            for tv in self.base_tune_file.pc_variables:
                if isinstance(tv.value, float):
                    result[tv.name] = tv.value
        for name, tv in self.staged_values.items():
            if isinstance(tv.value, float):
                result[name] = tv.value
        return result

    def is_dirty(self, name: str | None = None) -> bool:
        if name is None:
            return bool(self.staged_values)
        return name in self.staged_values

    def _ensure_staged_copy(self, name: str, tune_value: TuneValue) -> TuneValue:
        if name not in self.staged_values:
            copied_value = self._copy_value(tune_value.value)
            self.staged_values[name] = replace(tune_value, value=copied_value)
            self._history[name] = [self._copy_value(copied_value)]
            self._history_index[name] = 0
        return self.staged_values[name]

    def _commit_history(self, name: str, current_value: str | float | list[float]) -> None:
        history = self._history.setdefault(name, [self._copy_value(current_value)])
        index = self._history_index.setdefault(name, len(history) - 1)
        history[:] = history[: index + 1]
        if history[-1] != current_value:
            history.append(self._copy_value(current_value))
            self._history_index[name] = len(history) - 1

    @staticmethod
    def _copy_value(value: str | float | list[float]) -> str | float | list[float]:
        if isinstance(value, list):
            return list(value)
        return value
