"""Python ↔ C++ parity harness for tuner_core::board_detection.

Pins the C++ regex matchers against
`BoardDetectionService._detect_from_text` byte-for-byte and the
capability fallback against `detect_from_capabilities`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tuner.domain.firmware import BoardFamily
from tuner.services.board_detection_service import BoardDetectionService


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
    reason="tuner_core C++ extension not built.",
)


_py = BoardDetectionService()


def _py_to_str(family):
    return family.name if family is not None else None


def _cpp_to_str(family):
    return family.name if family is not None else None


@pytest.mark.parametrize(
    "text",
    [
        # Teensy 4.1
        "speeduino 202501-T41",
        "speeduino 202501-T41-U16P2",
        "Teensy 4.1 build",
        "teensy_4.1",
        "TEENSY-4.1",
        "teensy41 build",
        "Teensy41",
        # Teensy 3.5 / 3.6
        "Teensy 3.5",
        "Teensy 3.6",
        "T35",
        "T36",
        "TEENSY 3.5 alt",
        # STM32 F407
        "STM32F407",
        "Black Pill F407 build",
        "DFU mode build",
        # ATmega2560
        "ATmega2560",
        "MEGA2560 build",
        "Arduino Mega",
        "Arduino   Mega",
        # Negatives
        "ESP32-S3",
        "speeduino",
        "RP2040",
        "",
        # Edge: similar but not matching
        "T42",
        "TEENSY 3.0",
        "STM32F4",
    ],
)
def test_detect_from_text_matches_python(text):
    py = _py._detect_from_text(text)
    cpp = _tuner_core.board_detect_from_text(text)
    assert _py_to_str(py) == _cpp_to_str(cpp)


def _py_detect_from_capabilities(experimental_u16p2, signature):
    caps = Mock()
    caps.experimental_u16p2 = experimental_u16p2
    return _py.detect_from_capabilities(caps, signature=signature or None)


@pytest.mark.parametrize(
    "experimental_u16p2,signature",
    [
        (False, ""),
        (True, ""),
        (False, "speeduino 202501-T41"),
        (True, "speeduino 202501-T36"),
        (False, "ESP32-S3"),
        (True, "ESP32-S3"),
        (False, "Teensy 3.5"),
        (True, "stm32f407"),
    ],
)
def test_detect_from_capabilities_matches_python(experimental_u16p2, signature):
    py = _py_detect_from_capabilities(experimental_u16p2, signature)
    cpp = _tuner_core.board_detect_from_capabilities(experimental_u16p2, signature)
    assert _py_to_str(py) == _cpp_to_str(cpp)
