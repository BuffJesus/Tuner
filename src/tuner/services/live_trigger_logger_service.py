"""Live trigger logger service.

Decodes raw binary log buffers returned by ``SpeeduinoControllerClient.fetch_logger_data()``
into named-column records that are compatible with the existing
``TriggerLogAnalysisService`` CSV path.

Tooth records
-------------
Each record is 4 bytes (``u32 LE``): the inter-tooth time in microseconds.
Column: ``ToothTime``

Composite records
-----------------
Each record is 5 bytes:
- Byte 0 bits: priLevel(0), secLevel(1), ThirdLevel(2), trigger(3), sync(4), cycle(5)
- Bytes 1-4: refTime (u32 LE), scale × 0.001 → milliseconds
Columns: ``PriLevel``, ``SecLevel``, ``ThirdLevel``, ``Trigger``, ``Sync``, ``Cycle``, ``RefTime``

The service returns a ``TriggerLogCapture`` that wraps the decoded rows and can be
written to a temporary CSV for hand-off to the existing analysis pipeline.
"""
from __future__ import annotations

import csv
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tuner.domain.ecu_definition import LoggerDefinition, LoggerRecordField


@dataclass(slots=True)
class TriggerLogCapture:
    """Decoded records from a live logger capture."""
    logger_name: str
    display_name: str
    kind: str               # "tooth" or "composite"
    columns: tuple[str, ...]
    rows: list[dict[str, float]] = field(default_factory=list)

    @property
    def record_count(self) -> int:
        return len(self.rows)

    def to_csv_path(self) -> Path:
        """Write records to a temp CSV file and return its path.

        The file is named ``trigger_live_<logger_name>.csv`` in the system temp
        directory.  The caller owns the file; it is not cleaned up automatically.
        """
        tmp = Path(tempfile.gettempdir()) / f"trigger_live_{self.logger_name}.csv"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(self.columns))
            writer.writeheader()
            writer.writerows(self.rows)
        return tmp


class LiveTriggerLoggerService:
    """Decode raw logger bytes into ``TriggerLogCapture`` records.

    The decoding logic is driven entirely by the ``LoggerDefinition`` domain
    model — no hard-coded byte layouts, so it automatically adapts to different
    logger types parsed from the INI.
    """

    def decode(self, logger: LoggerDefinition, raw: bytes) -> TriggerLogCapture:
        """Decode *raw* bytes according to *logger*'s ``record_fields``.

        Parameters
        ----------
        logger:
            The ``LoggerDefinition`` that describes the record format.
        raw:
            Raw bytes as returned by ``SpeeduinoControllerClient.fetch_logger_data()``.

        Returns
        -------
        TriggerLogCapture
            Decoded records.  Columns are the ``header`` names from each
            ``recordField`` (matching the CSV column names the analysis service
            expects).
        """
        columns = tuple(f.header for f in logger.record_fields)
        rows: list[dict[str, float]] = []

        rec_len = logger.record_len
        if rec_len == 0:
            return TriggerLogCapture(
                logger_name=logger.name,
                display_name=logger.display_name,
                kind=logger.kind,
                columns=columns,
                rows=rows,
            )

        for i in range(logger.record_count):
            start = logger.record_header_len + i * rec_len
            end = start + rec_len
            if end > len(raw):
                break
            record_bytes = raw[start:end]
            row: dict[str, float] = {}
            for field_def in logger.record_fields:
                value = _extract_field(record_bytes, field_def)
                row[field_def.header] = value
            rows.append(row)

        return TriggerLogCapture(
            logger_name=logger.name,
            display_name=logger.display_name,
            kind=logger.kind,
            columns=columns,
            rows=rows,
        )


def _extract_field(record: bytes, field_def: LoggerRecordField) -> float:
    """Extract a single field value from a record byte slice.

    Handles bit-level extraction for 1-bit flags and full u32 LE integers.
    Scale is applied before returning.
    """
    start_bit = field_def.start_bit
    bit_count = field_def.bit_count
    scale = field_def.scale

    if bit_count == 1:
        byte_index = start_bit // 8
        bit_index = start_bit % 8
        if byte_index >= len(record):
            return 0.0
        raw_bit = (record[byte_index] >> bit_index) & 0x01
        return float(raw_bit) * scale

    if bit_count == 32:
        byte_index = start_bit // 8
        if byte_index + 4 > len(record):
            return 0.0
        raw_u32 = struct.unpack_from("<I", record, byte_index)[0]
        return float(raw_u32) * scale

    # Generic: extract the relevant bits across bytes
    byte_index = start_bit // 8
    bit_offset = start_bit % 8
    needed_bytes = (bit_offset + bit_count + 7) // 8
    if byte_index + needed_bytes > len(record):
        return 0.0
    accumulated = 0
    for j in range(needed_bytes):
        accumulated |= record[byte_index + j] << (8 * j)
    mask = (1 << bit_count) - 1
    raw_val = (accumulated >> bit_offset) & mask
    return float(raw_val) * scale
