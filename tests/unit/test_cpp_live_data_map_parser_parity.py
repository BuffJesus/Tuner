"""Python ↔ C++ parity harness for tuner_core::live_data_map_parser."""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from tuner.services.live_data_map_parser import LiveDataMapParser


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


_py = LiveDataMapParser()


def _check_entries(py_entries, cpp_entries):
    assert len(py_entries) == len(cpp_entries)
    for p, c in zip(py_entries, cpp_entries):
        assert c.name == p.name
        assert c.byte_start == p.byte_start
        assert c.byte_end == p.byte_end
        assert c.readable_index == p.readable_index
        assert c.encoding.name == p.encoding.value
        assert c.field == p.field
        assert c.notes == p.notes
        assert c.locked == p.locked


def _check_contract(py_c, cpp_c):
    assert cpp_c.log_entry_size == py_c.log_entry_size
    assert cpp_c.runtime_status_a_offset == py_c.runtime_status_a_offset
    assert cpp_c.board_capability_flags_offset == py_c.board_capability_flags_offset
    assert cpp_c.flash_health_status_offset == py_c.flash_health_status_offset
    _check_entries(py_c.entries, cpp_c.entries)


_SAMPLE_HEADER = textwrap.dedent("""\
    /*
     * byte    ridx  field                          encoding       notes
     * 4-5      4    MAP                            U16 LE         map (kPa)
     * 14-15    13   RPM                            U16 LE         rpm
     * 84       57   status3                        U08 bits       status3 [LOCKED]
     * 100      -    AEamount >> 1                  U08            AEamount [low]
     * 200      -    legacyVar                      U08            DEPRECATED: use newVar
     */

    #define LIVE_DATA_MAP_SIZE  148U

    static constexpr uint16_t OCH_OFFSET_RUNTIME_STATUS_A    = 147U;
    static constexpr uint16_t OCH_OFFSET_BOARD_CAPABILITY_FLAGS = 130U;
    static constexpr uint16_t OCH_OFFSET_FLASH_HEALTH_STATUS = 131U;
    """)


def test_sample_header_matches_python():
    py = _py.parse_text(_SAMPLE_HEADER)
    cpp = _tuner_core.live_data_map_parse_text(_SAMPLE_HEADER, None)
    _check_contract(py, cpp)


def test_firmware_signature_round_trips():
    py = _py.parse_text(_SAMPLE_HEADER, firmware_signature="speeduino 202501-T41")
    cpp = _tuner_core.live_data_map_parse_text(
        _SAMPLE_HEADER, "speeduino 202501-T41")
    _check_contract(py, cpp)
    assert cpp.firmware_signature == "speeduino 202501-T41"


def test_empty_text_matches_python():
    py = _py.parse_text("")
    cpp = _tuner_core.live_data_map_parse_text("", None)
    _check_contract(py, cpp)


def test_no_table_only_size_matches_python():
    text = "#define LIVE_DATA_MAP_SIZE  148U\n"
    py = _py.parse_text(text)
    cpp = _tuner_core.live_data_map_parse_text(text, None)
    _check_contract(py, cpp)


def test_only_offset_constants_matches_python():
    text = (
        "static constexpr uint16_t OCH_OFFSET_RUNTIME_STATUS_A = 147U;\n"
        "static constexpr uint16_t OCH_OFFSET_BOARD_CAPABILITY_FLAGS = 130U;\n"
    )
    py = _py.parse_text(text)
    cpp = _tuner_core.live_data_map_parse_text(text, None)
    _check_contract(py, cpp)


_PRODUCTION_HEADER = (
    Path("C:/Users/Cornelio/Desktop/speeduino-202501.6/speeduino/live_data_map.h")
)


@pytest.mark.skipif(
    not _PRODUCTION_HEADER.exists(),
    reason="production live_data_map.h not available",
)
def test_production_header_matches_python():
    text = _PRODUCTION_HEADER.read_text(encoding="utf-8")
    py = _py.parse_text(text)
    cpp = _tuner_core.live_data_map_parse_text(text, None)
    _check_contract(py, cpp)
    # Sanity check: the production header should produce a non-trivial
    # contract on both sides.
    assert cpp.log_entry_size > 0
    assert len(cpp.entries) > 0
