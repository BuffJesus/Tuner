"""Python ↔ C++ parity harness for the live trigger logger decoder.

Pins the C++ `live_trigger_logger_decode` (port of
`LiveTriggerLoggerService.decode`) against the Python service across:

  - tooth (4-byte u32 LE) records
  - composite (5-byte: bit flags + u32 LE refTime) records
  - record_header_len skip
  - truncated raw stops at last full record
  - rec_len == 0 -> empty rows but full metadata
  - random byte sequences
  - bit-level field extraction (bit_count == 1, == 32, generic window)

The CSV temp-file write (`to_csv_path`) is out of scope — the C++ side
only owns the byte -> typed-row decoder.
"""
from __future__ import annotations

import importlib
import random
import struct
import sys
from pathlib import Path

import pytest

from tuner.domain.ecu_definition import LoggerDefinition, LoggerRecordField
from tuner.services.live_trigger_logger_service import (
    LiveTriggerLoggerService,
    _extract_field,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CPP_BUILD_CANDIDATES = [
    _REPO_ROOT / "build" / "cpp",
    _REPO_ROOT / "build" / "cpp" / "Release",
    _REPO_ROOT / "build" / "cpp" / "Debug",
    _REPO_ROOT / "cpp" / "build",
]


def _try_import_tuner_core():
    try:
        return importlib.import_module("tuner._native.tuner_core")
    except ImportError:
        pass
    for candidate in _CPP_BUILD_CANDIDATES:
        if not candidate.exists():
            continue
        added = str(candidate)
        if added not in sys.path:
            sys.path.insert(0, added)
        try:
            return importlib.import_module("tuner_core")
        except ImportError:
            sys.path.remove(added)
            continue
    return None


_tuner_core = _try_import_tuner_core()

pytestmark = pytest.mark.skipif(
    _tuner_core is None,
    reason="tuner_core C++ extension not built — see cpp/README.md.",
)


# ---------------------------------------------------------------------------
# Helpers — translate Python LoggerDefinition <-> C++ IniLoggerDefinition.
# ---------------------------------------------------------------------------


def _to_cpp_field(py_field: LoggerRecordField):
    f = _tuner_core.IniLoggerRecordField()
    f.name = py_field.name
    f.header = py_field.header
    f.start_bit = py_field.start_bit
    f.bit_count = py_field.bit_count
    f.scale = py_field.scale
    f.units = py_field.units or ""
    return f


def _to_cpp_logger(py_logger: LoggerDefinition):
    l = _tuner_core.IniLoggerDefinition()
    l.name = py_logger.name
    l.display_name = py_logger.display_name
    l.kind = py_logger.kind
    l.start_command = py_logger.start_command or ""
    l.stop_command = py_logger.stop_command or ""
    l.data_read_command = list(py_logger.data_read_command or b"")
    l.data_read_timeout_ms = py_logger.data_read_timeout_ms or 5000
    l.continuous_read = py_logger.continuous_read
    l.record_header_len = py_logger.record_header_len
    l.record_footer_len = py_logger.record_footer_len
    l.record_len = py_logger.record_len
    l.record_count = py_logger.record_count
    l.record_fields = [_to_cpp_field(f) for f in py_logger.record_fields]
    return l


def _field(name, start_bit, bit_count, scale):
    return LoggerRecordField(
        name=name, header=name,
        start_bit=start_bit, bit_count=bit_count, scale=scale, units="",
    )


def _make_tooth_logger(record_count: int) -> LoggerDefinition:
    return LoggerDefinition(
        name="ToothLog",
        display_name="Tooth Log",
        kind="tooth",
        start_command="",
        stop_command="",
        data_read_command=b"",
        data_read_timeout_ms=5000,
        continuous_read=False,
        record_header_len=0,
        record_footer_len=0,
        record_len=4,
        record_count=record_count,
        record_fields=(_field("ToothTime", 0, 32, 1.0),),
    )


def _make_composite_logger(record_count: int) -> LoggerDefinition:
    return LoggerDefinition(
        name="CompositeLog",
        display_name="Composite Log",
        kind="composite",
        start_command="",
        stop_command="",
        data_read_command=b"",
        data_read_timeout_ms=5000,
        continuous_read=False,
        record_header_len=0,
        record_footer_len=0,
        record_len=5,
        record_count=record_count,
        record_fields=(
            _field("PriLevel",   0, 1, 1.0),
            _field("SecLevel",   1, 1, 1.0),
            _field("ThirdLevel", 2, 1, 1.0),
            _field("Trigger",    3, 1, 1.0),
            _field("Sync",       4, 1, 1.0),
            _field("Cycle",      5, 1, 1.0),
            _field("RefTime",    8, 32, 0.001),
        ),
    )


def _assert_capture_parity(py_capture, cpp_capture) -> None:
    assert py_capture.logger_name == cpp_capture.logger_name
    assert py_capture.display_name == cpp_capture.display_name
    assert py_capture.kind == cpp_capture.kind
    assert list(py_capture.columns) == list(cpp_capture.columns)
    assert py_capture.record_count == cpp_capture.record_count
    assert len(py_capture.rows) == len(cpp_capture.rows)
    for py_row, cpp_row in zip(py_capture.rows, cpp_capture.rows):
        assert set(py_row.keys()) == set(cpp_row.values.keys())
        for k, v in py_row.items():
            assert cpp_row.values[k] == pytest.approx(v)


# ---------------------------------------------------------------------------
# Tooth records
# ---------------------------------------------------------------------------


def test_tooth_decode_three_records_parity():
    logger = _make_tooth_logger(3)
    raw = b"".join(struct.pack("<I", v) for v in (1000, 1500, 1234567))
    py_capture = LiveTriggerLoggerService().decode(logger, raw)
    cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
    _assert_capture_parity(py_capture, cpp_capture)


def test_tooth_decode_empty_buffer_parity():
    logger = _make_tooth_logger(0)
    raw = b""
    py_capture = LiveTriggerLoggerService().decode(logger, raw)
    cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
    _assert_capture_parity(py_capture, cpp_capture)


def test_tooth_decode_truncated_buffer_parity():
    # Logger says 3 records but raw only carries 2 full + 2 stray bytes.
    logger = _make_tooth_logger(3)
    raw = struct.pack("<I", 1) + struct.pack("<I", 2) + b"\x03\x00"
    py_capture = LiveTriggerLoggerService().decode(logger, raw)
    cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
    _assert_capture_parity(py_capture, cpp_capture)
    assert py_capture.record_count == 2


def test_tooth_decode_with_record_header_len_parity():
    base = _make_tooth_logger(2)
    logger = LoggerDefinition(
        name=base.name, display_name=base.display_name, kind=base.kind,
        start_command=base.start_command, stop_command=base.stop_command,
        data_read_command=base.data_read_command,
        data_read_timeout_ms=base.data_read_timeout_ms,
        continuous_read=base.continuous_read,
        record_header_len=3, record_footer_len=0, record_len=4,
        record_count=2, record_fields=base.record_fields,
    )
    raw = b"\xAA\xBB\xCC" + struct.pack("<I", 5) + struct.pack("<I", 6)
    py_capture = LiveTriggerLoggerService().decode(logger, raw)
    cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
    _assert_capture_parity(py_capture, cpp_capture)


# ---------------------------------------------------------------------------
# Composite records
# ---------------------------------------------------------------------------


def test_composite_decode_single_record_parity():
    logger = _make_composite_logger(1)
    # Bits 0,1,3 set (priLevel, secLevel, trigger). RefTime = 5000us -> 5.0ms.
    raw = bytes([0b0000_1011]) + struct.pack("<I", 5000)
    py_capture = LiveTriggerLoggerService().decode(logger, raw)
    cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
    _assert_capture_parity(py_capture, cpp_capture)


def test_composite_decode_random_records_parity():
    rng = random.Random(0xC0FFEE)
    n = 64
    logger = _make_composite_logger(n)
    parts = []
    for _ in range(n):
        flags = rng.randint(0, 0x3F)  # 6 valid bits
        ref = rng.randint(0, 0xFFFF_FFFF)
        parts.append(bytes([flags]) + struct.pack("<I", ref))
    raw = b"".join(parts)
    py_capture = LiveTriggerLoggerService().decode(logger, raw)
    cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
    _assert_capture_parity(py_capture, cpp_capture)


# ---------------------------------------------------------------------------
# rec_len == 0 short-circuit
# ---------------------------------------------------------------------------


def test_rec_len_zero_returns_empty_rows_with_metadata():
    logger = LoggerDefinition(
        name="Empty", display_name="Empty Log", kind="tooth",
        start_command="", stop_command="",
        data_read_command=b"", data_read_timeout_ms=5000, continuous_read=False,
        record_header_len=0, record_footer_len=0,
        record_len=0, record_count=5,
        record_fields=(_field("X", 0, 8, 1.0),),
    )
    raw = b"\x01\x02\x03\x04\x05"
    py_capture = LiveTriggerLoggerService().decode(logger, raw)
    cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
    _assert_capture_parity(py_capture, cpp_capture)
    assert py_capture.record_count == 0
    assert list(py_capture.columns) == ["X"]


# ---------------------------------------------------------------------------
# extract_field — bit, u32, generic window
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("start_bit,bit_count,scale,record,expected", [
    # 1-bit flags within byte 0 = 0xA5 = 1010_0101
    (0,  1, 1.0, b"\xA5", 1.0),
    (1,  1, 1.0, b"\xA5", 0.0),
    (2,  1, 1.0, b"\xA5", 1.0),
    (5,  1, 1.0, b"\xA5", 1.0),
    # 1-bit flags crossing byte boundary
    (12, 1, 1.0, b"\xA5\x10", 1.0),
    (13, 1, 1.0, b"\xA5\x10", 0.0),
    # u32 LE
    (0,  32, 1.0, struct.pack("<I", 1234567890), 1234567890.0),
    (8,  32, 0.001, b"\x00" + struct.pack("<I", 5000), 5.0),
    # Generic bit window: 12-bit field at bit 4 across two bytes.
    (4, 12, 1.0, b"\x34\x12", 0x123),
    # Out-of-range -> 0.0
    (16, 1, 1.0, b"\xFF", 0.0),
    (0,  32, 1.0, b"\xFF", 0.0),
    (0,  16, 1.0, b"\xFF", 0.0),
])
def test_extract_field_parity(start_bit, bit_count, scale, record, expected):
    field = LoggerRecordField(
        name="x", header="x",
        start_bit=start_bit, bit_count=bit_count, scale=scale, units="",
    )
    py_val = _extract_field(record, field)
    cpp_val = _tuner_core.live_trigger_logger_extract_field(record, _to_cpp_field(field))
    assert py_val == pytest.approx(expected)
    assert cpp_val == pytest.approx(expected)
    assert py_val == pytest.approx(cpp_val)


def test_extract_field_random_generic_windows_parity():
    rng = random.Random(0xDECAF)
    for _ in range(60):
        # Random window 2..16 bits at random start_bit, on a 4-byte buffer.
        bit_count = rng.randint(2, 16)
        start_bit = rng.randint(0, 32 - bit_count)
        record = bytes(rng.randint(0, 255) for _ in range(4))
        scale = rng.choice([1.0, 0.5, 2.0, 0.001])
        field = LoggerRecordField(
            name="x", header="x",
            start_bit=start_bit, bit_count=bit_count, scale=scale, units="",
        )
        py_val = _extract_field(record, field)
        cpp_val = _tuner_core.live_trigger_logger_extract_field(record, _to_cpp_field(field))
        assert py_val == pytest.approx(cpp_val), (
            f"start_bit={start_bit} bit_count={bit_count} scale={scale} "
            f"record={record.hex()} py={py_val} cpp={cpp_val}"
        )


# ---------------------------------------------------------------------------
# Random end-to-end tooth + composite buffers
# ---------------------------------------------------------------------------


def test_random_tooth_buffers_parity():
    rng = random.Random(0xBADF00D)
    for _ in range(20):
        n = rng.randint(0, 32)
        logger = _make_tooth_logger(n)
        raw = b"".join(struct.pack("<I", rng.randint(0, 0xFFFF_FFFF))
                       for _ in range(n))
        py_capture = LiveTriggerLoggerService().decode(logger, raw)
        cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
        _assert_capture_parity(py_capture, cpp_capture)


def test_random_composite_buffers_parity():
    rng = random.Random(0xFEEDFACE)
    for _ in range(20):
        n = rng.randint(0, 32)
        logger = _make_composite_logger(n)
        raw = b"".join(
            bytes([rng.randint(0, 0x3F)]) + struct.pack("<I", rng.randint(0, 0xFFFF_FFFF))
            for _ in range(n)
        )
        py_capture = LiveTriggerLoggerService().decode(logger, raw)
        cpp_capture = _tuner_core.live_trigger_logger_decode(_to_cpp_logger(logger), raw)
        _assert_capture_parity(py_capture, cpp_capture)
