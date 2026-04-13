// SPDX-License-Identifier: MIT
//
// tuner_core::wue_analyze_helpers — pure-logic helpers from
// `tuner.services.wue_analyze_service`. Sixth sub-slice of the
// Phase 14 workspace-services port (Slice 4).
//
// Ported helpers:
//   - confidence_label(sample_count)  → "insufficient" / "low" / "medium" / "high"
//   - is_clt_axis(param_name)         → CLT/warmup keyword substring match
//   - clt_from_record(values)         → CLT channel lookup over record
//   - nearest_index(axis, value)      → nearest-value index in a numeric axis
//   - numeric_axis(labels)            → parse string labels to floats (all-or-nothing)
//   - parse_cell_float(text)          → safe float parse with nullopt fallback
//   - target_lambda_from_cell(raw, fallback) → AFR↔lambda conversion semantics
//
// The stateful `WueAnalyzeAccumulator` is not ported here — it depends
// on `TablePageSnapshot` and `ReplaySampleGateService`, which haven't
// landed in C++ yet. The helpers above are the substrate the
// accumulator builds on, plus they're directly useful from any C++
// service that wants the same CLT-axis detection / numeric-axis
// parsing semantics.

#pragma once

#include "tuner_core/sample_gate_helpers.hpp"

#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::wue_analyze_helpers {

using ValueMap = sample_gate_helpers::ValueMap;

// Confidence thresholds — same constants as the Python module.
inline constexpr int kConfidenceLow = 3;
inline constexpr int kConfidenceMedium = 10;
inline constexpr int kConfidenceHigh = 30;

// Stoichiometric AFR for gasoline (used by AFR ↔ lambda conversion).
inline constexpr double kStoichAfr = 14.7;

// Threshold above which a value is interpreted as AFR rather than
// lambda (used by `target_lambda_from_cell`).
inline constexpr double kAfrUnitMin = 2.0;

// Mirror Python `_confidence`. Returns the bucket label for a given
// sample count.
std::string confidence_label(int sample_count);

// Mirror Python `_is_clt_axis`: substring match against any of the
// CLT/warmup keywords (`"clt"`, `"coolant"`, `"warmup"`, `"wue"`,
// `"cold"`, `"temp"`). Empty / null name returns false.
bool is_clt_axis(std::string_view param_name);

// Mirror `_clt_from_record`: returns the first channel whose
// lowercased key contains "coolant" or "clt".
std::optional<double> clt_from_record(const ValueMap& values);

// Mirror `_nearest_index`: returns the index in `axis` whose value
// is nearest to `value`. Returns 0 for an empty axis (caller should
// guard) — preserves the Python no-throw behaviour for the empty
// case via the access pattern below.
std::size_t nearest_index(std::span<const double> axis, double value);

// Mirror `_numeric_axis`: parse `labels` as floats, return the
// resulting vector. Returns an empty vector if any label fails to
// parse (all-or-nothing, exactly like the Python function).
std::vector<double> numeric_axis(std::span<const std::string> labels);

// Mirror `_parse_cell_float`: safe float parse. Returns nullopt for
// empty / null / unparseable input.
std::optional<double> parse_cell_float(std::string_view cell_text);

// Mirror `_target_lambda_from_table`'s scalar branch: takes a raw
// cell value (as already-parsed double) and returns the lambda
// equivalent. Values above `kAfrUnitMin` are interpreted as AFR and
// divided by 14.7; smaller positive values are interpreted as
// lambda directly. Negative or zero values fall back to
// `scalar_fallback`.
double target_lambda_from_cell(double raw, double scalar_fallback);

}  // namespace tuner_core::wue_analyze_helpers
