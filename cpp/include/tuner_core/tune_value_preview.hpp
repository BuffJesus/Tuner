// SPDX-License-Identifier: MIT
//
// tuner_core::tune_value_preview — pure-logic port of the `_preview` /
// `_list_preview` helpers shared by `StagedChangeService` and
// `TuningPageDiffService`. Eleventh sub-slice of the Phase 14
// workspace-services port (Slice 4).
//
// Mirrors Python's `str(float)` repr exactly: shortest round-trip
// representation, with an explicit trailing `.0` for whole-number
// floats so they remain visually distinct from ints. List previews
// truncate after the first 4 items and append `" ... (N values)"`
// when more items exist.

#pragma once

#include <span>
#include <string>
#include <variant>
#include <vector>

namespace tuner_core::tune_value_preview {

// A staged tune value is either a single double (scalar) or a list
// of doubles (table / array). Mirrors the Python `TuneValue.value`
// shape from the staged-change layer.
using ScalarOrList = std::variant<double, std::vector<double>>;

// Format `value` the way Python's `str(float)` does — shortest
// round-trip representation, with an explicit `.0` suffix for
// whole-number floats.
std::string format_scalar_python_repr(double value);

// Format a list of doubles as `"a, b, c, d ... (N values)"` (or
// without the suffix when N <= 4). Mirrors `_list_preview`.
std::string format_list_preview(std::span<const double> values);

// Dispatch helper: scalar arm goes through `format_scalar_python_repr`,
// list arm goes through `format_list_preview`. Mirrors the inner
// branch of `_preview`. The "n/a" branch for `tune_value is None` is
// the caller's responsibility — pass `format_value_preview(...)` only
// when you have a value.
std::string format_value_preview(const ScalarOrList& value);

}  // namespace tuner_core::tune_value_preview
