// SPDX-License-Identifier: MIT
//
// tuner_core::scalar_page_editor — port of `ScalarPageEditorService.build_sections`.
// Twenty-sixth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Composes the visibility evaluator (already in C++) with section
// walking + per-field snapshot construction. Mirrors the Python
// service's two-level visibility filtering: per-field
// `visibility_expression` AND per-section `visibility_expression`.
// Falls back to a single section containing all visible fields when
// no explicit sections are defined.

#pragma once

#include "tuner_core/tune_value_preview.hpp"

#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace tuner_core::scalar_page_editor {

using ScalarOrList = tune_value_preview::ScalarOrList;

// Minimal POD shells — only the fields the section walker reads.
struct Parameter {
    std::string name;
    std::string label;
    std::string kind;  // "scalar" / "table" / "other"
    std::optional<std::string> units;
    std::optional<std::string> help_text;
    std::optional<double> min_value;
    std::optional<double> max_value;
    std::optional<int> digits;
    std::vector<std::string> options;
    std::vector<std::string> option_values;
    bool requires_power_cycle = false;
    std::string visibility_expression;  // empty ⇒ always visible
};

struct Section {
    std::string title;
    std::vector<std::string> notes;
    std::vector<std::string> parameter_names;
    std::string visibility_expression;
};

struct Page {
    std::string title;
    std::vector<Parameter> parameters;
    std::vector<Section> sections;
};

struct FieldSnapshot {
    std::string name;
    std::string label;
    std::string value_text;
    std::string base_value_text;
    std::optional<std::string> units;
    std::optional<std::string> help_text;
    std::optional<double> min_value;
    std::optional<double> max_value;
    std::optional<int> digits;
    std::vector<std::string> options;
    std::vector<std::string> option_values;
    bool is_dirty = false;
    bool requires_power_cycle = false;
    std::string visibility_expression;
};

struct SectionSnapshot {
    std::string title;
    std::vector<std::string> notes;
    std::vector<FieldSnapshot> fields;
    std::string visibility_expression;
};

// Caller-supplied lookups. The first returns the current value
// (post-staged) for a parameter; the second returns the base value;
// the third reports whether the parameter is currently dirty.
using ValueLookup = std::function<std::optional<ScalarOrList>(std::string_view)>;
using DirtyCheck = std::function<bool(std::string_view)>;

// The visibility evaluator's flat scalar value map. Same shape as
// the `tuning_page_validation` slice.
using ScalarValueMap = std::vector<std::pair<std::string, double>>;

// Mirror `ScalarPageEditorService.build_sections`. Returns a list
// of `SectionSnapshot` — at least one section is always returned
// (the fallback path produces one section even when the page
// defines none).
std::vector<SectionSnapshot> build_sections(
    const Page& page,
    const ValueLookup& get_value,
    const ValueLookup& get_base_value,
    const DirtyCheck& is_dirty,
    const ScalarValueMap& scalar_values);

}  // namespace tuner_core::scalar_page_editor
