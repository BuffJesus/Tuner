// SPDX-License-Identifier: MIT
//
// tuner_core::replay_sample_gate — port of the Python
// `ReplaySampleGateService`. Thirtieth sub-slice of the Phase 14
// workspace-services port (Slice 4).
//
// Mirrors `tuner.services.replay_sample_gate_service` exactly: the
// same default gate set and priority order, the same parametric
// thresholds, the same fail-fast evaluation, and the same aggregate
// summary text format. Sits on top of `sample_gate_helpers` for the
// alias-aware channel resolver and the AFR/lambda derivation.
//
// The Python service composes `DataLog` / `DataLogRecord` directly;
// the C++ side takes a flat `ValueMap` per record so this slice does
// not pull the datalog domain types in. The future C++ datalog port
// can wrap this with a thin shim.

#pragma once

#include "tuner_core/sample_gate_helpers.hpp"

#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace tuner_core::replay_sample_gate {

using ValueMap = sample_gate_helpers::ValueMap;

// Mirror of Python `SampleGatingConfig`. Defaults match the Python
// dataclass field-for-field; an empty `enabled_gates` means "use
// the default gate set".
struct Config {
    std::set<std::string> enabled_gates;  // empty → DEFAULT_GATES
    double afr_min = 7.0;
    double afr_max = 25.0;
    double clt_min_celsius = 70.0;
    double tps_max_percent = 100.0;
    double rpm_min = 300.0;
    double pulsewidth_min_ms = 0.0;
    std::optional<double> axis_x_min;
    std::optional<double> axis_x_max;
    std::optional<double> axis_y_min;
    std::optional<double> axis_y_max;
    std::optional<double> axis_x_value;
    std::optional<double> axis_y_value;
    bool firmware_learn_gate_enabled = false;
};

// Result of evaluating one gate against one record. Mirrors the
// Python `SampleGateEval` field-for-field.
struct Eval {
    std::string gate_name;
    bool accepted = true;
    std::string reason;  // human-readable; non-empty when rejected
};

// Aggregate result of gating a sequence of records. Mirrors the
// Python `GatedSampleSummary`. `rejection_counts_by_gate` is sorted
// alphabetically by gate name (Python `sorted(dict.items())`).
struct Summary {
    std::size_t total_count = 0;
    std::size_t accepted_count = 0;
    std::size_t rejected_count = 0;
    std::vector<std::pair<std::string, std::size_t>> rejection_counts_by_gate;
    std::string summary_text;
    std::vector<std::string> detail_lines;
};

// Default gate set (used when `Config::enabled_gates` is empty).
// Returned in priority order, NOT alphabetical, mirroring the
// Python `_DEFAULT_GATE_ORDER` tuple. std_DeadLambda runs first
// because it is the most common fast-reject on real datalogs.
const std::vector<std::string>& default_gate_order();

// Evaluate every active gate against `record_values`. Stops at the
// first rejection (fail-fast) so callers get the primary reason
// only. Returns the partial list of evaluations up to and including
// the first rejection (or all of them if everything passed).
//
// When `Config::enabled_gates` is non-empty, the gates are run in
// alphabetical order to match Python `sorted(cfg.enabled_gates)`.
// When it is empty, `default_gate_order()` is used. The
// `firmwareLearnGate` is prepended (and runs first) whenever
// `Config::firmware_learn_gate_enabled` is true and the gate is not
// already in the active set.
std::vector<Eval> evaluate_record(
    const ValueMap& record_values,
    const Config& config);

// Convenience: returns true only if every active gate accepts the
// record.
bool is_accepted(const ValueMap& record_values, const Config& config);

// Convenience: returns the first rejection (or `std::nullopt` if the
// record was accepted by every gate).
std::optional<Eval> primary_rejection(
    const ValueMap& record_values,
    const Config& config);

// Aggregate gating over a sequence of records. The summary text and
// detail lines match the Python `gate_log` byte-for-byte.
Summary gate_records(
    const std::vector<ValueMap>& records,
    const Config& config);

}  // namespace tuner_core::replay_sample_gate
