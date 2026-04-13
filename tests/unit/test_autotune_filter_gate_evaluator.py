"""Tests for AutotuneFilterGateEvaluator.

Covers:
- Standard named gates (std_DeadLambda, std_xAxisMin/Max, std_yAxisMin/Max, std_Custom)
- Parametric gates with all supported operators (<, >, <=, >=, ==, !=, &)
- Default-disabled gates pass through without evaluating
- Missing channel pass-through
- Operator normalisation (= treated as ==)
"""

from __future__ import annotations

import pytest

from tuner.domain.ecu_definition import AutotuneFilterGate
from tuner.services.autotune_filter_gate_evaluator import (
    AutotuneFilterGateEvaluator,
    AxisContext,
)


def _gate(
    name: str,
    label: str | None = None,
    channel: str | None = None,
    operator: str | None = None,
    threshold: float | None = None,
    default_enabled: bool = True,
) -> AutotuneFilterGate:
    return AutotuneFilterGate(
        name=name,
        label=label,
        channel=channel,
        operator=operator,
        threshold=threshold,
        default_enabled=default_enabled,
    )


# ---------------------------------------------------------------------------
# std_DeadLambda
# ---------------------------------------------------------------------------

class TestStdDeadLambda:
    _GATE = _gate("std_DeadLambda")

    def test_rejects_high_afr(self) -> None:
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(self._GATE, {"afr": 40.0})
        assert not result.accepted
        assert "lambda" in result.reason.lower() or "40" in result.reason

    def test_rejects_missing_channel(self) -> None:
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(self._GATE, {"rpm": 1000.0})
        assert not result.accepted
        assert "no lambda" in result.reason

    def test_accepts_normal_afr(self) -> None:
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(self._GATE, {"afr": 14.7})
        assert result.accepted

    def test_accepts_lambda_channel(self) -> None:
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(self._GATE, {"lambda": 1.0})
        assert result.accepted

    def test_rejects_lambda_out_of_range(self) -> None:
        ev = AutotuneFilterGateEvaluator()
        # lambda 0.3 = AFR ~4.4 — implausible
        result = ev.evaluate(self._GATE, {"lambda": 0.3})
        assert not result.accepted

    def test_accepts_boundary_lambda(self) -> None:
        ev = AutotuneFilterGateEvaluator()
        assert AutotuneFilterGateEvaluator().evaluate(self._GATE, {"lambda": 0.5}).accepted
        assert AutotuneFilterGateEvaluator().evaluate(self._GATE, {"lambda": 1.8}).accepted


# ---------------------------------------------------------------------------
# std_Custom pass-through
# ---------------------------------------------------------------------------

def test_std_custom_always_passes() -> None:
    gate = _gate("std_Custom")
    ev = AutotuneFilterGateEvaluator()
    result = ev.evaluate(gate, {"afr": 40.0})
    assert result.accepted


# ---------------------------------------------------------------------------
# Axis bound gates
# ---------------------------------------------------------------------------

class TestAxisBoundGates:
    def test_x_axis_min_rejects(self) -> None:
        gate = _gate("std_xAxisMin")
        ev = AutotuneFilterGateEvaluator()
        ctx = AxisContext(x_value=400.0, x_min=500.0)
        result = ev.evaluate(gate, {}, axis_context=ctx)
        assert not result.accepted
        assert "400" in result.reason

    def test_x_axis_min_accepts(self) -> None:
        gate = _gate("std_xAxisMin")
        ev = AutotuneFilterGateEvaluator()
        ctx = AxisContext(x_value=600.0, x_min=500.0)
        result = ev.evaluate(gate, {}, axis_context=ctx)
        assert result.accepted

    def test_x_axis_max_rejects(self) -> None:
        gate = _gate("std_xAxisMax")
        ev = AutotuneFilterGateEvaluator()
        ctx = AxisContext(x_value=7000.0, x_max=6000.0)
        result = ev.evaluate(gate, {}, axis_context=ctx)
        assert not result.accepted

    def test_y_axis_min_rejects(self) -> None:
        gate = _gate("std_yAxisMin")
        ev = AutotuneFilterGateEvaluator()
        ctx = AxisContext(y_value=20.0, y_min=30.0)
        result = ev.evaluate(gate, {}, axis_context=ctx)
        assert not result.accepted

    def test_y_axis_max_rejects(self) -> None:
        gate = _gate("std_yAxisMax")
        ev = AutotuneFilterGateEvaluator()
        ctx = AxisContext(y_value=110.0, y_max=100.0)
        result = ev.evaluate(gate, {}, axis_context=ctx)
        assert not result.accepted

    def test_axis_gate_passes_without_context(self) -> None:
        for gate_name in ("std_xAxisMin", "std_xAxisMax", "std_yAxisMin", "std_yAxisMax"):
            gate = _gate(gate_name)
            ev = AutotuneFilterGateEvaluator()
            result = ev.evaluate(gate, {"rpm": 1000.0})
            assert result.accepted, f"{gate_name} should pass through without axis context"


