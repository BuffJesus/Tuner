from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.datalog import DataLog
from tuner.services.replay_sample_gate_service import (
    ReplaySampleGateService,
    SampleGatingConfig,
)
from tuner.services.table_replay_context_service import TableReplayContextService
from tuner.services.tuning_workspace_presenter import TablePageSnapshot


@dataclass(slots=True, frozen=True)
class TableReplayHitCellSnapshot:
    row_index: int
    column_index: int
    hit_count: int
    mean_afr: float | None = None


@dataclass(slots=True, frozen=True)
class TableReplayHitSummarySnapshot:
    summary_text: str
    detail_text: str
    hot_cells: tuple[TableReplayHitCellSnapshot, ...]
    accepted_row_count: int
    rejected_row_count: int
    rejected_reason_counts: tuple[tuple[str, int], ...] = ()


class TableReplayHitService:
    def __init__(
        self,
        table_replay_context_service: TableReplayContextService | None = None,
        gate_service: ReplaySampleGateService | None = None,
    ) -> None:
        self._context_service = table_replay_context_service or TableReplayContextService()
        self._gate_service = gate_service or ReplaySampleGateService()

    _MAX_RECORDS = 50_000

    def build(
        self,
        *,
        table_snapshot: TablePageSnapshot,
        log: DataLog | None,
        gating_config: SampleGatingConfig | None = None,
    ) -> TableReplayHitSummarySnapshot | None:
        if log is None or not log.records or table_snapshot.table_model is None:
            return None

        # Pre-compute axis mapping once — avoids per-record object construction.
        x_axis = TableReplayContextService._numeric_axis(table_snapshot.x_labels)
        y_axis = TableReplayContextService._numeric_axis(table_snapshot.y_labels)
        if not x_axis or not y_axis:
            return None
        x_candidates = self._axis_candidates(table_snapshot.x_parameter_name)
        y_candidates = self._axis_candidates(table_snapshot.y_parameter_name)

        counts: dict[tuple[int, int], int] = {}
        afr_sums: dict[tuple[int, int], float] = {}
        afr_counts: dict[tuple[int, int], int] = {}
        rejected_rows = 0
        rejected_reason_counts: dict[str, int] = {}

        for record in log.records[: self._MAX_RECORDS]:
            # --- sample gate evaluation ---
            rejection = self._gate_service.primary_rejection(record, gating_config)
            if rejection is not None:
                rejected_rows += 1
                rejected_reason_counts[rejection.gate_name] = (
                    rejected_reason_counts.get(rejection.gate_name, 0) + 1
                )
                continue

            # --- axis lookup directly from record dict (no EvidenceReplaySnapshot) ---
            x_value = self._lookup_channel(record.values, x_candidates)
            y_value = self._lookup_channel(record.values, y_candidates)
            if x_value is None or y_value is None:
                rejected_rows += 1
                rejected_reason_counts["unmappable_axes"] = (
                    rejected_reason_counts.get("unmappable_axes", 0) + 1
                )
                continue

            col = TableReplayContextService._nearest_index(x_axis, x_value)
            row = TableReplayContextService._nearest_index(y_axis, y_value)
            key = (row, col)
            counts[key] = counts.get(key, 0) + 1

            afr = self._afr_value(record.values)
            if afr is not None:
                afr_sums[key] = afr_sums.get(key, 0.0) + afr
                afr_counts[key] = afr_counts.get(key, 0) + 1

        if not counts:
            return None

        ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:3]
        hot_cells = tuple(
            TableReplayHitCellSnapshot(
                row_index=row,
                column_index=column,
                hit_count=hit_count,
                mean_afr=(
                    afr_sums[(row, column)] / afr_counts[(row, column)]
                    if (row, column) in afr_counts and afr_counts[(row, column)] > 0
                    else None
                ),
            )
            for (row, column), hit_count in ordered
        )
        accepted_rows = sum(counts.values())
        summary = (
            f"Replay hit summary found {accepted_rows} mappable row(s) across {len(counts)} table cell(s); "
            f"{rejected_rows} row(s) could not be mapped."
        )
        detail = summary + " " + " ".join(
            (
                f"Hot cell row {cell.row_index + 1}, column {cell.column_index + 1}: {cell.hit_count} hit(s)"
                + (f", mean AFR {cell.mean_afr:.2f}." if cell.mean_afr is not None else ".")
            )
            for cell in hot_cells
        )
        if rejected_reason_counts:
            detail += " Rejections: " + ", ".join(
                f"{reason}={count}" for reason, count in sorted(rejected_reason_counts.items())
            ) + "."
        return TableReplayHitSummarySnapshot(
            summary_text=summary,
            detail_text=detail,
            hot_cells=hot_cells,
            accepted_row_count=accepted_rows,
            rejected_row_count=rejected_rows,
            rejected_reason_counts=tuple(sorted(rejected_reason_counts.items())),
        )

    # Mirrors TableReplayContextService._AXIS_CHANNEL_HINTS
    _AXIS_HINTS: dict[str, tuple[str, ...]] = {
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

    @classmethod
    def _axis_candidates(cls, axis_name: str | None) -> tuple[str, ...]:
        """Return ordered channel name candidates for an axis parameter name."""
        if not axis_name:
            return ()
        normalized = axis_name.lower()
        candidates: list[str] = []
        for token, channel_names in cls._AXIS_HINTS.items():
            if token in normalized:
                for ch in channel_names:
                    if ch not in candidates:
                        candidates.append(ch)
        if not candidates:
            candidates.append(normalized)
        return tuple(candidates)

    @staticmethod
    def _lookup_channel(values: dict[str, float], candidates: tuple[str, ...]) -> float | None:
        """Return the first matching channel value from a flat record dict."""
        for candidate in candidates:
            for name, value in values.items():
                if candidate in name.lower():
                    return value
        return None

    @staticmethod
    def _afr_value(values: dict[str, float]) -> float | None:
        for name, value in values.items():
            normalized = name.lower()
            if "afr" in normalized:
                return value
            if "lambda" in normalized:
                return value * 14.7
        return None
