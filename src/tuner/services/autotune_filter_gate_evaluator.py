"""Evaluates AutotuneFilterGate objects parsed from INI [VeAnalyze]/[WueAnalyze] sections.

Standard named gates implement known semantics so they can be evaluated even when
no parametric channel/operator/threshold is supplied by the INI.  Parametric gates
carry all four fields and are evaluated structurally.

Supported operators (matching TunerStudio VeAnalyze syntax):
    <   less-than
    >   greater-than
    <=  less-than-or-equal
    >=  greater-than-or-equal
    ==  equal (also = is normalised to ==)
    !=  not-equal
    &   bitwise-AND non-zero (used for engine status flags)

Standard named gates handled here:
    std_DeadLambda  — lambda/AFR outside plausible range [0.5, 1.8] lambda
    std_xAxisMin    — below X-axis minimum (requires axis context)
    std_xAxisMax    — above X-axis maximum
    std_yAxisMin    — below Y-axis minimum
    std_yAxisMax    — above Y-axis maximum
    std_Custom      — custom expression; treated as pass-through (not rejectable here)

Axis bound gates (std_xAxisMin/Max, std_yAxisMin/Max) require the caller to supply
``axis_x_value``, ``axis_x_min``/``max``, etc. via ``AxisContext``.  Without those
values the gate passes through silently.
"""

from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.ecu_definition import AutotuneFilterGate
from tuner.services.replay_sample_gate_service import SampleGateEval, _resolve_channel


@dataclass(slots=True, frozen=True)
class AxisContext:
    """Optional axis bound information for std_xAxis/std_yAxis gate evaluation."""

    x_value: float | None = None
    x_min: float | None = None
    x_max: float | None = None
    y_value: float | None = None
    y_min: float | None = None
    y_max: float | None = None


# Lambda plausibility range used by std_DeadLambda (0.5–1.8 λ covers AFR ~7.3–26.5)
_LAMBDA_MIN = 0.5
_LAMBDA_MAX = 1.8

# Standard named gates that do not carry channel/operator/threshold in the INI
_STANDARD_PASSTHROUGH_GATES = frozenset({"std_Custom"})

_STANDARD_GATE_LABELS: dict[str, str] = {
    "std_DeadLambda": "Dead/implausible lambda reading",
    "std_xAxisMin":   "Below X-axis minimum",
    "std_xAxisMax":   "Above X-axis maximum",
    "std_yAxisMin":   "Below Y-axis minimum",
    "std_yAxisMax":   "Above Y-axis maximum",
    "std_Custom":     "Custom expression filter",
}


def _normalise_operator(op: str) -> str:
    s = op.strip()
    if s == "=":
        return "=="
    return s


def _apply_operator(channel_value: float, operator: str, threshold: float) -> bool:
    """Return True when the channel_value passes the gate (i.e. the sample is NOT rejected).

    TunerStudio VeAnalyze filter semantics: a filter *rejects* when the expression
    evaluates to True.  We return True here when the expression fires (reject condition
    is met) so the caller can decide whether to accept or reject.
    """
    op = _normalise_operator(operator)
    if op == "<":
        return channel_value < threshold
    if op == ">":
        return channel_value > threshold
    if op == "<=":
        return channel_value <= threshold
    if op == ">=":
        return channel_value >= threshold
    if op == "==":
        return channel_value == threshold
    if op == "!=":
        return channel_value != threshold
    if op == "&":
        return bool(int(channel_value) & int(threshold))
    return False  # unknown operator → do not reject


