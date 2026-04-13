// SPDX-License-Identifier: MIT
//
// tuner_core::parameter_catalog implementation. Pure logic.

#include "tuner_core/parameter_catalog.hpp"

#include <algorithm>
#include <cctype>
#include <map>
#include <variant>

namespace tuner_core::parameter_catalog {

namespace {

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

// Mirror Python `_preview_value`: None → "" (different from
// `tune_value_preview::format_value_preview` which returns "n/a").
// List arm and scalar arm match the standard preview formatter
// otherwise.
std::string preview_value(const ScalarOrList* value) {
    if (value == nullptr) return "";
    return tune_value_preview::format_value_preview(*value);
}

bool contains(std::string_view haystack, std::string_view needle) noexcept {
    return haystack.find(needle) != std::string_view::npos;
}

}  // namespace

std::vector<Entry> build_catalog(
    const std::vector<ScalarParameterInput>& scalars,
    const std::vector<TableParameterInput>& tables,
    const std::vector<TuneValueInput>& tune_values) {
    // Mirror `_tune_index` + the Python `staged_values.update(...)`
    // step the caller normally chains: build a name → TuneValueInput
    // map. The caller is responsible for already merging the staged
    // values on top of the tune file's constants + pc_variables, in
    // the same order Python does (`tune_file.constants` first,
    // `pc_variables` next, `staged_values` last).
    std::map<std::string, const TuneValueInput*> tune_index;
    for (const auto& tv : tune_values) {
        tune_index[tv.name] = &tv;
    }

    std::vector<Entry> entries;

    // Scalars from the definition.
    for (const auto& scalar : scalars) {
        Entry e;
        e.name = scalar.name;
        e.kind = "scalar";
        e.page = scalar.page;
        e.offset = scalar.offset;
        e.units = scalar.units;
        e.data_type = scalar.data_type;
        e.shape = "1x1";
        auto it = tune_index.find(scalar.name);
        e.tune_present = it != tune_index.end();
        e.tune_preview = e.tune_present ? preview_value(&it->second->value) : preview_value(nullptr);
        entries.push_back(std::move(e));
    }

    // Tables from the definition.
    for (const auto& table : tables) {
        Entry e;
        e.name = table.name;
        e.kind = "table";
        e.page = table.page;
        e.offset = table.offset;
        e.units = table.units;
        e.data_type = "array";
        e.shape = std::to_string(table.rows) + "x" + std::to_string(table.columns);
        auto it = tune_index.find(table.name);
        e.tune_present = it != tune_index.end();
        e.tune_preview = e.tune_present ? preview_value(&it->second->value) : preview_value(nullptr);
        entries.push_back(std::move(e));
    }

    // Tune-only entries: any tune value not already covered by a
    // definition entry. Mirrors the Python comprehension over
    // `tune_index.values()`.
    for (const auto& tv : tune_values) {
        bool already_present = false;
        for (const auto& e : entries) {
            if (e.name == tv.name) {
                already_present = true;
                break;
            }
        }
        if (already_present) continue;

        bool is_list = std::holds_alternative<std::vector<double>>(tv.value);
        bool is_table = (tv.rows > 0) || (tv.cols > 0) || is_list;

        std::string shape;
        if (is_list) {
            const auto& list = std::get<std::vector<double>>(tv.value);
            int rows = tv.rows > 0 ? tv.rows : static_cast<int>(list.size());
            int cols = tv.cols > 0 ? tv.cols : 1;
            shape = std::to_string(rows) + "x" + std::to_string(cols);
        } else {
            shape = "1x1";
        }

        Entry e;
        e.name = tv.name;
        e.kind = is_table ? "table" : "scalar";
        e.page = std::nullopt;
        e.offset = std::nullopt;
        e.units = tv.units;
        e.data_type = "tune-only";
        e.shape = std::move(shape);
        e.tune_present = true;
        e.tune_preview = preview_value(&tv.value);
        entries.push_back(std::move(e));
    }

    // Sort by (page or 9999, offset or 999999, lower(name)).
    std::sort(entries.begin(), entries.end(),
              [](const Entry& a, const Entry& b) {
                  int ap = a.page.value_or(9999);
                  int bp = b.page.value_or(9999);
                  if (ap != bp) return ap < bp;
                  int ao = a.offset.value_or(999999);
                  int bo = b.offset.value_or(999999);
                  if (ao != bo) return ao < bo;
                  return lowercase(a.name) < lowercase(b.name);
              });

    return entries;
}

std::vector<Entry> filter_catalog(
    const std::vector<Entry>& entries,
    std::string_view query) {
    // Mirror Python `query.strip().lower()`.
    std::string normalized;
    {
        auto first = query.find_first_not_of(" \t\r\n");
        auto last = query.find_last_not_of(" \t\r\n");
        if (first != std::string_view::npos) {
            normalized = lowercase(query.substr(first, last - first + 1));
        }
    }
    if (normalized.empty()) return entries;

    std::vector<Entry> out;
    for (const auto& entry : entries) {
        std::string name_lower = lowercase(entry.name);
        std::string kind_lower = lowercase(entry.kind);
        std::string units_lower = lowercase(entry.units.value_or(""));
        std::string dtype_lower = lowercase(entry.data_type);
        if (contains(name_lower, normalized) ||
            contains(kind_lower, normalized) ||
            contains(units_lower, normalized) ||
            contains(dtype_lower, normalized)) {
            out.push_back(entry);
        }
    }
    return out;
}

}  // namespace tuner_core::parameter_catalog
