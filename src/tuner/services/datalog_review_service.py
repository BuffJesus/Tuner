from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.datalog import DataLog
from tuner.domain.datalog_profile import DatalogProfile


@dataclass(slots=True, frozen=True)
class DatalogReviewTraceSnapshot:
    name: str
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]


@dataclass(slots=True, frozen=True)
class DatalogReviewSnapshot:
    summary_text: str
    selected_index: int
    marker_x: float
    traces: tuple[DatalogReviewTraceSnapshot, ...]


class DatalogReviewService:
    _PRIORITY_CHANNELS = ("rpm", "map", "tps", "afr", "lambda", "advance", "pw", "ego")

    def build(
        self,
        *,
        log: DataLog,
        selected_index: int,
        profile: DatalogProfile | None = None,
    ) -> DatalogReviewSnapshot:
        if not log.records:
            raise ValueError("Datalog is empty.")
        bounded_index = max(0, min(selected_index, len(log.records) - 1))
        base_time = log.records[0].timestamp
        channel_names = self._select_channels(log, profile=profile)
        traces: list[DatalogReviewTraceSnapshot] = []
        for channel_name in channel_names:
            x_values: list[float] = []
            y_values: list[float] = []
            for record in log.records:
                if channel_name not in record.values:
                    continue
                x_values.append((record.timestamp - base_time).total_seconds())
                y_values.append(record.values[channel_name])
            if x_values:
                traces.append(
                    DatalogReviewTraceSnapshot(
                        name=channel_name,
                        x_values=tuple(x_values),
                        y_values=tuple(y_values),
                    )
                )
        marker_x = (log.records[bounded_index].timestamp - base_time).total_seconds()
        summary = (
            f"Datalog review shows {len(traces)} trace(s) across {len(log.records)} row(s). "
            f"Selected replay row {bounded_index + 1} is at +{marker_x:.3f}s."
        )
        return DatalogReviewSnapshot(
            summary_text=summary,
            selected_index=bounded_index,
            marker_x=marker_x,
            traces=tuple(traces),
        )

    def _select_channels(
        self,
        log: DataLog,
        profile: DatalogProfile | None = None,
    ) -> tuple[str, ...]:
        # Collect all channel names present in the log (insertion order).
        available: list[str] = []
        for record in log.records:
            for name in record.values:
                if name not in available:
                    available.append(name)

        # When a profile is provided, prefer its enabled channel order.
        if profile is not None:
            available_set = set(available)
            selected: list[str] = []
            for ch in profile.enabled_channels:
                if ch.name in available_set:
                    selected.append(ch.name)
                    if len(selected) >= 3:
                        return tuple(selected)
            if selected:
                return tuple(selected)
            # Fall through to heuristic if no profile channels matched.

        # Heuristic: pick up to 3 channels by priority, then fill from available.
        selected = []
        lowered = {name.lower(): name for name in available}
        for priority in self._PRIORITY_CHANNELS:
            actual = lowered.get(priority)
            if actual is not None and actual not in selected:
                selected.append(actual)
            if len(selected) >= 3:
                return tuple(selected)
        for name in available:
            if name not in selected:
                selected.append(name)
            if len(selected) >= 3:
                break
        return tuple(selected)
