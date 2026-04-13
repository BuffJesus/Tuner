"""Python <-> C++ parity harness for the protocol simulator dispatch.

Pins the C++ `protocol_simulator_*` helpers (port of the pure-logic
half of `ProtocolSimulatorServer`) against the Python original across:

  - `SimulatorState.runtime_values` (rpm/map/afr from sin/cos)
  - `_handle` for hello / runtime / read_parameter / write_parameter /
    burn / verify_crc / unknown command branches
  - heterogeneous parameter value types (int / float / str / bool)
  - successive runtime calls (tick monotonicity)

Socket I/O — TCP accept loop, recv/sendall — is out of scope. The
Python parity targets are `SimulatorState` and the static `_handle`
method on `ProtocolSimulatorServer`, called directly without ever
opening a socket.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from tuner.simulator.protocol_simulator import (
    ProtocolSimulatorServer,
    SimulatorState,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_python_server() -> ProtocolSimulatorServer:
    """Build a Python server *without* opening a socket.

    `ProtocolSimulatorServer.__init__` constructs an unbound socket but
    only calls `bind` / `listen` from `start()`, which we never invoke.
    """
    return ProtocolSimulatorServer()


def _make_cpp_state():
    return _tuner_core.ProtocolSimulatorStateCpp()


def _dispatch_python(server: ProtocolSimulatorServer, payload: dict) -> dict:
    return server._handle(payload)


def _dispatch_cpp(state, payload: dict) -> dict:
    return json.loads(_tuner_core.protocol_simulator_handle_command_json(
        state, json.dumps(payload, separators=(",", ":"))))


# ---------------------------------------------------------------------------
# runtime_values parity
# ---------------------------------------------------------------------------


def test_runtime_values_first_tick_parity():
    py_state = SimulatorState()
    cpp_state = _make_cpp_state()
    py_values = py_state.runtime_values()
    cpp_values = dict(_tuner_core.protocol_simulator_runtime_values(cpp_state))
    assert py_state.tick == cpp_state.tick == 1
    assert py_values == cpp_values  # exact byte equality on doubles


def test_runtime_values_50_consecutive_ticks_parity():
    py_state = SimulatorState()
    cpp_state = _make_cpp_state()
    for _ in range(50):
        py = py_state.runtime_values()
        cpp = dict(_tuner_core.protocol_simulator_runtime_values(cpp_state))
        assert py_state.tick == cpp_state.tick
        assert py == cpp


# ---------------------------------------------------------------------------
# handle_command parity per branch
# ---------------------------------------------------------------------------


def test_handle_hello_parity():
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    py = _dispatch_python(py_server, {"command": "hello"})
    cpp = _dispatch_cpp(cpp_state, {"command": "hello"})
    assert py == cpp


def test_handle_runtime_parity():
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    py = _dispatch_python(py_server, {"command": "runtime"})
    cpp = _dispatch_cpp(cpp_state, {"command": "runtime"})
    assert py == cpp
    # Both sides should have ticked exactly once.
    assert py_server.state.tick == cpp_state.tick == 1


def test_handle_read_parameter_default_zero_parity():
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    py = _dispatch_python(py_server, {"command": "read_parameter", "name": "missing"})
    cpp = _dispatch_cpp(cpp_state, {"command": "read_parameter", "name": "missing"})
    assert py == cpp
    # Default is float 0.0 — both sides should agree.
    assert py["value"] == 0.0
    assert isinstance(py["value"], float)
    assert isinstance(cpp["value"], float)


@pytest.mark.parametrize("name,value", [
    ("boost_target", 18.5),
    ("rev_limit", 7500),
    ("comment", "tuned at altitude"),
    ("dual_idle_enabled", True),
    ("dual_idle_disabled", False),
    ("zero_int", 0),
    ("zero_float", 0.0),
    ("negative", -3.14),
])
def test_handle_write_then_read_parameter_parity(name, value):
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    # Write.
    py_w = _dispatch_python(py_server, {"command": "write_parameter", "name": name, "value": value})
    cpp_w = _dispatch_cpp(cpp_state, {"command": "write_parameter", "name": name, "value": value})
    assert py_w == cpp_w == {"status": "ok"}
    # Read back.
    py_r = _dispatch_python(py_server, {"command": "read_parameter", "name": name})
    cpp_r = _dispatch_cpp(cpp_state, {"command": "read_parameter", "name": name})
    assert py_r == cpp_r
    assert py_r["value"] == value


def test_handle_write_overwrite_parity():
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    for value in [10, 20, 30, "stringy", True, 42.5]:
        _dispatch_python(py_server, {"command": "write_parameter", "name": "x", "value": value})
        _dispatch_cpp(cpp_state, {"command": "write_parameter", "name": "x", "value": value})
        py_r = _dispatch_python(py_server, {"command": "read_parameter", "name": "x"})
        cpp_r = _dispatch_cpp(cpp_state, {"command": "read_parameter", "name": "x"})
        assert py_r == cpp_r


def test_handle_burn_parity():
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    py = _dispatch_python(py_server, {"command": "burn"})
    cpp = _dispatch_cpp(cpp_state, {"command": "burn"})
    assert py == cpp == {"status": "ok"}


def test_handle_verify_crc_parity():
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    py = _dispatch_python(py_server, {"command": "verify_crc"})
    cpp = _dispatch_cpp(cpp_state, {"command": "verify_crc"})
    assert py == cpp


@pytest.mark.parametrize("command", ["wat", "frobnicate", "", "RUNTIME"])
def test_handle_unknown_command_parity(command):
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    py = _dispatch_python(py_server, {"command": command})
    cpp = _dispatch_cpp(cpp_state, {"command": command})
    assert py == cpp
    assert py["status"] == "error"
    assert py["message"] == f"Unknown command: {command}"


# ---------------------------------------------------------------------------
# Multi-step session parity (mixed write / runtime / read)
# ---------------------------------------------------------------------------


def test_handle_mixed_session_parity():
    """A small ordered session: hello, write a few params, runtime ticks,
    read params, runtime ticks, burn. Both sides should agree on every
    response and on the tick counter at every step.
    """
    py_server = _make_python_server()
    cpp_state = _make_cpp_state()
    sequence = [
        {"command": "hello"},
        {"command": "write_parameter", "name": "rev_limit", "value": 7500},
        {"command": "write_parameter", "name": "comment", "value": "alpha"},
        {"command": "runtime"},
        {"command": "runtime"},
        {"command": "read_parameter", "name": "rev_limit"},
        {"command": "read_parameter", "name": "comment"},
        {"command": "read_parameter", "name": "missing_one"},
        {"command": "runtime"},
        {"command": "verify_crc"},
        {"command": "write_parameter", "name": "comment", "value": "beta"},
        {"command": "read_parameter", "name": "comment"},
        {"command": "burn"},
    ]
    for payload in sequence:
        py_resp = _dispatch_python(py_server, payload)
        cpp_resp = _dispatch_cpp(cpp_state, payload)
        assert py_resp == cpp_resp, f"divergence on payload {payload}"
        assert py_server.state.tick == cpp_state.tick
