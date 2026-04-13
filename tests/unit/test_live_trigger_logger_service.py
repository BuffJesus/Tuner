"""Unit tests for LiveTriggerLoggerService.

Tests cover decode logic for both tooth and composite record formats using
synthetic raw byte buffers constructed from known values.
"""
from __future__ import annotations

import csv
import struct

import pytest

from tuner.domain.ecu_definition import LoggerDefinition, LoggerRecordField
from tuner.services.live_trigger_logger_service import LiveTriggerLoggerService, TriggerLogCapture


# ---------------------------------------------------------------------------
# Helpers — build minimal LoggerDefinition fixtures
# ---------------------------------------------------------------------------

def _tooth_logger(record_count: int = 3) -> LoggerDefinition:
    return LoggerDefinition(
        name="tooth",
        display_name="Tooth Logger",
        kind="tooth",
        start_command="H",
        stop_command="h",
        data_read_command=b"T\x00\x00\x01\xfc\x00\x01\xfc",
        data_read_timeout_ms=5000,
        continuous_read=True,
        record_header_len=0,
        record_footer_len=0,
        record_len=4,
        record_count=record_count,
        record_fields=(
            LoggerRecordField(
                name="toothTime", header="ToothTime",
                start_bit=0, bit_count=32, scale=1.0, units="uS",
            ),
        ),
    )


def _composite_logger(record_count: int = 3) -> LoggerDefinition:
    return LoggerDefinition(
        name="compositeLogger",
        display_name="Composite Logger",
        kind="composite",
        start_command="J",
        stop_command="j",
        data_read_command=b"T\x00\x00\x00\x00\x00\x02\x7b",
        data_read_timeout_ms=5000,
        continuous_read=True,
        record_header_len=0,
        record_footer_len=0,
        record_len=5,
        record_count=record_count,
        record_fields=(
            LoggerRecordField("priLevel",   "PriLevel",   0, 1, 1.0, "Flag"),
            LoggerRecordField("secLevel",   "SecLevel",   1, 1, 1.0, "Flag"),
            LoggerRecordField("ThirdLevel", "ThirdLevel", 2, 1, 1.0, "Flag"),
            LoggerRecordField("trigger",    "Trigger",    3, 1, 1.0, "Flag"),
            LoggerRecordField("sync",       "Sync",       4, 1, 1.0, "Flag"),
            LoggerRecordField("cycle",      "Cycle",      5, 1, 1.0, "Flag"),
            LoggerRecordField("refTime",    "RefTime",    8, 32, 0.001, "ms"),
        ),
    )


def _build_tooth_raw(times_us: list[int]) -> bytes:
    """Build raw bytes for a tooth log from a list of microsecond values."""
    buf = bytearray()
    for t in times_us:
        buf.extend(struct.pack("<I", t))
    return bytes(buf)


def _build_composite_raw(records: list[tuple[int, int]]) -> bytes:
    """Build raw bytes for a composite log.

    Each record is (flags_byte, ref_time_us).  The flags byte maps directly
    to byte 0 of each 5-byte record; ref_time is stored at byte 1 as u32 LE.
    """
    buf = bytearray()
    for flags, ref_time in records:
        buf.append(flags & 0xFF)
        buf.extend(struct.pack("<I", ref_time))
    return bytes(buf)


# ---------------------------------------------------------------------------
# Tooth logger decode
# ---------------------------------------------------------------------------

def test_tooth_decode_returns_capture(tmp_path) -> None:
    svc = LiveTriggerLoggerService()
    raw = _build_tooth_raw([1000, 2000, 3000])
    capture = svc.decode(_tooth_logger(3), raw)
    assert isinstance(capture, TriggerLogCapture)


def test_tooth_decode_record_count(tmp_path) -> None:
    svc = LiveTriggerLoggerService()
    raw = _build_tooth_raw([500, 750, 1250])
    capture = svc.decode(_tooth_logger(3), raw)
    assert capture.record_count == 3


