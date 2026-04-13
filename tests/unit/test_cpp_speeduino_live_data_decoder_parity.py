"""Python ↔ C++ parity harness for tuner_core::speeduino_live_data_decoder.

`SpeeduinoControllerClient.read_runtime` issues a `_runtime_request`
under the hood, which needs a live transport. This parity test
side-steps that by exercising the *decode loop* directly: it builds
a list of `ScalarParameterDefinition` channels (the same shape
`read_runtime` iterates), runs the C++ decoder, and compares against
the equivalent Python list comprehension over `_decode_scalar`.

Loaded against the production INI fixture so the channel set is real
(>100 channels covering U08/S08/U16/S16/F32 with mixed scale and
translate).
"""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tuner.comms.speeduino_controller_client import SpeeduinoControllerClient
from tuner.parsers.ini_parser import IniParser


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CPP_BUILD_CANDIDATES = [
    _REPO_ROOT / "build" / "cpp",
    _REPO_ROOT / "build" / "cpp" / "Release",
    _REPO_ROOT / "build" / "cpp" / "Debug",
    _REPO_ROOT / "cpp" / "build",
]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


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

pytestmark = [
    pytest.mark.skipif(
        _tuner_core is None,
        reason="tuner_core C++ extension not built.",
    ),
    pytest.mark.skipif(
        not _PRODUCTION_INI.exists(),
        reason="production INI fixture not available",
    ),
]


_self = Mock()
_self._data_size = SpeeduinoControllerClient._data_size
_self._encode_raw_value = SpeeduinoControllerClient._encode_raw_value
_self._decode_raw_value = SpeeduinoControllerClient._decode_raw_value


def _py_decode_scalar(definition, payload):
    return SpeeduinoControllerClient._decode_scalar(_self, definition, bytes(payload))


def _channels_from_definition(defn):
    """Filter to scalar channels with a numeric offset and a known data type.

    Bit-field output channels live in the same list but the runtime
    decode loop in `read_runtime` already filters them via the
    `if field.offset is not None` guard. We mirror that here.
    """
    out = []
    for f in defn.output_channel_definitions:
        if f.offset is None:
            continue
        try:
            SpeeduinoControllerClient._data_size(f.data_type)
        except RuntimeError:
            continue
        out.append(f)
    return out


def _build_arrays(channels):
    names = [c.name for c in channels]
    units = [c.units or "" for c in channels]
    offsets = [int(c.offset) for c in channels]
    data_types = [c.data_type for c in channels]
    scales = [c.scale for c in channels]
    translates = [c.translate for c in channels]
    bit_offsets = [c.bit_offset if c.bit_offset is not None else -1 for c in channels]
    bit_lengths = [c.bit_length if c.bit_length is not None else -1 for c in channels]
    return names, units, offsets, data_types, scales, translates, bit_offsets, bit_lengths


@pytest.fixture(scope="module")
def production_channels():
    defn = IniParser().parse(_PRODUCTION_INI)
    return _channels_from_definition(defn)


def test_runtime_packet_size_matches_python(production_channels):
    py_size = max(
        c.offset + SpeeduinoControllerClient._data_size(c.data_type)
        for c in production_channels
    )
    args = _build_arrays(production_channels)
    cpp_size = _tuner_core.speeduino_runtime_packet_size(*args)
    assert cpp_size == py_size


def test_decode_runtime_packet_matches_python_on_zero_payload(production_channels):
    args = _build_arrays(production_channels)
    packet_len = _tuner_core.speeduino_runtime_packet_size(*args)
    payload = bytes(packet_len)
    cpp_values = _tuner_core.speeduino_decode_runtime_packet(*args, list(payload))
    assert len(cpp_values) == len(production_channels)
    for cv, ch in zip(cpp_values, production_channels):
        py_value = _py_decode_scalar(ch, payload)
        assert cv.name == ch.name
        assert cv.units == (ch.units or "")
        assert cv.value == pytest.approx(float(py_value))


def test_decode_runtime_packet_matches_python_on_random_payload(production_channels):
    args = _build_arrays(production_channels)
    packet_len = _tuner_core.speeduino_runtime_packet_size(*args)
    rng = random.Random(0xC0FFEE)
    payload = bytes(rng.getrandbits(8) for _ in range(packet_len))
    cpp_values = _tuner_core.speeduino_decode_runtime_packet(*args, list(payload))
    assert len(cpp_values) == len(production_channels)
    mismatches = []
    for cv, ch in zip(cpp_values, production_channels):
        py_value = float(_py_decode_scalar(ch, payload))
        if cv.value != pytest.approx(py_value):
            mismatches.append(f"{ch.name}: cpp={cv.value} py={py_value}")
    assert not mismatches, "\n".join(mismatches[:20])


def test_decode_runtime_packet_preserves_input_order(production_channels):
    args = _build_arrays(production_channels)
    packet_len = _tuner_core.speeduino_runtime_packet_size(*args)
    cpp_values = _tuner_core.speeduino_decode_runtime_packet(
        *args, list(bytes(packet_len))
    )
    assert [v.name for v in cpp_values] == [c.name for c in production_channels]
