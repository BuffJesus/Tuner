"""Python ↔ C++ parity harness for tuner_core::speeduino_framing.

Pins the C++ CRC32 implementation against Python's `zlib.crc32` and
the C++ frame encoder against `TcpTransport.write_framed`'s exact byte
layout. The framing helpers are pure logic, so this is a self-contained
parity test (no fixture INI required).
"""
from __future__ import annotations

import importlib
import random
import struct
import sys
import zlib
from pathlib import Path

import pytest


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


def _python_frame(payload: bytes) -> bytes:
    """Mirror of `TcpTransport.write_framed` on the Python side."""
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return struct.pack("<H", len(payload)) + payload + struct.pack("<I", crc)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"a",
        b"123456789",
        b"ABC",
        b"\x00\x01\x02\x03",
        b"S",  # Speeduino signature query
        b"r\x00\x00\x00\x00\x00\x80\x00",  # page-read command shape
        b"\xff" * 256,
    ],
)
def test_crc32_matches_zlib(payload: bytes) -> None:
    cpp = _tuner_core.speeduino_crc32(list(payload))
    py = zlib.crc32(payload) & 0xFFFFFFFF
    assert cpp == py


def test_crc32_matches_zlib_on_random_payloads() -> None:
    rng = random.Random(0xC0FFEE)
    for _ in range(50):
        n = rng.randint(0, 4096)
        payload = bytes(rng.getrandbits(8) for _ in range(n))
        cpp = _tuner_core.speeduino_crc32(list(payload))
        py = zlib.crc32(payload) & 0xFFFFFFFF
        assert cpp == py, f"CRC mismatch on {n}-byte payload"


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"S",
        b"ABC",
        b"\x00\x01\x02\x03\x04\x05",
        bytes(range(256)),
    ],
)
def test_encode_frame_matches_tcp_transport(payload: bytes) -> None:
    cpp_frame = bytes(_tuner_core.speeduino_encode_frame(list(payload)))
    py_frame = _python_frame(payload)
    assert cpp_frame == py_frame


def test_encode_frame_round_trips_random_payloads() -> None:
    rng = random.Random(0xBEEF)
    for _ in range(25):
        n = rng.randint(0, 2048)
        payload = bytes(rng.getrandbits(8) for _ in range(n))
        cpp_frame = bytes(_tuner_core.speeduino_encode_frame(list(payload)))
        assert cpp_frame == _python_frame(payload)
        decoded = _tuner_core.speeduino_decode_frame(list(cpp_frame))
        assert bytes(decoded.payload) == payload
        assert decoded.crc_valid is True
        assert decoded.bytes_consumed == len(cpp_frame)


def test_decode_frame_flags_corrupted_crc() -> None:
    payload = b"hello"
    frame = bytearray(_python_frame(payload))
    frame[-1] ^= 0xFF
    decoded = _tuner_core.speeduino_decode_frame(list(frame))
    assert bytes(decoded.payload) == payload
    assert decoded.crc_valid is False


def test_decode_frame_consumes_only_declared_length() -> None:
    payload = b"\x10\x20"
    frame = _python_frame(payload) + b"trailing-bytes"
    decoded = _tuner_core.speeduino_decode_frame(list(frame))
    assert bytes(decoded.payload) == payload
    assert decoded.bytes_consumed == 2 + len(payload) + 4
