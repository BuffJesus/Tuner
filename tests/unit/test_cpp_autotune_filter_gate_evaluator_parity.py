"""Python ↔ C++ parity harness for tuner_core::autotune_filter_gate_evaluator.

Pins the C++ evaluator against `AutotuneFilterGateEvaluator` across
every standard gate (std_DeadLambda, std_xAxisMin/Max, std_yAxisMin/Max,
std_Custom), parametric gates, disabled-by-default fall-through, and
the rejection-reason strings the workspace surfaces back to the operator.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.domain.ecu_definition import AutotuneFilterGate
from tuner.services.autotune_filter_gate_evaluator import (
    AutotuneFilterGateEvaluator,
    AxisContext,
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


_py_eval = AutotuneFilterGateEvaluator()


def _items(d):
    return list(d.items())


def _to_cpp_gate(py: AutotuneFilterGate):
    g = _tuner_core.AutotuneGate()
    g.name = py.name
    g.label = py.label or ""
    g.channel = py.channel
    g.op = py.operator
    g.threshold = py.threshold
    g.default_enabled = py.default_enabled
    return g


def _to_cpp_axis(py: AxisContext | None):
    if py is None:
        return None
    a = _tuner_core.AutotuneAxisContext()
    a.x_value = py.x_value
    a.x_min = py.x_min
    a.x_max = py.x_max
    a.y_value = py.y_value
    a.y_min = py.y_min
    a.y_max = py.y_max
    return a


def _evaluate_both(py_gate, values, axis=None):
    py = _py_eval.evaluate(py_gate, values, axis_context=axis)
    cpp = _tuner_core.autotune_evaluate_gate(
        _to_cpp_gate(py_gate), _items(values), _to_cpp_axis(axis)
    )
    return py, cpp


def _check(py, cpp):
    assert cpp.gate_name == py.gate_name
    assert cpp.accepted == py.accepted
    assert cpp.reason == py.reason


# ---------------------------------------------------------------------------
# Disabled-by-default + std_Custom pass-through
# ---------------------------------------------------------------------------

def test_disabled_gate_passes_through():
    g = AutotuneFilterGate(
        name="custom", channel="rpm", operator=">", threshold=5000.0,
        default_enabled=False,
    )
    py, cpp = _evaluate_both(g, {"rpm": 6000.0})
    _check(py, cpp)
    assert cpp.accepted is True


def test_std_custom_passes_through():
    g = AutotuneFilterGate(name="std_Custom")
    py, cpp = _evaluate_both(g, {})
    _check(py, cpp)


# ---------------------------------------------------------------------------
# std_DeadLambda
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "values",
    [
        {"lambda1": 1.05},
        {"lambda1": 0.85},
        {"afr1": 14.7},        # → λ 1.0
        {"egoTarget": 12.5},   # → λ 0.85
        {"lambda": 0.3},       # out of range — reject
        {"lambda": 2.0},       # out of range — reject
        {"rpm": 5500.0},       # no lambda channel — reject
        {},                    # empty record — reject
    ],
)
def test_std_dead_lambda_matches_python(values):
    g = AutotuneFilterGate(name="std_DeadLambda")
    py, cpp = _evaluate_both(g, values)
    _check(py, cpp)


# ---------------------------------------------------------------------------
# std_xAxis* / std_yAxis*
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "gate_name,axis",
    [
        ("std_xAxisMin", AxisContext(x_value=100.0, x_min=200.0)),  # reject
        ("std_xAxisMin", AxisContext(x_value=300.0, x_min=200.0)),  # pass
        ("std_xAxisMax", AxisContext(x_value=300.0, x_max=200.0)),  # reject
        ("std_xAxisMax", AxisContext(x_value=100.0, x_max=200.0)),  # pass
        ("std_yAxisMin", AxisContext(y_value=50.0, y_min=100.0)),
        ("std_yAxisMax", AxisContext(y_value=200.0, y_max=150.0)),
        # Missing axis context → pass
        ("std_xAxisMin", None),
        # Missing limit → pass
        ("std_xAxisMin", AxisContext(x_value=100.0)),
    ],
)
def test_std_axis_gates_match_python(gate_name, axis):
    g = AutotuneFilterGate(name=gate_name)
    py, cpp = _evaluate_both(g, {}, axis)
    _check(py, cpp)


# ---------------------------------------------------------------------------
# Parametric gates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "gate,values",
    [
        # rpm filter — reject below threshold
        (AutotuneFilterGate(
            name="minRPM", channel="rpm", operator="<", threshold=300.0),
         {"rpm": 200.0}),
        (AutotuneFilterGate(
            name="minRPM", channel="rpm", operator="<", threshold=300.0),
         {"rpm": 1500.0}),
        # CLT filter
        (AutotuneFilterGate(
            name="minCltFilter", channel="coolant", operator="<", threshold=70.0),
         {"clt": 60.0}),
        (AutotuneFilterGate(
            name="minCltFilter", channel="coolant", operator="<", threshold=70.0),
         {"clt": 90.0}),
        # Bitwise & (engine status flags)
        (AutotuneFilterGate(
            name="accelFilter", channel="engine", operator="&", threshold=16.0),
         {"engineStatus": 16.0}),
        (AutotuneFilterGate(
            name="accelFilter", channel="engine", operator="&", threshold=16.0),
         {"engineStatus": 4.0}),
        # Channel missing — pass through
        (AutotuneFilterGate(
            name="minRPM", channel="rpm", operator="<", threshold=300.0),
         {"clt": 90.0}),
        # Custom label exposed in reason
        (AutotuneFilterGate(
            name="custom", label="My Limit",
            channel="rpm", operator=">", threshold=7000.0),
         {"rpm": 8000.0}),
    ],
)
def test_parametric_gates_match_python(gate, values):
    py, cpp = _evaluate_both(gate, values)
    _check(py, cpp)


# ---------------------------------------------------------------------------
# evaluate_all + gate_label
# ---------------------------------------------------------------------------

def test_evaluate_all_fail_fast_matches_python():
    gates = [
        AutotuneFilterGate(name="minRPM", channel="rpm", operator="<", threshold=300.0),
        AutotuneFilterGate(name="maxRPM", channel="rpm", operator=">", threshold=7000.0),
    ]
    values = {"rpm": 200.0}
    py = _py_eval.evaluate_all(tuple(gates), values)
    cpp = _tuner_core.autotune_evaluate_all_gates(
        [_to_cpp_gate(g) for g in gates], _items(values), None, True
    )
    assert len(cpp) == len(py) == 1
    _check(py[0], cpp[0])


def test_evaluate_all_no_fail_fast_matches_python():
    gates = [
        AutotuneFilterGate(name="minRPM", channel="rpm", operator="<", threshold=300.0),
        AutotuneFilterGate(name="maxRPM", channel="rpm", operator=">", threshold=7000.0),
    ]
    values = {"rpm": 200.0}
    py = _py_eval.evaluate_all(tuple(gates), values, fail_fast=False)
    cpp = _tuner_core.autotune_evaluate_all_gates(
        [_to_cpp_gate(g) for g in gates], _items(values), None, False
    )
    assert len(cpp) == len(py) == 2
    for p, c in zip(py, cpp):
        _check(p, c)


@pytest.mark.parametrize(
    "gate",
    [
        AutotuneFilterGate(name="std_DeadLambda"),
        AutotuneFilterGate(name="std_xAxisMin"),
        AutotuneFilterGate(name="customGate"),
        AutotuneFilterGate(name="custom", label="My Custom Label"),
    ],
)
def test_gate_label_matches_python(gate):
    py = _py_eval.gate_label(gate)
    cpp = _tuner_core.autotune_gate_label(_to_cpp_gate(gate))
    assert cpp == py
