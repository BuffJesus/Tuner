// SPDX-License-Identifier: MIT
//
// tuner_core::autotune_filter_gate_evaluator — port of the Python
// `AutotuneFilterGateEvaluator`. Fifth sub-slice of the Phase 14
// workspace-services port (Slice 4).
//
// Mirrors `tuner.services.autotune_filter_gate_evaluator` exactly:
// the same standard named gates (std_DeadLambda, std_xAxisMin/Max,
// std_yAxisMin/Max, std_Custom), the same parametric-gate fallthrough,
// and the same fail-open semantics for unknown / under-specified
// gates. Sits on top of `sample_gate_helpers` for the operator
// dispatch and channel resolver.

#pragma once

#include "tuner_core/sample_gate_helpers.hpp"

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::autotune_filter_gate_evaluator {

// POD mirror of the Python `AutotuneFilterGate`. Only the fields the
// evaluator actually reads are carried — the full domain dataclass on
// the Python side has additional INI-source metadata that is not
// load-bearing for evaluation.
struct Gate {
    std::string name;
    std::string label;
    std::optional<std::string> channel;
    std::optional<std::string> op;       // "<", ">", "<=", ">=", "==", "!=", "&" (or "=")
    std::optional<double> threshold;
    bool default_enabled = true;
};

// POD mirror of the Python `AxisContext`. Each field is independently
// optional so the caller can supply only the axes that exist for the
// current table.
struct AxisContext {
    std::optional<double> x_value;
    std::optional<double> x_min;
    std::optional<double> x_max;
    std::optional<double> y_value;
    std::optional<double> y_min;
    std::optional<double> y_max;
};

// Result of evaluating one gate against one record. Mirrors
// `SampleGateEval` field-for-field.
struct Eval {
    std::string gate_name;
    bool accepted = true;
    std::string reason;  // human-readable; non-empty when rejected
};

using ValueMap = sample_gate_helpers::ValueMap;

// Evaluate a single gate against a record. Standard named gates
// (`std_DeadLambda`, `std_xAxis*`, `std_yAxis*`, `std_Custom`) take
// the named-gate path; everything else with channel+operator+threshold
// takes the parametric path; anything else passes through.
Eval evaluate(
    const Gate& gate,
    const ValueMap& record_values,
    const AxisContext* axis_context = nullptr);

// Evaluate a sequence of gates. Stops at the first rejection when
// `fail_fast == true`. Mirrors `evaluate_all`.
std::vector<Eval> evaluate_all(
    const std::vector<Gate>& gates,
    const ValueMap& record_values,
    const AxisContext* axis_context = nullptr,
    bool fail_fast = true);

// Human-readable label for a gate: returns the explicit label when
// set, otherwise the standard-gate label, otherwise the gate name.
std::string gate_label(const Gate& gate);

}  // namespace tuner_core::autotune_filter_gate_evaluator