def test_tooth_decode_values(tmp_path) -> None:
    svc = LiveTriggerLoggerService()
    times = [1111, 2222, 3333]
    raw = _build_tooth_raw(times)
    capture = svc.decode(_tooth_logger(3), raw)
    for i, row in enumerate(capture.rows):
        assert row["ToothTime"] == pytest.approx(float(times[i]))


def test_tooth_decode_column_name(tmp_path) -> None:
    svc = LiveTriggerLoggerService()
    capture = svc.decode(_tooth_logger(1), _build_tooth_raw([100]))
    assert capture.columns == ("ToothTime",)


def test_tooth_decode_scale_applied() -> None:
    # scale = 1.0 → value unchanged
    svc = LiveTriggerLoggerService()
    capture = svc.decode(_tooth_logger(1), _build_tooth_raw([99999]))
    assert capture.rows[0]["ToothTime"] == pytest.approx(99999.0)


def test_tooth_decode_large_value() -> None:
    svc = LiveTriggerLoggerService()
    large = 0xFFFFFF  # 24-bit max just under u32 limit
    capture = svc.decode(_tooth_logger(1), _build_tooth_raw([large]))
    assert capture.rows[0]["ToothTime"] == pytest.approx(float(large))


def test_tooth_decode_truncated_data_stops_early() -> None:
    """If raw data is shorter than record_count × record_len, stop at the last complete record."""
    svc = LiveTriggerLoggerService()
    # 3 records declared, only 2 worth of bytes provided
    raw = _build_tooth_raw([10, 20])  # 8 bytes, not 12
    capture = svc.decode(_tooth_logger(3), raw)
    assert capture.record_count == 2


def test_tooth_decode_metadata(tmp_path) -> None:
    svc = LiveTriggerLoggerService()
    capture = svc.decode(_tooth_logger(1), _build_tooth_raw([1]))
    assert capture.logger_name == "tooth"
    assert capture.display_name == "Tooth Logger"
    assert capture.kind == "tooth"


def test_tooth_empty_raw_returns_zero_records() -> None:
    svc = LiveTriggerLoggerService()
    capture = svc.decode(_tooth_logger(3), b"")
    assert capture.record_count == 0


# ---------------------------------------------------------------------------
# Composite logger decode
# ---------------------------------------------------------------------------

def test_composite_decode_record_count() -> None:
    svc = LiveTriggerLoggerService()
    records = [(0b000001, 1000), (0b000010, 2000), (0b000100, 3000)]
    raw = _build_composite_raw(records)
    capture = svc.decode(_composite_logger(3), raw)
    assert capture.record_count == 3


def test_composite_decode_priLevel_flag() -> None:
    svc = LiveTriggerLoggerService()
    # priLevel = bit 0 of flags byte
    raw = _build_composite_raw([(0b00000001, 500)])
    capture = svc.decode(_composite_logger(1), raw)
    assert capture.rows[0]["PriLevel"] == pytest.approx(1.0)


def test_composite_decode_secLevel_flag() -> None:
    svc = LiveTriggerLoggerService()
    raw = _build_composite_raw([(0b00000010, 500)])
    capture = svc.decode(_composite_logger(1), raw)
    assert capture.rows[0]["SecLevel"] == pytest.approx(1.0)
    assert capture.rows[0]["PriLevel"] == pytest.approx(0.0)


def test_composite_decode_sync_flag() -> None:
    svc = LiveTriggerLoggerService()
    # sync = bit 4
    raw = _build_composite_raw([(0b00010000, 500)])
    capture = svc.decode(_composite_logger(1), raw)
    assert capture.rows[0]["Sync"] == pytest.approx(1.0)
    assert capture.rows[0]["PriLevel"] == pytest.approx(0.0)


def test_composite_decode_multiple_flags() -> None:
    svc = LiveTriggerLoggerService()
    # priLevel(0) + trigger(3) + sync(4) set
    flags = 0b00011001
    raw = _build_composite_raw([(flags, 100)])
    capture = svc.decode(_composite_logger(1), raw)
    assert capture.rows[0]["PriLevel"] == pytest.approx(1.0)
    assert capture.rows[0]["Trigger"] == pytest.approx(1.0)
    assert capture.rows[0]["Sync"] == pytest.approx(1.0)
    assert capture.rows[0]["SecLevel"] == pytest.approx(0.0)


