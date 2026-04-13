// SPDX-License-Identifier: MIT
//
// tuner_core::sample_gate_helpers — pure-logic port of the small
// substrate that `ReplaySampleGateService` and
// `AutotuneFilterGateEvaluator` share. Fourth sub-slice of the
// Phase 14 workspace-services port (Slice 4).
//
// Functions ported:
//   - normalise_operator   (rewrite "=" to "==")
//   - apply_operator       (dispatch < > <= >= == != & on a channel value)
//   - resolve_channel      (alias-aware substring lookup over a record)
//   - lambda_value         (find lambda channel, or derive from AFR)
//   - afr_value            (find AFR channel, or derive from lambda)
//
// These helpers are used by both gate evaluators on the Python side;
// porting them first lets the larger gate-evaluator slices land
// without re-deriving the substrate each time.

#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace tuner_core::sample_gate_helpers {

// Insertion-order preserving record value map. Python dicts iterate
// in insertion order (since 3.7) and the alias resolver returns the
// FIRST matching key — so the C++ side must preserve order too. A
// `std::map` would break parity by sorting keys alphabetically.
using ValueMap = std::vector<std::pair<std::string, double>>;

// Mirror Python `_normalise_operator`: returns "==" when given "=",
// otherwise returns the input stripped of leading/trailing whitespace.
std::string normalise_operator(std::string_view op);

// Mirror `_apply_operator`. Returns true when the comparison fires
// (the reject condition is met) — the caller decides whether to
// accept or reject the sample. Unknown operators return false
// (do not reject), matching the Python fall-through.
bool apply_operator(double channel_value, std::string_view op, double threshold);

// Mirror `_resolve_channel`. Looks up `name` against a built-in
// alias table; for each alias, scans the record values for any key
// whose lowercased form contains the alias as a substring and
// returns the first match. Returns `std::nullopt` when no candidate
// matches.
std::optional<double> resolve_channel(std::string_view name, const ValueMap& values);

// Mirror `_lambda_value`: prefer a lambda channel, otherwise derive
// lambda from any AFR/EGO channel by dividing by 14.7.
std::optional<double> lambda_value(const ValueMap& values);

// Mirror `_afr_value`: prefer an AFR channel, otherwise derive AFR
// from a lambda channel by multiplying by 14.7.
std::optional<double> afr_value(const ValueMap& values);

}  // namespace tuner_core::sample_gate_helpers