class AutotuneFilterGateEvaluator:
    """Evaluate a single ``AutotuneFilterGate`` against a record's channel values.

    Usage::

        evaluator = AutotuneFilterGateEvaluator()
        result = evaluator.evaluate(gate, record.values)
        if not result.accepted:
            print(result.reason)
    """

    def evaluate(
        self,
        gate: AutotuneFilterGate,
        record_values: dict[str, float],
        *,
        axis_context: AxisContext | None = None,
    ) -> SampleGateEval:
        """Evaluate *gate* against *record_values* and return a ``SampleGateEval``."""
        if not gate.default_enabled:
            # Gate declared disabled by default; pass through unless caller overrides.
            return SampleGateEval(gate_name=gate.name, accepted=True, reason="")

        # Standard pass-through gates (std_Custom)
        if gate.name in _STANDARD_PASSTHROUGH_GATES:
            return SampleGateEval(gate_name=gate.name, accepted=True, reason="")

        # Dispatch to specialised standard-gate handlers
        if gate.name == "std_DeadLambda":
            return self._eval_dead_lambda(gate, record_values)
        if gate.name == "std_xAxisMin":
            return self._eval_axis_bound(gate, axis_context, "x", "min")
        if gate.name == "std_xAxisMax":
            return self._eval_axis_bound(gate, axis_context, "x", "max")
        if gate.name == "std_yAxisMin":
            return self._eval_axis_bound(gate, axis_context, "y", "min")
        if gate.name == "std_yAxisMax":
            return self._eval_axis_bound(gate, axis_context, "y", "max")

        # Parametric gate: must have channel + operator + threshold
        if gate.channel and gate.operator and gate.threshold is not None:
            return self._eval_parametric(gate, record_values)

        # Named gate with no parametric fields and not a known standard gate —
        # treat as pass-through rather than silently rejecting everything.
        return SampleGateEval(gate_name=gate.name, accepted=True, reason="")

    # ------------------------------------------------------------------
    # Standard gate implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _eval_dead_lambda(
        gate: AutotuneFilterGate,
        record_values: dict[str, float],
    ) -> SampleGateEval:
        """Reject if lambda reading is absent or outside [0.5, 1.8] λ."""
        # Try lambda channel first, then derive from AFR
        lambda_val: float | None = None
        for key, value in record_values.items():
            if "lambda" in key.lower():
                lambda_val = value
                break
        if lambda_val is None:
            for key, value in record_values.items():
                k = key.lower()
                if "afr" in k or "ego" in k:
                    lambda_val = value / 14.7
                    break

        if lambda_val is None:
            return SampleGateEval(
                gate_name=gate.name,
                accepted=False,
                reason="no lambda/AFR channel present",
            )
        if not (_LAMBDA_MIN <= lambda_val <= _LAMBDA_MAX):
            return SampleGateEval(
                gate_name=gate.name,
                accepted=False,
                reason=(
                    f"lambda {lambda_val:.3f} outside plausible range "
                    f"[{_LAMBDA_MIN}, {_LAMBDA_MAX}]"
                ),
            )
        return SampleGateEval(gate_name=gate.name, accepted=True, reason="")

    @staticmethod
    def _eval_axis_bound(
        gate: AutotuneFilterGate,
        axis_context: AxisContext | None,
        axis: str,       # "x" or "y"
        bound: str,      # "min" or "max"
    ) -> SampleGateEval:
        """Reject if axis value is outside the declared bound."""
        if axis_context is None:
            return SampleGateEval(gate_name=gate.name, accepted=True, reason="")
        if axis == "x":
            value = axis_context.x_value
            limit = axis_context.x_min if bound == "min" else axis_context.x_max
        else:
            value = axis_context.y_value
            limit = axis_context.y_min if bound == "min" else axis_context.y_max

        if value is None or limit is None:
            return SampleGateEval(gate_name=gate.name, accepted=True, reason="")

        reject = (value < limit) if bound == "min" else (value > limit)
        if reject:
            direction = "below" if bound == "min" else "above"
            return SampleGateEval(
                gate_name=gate.name,
                accepted=False,
                reason=f"{axis.upper()} value {value} {direction} axis {bound} {limit}",
            )
        return SampleGateEval(gate_name=gate.name, accepted=True, reason="")

    @staticmethod
    def _eval_parametric(
        gate: AutotuneFilterGate,
        record_values: dict[str, float],
    ) -> SampleGateEval:
        """Evaluate a parametric gate (channel op threshold)."""
        assert gate.channel is not None
        assert gate.operator is not None
        assert gate.threshold is not None

        channel_value = _resolve_channel(gate.channel, record_values)
        if channel_value is None:
            # Channel not present in this record → pass through
            return SampleGateEval(gate_name=gate.name, accepted=True, reason="")

        reject_condition_fires = _apply_operator(
            channel_value, gate.operator, gate.threshold
        )
        if reject_condition_fires:
            label = gate.label or gate.name
            op_str = _normalise_operator(gate.operator)
            return SampleGateEval(
                gate_name=gate.name,
                accepted=False,
                reason=(
                    f"{label}: {gate.channel}={channel_value} "
                    f"{op_str} {gate.threshold} (reject condition met)"
                ),
            )
        return SampleGateEval(gate_name=gate.name, accepted=True, reason="")

    def evaluate_all(
        self,
        gates: tuple[AutotuneFilterGate, ...],
        record_values: dict[str, float],
        *,
        axis_context: AxisContext | None = None,
        fail_fast: bool = True,
    ) -> list[SampleGateEval]:
        """Evaluate a sequence of gates, stopping at the first rejection when fail_fast=True."""
        results: list[SampleGateEval] = []
        for gate in gates:
            result = self.evaluate(gate, record_values, axis_context=axis_context)
            results.append(result)
            if fail_fast and not result.accepted:
                break
        return results

    def gate_label(self, gate: AutotuneFilterGate) -> str:
        """Human-readable label for a gate."""
        if gate.label:
            return gate.label
        return _STANDARD_GATE_LABELS.get(gate.name, gate.name)
