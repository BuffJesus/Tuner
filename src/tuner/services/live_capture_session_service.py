from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.datalog_profile import DatalogProfile
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.services.datalog_profile_service import DatalogProfileService


@dataclass(slots=True, frozen=True)
class CaptureSessionStatus:
    recording: bool
    row_count: int
    elapsed_seconds: float
    profile_name: str

    @property
    def status_text(self) -> str:
        if self.recording:
            return f"Recording: {self.row_count} rows ({self.elapsed_seconds:.1f}s)"
        if self.row_count > 0:
            return f"Stopped — {self.row_count} rows captured ({self.elapsed_seconds:.1f}s)"
        return "Ready"


class LiveCaptureSessionService:
    """Manages a single live logging capture session.

    Lifecycle::

        service.start(profile)
        # on each runtime tick:
        service.append(snapshot)
        service.stop()
        csv_text = service.to_csv()        # or service.save_csv(path)
    """

    def __init__(
        self,
        profile_service: DatalogProfileService | None = None,
    ) -> None:
        self._profile_service = profile_service or DatalogProfileService()
        self._profile: DatalogProfile | None = None
        self._records: list[DataLogRecord] = []
        self._started_at: datetime | None = None
        self._ended_at: datetime | None = None
        self._recording = False
        self._output_file = None
        self._csv_stream_writer = None
        self._stream_columns: list[str] = []

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def row_count(self) -> int:
        return len(self._records)

    @property
    def has_data(self) -> bool:
        return len(self._records) > 0

    @property
    def elapsed_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        end = self._ended_at or datetime.now(UTC)
        return (end - self._started_at).total_seconds()

    def status(self) -> CaptureSessionStatus:
        return CaptureSessionStatus(
            recording=self._recording,
            row_count=len(self._records),
            elapsed_seconds=self.elapsed_seconds,
            profile_name=self._profile.name if self._profile else "(none)",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, profile: DatalogProfile, output_path=None) -> None:  # noqa: ANN001
        """Begin a new capture session, discarding any previous unsaved data.

        When *output_path* is given (``str`` or ``Path``), rows are written to
        that CSV file in real time on every :meth:`append` call.
        """
        from pathlib import Path as _Path
        self._profile = profile
        self._records = []
        self._started_at = datetime.now(UTC)
        self._ended_at = None
        self._recording = True
        self._stream_columns = [ch.name for ch in profile.enabled_channels]
        self._close_stream()
        if output_path is not None:
            self._output_file = open(_Path(output_path), "w", newline="", encoding="utf-8")
            self._csv_stream_writer = csv.writer(self._output_file)
            self._csv_stream_writer.writerow(["Time_ms", *self._stream_columns])
            self._output_file.flush()

    def append(self, snapshot: OutputChannelSnapshot) -> None:
        """Record one snapshot tick.  Filters to profile's enabled channels.

        Silently no-ops if not currently recording.
        """
        if not self._recording or self._profile is None:
            return
        filtered = self._profile_service.filter_snapshot(self._profile, snapshot)
        if filtered.values:
            record = DataLogRecord(timestamp=filtered.timestamp, values=filtered.as_dict())
            self._records.append(record)
            if self._csv_stream_writer is not None and self._output_file is not None:
                base = self._records[0].timestamp
                elapsed_ms = (record.timestamp - base).total_seconds() * 1000.0
                row_vals: list[str] = [f"{elapsed_ms:.0f}"]
                for name in self._stream_columns:
                    value = record.values.get(name)
                    if value is not None:
                        fmt = self._format_digits_for(name)
                        row_vals.append(f"{value:.{fmt}f}" if fmt is not None else str(value))
                    else:
                        row_vals.append("")
                self._csv_stream_writer.writerow(row_vals)
                self._output_file.flush()

    def stop(self) -> None:
        """Stop recording.  Captured rows are retained until the next start() or reset()."""
        self._recording = False
        self._ended_at = datetime.now(UTC)
        self._close_stream()

    def reset(self) -> None:
        """Discard all captured rows and reset to idle state."""
        self._close_stream()
        self._recording = False
        self._records = []
        self._started_at = None
        self._ended_at = None

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_log(self) -> DataLog:
        """Return the captured rows as a DataLog."""
        name = (
            f"{self._profile.name}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
            if self._profile
            else "capture"
        )
        return DataLog(name=name, records=list(self._records))

    def to_csv(self) -> str:
        """Return the captured rows as a CSV string (UTF-8)."""
        if not self._records:
            return ""
        buf = io.StringIO()
        channel_names = self._ordered_column_names()
        writer = csv.DictWriter(buf, fieldnames=["Time_ms", *channel_names], extrasaction="ignore")
        writer.writeheader()
        base = self._records[0].timestamp
        for record in self._records:
            elapsed_ms = (record.timestamp - base).total_seconds() * 1000.0
            row = {"Time_ms": f"{elapsed_ms:.0f}"}
            for name in channel_names:
                value = record.values.get(name)
                if value is not None:
                    fmt = self._format_digits_for(name)
                    row[name] = f"{value:.{fmt}f}" if fmt is not None else str(value)
            writer.writerow(row)
        return buf.getvalue()

    def save_csv(self, path) -> None:  # noqa: ANN001
        """Write the captured CSV to *path* (accepts str or Path)."""
        from pathlib import Path as _Path
        _Path(path).write_text(self.to_csv(), encoding="utf-8")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _close_stream(self) -> None:
        if self._output_file is not None:
            try:
                self._output_file.close()
            except Exception:
                pass
            self._output_file = None
            self._csv_stream_writer = None

    def _ordered_column_names(self) -> list[str]:
        """Return column names respecting profile channel order."""
        if self._profile:
            profile_names = [ch.name for ch in self._profile.enabled_channels]
            # Add any extra names seen in records that aren't in the profile
            seen: set[str] = set()
            ordered: list[str] = []
            for name in profile_names:
                seen.add(name)
                ordered.append(name)
            for record in self._records:
                for name in record.values:
                    if name not in seen:
                        seen.add(name)
                        ordered.append(name)
            return ordered
        # Fall back: collect all names in insertion order
        seen = set()
        ordered = []
        for record in self._records:
            for name in record.values:
                if name not in seen:
                    seen.add(name)
                    ordered.append(name)
        return ordered

    def _format_digits_for(self, name: str) -> int | None:
        if self._profile is None:
            return None
        for ch in self._profile.channels:
            if ch.name == name:
                return ch.format_digits
        return None
