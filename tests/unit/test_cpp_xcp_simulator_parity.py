"""Python <-> C++ parity harness for the XCP simulator command dispatch.

Pins the C++ `xcp_simulator_*` helpers (port of the pure-logic half of
`XcpSimulatorServer`) against the Python original across:

  - `_expected_command_size` for every known opcode + unknown fallback
  - default state seeding (`__post_init__` memory fixture bytes)
  - `_handle` for CONNECT / GET_STATUS / GET_ID / SET_MTA / UPLOAD /
    truncated SET_MTA / truncated UPLOAD / unknown opcode / empty packet
  - successive (UPLOAD, SET_MTA, UPLOAD) MTA-threading round-trips

Socket I/O — TCP accept loop, recv/sendall — is out of scope. The
Python parity targets are `XcpSimulatorState` and the static
`_expected_command_size` and `_handle` methods on `XcpSimulatorServer`,
called directly without ever opening a socket.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.comms.xcp.packets import XcpCommand, XcpPid
from tuner.simulator.xcp_simulator import XcpSimulatorServer, XcpSimulatorState


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
# Helpers
# ---------------------------------------------------------------------------


def _make_python_server() -> XcpSimulatorServer:
    """Build a Python server *without* opening a socket.

    `XcpSimulatorServer.__init__` constructs an unbound socket but only
    calls `bind` / `listen` from `start()`, which we never invoke.
    """
    return XcpSimulatorServer()


def _to_cpp_state(py_state: XcpSimulatorState):
    """Mirror a Python state into the C++ binding class."""
    cpp = _tuner_core.XcpSimulatorStateCpp.default_state()
    cpp.session_status = py_state.session_status
    cpp.protection_status = py_state.protection_status
    cpp.configuration_status = py_state.configuration_status
    cpp.resource = py_state.resource
    cpp.comm_mode_basic = py_state.comm_mode_basic
    cpp.max_cto = py_state.max_cto
    cpp.max_dto = py_state.max_dto
    cpp.protocol_layer_version = py_state.protocol_layer_version
    cpp.transport_layer_version = py_state.transport_layer_version
    cpp.identifier = list(py_state.identifier)
    cpp.memory = list(py_state.memory)
    return cpp


# ---------------------------------------------------------------------------
# expected_command_size parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("opcode", [
    XcpCommand.CONNECT,
    XcpCommand.DISCONNECT,
    XcpCommand.GET_STATUS,
    XcpCommand.SYNCH,
    XcpCommand.GET_COMM_MODE_INFO,
    XcpCommand.GET_ID,
    XcpCommand.SET_MTA,
    XcpCommand.UPLOAD,
    0x00,
    0x42,
    0xAB,
    0xFF,  # CONNECT shares 0xFF — already covered above
])
def test_expected_command_size_parity(opcode):
    py = XcpSimulatorServer._expected_command_size(opcode)
    cpp = _tuner_core.xcp_simulator_expected_command_size(opcode)
    assert py == cpp


# ---------------------------------------------------------------------------
# default state seeding parity
# ---------------------------------------------------------------------------


def test_default_state_memory_seed_parity():
    py_state = XcpSimulatorState()
    cpp_state = _tuner_core.XcpSimulatorStateCpp.default_state()
    assert bytes(py_state.memory) == bytes(cpp_state.memory)


def test_default_state_field_parity():
    py_state = XcpSimulatorState()
    cpp_state = _tuner_core.XcpSimulatorStateCpp.default_state()
    assert py_state.session_status == cpp_state.session_status
    assert py_state.protection_status == cpp_state.protection_status
    assert py_state.configuration_status == cpp_state.configuration_status
    assert py_state.resource == cpp_state.resource
    assert py_state.comm_mode_basic == cpp_state.comm_mode_basic
    assert py_state.max_cto == cpp_state.max_cto
    assert py_state.max_dto == cpp_state.max_dto
    assert py_state.protocol_layer_version == cpp_state.protocol_layer_version
    assert py_state.transport_layer_version == cpp_state.transport_layer_version
    assert bytes(py_state.identifier) == bytes(cpp_state.identifier)


# ---------------------------------------------------------------------------
# handle_command parity (per branch)
# ---------------------------------------------------------------------------


def _dispatch_python(server: XcpSimulatorServer, packet: bytes) -> bytes:
    return server._handle(packet)


def test_handle_connect_parity():
    py_server = _make_python_server()
    py_state = py_server.state
    cpp_state = _to_cpp_state(py_state)
    packet = bytes([XcpCommand.CONNECT, 0x00])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 0)
    assert py_resp == bytes(cpp_result.response)
    assert cpp_result.new_mta_address == 0


def test_handle_get_status_parity():
    py_server = _make_python_server()
    cpp_state = _to_cpp_state(py_server.state)
    packet = bytes([XcpCommand.GET_STATUS])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 7)
    assert py_resp == bytes(cpp_result.response)
    assert cpp_result.new_mta_address == 7


def test_handle_get_id_parity():
    py_server = _make_python_server()
    cpp_state = _to_cpp_state(py_server.state)
    packet = bytes([XcpCommand.GET_ID, 0x00])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 0)
    assert py_resp == bytes(cpp_result.response)


def test_handle_set_mta_parity():
    py_server = _make_python_server()
    cpp_state = _to_cpp_state(py_server.state)
    packet = bytes([
        XcpCommand.SET_MTA, 0x00, 0x00, 0x00,
        0x12, 0x34, 0x56, 0x78,
    ])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 0)
    assert py_resp == bytes(cpp_result.response)
    # Python tracks MTA on the server instance.
    assert py_server._mta_address == 0x12345678
    assert cpp_result.new_mta_address == 0x12345678


def test_handle_set_mta_truncated_parity():
    py_server = _make_python_server()
    cpp_state = _to_cpp_state(py_server.state)
    packet = bytes([XcpCommand.SET_MTA, 0x00, 0x00, 0x00, 0x12, 0x34])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 5)
    assert py_resp == bytes(cpp_result.response) == bytes([0xFE, 0x20])
    assert cpp_result.new_mta_address == 5  # unchanged


def test_handle_upload_from_zero_parity():
    py_server = _make_python_server()
    py_server._mta_address = 0
    cpp_state = _to_cpp_state(py_server.state)
    packet = bytes([XcpCommand.UPLOAD, 4])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 0)
    assert py_resp == bytes(cpp_result.response)
    assert py_server._mta_address == 4
    assert cpp_result.new_mta_address == 4


def test_handle_upload_past_end_zero_pads_parity():
    py_server = _make_python_server()
    py_server._mta_address = 254
    cpp_state = _to_cpp_state(py_server.state)
    packet = bytes([XcpCommand.UPLOAD, 4])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 254)
    assert py_resp == bytes(cpp_result.response)
    assert py_server._mta_address == 258
    assert cpp_result.new_mta_address == 258


def test_handle_upload_truncated_parity():
    py_server = _make_python_server()
    py_server._mta_address = 9
    cpp_state = _to_cpp_state(py_server.state)
    packet = bytes([XcpCommand.UPLOAD])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 9)
    assert py_resp == bytes(cpp_result.response) == bytes([0xFE, 0x20])
    assert cpp_result.new_mta_address == 9


def test_handle_unknown_opcode_parity():
    py_server = _make_python_server()
    cpp_state = _to_cpp_state(py_server.state)
    packet = bytes([0x42])
    py_resp = _dispatch_python(py_server, packet)
    cpp_result = _tuner_core.xcp_simulator_handle_command(cpp_state, packet, 0)
    assert py_resp == bytes(cpp_result.response) == bytes([0xFE, 0x20])


# ---------------------------------------------------------------------------
# Multi-step MTA threading
# ---------------------------------------------------------------------------


def test_handle_upload_setmta_upload_threading_parity():
    py_server = _make_python_server()
    py_server._mta_address = 0
    cpp_state = _to_cpp_state(py_server.state)
    cpp_mta = 0

    # Step 1: UPLOAD 4 bytes from address 0.
    p1 = bytes([XcpCommand.UPLOAD, 4])
    py_r1 = _dispatch_python(py_server, p1)
    cpp_r1 = _tuner_core.xcp_simulator_handle_command(cpp_state, p1, cpp_mta)
    cpp_mta = cpp_r1.new_mta_address
    assert py_r1 == bytes(cpp_r1.response)
    assert py_server._mta_address == cpp_mta == 4

    # Step 2: SET_MTA to 8.
    p2 = bytes([XcpCommand.SET_MTA, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08])
    py_r2 = _dispatch_python(py_server, p2)
    cpp_r2 = _tuner_core.xcp_simulator_handle_command(cpp_state, p2, cpp_mta)
    cpp_mta = cpp_r2.new_mta_address
    assert py_r2 == bytes(cpp_r2.response)
    assert py_server._mta_address == cpp_mta == 8

    # Step 3: UPLOAD 2 bytes — should read big-endian u16 875 = 0x036B.
    p3 = bytes([XcpCommand.UPLOAD, 2])
    py_r3 = _dispatch_python(py_server, p3)
    cpp_r3 = _tuner_core.xcp_simulator_handle_command(cpp_state, p3, cpp_mta)
    cpp_mta = cpp_r3.new_mta_address
    assert py_r3 == bytes(cpp_r3.response)
    assert py_server._mta_address == cpp_mta == 10
    # Decoded value should be 875.
    decoded = int.from_bytes(bytes(cpp_r3.response[1:3]), byteorder="big", signed=False)
    assert decoded == 875


def test_handle_upload_random_walk_parity():
    """Random walk through SET_MTA + UPLOAD pairs across the memory.

    The Python and C++ implementations should agree on every response
    byte and on the trailing MTA pointer for any deterministic sequence
    of commands.
    """
    import random
    rng = random.Random(0xBADCAFE)
    py_server = _make_python_server()
    py_server._mta_address = 0
    cpp_state = _to_cpp_state(py_server.state)
    cpp_mta = 0
    for _ in range(40):
        if rng.random() < 0.4:
            # SET_MTA to a random in-range address.
            addr = rng.randint(0, 250)
            packet = bytes([
                XcpCommand.SET_MTA, 0x00, 0x00, 0x00,
                (addr >> 24) & 0xFF, (addr >> 16) & 0xFF,
                (addr >> 8) & 0xFF, addr & 0xFF,
            ])
        else:
            # UPLOAD a small block.
            size = rng.randint(1, 16)
            packet = bytes([XcpCommand.UPLOAD, size])
        py_resp = _dispatch_python(py_server, packet)
        cpp_result = _tuner_core.xcp_simulator_handle_command(
            cpp_state, packet, cpp_mta)
        cpp_mta = cpp_result.new_mta_address
        assert py_resp == bytes(cpp_result.response)
        assert py_server._mta_address == cpp_mta
