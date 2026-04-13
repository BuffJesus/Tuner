from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class TriggerLogTraceSnapshot:
    name: str
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    offset: float
    is_digital: bool


@dataclass(slots=True, frozen=True)
class TriggerLogAnnotationSnapshot:
    time_ms: float
    label: str
    severity: str


@dataclass(slots=True, frozen=True)
class TriggerLogVisualizationSnapshot:
    trace_count: int
    point_count: int
    summary_text: str
    traces: tuple[TriggerLogTraceSnapshot, ...]
    annotations: tuple[TriggerLogAnnotationSnapshot, ...]


class TriggerLogVisualizationService:
    def build_from_csv(self, path: Path) -> TriggerLogVisualizationSnapshot:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = tuple(reader.fieldnames or ())
            rows = [row for row in reader]
        return self.build_from_rows(rows, columns=headers)

    def build_from_rows(
        self,
        rows: list[dict[str, str]],
        *,
        columns: tuple[str, ...],
    ) -> TriggerLogVisualizationSnapshot:
        normalized_columns = tuple(column.strip() for column in columns if column and column.strip())
        time_column = self._find_time_column(normalized_columns)
        if time_column is None or not rows:
            return TriggerLogVisualizationSnapshot(
                trace_count=0,
                point_count=0,
                summary_text="Visualization unavailable: the CSV needs a time column and at least one row.",
                traces=(),
                annotations=(),
            )

        x_values = self._time_values(rows, time_column)
        if not x_values:
            return TriggerLogVisualizationSnapshot(
                trace_count=0,
                point_count=0,
                summary_text="Visualization unavailable: the time column could not be parsed.",
                traces=(),
                annotations=(),
            )

        traces: list[TriggerLogTraceSnapshot] = []
        annotations: list[TriggerLogAnnotationSnapshot] = []
        offset = 0.0
        for column in normalized_columns:
            if column == time_column:
                continue
            y_values = self._numeric_values(rows, column)
            if len(y_values) != len(x_values):
                continue
            if not y_values:
                continue
            is_digital = self._is_digital_signal(y_values)
            min_value = min(y_values)
            normalized = tuple((value - min_value) + offset for value in y_values)
            traces.append(
                TriggerLogTraceSnapshot(
                    name=column,
                    x_values=tuple(x_values),
                    y_values=normalized,
                    offset=offset,
                    is_digital=is_digital,
                )
            )
            annotations.extend(self._trace_annotations(column, x_values, y_values))
            offset += max(1.0, (max(y_values) - min_value) + 0.75)

        gap_annotation = self._gap_annotation(x_values)
        if gap_annotation is not None:
            annotations.append(gap_annotation)

        if not traces:
            return TriggerLogVisualizationSnapshot(
                trace_count=0,
                point_count=len(x_values),
                summary_text="Visualization unavailable: no numeric signal columns were found beside the time axis.",
                traces=(),
                annotations=(),
            )

        annotation_text = f"{len(annotations)} annotation(s)" if annotations else "no decoder-aware annotations"
        return TriggerLogVisualizationSnapshot(
            trace_count=len(traces),
            point_count=len(x_values),
            summary_text=f"Visualization: {len(traces)} numeric trace(s) across {len(x_values)} sample(s), {annotation_text}.",
            traces=tuple(traces),
            annotations=tuple(annotations),
        )

    @staticmethod
    def _find_time_column(columns: tuple[str, ...]) -> str | None:
        for column in columns:
            lowered = column.lower()
            if lowered in {"time", "timems", "timestamp", "time_ms", "time (ms)"} or "time" in lowered:
                return column
        return None

    @staticmethod
    def _time_values(rows: list[dict[str, str]], time_column: str) -> list[float]:
        values: list[float] = []
        for row in rows:
            raw = row.get(time_column, "").strip()
            if not raw:
                return []
            try:
                values.append(float(raw))
            except ValueError:
                return []
        return values

    @staticmethod
    def _numeric_values(rows: list[dict[str, str]], column: str) -> list[float]:
        values: list[float] = []
        for row in rows:
            raw = row.get(column, "").strip()
            if not raw:
                return []
            try:
                values.append(float(raw))
            except ValueError:
                return []
        return values

    @staticmethod
    def _is_digital_signal(values: list[float]) -> bool:
        unique = {round(value, 6) for value in values}
        return unique.issubset({0.0, 1.0})

    def _trace_annotations(
        self,
        name: str,
        x_values: list[float],
        y_values: list[float],
    ) -> list[TriggerLogAnnotationSnapshot]:
        if not self._is_digital_signal(y_values):
            return []
        lowered = name.lower()
        if not any(token in lowered for token in ("crank", "cam", "trigger", "sync", "tooth", "composite")):
            return []
        annotations: list[TriggerLogAnnotationSnapshot] = []
        edge_count = 0
        for index, (left, right) in enumerate(zip(y_values, y_values[1:]), start=1):
            if left == right:
                continue
            edge_count += 1
            if edge_count > 6:
                break
            direction = "rising" if right > left else "falling"
            annotations.append(
                TriggerLogAnnotationSnapshot(
                    time_ms=x_values[index],
                    label=f"{name} {direction}",
                    severity="info",
                )
            )
        return annotations

    @staticmethod
    def _gap_annotation(x_values: list[float]) -> TriggerLogAnnotationSnapshot | None:
        if len(x_values) < 6:
            return None
        deltas = [right - left for left, right in zip(x_values, x_values[1:]) if right > left]
        if len(deltas) < 4:
            return None
        sorted_deltas = sorted(deltas)
        median = sorted_deltas[len(sorted_deltas) // 2]
        if median <= 0.0:
            return None
        max_gap = max(deltas)
        if max_gap < median * 1.6:
            return None
        gap_index = deltas.index(max_gap) + 1
        return TriggerLogAnnotationSnapshot(
            time_ms=x_values[gap_index],
            label="Possible missing-tooth gap",
            severity="warning",
        )
