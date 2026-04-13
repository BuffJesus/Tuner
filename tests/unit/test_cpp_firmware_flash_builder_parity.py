"""Python <-> C++ parity harness for firmware flash builder helpers.

Pins the C++ `firmware_flash_builder_*` functions (port of the
pure-logic helpers in `FirmwareFlashService`) against the Python
service across:

  - `_platform_dir` for every (tool, system, machine) triple
  - `_tool_filename` for every tool / OS combination
  - `_linux_platform_dir` for every architecture branch
  - `_supports_internal_teensy`
  - `_teensy_cli_filename`
  - `_teensy_mcu_spec` for every Teensy family
  - command argument list builders for AVRDUDE / Teensy CLI / legacy
    Teensy / internal Teensy / DFU

I/O — subprocess execution, file existence checks, USB device write —
is out of scope. The Python parity targets are the private helpers
called by `build_command`, not `build_command` itself.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.domain.firmware import BoardFamily, FlashTool
from tuner.services.firmware_flash_service import FirmwareFlashService


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
# Helpers — translate Python enums into the C++ binding enums.
# ---------------------------------------------------------------------------

def _cpp_tool(py_tool: FlashTool):
    if py_tool == FlashTool.AVRDUDE:  return _tuner_core.FlashToolKind.AVRDUDE
    if py_tool == FlashTool.TEENSY:   return _tuner_core.FlashToolKind.TEENSY
    if py_tool == FlashTool.DFU_UTIL: return _tuner_core.FlashToolKind.DFU_UTIL
    raise AssertionError(f"unknown tool: {py_tool}")


def _cpp_board(py_family: BoardFamily):
    return getattr(_tuner_core.BoardFamily, py_family.value)


def _make_service(system: str, machine: str = "x86_64") -> FirmwareFlashService:
    return FirmwareFlashService(system_name=system, machine_name=machine)


# ---------------------------------------------------------------------------
# _platform_dir parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", list(FlashTool))
@pytest.mark.parametrize("system,machine", [
    ("windows", "x86_64"),
    ("darwin",  "x86_64"),
    ("linux",   "x86_64"),
    ("linux",   "amd64"),
    ("linux",   "i386"),
    ("linux",   "i686"),
    ("linux",   "x86"),
    ("linux",   "armv7l"),
    ("linux",   "arm"),
    ("linux",   "aarch64"),
    ("linux",   "arm64"),
])
def test_platform_dir_parity(tool, system, machine):
    svc = _make_service(system, machine)
    py = svc._platform_dir(tool)
    cpp = _tuner_core.firmware_flash_builder_platform_dir(
        _cpp_tool(tool), system, machine)
    assert py == cpp


def test_platform_dir_unknown_system_throws_on_both_sides():
    svc = _make_service("freebsd")
    with pytest.raises(RuntimeError):
        svc._platform_dir(FlashTool.AVRDUDE)
    with pytest.raises(Exception):
        _tuner_core.firmware_flash_builder_platform_dir(
            _tuner_core.FlashToolKind.AVRDUDE, "freebsd", "x86_64")


# ---------------------------------------------------------------------------
# _tool_filename parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", list(FlashTool))
@pytest.mark.parametrize("system", ["windows", "darwin", "linux"])
def test_tool_filename_parity(tool, system):
    svc = _make_service(system)
    py = svc._tool_filename(tool)
    cpp = _tuner_core.firmware_flash_builder_tool_filename(_cpp_tool(tool), system)
    assert py == cpp


# ---------------------------------------------------------------------------
# _linux_platform_dir parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", ["avrdude", "teensy_loader_cli", "dfuutil"])
@pytest.mark.parametrize("machine", [
    "x86_64", "amd64", "i386", "i686", "x86",
    "armv7l", "arm", "aarch64", "arm64",
])
def test_linux_platform_dir_parity(prefix, machine):
    svc = _make_service("linux", machine)
    py = svc._linux_platform_dir(prefix)
    cpp = _tuner_core.firmware_flash_builder_linux_platform_dir(prefix, machine)
    assert py == cpp


def test_linux_platform_dir_unknown_arch_throws_on_both_sides():
    svc = _make_service("linux", "riscv64")
    with pytest.raises(RuntimeError):
        svc._linux_platform_dir("avrdude")
    with pytest.raises(Exception):
        _tuner_core.firmware_flash_builder_linux_platform_dir("avrdude", "riscv64")


# ---------------------------------------------------------------------------
# _supports_internal_teensy / _teensy_cli_filename parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("system", ["windows", "darwin", "linux"])
def test_supports_internal_teensy_parity(system):
    svc = _make_service(system)
    py = svc._supports_internal_teensy()
    cpp = _tuner_core.firmware_flash_builder_supports_internal_teensy(system)
    assert py == cpp


@pytest.mark.parametrize("system", ["windows", "darwin", "linux"])
def test_teensy_cli_filename_parity(system):
    svc = _make_service(system)
    py = svc._teensy_cli_filename()
    cpp = _tuner_core.firmware_flash_builder_teensy_cli_filename(system)
    assert py == cpp


# ---------------------------------------------------------------------------
# _teensy_mcu_spec parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("family", [
    BoardFamily.TEENSY35, BoardFamily.TEENSY36, BoardFamily.TEENSY41,
])
def test_teensy_mcu_spec_parity(family):
    py_spec = FirmwareFlashService._teensy_mcu_spec(family)
    cpp_spec = _tuner_core.firmware_flash_builder_teensy_mcu_spec(_cpp_board(family))
    assert py_spec.name == cpp_spec.name
    assert py_spec.code_size == cpp_spec.code_size
    assert py_spec.block_size == cpp_spec.block_size


@pytest.mark.parametrize("family", [BoardFamily.ATMEGA2560, BoardFamily.STM32F407_DFU])
def test_teensy_mcu_spec_throws_for_non_teensy(family):
    with pytest.raises(RuntimeError):
        FirmwareFlashService._teensy_mcu_spec(family)
    with pytest.raises(Exception):
        _tuner_core.firmware_flash_builder_teensy_mcu_spec(_cpp_board(family))


# ---------------------------------------------------------------------------
# Argument list parity — drive the Python `_build_*_command` paths
# against fake-resolved paths and compare the `arguments` list.
# ---------------------------------------------------------------------------


def test_avrdude_arguments_parity_against_python_build():
    svc = _make_service("linux")
    # We can't easily call _build_avrdude_command without an existing
    # avrdude binary on disk (it calls _require_file). Instead, we
    # mirror the literal arguments=[...] block by hand from the source
    # and assert the C++ output matches that hand-written list.
    expected = [
        "-v", "-patmega2560",
        "-C", "/etc/avrdude.conf",
        "-cwiring",
        "-b", "115200",
        "-P", "COM7",
        "-D",
        "-U", "flash:w:/fw/firmware.hex:i",
    ]
    cpp = _tuner_core.firmware_flash_builder_avrdude_arguments(
        "COM7", "/etc/avrdude.conf", "/fw/firmware.hex")
    assert list(cpp) == expected


def test_avrdude_arguments_throws_on_missing_serial_port():
    with pytest.raises(Exception):
        _tuner_core.firmware_flash_builder_avrdude_arguments(
            "", "/etc/avrdude.conf", "/fw/firmware.hex")


def test_teensy_cli_arguments_match_python_literal():
    expected = ["--mcu=TEENSY41", "-w", "-v", "/fw/firmware.hex"]
    cpp = _tuner_core.firmware_flash_builder_teensy_cli_arguments(
        "TEENSY41", "/fw/firmware.hex")
    assert list(cpp) == expected


def test_teensy_legacy_arguments_match_python_literal():
    expected = [
        "-board=TEENSY35",
        "-reboot",
        "-file=speeduino_teensy35",
        "-path=/fw",
        "-tools=/tools/teensy",
    ]
    cpp = _tuner_core.firmware_flash_builder_teensy_legacy_arguments(
        "TEENSY35", "speeduino_teensy35", "/fw", "/tools/teensy")
    assert list(cpp) == expected


def test_internal_teensy_arguments_match_python_literal():
    expected = ["--mcu=TEENSY41", "-w", "/fw/firmware.hex"]
    cpp = _tuner_core.firmware_flash_builder_internal_teensy_arguments(
        "TEENSY41", "/fw/firmware.hex")
    assert list(cpp) == expected


def test_dfu_arguments_match_python_literal():
    expected = [
        "-d", "0483:df11",
        "-a", "0",
        "-s", "0x08000000:leave",
        "-D", "/fw/firmware.bin",
    ]
    cpp = _tuner_core.firmware_flash_builder_dfu_arguments(
        "0483", "df11", "/fw/firmware.bin")
    assert list(cpp) == expected


def test_dfu_arguments_throws_on_missing_vid_or_pid():
    with pytest.raises(Exception):
        _tuner_core.firmware_flash_builder_dfu_arguments("", "df11", "/fw/firmware.bin")
    with pytest.raises(Exception):
        _tuner_core.firmware_flash_builder_dfu_arguments("0483", "", "/fw/firmware.bin")
