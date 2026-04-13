// SPDX-License-Identifier: MIT
//
// tuner_core::tuning_page_validation implementation. Pure logic —
// composes the visibility evaluator with structural and per-parameter
// validation passes.

#include "tuner_core/tuning_page_validation.hpp"

#include "tuner_core/visibility_expression.hpp"

#include <algorithm>
#include <map>
#include <set>
#include <variant>

namespace tuner_core::tuning_page_validation {

namespace {

bool expects_tune_value(int page, int offset) noexcept {
    return page >= 0 || offset >= 0;
}

// Convert the parallel-array scalar value map into the
// `ValueMap` shape the visibility evaluator expects (a sorted
// std::map keyed by name). The visibility evaluator's order
// independence makes the sort harmless.
visibility_expression::ValueMap to_visibility_value_map(
    const ScalarValueMap& values) {
    visibility_expression::ValueMap out;
    for (const auto& [k, v] : values) {
        out.emplace(k, v);
    }
    return out;
}

// Mirror Python's `(name in errors_so_far)` dedupe via
// `tuple(dict.fromkeys(errors))` — preserves first occurrence,
// drops duplicates.
void dedupe(std::vector<std::string>& items) {
    std::set<std::string> seen;
    auto write = items.begin();
    for (auto read = items.begin(); read != items.end(); ++read) {
        if (seen.insert(*read).second) {
            if (write != read) *write = std::move(*read);
            ++write;
        }
    }
    items.erase(write, items.end());
}

bool is_list_value(const ScalarOrList& v) noexcept {
    return std::holds_alternative<std::vector<double>>(v);
}

const std::vector<double>* as_list(const ScalarOrList& v) noexcept {
    return std::get_if<std::vector<double>>(&v);
}

const double* as_scalar(const ScalarOrList& v) noexcept {
    return std::get_if<double>(&v);
}

}  // namespace

Result validate_page(
    const Page& page,
    const ValueLookup& get_value,
    const ScalarValueMap& scalar_values) {
    Result result;
    auto values_dict = to_visibility_value_map(scalar_values);

    // Pass 1: visibility check + availability + missing-value error.
    std::map<std::string, std::optional<ScalarOrList>> available_values;
    for (const auto& parameter : page.parameters) {
        if (!visibility_expression::evaluate(
                parameter.visibility_expression, values_dict)) {
            continue;
        }
        auto tune_value = get_value(parameter.name);
        available_values.emplace(parameter.name, tune_value);
        if (!tune_value.has_value() &&
            expects_tune_value(parameter.page, parameter.offset)) {
            result.errors.push_back(
                "Missing tune value for '" + parameter.name + "'.");
        }
    }

    if (page.kind == PageKind::TABLE) {
        // Main table presence + list-shape check.
        if (page.table_name.has_value() && !page.table_name->empty()) {
            auto table_value = get_value(*page.table_name);
            if (!table_value.has_value()) {
                result.errors.push_back(
                    "Main table '" + *page.table_name + "' is unavailable.");
            } else if (!is_list_value(*table_value)) {
                result.errors.push_back(
                    "Main table '" + *page.table_name +
                    "' is not list-backed.");
            }
        } else {
            result.errors.push_back(
                "This table page does not define a main table name.");
        }

        // Axis name presence + shape + non-empty checks.
        const std::pair<const std::optional<std::string>*, const char*> axes[] = {
            {&page.x_axis_name, "X axis"},
            {&page.y_axis_name, "Y axis"},
        };
        for (auto [axis_opt, axis_label] : axes) {
            if (!axis_opt->has_value() || (*axis_opt)->empty()) continue;
            const auto& axis_name = **axis_opt;
            auto axis_value = get_value(axis_name);
            if (!axis_value.has_value()) {
                result.errors.push_back(
                    std::string(axis_label) + " '" + axis_name + "' is unavailable.");
                continue;
            }
            if (!is_list_value(*axis_value)) {
                result.errors.push_back(
                    std::string(axis_label) + " '" + axis_name +
                    "' is not list-backed.");
                continue;
            }
            if (as_list(*axis_value)->empty()) {
                result.warnings.push_back(
                    std::string(axis_label) + " '" + axis_name +
                    "' has no labels.");
            }
        }
    } else {
        // Non-table page: scalar range warnings + fallback "table only" warning.
        std::size_t scalar_count = 0;
        std::size_t table_count = 0;
        for (const auto& parameter : page.parameters) {
            auto it = available_values.find(parameter.name);
            std::optional<ScalarOrList> tune_value;
            if (it != available_values.end()) tune_value = it->second;
            if (parameter.kind == ParameterKind::SCALAR) {
                ++scalar_count;
                if (tune_value.has_value()) {
                    const double* scalar = as_scalar(*tune_value);
                    if (scalar != nullptr) {
                        if (parameter.min_value.has_value() &&
                            *scalar < *parameter.min_value) {
                            result.warnings.push_back(
                                "'" + parameter.name + "' value " +
                                tune_value_preview::format_scalar_python_repr(*scalar) +
                                " is below minimum " +
                                tune_value_preview::format_scalar_python_repr(*parameter.min_value) +
                                ".");
                        } else if (parameter.max_value.has_value() &&
                                   *scalar > *parameter.max_value) {
                            result.warnings.push_back(
                                "'" + parameter.name + "' value " +
                                tune_value_preview::format_scalar_python_repr(*scalar) +
                                " exceeds maximum " +
                                tune_value_preview::format_scalar_python_repr(*parameter.max_value) +
                                ".");
                        }
                    }
                }
            } else if (parameter.kind == ParameterKind::TABLE) {
                ++table_count;
                if (tune_value.has_value() && !is_list_value(*tune_value)) {
                    result.warnings.push_back(
                        "Fallback table '" + parameter.name +
                        "' is not list-backed in the tune.");
                }
            }
        }
        if (scalar_count == 0 && table_count > 0) {
            result.warnings.push_back(
                "This fallback page has only table content and no direct scalar edits.");
        }
    }

    dedupe(result.errors);
    dedupe(result.warnings);
    return result;
}

}  // namespace tuner_core::tuning_page_validation
