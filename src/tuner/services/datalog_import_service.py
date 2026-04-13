from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tuner.domain.datalog import DataLog, DataLogRecord


@dataclass(slots=True, frozen=True)
class DatalogImportSnapshot:
    log: DataLog
    row_count: int
    channel_names: tuple[str, ...]
    summary_text: str
    preview_text: str


class DatalogImportService:
    _TIME_NAMES_MS = {"timems", "time_ms", "timestampms", "timestamp_ms"}
    _TIME_NAMES_S = {"time", "time_s", "times", "sec", "secs", "second", "seconds", "timestamp"}

    def load_csv(self, path: Path) -> DatalogImportSnapshot:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV does not contain a header row.")
            base_time = datetime.now(UTC)
            time_field = self._detect_time_field(reader.fieldnames)
            records: list[DataLogRecord] = []
            channel_names: list[str] = []
            for row_index, row in enumerate(reader):
                values: dict[str, float] = {}
                timestamp = base_time + timedelta(seconds=float(row_index))
                if time_field is not None:
                    raw_time = row.get(time_field, "")
                    parsed_time = self._parse_float(raw_time)
                    if parsed_time is not None:
                        seconds = parsed_time / 1000.0 if time_field.lower() in self._TIME_NAMES_MS else parsed_time
                        timestamp = base_time + timedelta(seconds=seconds)
                for name in reader.fieldnames:
                    if name == time_field:
                        continue
                    parsed = self._parse_float(row.get(name, ""))
                    if parsed is None:
                        continue
                    values[name] = parsed
                    if name not in channel_names:
                        channel_names.append(name)
                if values:
                    records.append(DataLogRecord(timestamp=timestamp, values=values))
            log = DataLog(name=path.stem, records=records)
        if not records:
            raise ValueError("CSV did not contain any numeric replay rows.")
        summary = (
            f"Imported {len(records)} datalog row(s) from {path.name}. "
            f"Channels: {', '.join(channel_names[:8])}"
            f"{'...' if len(channel_names) > 8 else ''}."
        )
        preview_lines = [summary]
        for index, record in enumerate(records[:3], start=1):
            sample_text = ", ".join(f"{name}={value}" for name, value in list(record.values.items())[:6])
            preview_lines.append(f"Row {index}: {sample_text}")
        return DatalogImportSnapshot(
            log=log,
            row_count=len(records),
            channel_names=tuple(channel_names),
            summary_text=summary,
            preview_text="\n".join(preview_lines),
        )

    def _detect_time_field(self, fieldnames: list[str]) -> str | None:
        normalized = {name.lower().replace(" ", "").replace("-", "_"): name for name in fieldnames}
        for candidate in (*self._TIME_NAMES_MS, *self._TIME_NAMES_S):
            actual = normalized.get(candidate)
            if actual is not None:
                return actual
        return None

    @staticmethod
    def _parse_float(raw_value: str | None) -> float | None:
        if raw_value is None:
            return None
        stripped = raw_value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
