from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.tune import TuneFile, TuneValue


@dataclass(slots=True)
class TableViewModel:
    rows: int
    columns: int
    cells: list[list[str]]


class TableViewService:
    def find_tune_value(self, tune_file: TuneFile | None, name: str) -> TuneValue | None:
        if tune_file is None:
            return None
        for item in tune_file.constants:
            if item.name == name:
                return item
        for item in tune_file.pc_variables:
            if item.name == name:
                return item
        return None

    def build_table_model(self, tune_value: TuneValue, shape: str | None = None) -> TableViewModel | None:
        if not isinstance(tune_value.value, list):
            return None
        rows, cols = self._resolve_shape(tune_value, shape)
        cells: list[list[str]] = []
        values = [str(item) for item in tune_value.value]
        for row_index in range(rows):
            start = row_index * cols
            end = start + cols
            row_values = values[start:end]
            if len(row_values) < cols:
                row_values.extend([""] * (cols - len(row_values)))
            cells.append(row_values)
        return TableViewModel(rows=rows, columns=cols, cells=cells)

    @staticmethod
    def _resolve_shape(tune_value: TuneValue, shape: str | None) -> tuple[int, int]:
        if tune_value.rows and tune_value.cols:
            return tune_value.rows, tune_value.cols
        if shape and "x" in shape:
            row_text, col_text = shape.lower().split("x", 1)
            try:
                return max(1, int(row_text)), max(1, int(col_text))
            except ValueError:
                pass
        count = len(tune_value.value) if isinstance(tune_value.value, list) else 1
        return count, 1
