"""Python ↔ C++ parity harness for flash target classifier logic.

Pins the C++ classifier against the Python `FlashTargetDetectionService`
private helpers (`_normalize_hex`, `_teensy_identity_from_pid_or_bcd`,
and the per-port classification branches) across every VID/PID/BCD
combination the Python side recognises.

I/O (`serial.tools.list_ports` / `usb.core`) is out of scope — the
C++ classifier takes normalized strings as inputs, same as the Python
private helpers do after normalization.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.domain.firmware import BoardFamily, DetectedFlashTarget
from tuner.services.flash_target_detection_service import FlashTargetDetectionService


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
# normalize_hex parity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("0x2341", "2341"),
    # Python's `.removeprefix("0x")` is case-sensitive — uppercase
    # `0X` is NOT stripped, and the subsequent `.upper()` produces
    # `0X16C0`. Mirror this quirk for parity.
    ("0X16c0", "0X16C0"),
    ("16c0", "16C0"),
    ("  0483  ", "0483"),
    # Python returns empty string for empty input (not None) —
    # `"".strip().removeprefix("0x").upper()` → `""`.
    ("", ""),
    ("   ", ""),
])
def test_normalize_hex_string_matches_python(raw, expected):
    py = FlashTargetDetectionService._normalize_hex(raw)
    cpp = _tuner_core.normalize_hex(raw)
    assert py == expected
    assert cpp == expected


# ---------------------------------------------------------------------------
# Teensy identity parity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pid,bcd,expected_family,expected_label", [
    # bcdDevice → family
    ("",     "0276", BoardFamily.TEENSY35, "3.5"),
    ("",     "0277", BoardFamily.TEENSY36, "3.6"),
    ("",     "0280", BoardFamily.TEENSY41, "4.1"),
    # serial PID → always TEENSY41
    ("0483", "",     BoardFamily.TEENSY41, "4.1"),
    ("0484", "",     BoardFamily.TEENSY41, "4.1"),
    ("0485", "",     BoardFamily.TEENSY41, "4.1"),
    ("0486", "",     BoardFamily.TEENSY41, "4.1"),
])
def test_teensy_identity_parity(pid, bcd, expected_family, expected_label):
    py_id = FlashTargetDetectionService._teensy_identity_from_pid_or_bcd(
        pid or None, bcd or None
    )
    cpp_id = _tuner_core.teensy_identity_from_pid_or_bcd(pid, bcd)
    assert py_id is not None
    assert cpp_id is not None
    assert py_id.board_family.value == str(cpp_id.board_family).split(".")[-1]
    assert py_id.label == cpp_id.label
    # Cross-check against the parametrize expectations.
    assert py_id.board_family == expected_family
    assert py_id.label == expected_label


def test_teensy_identity_unknown_returns_none():
    assert FlashTargetDetectionService._teensy_identity_from_pid_or_bcd("FFFF", "FFFF") is None
    cpp = _tuner_core.teensy_identity_from_pid_or_bcd("FFFF", "FFFF")
    assert cpp is None


# ---------------------------------------------------------------------------
# Per-port serial classification parity — stand up a fake pyserial port
# and feed it through the Python `_detect_serial_targets` helper, then
# call the C++ `classify_serial_port` with the same pre-normalized
# inputs and compare the resulting DetectedFlashTarget fields.
# ---------------------------------------------------------------------------

class _FakePort:
    """Duck-type for `serial.tools.list_ports_common.ListPortInfo`."""
    def __init__(self, vid, pid, device, description):
        self.vid = int(vid, 16) if vid else None
        self.pid = int(pid, 16) if pid else None
        self.device = device
        self.description = description


@pytest.mark.parametrize("vid_hex,pid_hex,device,description,expected_family,should_match", [
    # Arduino Mega official
    ("2341", "0010", "COM3", "Arduino Mega 2560", BoardFamily.ATMEGA2560, True),
    ("2341", "0042", "COM4", "Arduino Mega",      BoardFamily.ATMEGA2560, True),
    # CH340 clone
    ("1A86", "7523", "COM5", "USB-SERIAL CH340",  BoardFamily.ATMEGA2560, True),
    # Teensy known PID
    ("16C0", "0483", "COM6", "USB Serial",        BoardFamily.TEENSY41,   True),
    # Teensy 16C0 unknown PID → fallback TEENSY41
    ("16C0", "FFFF", "COM7", "PJRC Mystery",      BoardFamily.TEENSY41,   True),
    # STM32F407 in CDC-ACM
    ("0483", "5740", "COM8", "STM32 Virtual COM", BoardFamily.STM32F407_DFU, True),
    # Unknown
    ("FFFF", "0000", "COM9", "Some random",       None,                   False),
])
def test_classify_serial_port_parity(vid_hex, pid_hex, device, description,
                                      expected_family, should_match):
    fake = _FakePort(vid_hex, pid_hex, device, description)
    py_targets = FlashTargetDetectionService()._detect_serial_targets([fake])
    cpp_target = _tuner_core.classify_serial_port(vid_hex, pid_hex, device, description)

    if not should_match:
        assert py_targets == []
        assert cpp_target is None
        return

    assert len(py_targets) == 1
    py_t = py_targets[0]
    assert cpp_target is not None
    # board_family comparison — Python is a str-enum, C++ is a bound enum.
    assert py_t.board_family.value == str(cpp_target.board_family).split(".")[-1]
    assert py_t.source == cpp_target.source
    assert py_t.description == cpp_target.description
    assert (py_t.serial_port or "") == cpp_target.serial_port
    assert (py_t.usb_vid or "") == cpp_target.usb_vid
    assert (py_t.usb_pid or "") == cpp_target.usb_pid
    assert py_t.board_family == expected_family


# ---------------------------------------------------------------------------
# USB device classification — the Python path for USB mode needs usb.core
# which may not be installed. The C++ side takes pre-flattened inputs so
# we can test it directly without the Python I/O harness.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vid,pid,bcd,has_hid,expected_family,should_match", [
    # Uninitialized Teensy 4.1 in HalfKay HID mode
    ("16C0", "0478", "0280", True,  BoardFamily.TEENSY41,      True),
    # Uninitialized Teensy 3.5 in HalfKay HID mode
    ("16C0", "0478", "0276", True,  BoardFamily.TEENSY35,      True),
    # 16C0 but not HID → not in flashing mode
    ("16C0", "0478", "0280", False, None,                       False),
    # 16C0 HID but unknown bcd → not a known Teensy
    ("16C0", "0000", "FFFF", True,  None,                       False),
    # STM32F407 DFU
    ("0483", "DF11", "2200", False, BoardFamily.STM32F407_DFU, True),
    # STM32F407 wrong bcd → not in DFU
    ("0483", "DF11", "0000", False, None,                       False),
    # Unknown VID
    ("FFFF", "0000", "0000", True,  None,                       False),
])
def test_classify_usb_device(vid, pid, bcd, has_hid, expected_family, should_match):
    cpp_target = _tuner_core.classify_usb_device(vid, pid, bcd, has_hid)
    if not should_match:
        assert cpp_target is None
    else:
        assert cpp_target is not None
        assert str(cpp_target.board_family).split(".")[-1] == expected_family.value
        assert cpp_target.source == "usb"
        assert cpp_target.serial_port == ""
