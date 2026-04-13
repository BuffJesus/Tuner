from __future__ import annotations

from dataclasses import dataclass

from tuner.services.evidence_replay_service import EvidenceReplaySnapshot
from tuner.services.tuning_workspace_presenter import TablePageSnapshot


@dataclass(slots=True, frozen=True)
class TableReplayContextSnapshot:
    summary_text: str
    detail_text: str
    row_index: int
    column_index: int
    x_value: float
    y_value: float
    cell_value_text: str | None


class TableReplayContextService:
    _AXIS_CHANNEL_HINTS = {
        "rpm": ("rpm",),
        "map": ("map",),
        "load": ("map", "tps"),
        "kpa": ("map",),
        "tps": ("tps",),
        "throttle": ("tps",),
        "afr": ("afr", "lambda"),
        "lambda": ("lambda", "afr"),
        "spark": ("advance",),
        "advance": ("advance",),
    }

    def build(
        self,
        *,
        table_snapshot: TablePageSnapshot,
        evidence_snapshot: EvidenceReplaySnapshot | None,
    ) -> TableReplayContextSnapshot | None:
        if evidence_snapshot is None or table_snapshot.table_model is None:
            return None
        x_value = self._axis_value(table_snapshot.x_parameter_name, evidence_snapshot)
        y_value = self._axis_value(table_snapshot.y_parameter_name, evidence_snapshot)
        if x_value is None or y_value is None:
            return None
        x_axis = self._numeric_axis(table_snapshot.x_labels)
        y_axis = self._numeric_axis(table_snapshot.y_labels)
        if not x_axis or not y_axis:
            return None
        column_index = self._nearest_index(x_axis, x_value)
        row_index = self._nearest_index(y_axis, y_value)
        cell_value = None
        if 0 <= row_index < len(table_snapshot.table_model.cells):
            row = table_snapshot.table_model.cells[row_index]
            if 0 <= column_index < len(row):
                cell_value = row[column_index]
        summary = (
            f"Replay position is nearest row {row_index + 1}, column {column_index + 1} "
            f"for this table."
        )
        detail = (
            f"{summary}\n"
            f"Axis match: X={x_value:.1f} near {x_axis[column_index]:.1f}, "
            f"Y={y_value:.1f} near {y_axis[row_index]:.1f}."
        )
        if cell_value:
            detail += f" Table cell value: {cell_value}."
        return TableReplayContextSnapshot(
            summary_text=summary,
            detail_text=detail,
            row_index=row_index,
            column_index=column_index,
            x_value=x_value,
            y_value=y_value,
            cell_value_text=cell_value,
        )

    def _axis_value(self, axis_name: str | None, evidence_snapshot: EvidenceReplaySnapshot) -> float | None:
        if not axis_name:
            return None
        normalized = axis_name.lower()
        candidates: list[str] = []
        for token, channel_names in self._AXIS_CHANNEL_HINTS.items():
            if token in normalized:
                for channel_name in channel_names:
                    if channel_name not in candidates:
                        candidates.append(channel_name)
        if not candidates:
            candidates.append(normalized)
        for channel in evidence_snapshot.runtime_channels:
            lower_name = channel.name.lower()
            if any(candidate in lower_name for candidate in candidates):
                return channel.value
        return None

    @staticmethod
    def _numeric_axis(labels: tuple[str, ...]) -> tuple[float, ...]:
        values: list[float] = []
        for label in labels:
            try:
                values.append(float(label))
            except ValueError:
                return ()
        return tuple(values)

    @staticmethod
    def _nearest_index(axis: tuple[float, ...], value: float) -> int:
        best_index = 0
        best_error = abs(axis[0] - value)
        for index, axis_value in enumerate(axis[1:], start=1):
            error = abs(axis_value - value)
            if error < best_error:
                best_index = index
                best_error = error
        return best_index
