// SPDX-License-Identifier: MIT
//
// tuner_core::tuning_page_validation — port of
// `TuningPageValidationService.validate_page`. Seventeenth sub-slice
// of the Phase 14 workspace-services port (Slice 4).
//
// Composes the visibility evaluator (already in C++) with per-page
// structural validation (table page must define a main table; axis
// names must resolve to list-backed values) and per-parameter range
// checking (scalar values outside min/max → warning). Defines minimal
// `Parameter` and `Page` POD inputs so the slice doesn't drag in the
// full `TuningPage` / `LocalTuneEditService` shape.

#pragma once

#include "tuner_core/tune_value_preview.hpp"

#include <functional>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace tuner_core::tuning_page_validation {

using ScalarOrList = tune_value_preview::ScalarOrList;

enum class PageKind {
    TABLE,
    OTHER,  // SCALAR / MENU / CURVE / FALLBACK — anything that isn't a table page
};

enum class ParameterKind {
    SCALAR,
    TABLE,
    OTHER,
};

struct Parameter {
    std::string name;
    ParameterKind kind = ParameterKind::SCALAR;
    // -1 means "unset" — same semantics as Python `None` for the
    // page/offset pair used by `_expects_tune_value`.
    int page = -1;
    int offset = -1;
    // Optional `{expr}` visibility expression — empty string ⇒ always visible.
    std::string visibility_expression;
    // Optional value range (used only for scalar params).
    std::optional<double> min_value;
    std::optional<double> max_value;
};

struct Page {
    PageKind kind = PageKind::OTHER;
    std::vector<Parameter> parameters;
    // Only meaningful when `kind == TABLE`.
    std::optional<std::string> table_name;
    std::optional<std::string> x_axis_name;
    std::optional<std::string> y_axis_name;
};

struct Result {
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
};

// Caller-supplied value lookup. Returns nullopt for unknown / unstaged
// names. The lookup is consulted both for the `available_values` per-
// parameter map and for the table / axis names on table pages.
using ValueLookup = std::function<std::optional<ScalarOrList>(std::string_view)>;

// The visibility expression evaluator pulls scalar tune values from a
// flat name → double map. The Python service builds this map via
// `local_tune_edit_service.get_scalar_values_dict()`; the C++ caller
// supplies it directly.
using ScalarValueMap = std::vector<std::pair<std::string, double>>;

// Run the validator. Mirrors the iteration discipline of
// `TuningPageValidationService.validate_page`: walks `page.parameters`
// once for the visibility/availability/missing-value pass, then
// dispatches to the table-page or non-table-page branch.
Result validate_page(
    const Page& page,
    const ValueLookup& get_value,
    const ScalarValueMap& scalar_values);

}  // namespace tuner_core::tuning_page_validation
