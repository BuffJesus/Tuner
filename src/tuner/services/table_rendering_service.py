from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

from tuner.services.table_view_service import TableViewModel


@dataclass(slots=True, frozen=True)
class TableCellRender:
    text: str
    background_hex: str
    foreground_hex: str


@dataclass(slots=True, frozen=True)
class TableRenderModel:
    rows: int
    columns: int
    x_labels: tuple[str, ...]
    y_labels: tuple[str, ...]
    row_index_map: tuple[int, ...]
    cells: tuple[tuple[TableCellRender, ...], ...]


class TableRenderingService:
    def build_render_model(
        self,
        table_model: TableViewModel,
        x_labels: tuple[str, ...],
        y_labels: tuple[str, ...],
        invert_y_axis: bool = True,
    ) -> TableRenderModel:
        row_index_map = tuple(reversed(range(table_model.rows))) if invert_y_axis else tuple(range(table_model.rows))
        ordered_y_labels = tuple(y_labels[index] for index in row_index_map)
        numeric_values = self._numeric_values(table_model.cells)
        minimum = min(numeric_values) if numeric_values else 0.0
        maximum = max(numeric_values) if numeric_values else 0.0
        rendered_rows: list[tuple[TableCellRender, ...]] = []
        for model_row in row_index_map:
            rendered_rows.append(
                tuple(
                    self._render_cell(value, minimum, maximum)
                    for value in table_model.cells[model_row]
                )
            )
        return TableRenderModel(
            rows=table_model.rows,
            columns=table_model.columns,
            x_labels=x_labels,
            y_labels=ordered_y_labels,
            row_index_map=row_index_map,
            cells=tuple(rendered_rows),
        )

    @staticmethod
    def _numeric_values(rows: list[list[str]]) -> list[float]:
        values: list[float] = []
        for row in rows:
            for value in row:
                try:
                    values.append(float(value))
                except ValueError:
                    continue
        return values

    def _render_cell(self, text: str, minimum: float, maximum: float) -> TableCellRender:
        try:
            value = float(text)
        except ValueError:
            return TableCellRender(text=text, background_hex="#ffffff", foreground_hex="#000000")
        background = self._gradient_color(value, minimum, maximum)
        foreground = "#ffffff" if self._perceived_brightness(background) < 120 else "#000000"
        return TableCellRender(text=text, background_hex=background.name(), foreground_hex=foreground)

    @staticmethod
    def _gradient_color(value: float, minimum: float, maximum: float) -> QColor:
        if maximum <= minimum:
            ratio = 0.5
        else:
            ratio = max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))
        stops = (
            (0.0, QColor("#8aa8ff")),
            (0.25, QColor("#9dd9ff")),
            (0.5, QColor("#9af0a0")),
            (0.75, QColor("#e4ee8e")),
            (0.9, QColor("#f3b07b")),
            (1.0, QColor("#e58e8e")),
        )
        for index in range(len(stops) - 1):
            left_ratio, left_color = stops[index]
            right_ratio, right_color = stops[index + 1]
            if ratio <= right_ratio:
                span = right_ratio - left_ratio or 1.0
                local_ratio = (ratio - left_ratio) / span
                return QColor(
                    round(left_color.red() + ((right_color.red() - left_color.red()) * local_ratio)),
                    round(left_color.green() + ((right_color.green() - left_color.green()) * local_ratio)),
                    round(left_color.blue() + ((right_color.blue() - left_color.blue()) * local_ratio)),
                )
        return stops[-1][1]

    @staticmethod
    def _perceived_brightness(color: QColor) -> float:
        return (color.red() * 0.299) + (color.green() * 0.587) + (color.blue() * 0.114)
