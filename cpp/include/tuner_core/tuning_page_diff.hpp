// SPDX-License-Identifier: MIT
//
// tuner_core::tuning_page_diff — port of `TuningPageDiffService`.
// Thirteenth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Builds the per-page diff the workspace presenter renders for the
// "review staged changes on this page" surface. Composes the
// tune_value_preview helper with dirty-only iteration, plus the
// `summary` and `detail_text` projection helpers the workspace UI
// reads directly.

#pragma once

#include "tuner_core/tune_value_preview.hpp"

#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace tuner_core::tuning_page_diff {

using ScalarOrList = tune_value_preview::ScalarOrList;

struct DiffEntry {
    std::string name;
    std::string before_preview;
    std::string after_preview;
};

struct DiffResult {
    std::vector<DiffEntry> entries;
};

// Mirror `TuningPageDiffService.build_page_diff`. The function:
//   1. Iterates `parameter_names` in input order.
//   2. Skips entries not in `dirty_names` (mirrors `is_dirty(name)`).
//   3. Skips entries whose staged value is missing (Python: `staged_value is None`).
//   4. Formats both before (base) and after (staged) previews via
//      `tune_value_preview::format_value_preview`. Missing base
//      values become `"n/a"`.
//
// `parameter_names` carries the iteration order — typically the
// `page.parameter_names` tuple from the Python `TuningPage`. The
// staged and base value maps are passed as parallel-array lookups so
// the FFI boundary doesn't lose order or alias collisions.
DiffResult build_page_diff(
    const std::vector<std::string>& parameter_names,
    const std::set<std::string>& dirty_names,
    const std::vector<std::pair<std::string, ScalarOrList>>& staged_values,
    const std::vector<std::pair<std::string, ScalarOrList>>& base_values);

// Mirror `TuningPageDiffResult.summary` — returns
// "No staged changes on this page." for an empty result, otherwise
// "{N} staged change[s] on this page.".
std::string summary(const DiffResult& result);

// Mirror `TuningPageDiffResult.detail_text` — returns
// "No staged changes on this page." for empty results, otherwise a
// newline-joined "{name}: {before} -> {after}" line per entry.
std::string detail_text(const DiffResult& result);

}  // namespace tuner_core::tuning_page_diff
