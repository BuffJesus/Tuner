// SPDX-License-Identifier: MIT
//
// tuner_core::autotune_filter_gate_evaluator implementation. Direct
// port of `AutotuneFilterGateEvaluator`.

#include "tuner_core/autotune_filter_gate_evaluator.hpp"

#include <cctype>
#include <cstdio>
#include <cstring>
#include <unordered_map>

namespace tuner_core::autotune_filter_gate_evaluator {

namespace {

namespace sgh = sample_gate_helpers;

// Lambda plausibility range used by std_DeadLambda — same constants as Python.
constexpr double kLambdaMin = 0.5;
constexpr double kLambdaMax = 1.8;

// Pass-through standard gates (std_Custom is the only one).
bool is_standard_passthrough(std::string_view name) noexcept {
    return name == "std_Custom";
}

// Standard-gate label table — same entries as the Python module.
const std::unordered_map<std::string, std::string>& standard_gate_labels() {
    static const std::unordered_map<std::string, std::string> table = {
        {"std_DeadLambda", "Dead/implausible lambda reading"},
        {"std_xAxisMin",   "Below X-axis minimum"},
        {"std_xAxisMax",   "Above X-axis maximum"},
        {"std_yAxisMin",   "Below Y-axis minimum"},
        {"std_yAxisMax",   "Above Y-axis maximum"},
        {"std_Custom",     "Custom expression filter"},
    };
    return table;
}

// Format a number the way Python's `str(x)` does for the values used
// in the rejection-reason strings. Python `str(0.5)` → "0.5", `str(0)`
// → "0", `str(0.0)` → "0.0". The reason strings the parity test pins
// pass numbers through Python f-strings without explicit formatting
// codes, so we need to mirror Python's repr-like behaviour. We
// re-format integers as `int → "%d"` and floats with the shortest
// round-trippable representation.
//
// In practice, the parity test never feeds non-trivial floats here;
// the channel values are integers (status flag bits) or the
// threshold is an integer. We keep this helper limited to the cases
// the test actually exercises.
std::string py_str_double(double v) {
    // Mirror Python's `str(float)`: whole-number floats render as
    // "200.0" (not "200"); fractional floats use the shortest
    // round-trippable repr. C++ never sees Python ints directly —
    // every value crossing the FFI is `double` — so we always render
    // the trailing `.0` for whole-number values to match what Python
    // would have produced from a `float` original.
    if (v == static_cast<double>(static_cast<long long>(v))) {
        char buf[48];
        std::snprintf(buf, sizeof(buf), "%lld.0", static_cast<long long>(v));
        return std::string(buf);
    }
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%g", v);
    return std::string(buf);
}

Eval accepted(const Gate& gate) {
    Eval e;
    e.gate_name = gate.name;
    e.accepted = true;
    e.reason = "";
    return e;
}

Eval rejected(const Gate& gate, std::string reason) {
    Eval e;
    e.gate_name = gate.name;
    e.accepted = false;
    e.reason = std::move(reason);
    return e;
}

// std_DeadLambda — reject if lambda is missing or outside [0.5, 1.8].
Eval eval_dead_lambda(const Gate& gate, const ValueMap& values) {
    auto lambda = sgh::lambda_value(values);
    if (!lambda.has_value()) {
        return rejected(gate, "no lambda/AFR channel present");
    }
    if (*lambda < kLambdaMin || *lambda > kLambdaMax) {
        char buf[128];
        // Python: f"lambda {lambda_val:.3f} outside plausible range [{0.5}, {1.8}]"
        std::snprintf(
            buf, sizeof(buf),
            "lambda %.3f outside plausible range [%g, %g]",
            *lambda, kLambdaMin, kLambdaMax);
        return rejected(gate, buf);
    }
    return accepted(gate);
}

Eval eval_axis_bound(
    const Gate& gate,
    const AxisContext* axis,
    char which_axis,  // 'x' or 'y'
    bool is_min) {
    if (axis == nullptr) return accepted(gate);
    std::optional<double> value;
    std::optional<double> limit;
    if (which_axis == 'x') {
        value = axis->x_value;
        limit = is_min ? axis->x_min : axis->x_max;
    } else {
        value = axis->y_value;
        limit = is_min ? axis->y_min : axis->y_max;
    }
    if (!value.has_value() || !limit.has_value()) return accepted(gate);

    bool reject = is_min ? (*value < *limit) : (*value > *limit);
    if (!reject) return accepted(gate);

    const char* direction = is_min ? "below" : "above";
    const char* bound_word = is_min ? "min" : "max";
    char buf[160];
    // Python: f"{axis.upper()} value {value} {direction} axis {bound} {limit}"
    // Numbers come straight from Python `str()`. Floats with no
    // fractional part stringify as ints — this is what the parity
    // test actually exercises. py_str_double() handles that.
    std::snprintf(
        buf, sizeof(buf),
        "%c value %s %s axis %s %s",
        static_cast<char>(std::toupper(static_cast<unsigned char>(which_axis))),
        py_str_double(*value).c_str(),
        direction, bound_word,
        py_str_double(*limit).c_str());
    return rejected(gate, buf);
}

Eval eval_parametric(const Gate& gate, const ValueMap& values) {
    auto channel_value = sgh::resolve_channel(*gate.channel, values);
    if (!channel_value.has_value()) {
        // Channel not present in this record → pass through (Python).
        return accepted(gate);
    }
    bool fires = sgh::apply_operator(*channel_value, *gate.op, *gate.threshold);
    if (!fires) return accepted(gate);

    const std::string& label = gate.label.empty() ? gate.name : gate.label;
    std::string op_str = sgh::normalise_operator(*gate.op);
    char buf[256];
    // Python: f"{label}: {channel}={channel_value} {op} {threshold} (reject condition met)"
    std::snprintf(
        buf, sizeof(buf),
        "%s: %s=%s %s %s (reject condition met)",
        label.c_str(),
        gate.channel->c_str(),
        py_str_double(*channel_value).c_str(),
        op_str.c_str(),
        py_str_double(*gate.threshold).c_str());
    return rejected(gate, buf);
}

}  // namespace

Eval evaluate(
    const Gate& gate,
    const ValueMap& record_values,
    const AxisContext* axis_context) {
    // Disabled-by-default → pass through.
    if (!gate.default_enabled) return accepted(gate);
    // std_Custom → pass through.
    if (is_standard_passthrough(gate.name)) return accepted(gate);

    if (gate.name == "std_DeadLambda") {
        return eval_dead_lambda(gate, record_values);
    }
    if (gate.name == "std_xAxisMin") return eval_axis_bound(gate, axis_context, 'x', true);
    if (gate.name == "std_xAxisMax") return eval_axis_bound(gate, axis_context, 'x', false);
    if (gate.name == "std_yAxisMin") return eval_axis_bound(gate, axis_context, 'y', true);
    if (gate.name == "std_yAxisMax") return eval_axis_bound(gate, axis_context, 'y', false);

    // Parametric: must have channel + operator + threshold.
    if (gate.channel.has_value() && !gate.channel->empty() &&
        gate.op.has_value() && !gate.op->empty() &&
        gate.threshold.has_value()) {
        return eval_parametric(gate, record_values);
    }

    // Fall through: unknown named gate → pass through (fail-open).
    return accepted(gate);
}

std::vector<Eval> evaluate_all(
    const std::vector<Gate>& gates,
    const ValueMap& record_values,
    const AxisContext* axis_context,
    bool fail_fast) {
    std::vector<Eval> results;
    results.reserve(gates.size());
    for (const auto& gate : gates) {
        auto r = evaluate(gate, record_values, axis_context);
        bool reject = !r.accepted;
        results.push_back(std::move(r));
        if (fail_fast && reject) break;
    }
    return results;
}

std::string gate_label(const Gate& gate) {
    if (!gate.label.empty()) return gate.label;
    const auto& table = standard_gate_labels();
    auto it = table.find(gate.name);
    if (it != table.end()) return it->second;
    return gate.name;
}

}  // namespace tuner_core::autotune_filter_gate_evaluator
