"""Python ↔ C++ parity harness for tuner_core::speeduino_protocol.

Pins the C++ command-shape helpers byte-for-byte against
`SpeeduinoControllerClient`'s static command builders. The Python side
exposes `_page_request` (classmethod) and `_runtime_request` /
`burn` (instance methods we exercise indirectly via the same byte
math). All command shapes are pure logic — no transport, no fixture.
"""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

import pytest

from tuner.comms.speeduino_controller_client import (
    SEND_OUTPUT_CHANNELS,
    SpeeduinoControllerClient,
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


# `_page_request` is a static method on the Python client; calling it
# directly avoids needing a live connection.
_py_page_request = SpeeduinoControllerClient._page_request


def _py_runtime_request(offset: int, length: int) -> bytes:
    """Mirror of `SpeeduinoControllerClient._runtime_request` byte math.

    The Python instance method actually sends the bytes; we re-build
    the same shape here so the parity test stays I/O-free.
    """
    return bytes(
        (
            ord("r"),
            0x00,
            SEND_OUTPUT_CHANNELS,
            offset & 0xFF,
            (offset >> 8) & 0xFF,
            length & 0xFF,
            (length >> 8) & 0xFF,
        )
    )


def _py_burn_request(burn_char: str, page: int) -> bytes:
    """Mirror of the bytes `SpeeduinoControllerClient.burn` sends per page."""
    return bytes((ord(burn_char), 0x00, page & 0xFF))


@pytest.mark.parametrize(
    "command,page,offset,length",
    [
        ("p", 0, 0, 0),
        ("p", 1, 0, 256),
        ("p", 4, 256, 256),  # afrTable lastOffset shape
        ("p", 14, 0xFEDC, 0xBA98),
        ("M", 1, 0, 16),
        ("M", 7, 1024, 64),
    ],
)
def test_page_request_matches_python(
    command: str, page: int, offset: int, length: int
) -> None:
    cpp = bytes(
        _tuner_core.speeduino_page_request(command, page, offset, length)
    )
    py = _py_page_request(command, page, offset, length)
    assert cpp == py


@pytest.mark.parametrize(
    "page,offset,payload_len",
    [
        (1, 0, 0),
        (1, 0, 1),
        (1, 16, 32),
        (4, 256, 251),  # blocking factor sized chunk
        (7, 0, 256),
    ],
)
def test_page_write_request_matches_python(
    page: int, offset: int, payload_len: int
) -> None:
    rng = random.Random(0xC0DE + payload_len)
    payload = bytes(rng.getrandbits(8) for _ in range(payload_len))
    cpp = bytes(
        _tuner_core.speeduino_page_write_request(page, offset, list(payload), "M")
    )
    # Python builds the write as page_request(...) + chunk
    py = _py_page_request("M", page, offset, payload_len) + payload
    assert cpp == py


@pytest.mark.parametrize(
    "offset,length",
    [
        (0, 0),
        (0, 0x80),
        (8, 0x60),
        (0xABCD, 0x40),
        (0xFFFF, 0xFFFF),
    ],
)
def test_runtime_request_matches_python(offset: int, length: int) -> None:
    cpp = bytes(_tuner_core.speeduino_runtime_request(offset, length))
    py = _py_runtime_request(offset, length)
    assert cpp == py


@pytest.mark.parametrize(
    "burn_char,page",
    [
        ("b", 0),
        ("b", 1),
        ("b", 14),
        ("B", 7),
    ],
)
def test_burn_request_matches_python(burn_char: str, page: int) -> None:
    cpp = bytes(_tuner_core.speeduino_burn_request(page, burn_char))
    py = _py_burn_request(burn_char, page)
    assert cpp == py


def test_runtime_request_uses_send_output_channels_selector() -> None:
    req = bytes(_tuner_core.speeduino_runtime_request(0, 0))
    assert req[2] == SEND_OUTPUT_CHANNELS == 0x30
