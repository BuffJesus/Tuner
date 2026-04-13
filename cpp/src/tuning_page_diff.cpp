// SPDX-License-Identifier: MIT
//
// tuner_core::tuning_page_diff implementation. Pure logic.

#include "tuner_core/tuning_page_diff.hpp"

namespace tuner_core::tuning_page_diff {

namespace {

const ScalarOrList* find_value(
    const std::vector<std::pair<std::string, ScalarOrList>>& values,
    const std::string& name) {
    for (const auto& [k, v] : values) {
        if (k == name) return &v;
    }
    return nullptr;
}

}  // namespace

DiffResult build_page_diff(
    const std::vector<std::string>& parameter_names,
    const std::set<std::string>& dirty_names,
    const std::vector<std::pair<std::string, ScalarOrList>>& staged_values,
    const std::vector<std::pair<std::string, ScalarOrList>>& base_values) {
    DiffResult result;
    for (const auto& name : parameter_names) {
        if (dirty_names.count(name) == 0) continue;
        const auto* staged = find_value(staged_values, name);
        if (staged == nullptr) continue;  // mirrors `if staged_value is None: continue`
        DiffEntry entry;
        entry.name = name;
        const auto* base = find_value(base_values, name);
        entry.before_preview = (base != nullptr)
            ? tune_value_preview::format_value_preview(*base)
            : "n/a";
        entry.after_preview = tune_value_preview::format_value_preview(*staged);
        result.entries.push_back(std::move(entry));
    }
    return result;
}

std::string summary(const DiffResult& result) {
    const std::size_t count = result.entries.size();
    if (count == 0) return "No staged changes on this page.";
    std::string out = std::to_string(count);
    out += " staged change";
    if (count != 1) out += "s";
    out += " on this page.";
    return out;
}

std::string detail_text(const DiffResult& result) {
    if (result.entries.empty()) return "No staged changes on this page.";
    std::string out;
    for (std::size_t i = 0; i < result.entries.size(); ++i) {
        if (i > 0) out += "\n";
        out += result.entries[i].name;
        out += ": ";
        out += result.entries[i].before_preview;
        out += " -> ";
        out += result.entries[i].after_preview;
    }
    return out;
}

}  // namespace tuner_core::tuning_page_diff
