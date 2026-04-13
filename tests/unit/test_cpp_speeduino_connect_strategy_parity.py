"""Python <-> C++ parity harness for Speeduino connect strategy helpers.

Pins the C++ `speeduino_connect_*` functions (port of the connect-time
helpers in `SpeeduinoControllerClient`) against the Python originals
across:

  - `_command_char(raw, fallback)`
  - `_effective_blocking_factor` for every (firmware/definition × scalar/table)
    combination including the zero-treated-as-missing edge cases
  - `_signature_probe_candidates` driven through real EcuDefinition
    fields
  - `_baud_probe_candidates` driven through transport baud_rate
  - `_connect_delay_seconds` driven through real EcuDefinition.metadata

I/O — transport open / baud rate set / signature probe loop — is
out of scope. The Python parity targets are the static or pure
methods on `SpeeduinoControllerClient` called directly via a
`unittest.mock.Mock` standing in for `self`, so no transport ever
needs to exist.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

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


# ---------------------------------------------------------------------------
# command_char parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,fallback", [
    ("",      "p"),
    ("F",     "p"),
    ("FOO",   "p"),
    ("p",     "b"),
    ("",      "b"),
    ("Q",     "S"),
])
def test_command_char_parity(raw, fallback):
    py = SpeeduinoControllerClient._command_char(raw, fallback)
    cpp = _tuner_core.speeduino_connect_command_char(raw, fallback)
    assert py == cpp


def test_command_char_none_python_input():
    # Python tolerates None for `raw` (the call sites do
    # `definition.foo if definition else None`). The C++ binding takes
    # std::string, so callers pass an empty string instead of None.
    py = SpeeduinoControllerClient._command_char(None, "p")
    cpp = _tuner_core.speeduino_connect_command_char("", "p")
    assert py == cpp == "p"


# ---------------------------------------------------------------------------
# effective_blocking_factor parity
# ---------------------------------------------------------------------------


def _python_effective_blocking_factor(*, is_table, fw_blocking, fw_table_blocking,
                                       def_blocking, def_table_blocking):
    """Drive the Python helper via a Mock self that exposes the right
    capabilities + definition shapes."""
    self = Mock(spec=SpeeduinoControllerClient)
    self.capabilities = Mock()
    self.capabilities.blocking_factor = fw_blocking
    self.capabilities.table_blocking_factor = fw_table_blocking
    self.definition = Mock()
    self.definition.blocking_factor = def_blocking
    self.definition.table_blocking_factor = def_table_blocking
    return SpeeduinoControllerClient._effective_blocking_factor(self, is_table=is_table)


@pytest.mark.parametrize("is_table,fw_b,fw_tb,def_b,def_tb,expected", [
    (False, 256, None, 64, None, 256),       # firmware scalar wins
    (False, None, None, 64, None, 64),       # definition scalar fallback
    (False, None, None, None, None, 128),    # default
    (False, 0, None, 64, None, 64),          # fw=0 treated as missing
    (False, None, None, 0, None, 128),       # def=0 treated as missing
    (True,  256, 512, 64, 128, 512),         # firmware table wins
    (True,  256, None, 64, 128, 128),        # definition table fallback
    (True,  256, None, 64, None, 256),       # table falls through to scalar firmware
    (True,  None, None, None, 128, 128),     # only definition table available
    (True,  0, 0, 64, 0, 64),                # zero values pass through scalar
])
def test_effective_blocking_factor_parity(is_table, fw_b, fw_tb, def_b, def_tb, expected):
    py = _python_effective_blocking_factor(
        is_table=is_table,
        fw_blocking=fw_b, fw_table_blocking=fw_tb,
        def_blocking=def_b, def_table_blocking=def_tb,
    )
    cpp = _tuner_core.speeduino_connect_effective_blocking_factor(
        is_table, fw_b, fw_tb, def_b, def_tb)
    assert py == cpp == expected


# ---------------------------------------------------------------------------
# signature_probe_candidates parity
# ---------------------------------------------------------------------------


def _python_signature_probe_candidates(query_command, version_info_command):
    # _signature_probe_candidates calls `self._command_char(raw, "")`
    # where `_command_char` is a @staticmethod on the class. A
    # Mock(spec=...) inspects the descriptor and rejects the call
    # because it sees a 2-arg signature. Use a plain object so the
    # static method resolves the same way the real instance does.
    class _Stub:
        _command_char = staticmethod(SpeeduinoControllerClient._command_char)
    self = _Stub()
    self.definition = Mock()
    self.definition.query_command = query_command
    self.definition.version_info_command = version_info_command
    return SpeeduinoControllerClient._signature_probe_candidates(self)


@pytest.mark.parametrize("query,version", [
    ("", ""),
    ("S", ""),
    ("F", "Q"),
    ("Foo", "Bar"),
    ("X", "X"),
    ("S", "S"),
    ("Q", ""),
    ("", "F"),
])
def test_signature_probe_candidates_parity(query, version):
    py = _python_signature_probe_candidates(query, version)
    cpp = _tuner_core.speeduino_connect_signature_probe_candidates(query, version)
    assert py == list(cpp)


# ---------------------------------------------------------------------------
# baud_probe_candidates parity
# ---------------------------------------------------------------------------


def _python_baud_probe_candidates(current_baud):
    self = Mock(spec=SpeeduinoControllerClient)
    self._get_transport_baud_rate = Mock(return_value=current_baud)
    return SpeeduinoControllerClient._baud_probe_candidates(self)


@pytest.mark.parametrize("current", [None, 9600, 57600, 115200, 230400, 19200, 38400])
def test_baud_probe_candidates_parity(current):
    py = _python_baud_probe_candidates(current)
    cpp = _tuner_core.speeduino_connect_baud_probe_candidates(current)
    assert py == list(cpp)


# ---------------------------------------------------------------------------
# connect_delay_seconds parity
# ---------------------------------------------------------------------------


def _python_connect_delay_seconds(metadata):
    self = Mock(spec=SpeeduinoControllerClient)
    self.definition = Mock()
    self.definition.metadata = metadata
    return SpeeduinoControllerClient._connect_delay_seconds(self)


@pytest.mark.parametrize("metadata", [
    {},
    {"controllerConnectDelay": "2500"},
    {"connectDelay": "1000"},
    {"interWriteDelay": "750"},
    {"controllerConnectDelay": "1500,1000"},      # comma-split
    {"controllerConnectDelay": "  3000  "},       # whitespace strip
    {"controllerConnectDelay": "0"},              # zero -> default
    {"controllerConnectDelay": "-500"},           # negative -> default
    {"controllerConnectDelay": "not-a-number"},   # malformed -> default
    {"controllerConnectDelay": "", "connectDelay": "800"},  # empty key skipped
    {"controllerConnectDelay": "2500", "connectDelay": "1000"},  # priority
    {"unrelated": "value"},
])
def test_connect_delay_seconds_parity(metadata):
    py = _python_connect_delay_seconds(metadata)
    cpp = _tuner_core.speeduino_connect_delay_seconds(metadata)
    assert py == pytest.approx(cpp)


# ---------------------------------------------------------------------------
# Capability header parse / derived flags parity
# ---------------------------------------------------------------------------


from tuner.domain.ecu_definition import ScalarParameterDefinition as _PyField
from tuner.domain.firmware_capabilities import FirmwareCapabilities  # noqa: F401


def _python_read_capabilities(payload, definition_mock):
    self = Mock(spec=SpeeduinoControllerClient)
    self._query_capability_payload = Mock(return_value=payload)
    # `_live_data_size` and `_has_output_channel` both read
    # `self.definition` directly — wire it.
    self.definition = definition_mock
    self.firmware_signature = getattr(definition_mock, "firmware_signature", None)
    # The real methods still need to work — re-bind them from the class.
    self._live_data_size = SpeeduinoControllerClient._live_data_size.__get__(self)
    self._has_output_channel = SpeeduinoControllerClient._has_output_channel.__get__(self)
    self._data_size = SpeeduinoControllerClient._data_size  # @staticmethod
    return SpeeduinoControllerClient._read_capabilities(self)


@pytest.mark.parametrize("payload,expected_parsed,expected_spv,expected_bf,expected_tbf", [
    (None,                                       False, 0,   0,   0),
    (bytes([0x00, 0x02, 0x01, 0x80, 0x02, 0x00]),True,  2, 384, 512),
    (bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),True,  0,   0,   0),
    (bytes([0x01, 0x02, 0x00, 0x80, 0x01, 0x00]),False, 0,   0,   0),  # bad leading byte
    (bytes([0x00, 0x01, 0x02, 0x03]),            False, 0,   0,   0),  # short
])
def test_parse_capability_header_parity(payload, expected_parsed,
                                          expected_spv, expected_bf, expected_tbf):
    cpp = _tuner_core.speeduino_parse_capability_header(payload)
    assert cpp.parsed == expected_parsed
    assert cpp.serial_protocol_version == expected_spv
    assert cpp.blocking_factor == expected_bf
    assert cpp.table_blocking_factor == expected_tbf
    assert _tuner_core.speeduino_capability_source(cpp) == (
        "serial+definition" if expected_parsed else "definition")

    # Cross-check against the Python `_read_capabilities` (which runs
    # the same payload-parse inline): mock a minimal definition so the
    # Python method builds a real FirmwareCapabilities that we can
    # read the same fields off of.
    definition_mock = Mock()
    definition_mock.output_channel_definitions = []
    definition_mock.firmware_signature = None
    definition_mock.metadata = {}
    py = _python_read_capabilities(payload, definition_mock)
    if expected_parsed:
        assert py.source == "serial+definition"
        assert py.serial_protocol_version == expected_spv
        assert py.blocking_factor == expected_bf
        assert py.table_blocking_factor == expected_tbf
    else:
        assert py.source == "definition"
        assert py.serial_protocol_version is None
        assert py.blocking_factor is None
        assert py.table_blocking_factor is None


def test_compute_live_data_size_empty_parity():
    # Both sides should agree on the empty-channel nullopt.
    cpp = _tuner_core.speeduino_compute_live_data_size([])
    assert cpp is None


def _build_cpp_field(name, offset, data_type):
    f = _tuner_core.SpeeduinoOutputChannelField()
    f.name = name
    f.offset = offset
    f.data_type = data_type
    return f


def test_compute_live_data_size_production_shape_parity():
    # Drive the Python `_live_data_size` with a real channel definition
    # list then run the C++ helper on parallel data.
    class _Stub:
        _data_size = staticmethod(SpeeduinoControllerClient._data_size)
    self = _Stub()
    self.definition = Mock()
    py_fields = [
        _PyField(name="rpm", offset=14, data_type="U16", units=""),
        _PyField(name="map", offset=4,  data_type="U08", units=""),
        _PyField(name="iat", offset=6,  data_type="S08", units=""),
    ]
    self.definition.output_channel_definitions = py_fields
    py = SpeeduinoControllerClient._live_data_size(self)
    cpp_fields = [
        _build_cpp_field("rpm", 14, "U16"),
        _build_cpp_field("map", 4,  "U08"),
        _build_cpp_field("iat", 6,  "S08"),
    ]
    cpp = _tuner_core.speeduino_compute_live_data_size(cpp_fields)
    assert py == cpp


@pytest.mark.parametrize("defined,targets,expected", [
    ([],                          ["runtimeStatusA"], False),
    (["rpm", "map"],               ["runtimeStatusA", "rSA_tuneValid"], False),
    (["rpm", "runtimeStatusA"],    ["runtimeStatusA"], True),
    (["rpm", "rSA_tuneValid"],     ["runtimeStatusA", "rSA_tuneValid"], True),
    (["rpm", "map", "clt"],        [], False),
])
def test_has_any_output_channel_parity(defined, targets, expected):
    # Drive the Python helper via a real stub.
    class _Stub:
        pass
    self = _Stub()
    self.definition = Mock()
    self.definition.output_channel_definitions = [
        _PyField(name=n, offset=0, data_type="U08", units="") for n in defined
    ]
    py = SpeeduinoControllerClient._has_output_channel(self, *targets)
    cpp = _tuner_core.speeduino_has_any_output_channel(defined, targets)
    assert py == cpp == expected


@pytest.mark.parametrize("signature,expected", [
    ("speeduino 202501-T41-U16P2", True),
    ("speeduino 202501-T41-u16p2", True),
    ("speeduino 202501-T41",       False),
    ("",                            False),
    ("speeduino 202501-T41-U16P3", False),  # close but not exact
])
def test_is_experimental_u16p2_parity(signature, expected):
    # Python: `"U16P2" in (signature or "").upper()`
    py = "U16P2" in (signature or "").upper()
    cpp = _tuner_core.speeduino_is_experimental_u16p2_signature(signature)
    assert py == cpp == expected


@pytest.mark.parametrize("command,response,expected", [
    ("S", "",                           False),
    ("S", "S",                          False),
    ("F", "speeduino 202501-T41",       False),
    ("S", "speeduino 202501-T41",       True),
    ("Q", "speeduino 202501-T41",       True),
    ("Q", "Q",                          False),
])
def test_should_accept_probe_response_parity(command, response, expected):
    # Re-derive the Python predicate inline — the Python source has it
    # as inline conditions inside the loop rather than a named helper.
    py = bool(response) and response != command and command != "F"
    cpp = _tuner_core.speeduino_should_accept_probe_response(command, response)
    assert py == cpp == expected