# ---------------------------------------------------------------------------
# Parametric gates — all operators
# ---------------------------------------------------------------------------

class TestParametricGates:
    def test_less_than_rejects(self) -> None:
        gate = _gate("minCltFilter", "Minimum CLT", "coolant", "<", 71.0)
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(gate, {"coolant": 50.0})
        assert not result.accepted
        assert "coolant" in result.reason

    def test_less_than_accepts(self) -> None:
        gate = _gate("minCltFilter", "Minimum CLT", "coolant", "<", 71.0)
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(gate, {"coolant": 85.0})
        assert result.accepted

    def test_less_than_boundary(self) -> None:
        gate = _gate("minCltFilter", "Minimum CLT", "coolant", "<", 71.0)
        ev = AutotuneFilterGateEvaluator()
        assert ev.evaluate(gate, {"coolant": 71.0}).accepted

    def test_greater_than_rejects(self) -> None:
        gate = _gate("maxTPS", "Max TPS", "throttle", ">", 15.0)
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(gate, {"tps": 20.0})
        assert not result.accepted

    def test_greater_than_accepts(self) -> None:
        gate = _gate("maxTPS", "Max TPS", "throttle", ">", 15.0)
        ev = AutotuneFilterGateEvaluator()
        assert ev.evaluate(gate, {"tps": 10.0}).accepted

    def test_equal_rejects(self) -> None:
        gate = _gate("overrunFilter", "Overrun", "pulsewidth", "=", 0.0)
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(gate, {"pulseWidth": 0.0})
        assert not result.accepted

    def test_equal_accepts(self) -> None:
        gate = _gate("overrunFilter", "Overrun", "pulsewidth", "=", 0.0)
        ev = AutotuneFilterGateEvaluator()
        assert ev.evaluate(gate, {"pulseWidth": 3.5}).accepted

    def test_double_equal_normalised(self) -> None:
        gate = _gate("overrunFilter", "Overrun", "pulsewidth", "==", 0.0)
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(gate, {"pulseWidth": 0.0})
        assert not result.accepted

    def test_not_equal_rejects(self) -> None:
        gate = _gate("syncCheck", "Sync check", "sync", "!=", 1.0)
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(gate, {"sync": 0.0})
        assert not result.accepted

    def test_not_equal_accepts(self) -> None:
        gate = _gate("syncCheck", "Sync check", "sync", "!=", 1.0)
        ev = AutotuneFilterGateEvaluator()
        assert ev.evaluate(gate, {"sync": 1.0}).accepted

    def test_less_than_equal_rejects_at_boundary(self) -> None:
        gate = _gate("test", "Test <=", "rpm", "<=", 300.0)
        ev = AutotuneFilterGateEvaluator()
        assert not ev.evaluate(gate, {"rpm": 300.0}).accepted

    def test_greater_than_equal_rejects_at_boundary(self) -> None:
        gate = _gate("test", "Test >=", "rpm", ">=", 6000.0)
        ev = AutotuneFilterGateEvaluator()
        assert not ev.evaluate(gate, {"rpm": 6000.0}).accepted

    def test_bitwise_and_rejects(self) -> None:
        # accelFilter: engine & 16 → reject if accel enrichment active
        gate = _gate("accelFilter", "Accel Flag", "engine", "&", 16.0)
        ev = AutotuneFilterGateEvaluator()
        result = ev.evaluate(gate, {"engine": 16.0})
        assert not result.accepted
        assert "accelFilter" in result.reason or "Accel" in result.reason

    def test_bitwise_and_accepts_when_bit_clear(self) -> None:
        gate = _gate("accelFilter", "Accel Flag", "engine", "&", 16.0)
        ev = AutotuneFilterGateEvaluator()
        assert ev.evaluate(gate, {"engine": 0x01}).accepted

    def test_bitwise_and_rejects_combined_flags(self) -> None:
        gate = _gate("aseFilter", "ASE Flag", "engine", "&", 4.0)
        ev = AutotuneFilterGateEvaluator()
        assert not ev.evaluate(gate, {"engine": 0x07}).accepted


