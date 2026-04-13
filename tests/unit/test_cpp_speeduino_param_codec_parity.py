"""Python ↔ C++ parity harness for tuner_core::speeduino_param_codec.

Pins the C++ scalar/table parameter codec against
`SpeeduinoControllerClient._encode_scalar`, `_decode_scalar`,
`_encode_table`, and `_decode_table` byte-for-byte across scale,
translate, and bit-field positioning.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tuner.comms.speeduino_controller_client import SpeeduinoControllerClient
from tuner.domain.ecu_definition import (
    ScalarParameterDefinition,
    TableDefinition,
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


# All four target methods are bound methods, but they only call
# `self._data_size` / `self._encode_raw_value` / `self._decode_raw_value`,
# all of which are `@staticmethod`s on the class. A `Mock` is enough
# to satisfy the `self` slot without instantiating a real client.
_self = Mock()
_self._data_size = SpeeduinoControllerClient._data_size
_self._encode_raw_value = SpeeduinoControllerClient._encode_raw_value
_self._decode_raw_value = SpeeduinoControllerClient._decode_raw_value


def _py_encode_scalar(definition, value, page):
    return SpeeduinoControllerClient._encode_scalar(
        _self, definition, value, bytearray(page)
    )


def _py_decode_scalar(definition, page):
    return SpeeduinoControllerClient._decode_scalar(
        _self, definition, bytes(page)
    )


def _py_encode_table(table, values):
    return SpeeduinoControllerClient._encode_table(_self, table, values)


def _py_decode_table(table, page):
    return SpeeduinoControllerClient._decode_table(
        _self, table, bytes(page)
    )


def _cpp_encode_scalar(d: ScalarParameterDefinition, value, page) -> bytes:
    return bytes(
        _tuner_core.speeduino_encode_scalar(
            d.offset,
            d.data_type,
            d.scale,
            d.translate,
            d.bit_offset if d.bit_offset is not None else -1,
            d.bit_length if d.bit_length is not None else -1,
            float(value),
            list(page),
        )
    )


def _cpp_decode_scalar(d: ScalarParameterDefinition, page) -> float:
    return _tuner_core.speeduino_decode_scalar(
        d.offset,
        d.data_type,
        d.scale,
        d.translate,
        d.bit_offset if d.bit_offset is not None else -1,
        d.bit_length if d.bit_length is not None else -1,
        list(page),
    )


def _cpp_encode_table(t: TableDefinition, values) -> bytes:
    return bytes(
        _tuner_core.speeduino_encode_table(
            t.offset, t.data_type, t.scale, t.translate,
            t.rows, t.columns, [float(v) for v in values],
        )
    )


def _cpp_decode_table(t: TableDefinition, page) -> list[float]:
    return list(
        _tuner_core.speeduino_decode_table(
            t.offset, t.data_type, t.scale, t.translate,
            t.rows, t.columns, list(page),
        )
    )


# ---------------------------------------------------------------------------
# Scalar — non-bit-field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "data_type,scale,translate,value",
    [
        ("U08", 0.1, 0.0, 12.5),
        ("U08", 1.0, 0.0, 200),
        ("U08", 1.8, -22.23, 75.0),  # IAT shape
        ("S08", 1.0, 0.0, -42),
        ("U16", 1.0, 0.0, 12345),
        ("S16", 0.5, 0.0, -1234.5),
        ("U32", 1.0, 0.0, 100000),
    ],
)
def test_encode_scalar_matches_python(data_type, scale, translate, value):
    d = ScalarParameterDefinition(
        name="x", data_type=data_type, page=1, offset=4,
        scale=scale, translate=translate,
    )
    page = bytearray(32)
    cpp = _cpp_encode_scalar(d, value, page)
    py = _py_encode_scalar(d, value, page)
    assert cpp == py


@pytest.mark.parametrize(
    "data_type,scale,translate,raw_bytes",
    [
        ("U08", 0.1, 0.0, b"\x7d"),       # 125 → 12.5
        ("U08", 1.8, -22.23, b"\x7d"),    # IAT shape
        ("S08", 1.0, 0.0, b"\xd6"),       # -42
        ("U16", 1.0, 0.0, b"\x39\x30"),   # 12345
        ("S16", 0.5, 0.0, b"\x2e\xfb"),   # -1234
        ("U32", 1.0, 0.0, b"\xa0\x86\x01\x00"),
    ],
)
def test_decode_scalar_matches_python(data_type, scale, translate, raw_bytes):
    d = ScalarParameterDefinition(
        name="x", data_type=data_type, page=1, offset=2,
        scale=scale, translate=translate,
    )
    page = bytearray(16)
    page[2 : 2 + len(raw_bytes)] = raw_bytes
    cpp = _cpp_decode_scalar(d, page)
    py = _py_decode_scalar(d, page)
    assert cpp == pytest.approx(py)


# ---------------------------------------------------------------------------
# Scalar — bit-field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "page_byte,bit_offset,bit_length,new_value,expected_byte",
    [
        (0b1100_0001, 2, 1, 1, 0b1100_0101),
        (0b1111_1111, 4, 2, 0, 0b1100_1111),
        (0b0000_0000, 0, 8, 0xAB, 0xAB),
    ],
)
def test_encode_scalar_bit_field_matches_python(
    page_byte, bit_offset, bit_length, new_value, expected_byte
):
    d = ScalarParameterDefinition(
        name="x", data_type="U08", page=1, offset=3,
        bit_offset=bit_offset, bit_length=bit_length,
    )
    page = bytearray(8)
    page[3] = page_byte
    cpp = _cpp_encode_scalar(d, new_value, page)
    py = _py_encode_scalar(d, new_value, page)
    assert cpp == py
    assert cpp == bytes([expected_byte])


@pytest.mark.parametrize(
    "page_byte,bit_offset,bit_length,expected",
    [
        (0b0001_1000, 3, 2, 3),
        (0b0000_0001, 0, 1, 1),
        (0b1010_0000, 5, 3, 5),
    ],
)
def test_decode_scalar_bit_field_matches_python(
    page_byte, bit_offset, bit_length, expected
):
    d = ScalarParameterDefinition(
        name="x", data_type="U08", page=1, offset=0,
        bit_offset=bit_offset, bit_length=bit_length,
    )
    page = bytearray([page_byte])
    cpp = _cpp_decode_scalar(d, page)
    py = _py_decode_scalar(d, page)
    assert cpp == py == expected


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------

def _make_table(data_type="U08", scale=1.0, translate=0.0, rows=2, columns=3):
    return TableDefinition(
        name="t", rows=rows, columns=columns, page=1, offset=0,
        data_type=data_type, scale=scale, translate=translate,
    )


@pytest.mark.parametrize(
    "data_type,scale,translate,values",
    [
        ("U08", 1.0, 0.0, [0, 50, 100, 150, 200, 255]),
        ("U08", 0.1, 0.0, [1.5, 2.5, 3.5, 4.5, 5.5, 25.5]),
        ("U16", 1.0, 0.0, [0, 1000, 5000, 32000, 50000, 65535]),
        ("S16", 1.0, 0.0, [-32000, -1000, 0, 1000, 32000, -1]),
    ],
)
def test_encode_table_matches_python(data_type, scale, translate, values):
    t = _make_table(data_type=data_type, scale=scale, translate=translate)
    cpp = _cpp_encode_table(t, values)
    py = _py_encode_table(t, values)
    assert cpp == py


@pytest.mark.parametrize(
    "data_type,scale,translate",
    [
        ("U08", 1.0, 0.0),
        ("U08", 0.5, -10.0),
        ("U16", 0.1, 0.0),
        ("S16", 1.0, 0.0),
    ],
)
def test_decode_table_matches_python(data_type, scale, translate):
    t = _make_table(data_type=data_type, scale=scale, translate=translate)
    # Build a synthetic page with non-zero raw bytes covering the
    # whole table area.
    item_size = SpeeduinoControllerClient._data_size(data_type)
    n = t.rows * t.columns * item_size
    page = bytearray((i * 13 + 7) & 0xFF for i in range(n + 8))
    cpp = _cpp_decode_table(t, page)
    py = _py_decode_table(t, page)
    assert len(cpp) == len(py)
    for cv, pv in zip(cpp, py):
        assert cv == pytest.approx(pv)


def test_encode_table_round_trip_via_decode_matches_python():
    t = _make_table(data_type="U08", scale=0.1, translate=0.0, rows=4, columns=4)
    values = [(i % 256) * 0.1 for i in range(16)]
    cpp_bytes = _cpp_encode_table(t, values)
    py_bytes = _py_encode_table(t, values)
    assert cpp_bytes == py_bytes
    cpp_dec = _cpp_decode_table(t, cpp_bytes)
    py_dec = _py_decode_table(t, py_bytes)
    for cv, pv in zip(cpp_dec, py_dec):
        assert cv == pytest.approx(pv)
