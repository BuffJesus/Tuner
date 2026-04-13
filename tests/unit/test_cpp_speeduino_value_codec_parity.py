"""Python ↔ C++ parity harness for tuner_core::speeduino_value_codec.

Pins the C++ raw value codec against `SpeeduinoControllerClient._data_size`,
`_encode_raw_value`, and `_decode_raw_value` byte-for-byte across every
supported data type (U08, S08, U16, S16, U32, S32, F32). Pure-logic
parity — no transport, no fixture.
"""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

import pytest

from tuner.comms.speeduino_controller_client import SpeeduinoControllerClient


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


_py_data_size = SpeeduinoControllerClient._data_size
_py_encode = SpeeduinoControllerClient._encode_raw_value
_py_decode = SpeeduinoControllerClient._decode_raw_value


_INT_TAGS = ["U08", "S08", "U16", "S16", "U32", "S32"]


@pytest.mark.parametrize("tag", _INT_TAGS + ["F32"])
def test_data_size_matches_python(tag: str) -> None:
    assert _tuner_core.speeduino_data_size_bytes(tag) == _py_data_size(tag)


@pytest.mark.parametrize(
    "tag,values",
    [
        ("U08", [0, 1, 127, 128, 200, 255]),
        ("S08", [0, -1, -128, 127, 42]),
        ("U16", [0, 1, 0xBEEF, 0xFFFF, 12345]),
        ("S16", [0, -1, -32768, 32767, -1234]),
        ("U32", [0, 1, 0xDEADBEEF, 0xFFFFFFFF, 100000]),
        ("S32", [0, -1, -2147483648, 2147483647, -100000]),
    ],
)
def test_int_encode_matches_python(tag: str, values: list[int]) -> None:
    for v in values:
        cpp = bytes(_tuner_core.speeduino_encode_raw_value_int(v, tag))
        py = _py_encode(v, tag)
        assert cpp == py, f"{tag}({v}) cpp={cpp.hex()} py={py.hex()}"


@pytest.mark.parametrize(
    "tag,values",
    [
        ("U08", [0, 1, 200, 255]),
        ("S08", [0, -1, -128, 127]),
        ("U16", [0, 0xBEEF, 0xFFFF]),
        ("S16", [0, -32768, 32767, -1234]),
        ("U32", [0, 0xDEADBEEF, 0xFFFFFFFF]),
        ("S32", [0, -2147483648, 2147483647, -100000]),
    ],
)
def test_int_decode_matches_python(tag: str, values: list[int]) -> None:
    for v in values:
        encoded = _py_encode(v, tag)
        cpp = _tuner_core.speeduino_decode_raw_value_int(list(encoded), tag)
        py = _py_decode(encoded, tag)
        assert cpp == py


@pytest.mark.parametrize(
    "value",
    [0.0, 1.0, -1.0, 3.14159, -2.71828, 1.5e10, -1.5e-10],
)
def test_f32_encode_round_trips(value: float) -> None:
    cpp = bytes(_tuner_core.speeduino_encode_raw_value_float(value, "F32"))
    py = _py_encode(value, "F32")
    assert cpp == py
    decoded_cpp = _tuner_core.speeduino_decode_raw_value_float(list(cpp), "F32")
    decoded_py = _py_decode(py, "F32")
    # Both lose precision via float32; just check they agree.
    assert decoded_cpp == pytest.approx(decoded_py)


def test_random_int_round_trip_matches_python() -> None:
    rng = random.Random(0xC0DE)
    for _ in range(200):
        tag = rng.choice(_INT_TAGS)
        size = _py_data_size(tag)
        if tag.startswith("U"):
            v = rng.randint(0, (1 << (size * 8)) - 1)
        else:
            half = 1 << (size * 8 - 1)
            v = rng.randint(-half, half - 1)
        cpp_enc = bytes(_tuner_core.speeduino_encode_raw_value_int(v, tag))
        py_enc = _py_encode(v, tag)
        assert cpp_enc == py_enc
        cpp_dec = _tuner_core.speeduino_decode_raw_value_int(list(cpp_enc), tag)
        assert cpp_dec == v


def test_unknown_tag_raises() -> None:
    with pytest.raises(Exception):
        _tuner_core.speeduino_data_size_bytes("Q42")
