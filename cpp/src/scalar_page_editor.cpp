// SPDX-License-Identifier: MIT
//
// tuner_core::scalar_page_editor implementation. Pure logic — direct
// port of `ScalarPageEditorService.build_sections`.

#include "tuner_core/scalar_page_editor.hpp"

#include "tuner_core/visibility_expression.hpp"

#include <algorithm>
#include <map>
#include <variant>

namespace tuner_core::scalar_page_editor {

namespace {

// Mirror Python `_value_text`: empty for missing, comma-joined first
// 4 list items via `str(item)`, scalar via `str(value)`. The Python
// service uses bare `str(item)` (not `tune_value_preview`), so a
// scalar 12.5 renders as "12.5" but an integer-valued float renders
// as "12.0" — same shape as `tune_value_preview::format_scalar_python_repr`.
std::string value_text(const std::optional<ScalarOrList>& tune_value) {
    if (!tune_value.has_value()) return "";
    if (std::holds_alternative<std::vector<double>>(*tune_value)) {
        const auto& list = std::get<std::vector<double>>(*tune_value);
        std::string out;
        const std::size_t shown = std::min<std::size_t>(list.size(), 4);
        for (std::size_t i = 0; i < shown; ++i) {
            if (i > 0) out += ", ";
            out += tune_value_preview::format_scalar_python_repr(list[i]);
        }
        return out;
    }
    return tune_value_preview::format_scalar_python_repr(std::get<double>(*tune_value));
}

visibility_expression::ValueMap to_visibility_value_map(
    const ScalarValueMap& values) {
    visibility_expression::ValueMap out;
    for (const auto& [k, v] : values) out.emplace(k, v);
    return out;
}

FieldSnapshot make_field_snapshot(
    const Parameter& parameter,
    const ValueLookup& get_value,
    const ValueLookup& get_base_value,
    const DirtyCheck& is_dirty) {
    FieldSnapshot f;
    f.name = parameter.name;
    f.label = parameter.label;
    f.value_text = value_text(get_value(parameter.name));
    f.base_value_text = value_text(get_base_value(parameter.name));
    f.units = parameter.units;
    f.help_text = parameter.help_text;
    f.min_value = parameter.min_value;
    f.max_value = parameter.max_value;
    f.digits = parameter.digits;
    f.options = parameter.options;
    f.option_values = parameter.option_values;
    f.is_dirty = is_dirty(parameter.name);
    f.requires_power_cycle = parameter.requires_power_cycle;
    f.visibility_expression = parameter.visibility_expression;
    return f;
}

}  // namespace

std::vector<SectionSnapshot> build_sections(
    const Page& page,
    const ValueLookup& get_value,
    const ValueLookup& get_base_value,
    const DirtyCheck& is_dirty,
    const ScalarValueMap& scalar_values) {
    auto values_dict = to_visibility_value_map(scalar_values);

    // Index parameters by name for the section walker.
    std::map<std::string, const Parameter*> by_name;
    for (const auto& p : page.parameters) {
        by_name[p.name] = &p;
    }

    std::vector<SectionSnapshot> sections;
    for (const auto& section : page.sections) {
        // Build all fields for this section's parameter list,
        // filtering to scalars only.
        std::vector<FieldSnapshot> all_fields;
        for (const auto& name : section.parameter_names) {
            auto it = by_name.find(name);
            if (it == by_name.end()) continue;
            if (it->second->kind != "scalar") continue;
            all_fields.push_back(
                make_field_snapshot(*it->second, get_value, get_base_value, is_dirty));
        }
        // Per-field visibility filter.
        std::vector<FieldSnapshot> visible_fields;
        for (auto& f : all_fields) {
            if (visibility_expression::evaluate(f.visibility_expression, values_dict)) {
                visible_fields.push_back(std::move(f));
            }
        }
        // Section-level visibility filter — only emit the section
        // when it has visible fields (or notes) AND its expression
        // evaluates true.
        const bool has_content = !visible_fields.empty() || !section.notes.empty();
        if (has_content &&
            visibility_expression::evaluate(section.visibility_expression, values_dict)) {
            SectionSnapshot snap;
            snap.title = section.title;
            snap.notes = section.notes;
            snap.fields = std::move(visible_fields);
            snap.visibility_expression = section.visibility_expression;
            sections.push_back(std::move(snap));
        }
    }

    if (!sections.empty()) return sections;

    // Fallback path: no explicit sections produced anything visible —
    // emit a single section with the page title and every visible
    // scalar parameter.
    std::vector<FieldSnapshot> fallback_fields;
    for (const auto& parameter : page.parameters) {
        if (parameter.kind != "scalar") continue;
        if (!visibility_expression::evaluate(parameter.visibility_expression, values_dict)) {
            continue;
        }
        fallback_fields.push_back(
            make_field_snapshot(parameter, get_value, get_base_value, is_dirty));
    }
    SectionSnapshot fallback;
    fallback.title = page.title;
    fallback.fields = std::move(fallback_fields);
    sections.push_back(std::move(fallback));
    return sections;
}

}  // namespace tuner_core::scalar_page_editor