# ---------------------------------------------------------------------------
# Default-disabled gate passes through
# ---------------------------------------------------------------------------

def test_disabled_gate_always_passes() -> None:
    gate = _gate("accelFilter", "Accel Flag", "engine", "&", 16.0, default_enabled=False)
    ev = AutotuneFilterGateEvaluator()
    result = ev.evaluate(gate, {"engine": 16.0})
    assert result.accepted


# ---------------------------------------------------------------------------
# Missing channel pass-through
# ---------------------------------------------------------------------------

def test_parametric_gate_passes_through_when_channel_missing() -> None:
    gate = _gate("minCltFilter", "Min CLT", "coolant", "<", 71.0)
    ev = AutotuneFilterGateEvaluator()
    result = ev.evaluate(gate, {"rpm": 1000.0})  # no coolant channel
    assert result.accepted


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------

class TestEvaluateAll:
    def test_fail_fast_stops_at_first_rejection(self) -> None:
        gates = (
            _gate("minCltFilter", "Min CLT", "coolant", "<", 71.0),
            _gate("overrunFilter", "Overrun", "pulsewidth", "=", 0.0),
        )
        ev = AutotuneFilterGateEvaluator()
        results = ev.evaluate_all(
            gates,
            {"coolant": 50.0, "pulseWidth": 0.0},
            fail_fast=True,
        )
        assert len(results) == 1
        assert not results[0].accepted
        assert results[0].gate_name == "minCltFilter"

    def test_no_fail_fast_evaluates_all(self) -> None:
        gates = (
            _gate("minCltFilter", "Min CLT", "coolant", "<", 71.0),
            _gate("overrunFilter", "Overrun", "pulsewidth", "=", 0.0),
        )
        ev = AutotuneFilterGateEvaluator()
        results = ev.evaluate_all(
            gates,
            {"coolant": 50.0, "pulseWidth": 0.0},
            fail_fast=False,
        )
        assert len(results) == 2
        assert all(not r.accepted for r in results)

    def test_all_accepted(self) -> None:
        gates = (
            _gate("minCltFilter", "Min CLT", "coolant", "<", 71.0),
            _gate("overrunFilter", "Overrun", "pulsewidth", "=", 0.0),
        )
        ev = AutotuneFilterGateEvaluator()
        results = ev.evaluate_all(
            gates,
            {"coolant": 85.0, "pulseWidth": 3.5},
        )
        assert len(results) == 2
        assert all(r.accepted for r in results)


# ---------------------------------------------------------------------------
# gate_label
# ---------------------------------------------------------------------------

def test_gate_label_returns_ini_label_when_present() -> None:
    gate = _gate("minCltFilter", "Minimum CLT", "coolant", "<", 71.0)
    ev = AutotuneFilterGateEvaluator()
    assert ev.gate_label(gate) == "Minimum CLT"


def test_gate_label_falls_back_to_standard_label() -> None:
    gate = _gate("std_DeadLambda")
    ev = AutotuneFilterGateEvaluator()
    assert "lambda" in ev.gate_label(gate).lower() or "dead" in ev.gate_label(gate).lower()


def test_gate_label_falls_back_to_name() -> None:
    gate = _gate("customGate123")
    ev = AutotuneFilterGateEvaluator()
    assert ev.gate_label(gate) == "customGate123"
