// SPDX-License-Identifier: MIT
//
// tuner_core::parameter_catalog — port of `ParameterCatalogService`.
// Nineteenth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Builds the operator-facing parameter catalog the workspace
// presenter renders for "all parameters" surfaces (Engine Setup,
// quick-open, command palette). Aggregates definition scalars,
// definition tables, and tune-only values into a single sorted list
// with a name+kind+units+data_type substring filter.

#pragma once

#include "tuner_core/tune_value_preview.hpp"

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::parameter_catalog {

using ScalarOrList = tune_value_preview::ScalarOrList;

// Minimal scalar definition input — only the fields the catalog reads.
struct ScalarParameterInput {
    std::string name;
    std::optional<int> page;
    std::optional<int> offset;
    std::optional<std::string> units;
    std::string data_type;  // e.g. "U08", "U16", "F32"
};

// Minimal table definition input.
struct TableParameterInput {
    std::string name;
    std::optional<int> page;
    std::optional<int> offset;
    std::optional<std::string> units;
    std::size_t rows = 0;
    std::size_t columns = 0;
};

// A tune-only value (no matching definition entry). Mirrors the
// fields the Python `_tune_only_entry` reads from `TuneValue`.
struct TuneValueInput {
    std::string name;
    ScalarOrList value;
    std::optional<std::string> units;
    // -1 means "unset" — same as Python `None` for `rows` / `cols`.
    int rows = -1;
    int cols = -1;
};

struct Entry {
    std::string name;
    std::string kind;        // "scalar" / "table"
    std::optional<int> page;
    std::optional<int> offset;
    std::optional<std::string> units;
    std::string data_type;   // "U08" / "U16" / "F32" / "array" / "tune-only"
    std::string shape;       // "1x1" / "16x16" / etc.
    bool tune_present = false;
    std::string tune_preview;
};

// Build the catalog from definition scalars + tables + a tune-value
// list. Tune values are looked up by name to populate `tune_present`
// and `tune_preview`. Tune values that don't match any definition
// entry get a tune-only entry. Result is sorted by
// (page or 9999, offset or 999999, lower(name)).
std::vector<Entry> build_catalog(
    const std::vector<ScalarParameterInput>& scalars,
    const std::vector<TableParameterInput>& tables,
    const std::vector<TuneValueInput>& tune_values);

// Substring filter on name / kind / units / data_type. Mirrors the
// Python static method.
std::vector<Entry> filter_catalog(
    const std::vector<Entry>& entries,
    std::string_view query);

}  // namespace tuner_core::parameter_catalog