def test_composite_decode_refTime_scaled() -> None:
    svc = LiveTriggerLoggerService()
    # refTime scale = 0.001 → microseconds × 0.001 = milliseconds
    raw = _build_composite_raw([(0, 5000)])
    capture = svc.decode(_composite_logger(1), raw)
    assert capture.rows[0]["RefTime"] == pytest.approx(5.0)  # 5000 × 0.001


def test_composite_decode_refTime_large() -> None:
    svc = LiveTriggerLoggerService()
    raw = _build_composite_raw([(0, 1_000_000)])
    capture = svc.decode(_composite_logger(1), raw)
    assert capture.rows[0]["RefTime"] == pytest.approx(1000.0)


def test_composite_decode_columns(tmp_path) -> None:
    svc = LiveTriggerLoggerService()
    capture = svc.decode(_composite_logger(1), _build_composite_raw([(0, 0)]))
    assert "PriLevel" in capture.columns
    assert "RefTime" in capture.columns
    assert len(capture.columns) == 7


def test_composite_decode_truncated_stops_early() -> None:
    svc = LiveTriggerLoggerService()
    raw = _build_composite_raw([(0b01, 100), (0b10, 200)])  # 10 bytes, 3 declared
    capture = svc.decode(_composite_logger(3), raw)
    assert capture.record_count == 2


# ---------------------------------------------------------------------------
# to_csv_path round-trip
# ---------------------------------------------------------------------------

def test_to_csv_path_creates_file() -> None:
    svc = LiveTriggerLoggerService()
    capture = svc.decode(_tooth_logger(2), _build_tooth_raw([111, 222]))
    path = capture.to_csv_path()
    assert path.exists()
    path.unlink(missing_ok=True)


def test_to_csv_path_has_correct_header() -> None:
    svc = LiveTriggerLoggerService()
    capture = svc.decode(_tooth_logger(1), _build_tooth_raw([500]))
    path = capture.to_csv_path()
    try:
        with open(path) as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == ["ToothTime"]
    finally:
        path.unlink(missing_ok=True)


def test_to_csv_path_preserves_values() -> None:
    svc = LiveTriggerLoggerService()
    times = [1234, 5678]
    capture = svc.decode(_tooth_logger(2), _build_tooth_raw(times))
    path = capture.to_csv_path()
    try:
        with open(path) as fh:
            rows = list(csv.DictReader(fh))
        assert float(rows[0]["ToothTime"]) == pytest.approx(1234.0)
        assert float(rows[1]["ToothTime"]) == pytest.approx(5678.0)
    finally:
        path.unlink(missing_ok=True)


def test_to_csv_path_composite_values() -> None:
    svc = LiveTriggerLoggerService()
    capture = svc.decode(_composite_logger(2), _build_composite_raw([(0b01, 2000), (0b10, 4000)]))
    path = capture.to_csv_path()
    try:
        with open(path) as fh:
            rows = list(csv.DictReader(fh))
        assert float(rows[0]["PriLevel"]) == pytest.approx(1.0)
        assert float(rows[1]["SecLevel"]) == pytest.approx(1.0)
        assert float(rows[0]["RefTime"]) == pytest.approx(2.0)   # 2000 × 0.001
        assert float(rows[1]["RefTime"]) == pytest.approx(4.0)
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Zero record_len edge case
# ---------------------------------------------------------------------------

def test_zero_record_len_returns_empty() -> None:
    logger = LoggerDefinition(
        name="empty", display_name="Empty", kind="tooth",
        start_command="H", stop_command="h",
        data_read_command=b"T",
        data_read_timeout_ms=1000, continuous_read=False,
        record_header_len=0, record_footer_len=0,
        record_len=0, record_count=0,
        record_fields=(),
    )
    svc = LiveTriggerLoggerService()
    capture = svc.decode(logger, b"\x01\x02\x03\x04")
    assert capture.record_count == 0
