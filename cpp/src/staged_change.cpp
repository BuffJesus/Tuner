// SPDX-License-Identifier: MIT
//
// tuner_core::staged_change implementation. Pure logic.

#include "tuner_core/staged_change.hpp"

#include <algorithm>

namespace tuner_core::staged_change {

namespace {

const ScalarOrList* find_value(
    const std::vector<std::pair<std::string, ScalarOrList>>& values,
    const std::string& name) {
    for (const auto& [k, v] : values) {
        if (k == name) return &v;
    }
    return nullptr;
}

const std::string* find_string(
    const std::vector<std::pair<std::string, std::string>>& values,
    const std::string& name) {
    for (const auto& [k, v] : values) {
        if (k == name) return &v;
    }
    return nullptr;
}

}  // namespace

std::vector<StagedEntry> summarize(
    const std::vector<std::pair<std::string, ScalarOrList>>& staged_values,
    const std::vector<std::pair<std::string, ScalarOrList>>& base_values,
    const std::vector<std::pair<std::string, std::string>>& page_titles,
    const std::set<std::string>& written_names) {
    // Mirror `sorted(edit_service.staged_values.items())`: sort by
    // key (lexicographic) before iterating.
    std::vector<std::pair<std::string, ScalarOrList>> sorted_staged(staged_values);
    std::sort(sorted_staged.begin(), sorted_staged.end(),
              [](const auto& a, const auto& b) { return a.first < b.first; });

    std::vector<StagedEntry> entries;
    entries.reserve(sorted_staged.size());
    for (const auto& [name, staged] : sorted_staged) {
        StagedEntry entry;
        entry.name = name;
        entry.preview = tune_value_preview::format_value_preview(staged);
        const auto* base = find_value(base_values, name);
        entry.before_preview = (base != nullptr)
            ? tune_value_preview::format_value_preview(*base)
            : "n/a";
        const auto* title = find_string(page_titles, name);
        entry.page_title = (title != nullptr) ? *title : "Other";
        entry.is_written = written_names.count(name) > 0;
        entries.push_back(std::move(entry));
    }
    return entries;
}

}  // namespace tuner_core::staged_change
