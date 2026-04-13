// SPDX-License-Identifier: MIT
//
// tuner_core::staged_change — port of `StagedChangeService.summarize`.
// Twelfth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Builds the operator-facing list of staged changes the workspace
// review surface renders. Composes the `tune_value_preview` helpers
// (already in C++) with sorted iteration over staged values, a
// page-title lookup, and a written-names membership check.

#pragma once

#include "tuner_core/tune_value_preview.hpp"

#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace tuner_core::staged_change {

using ScalarOrList = tune_value_preview::ScalarOrList;

struct StagedEntry {
    std::string name;
    std::string preview;
    std::string before_preview;
    std::string page_title;
    bool is_written = false;
};

// Mirror `StagedChangeService.summarize`. The function:
//   1. Iterates `staged_values` in lexicographic key order (mirrors
//      Python's `sorted(edit_service.staged_values.items())`).
//   2. For each entry, formats the staged value via the
//      tune_value_preview helper.
//   3. Looks up the corresponding base value (nullopt → "n/a").
//   4. Resolves the page title via `page_titles.get(name, "Other")`.
//   5. Tags `is_written` from the `written_names` membership.
//
// `staged_values` and `base_values` are passed as parallel-array
// lists so the binding boundary doesn't lose insertion order (the
// staged side is sorted internally; the base side is queried by name).
std::vector<StagedEntry> summarize(
    const std::vector<std::pair<std::string, ScalarOrList>>& staged_values,
    const std::vector<std::pair<std::string, ScalarOrList>>& base_values,
    const std::vector<std::pair<std::string, std::string>>& page_titles,
    const std::set<std::string>& written_names);

}  // namespace tuner_core::staged_change
