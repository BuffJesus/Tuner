// SPDX-License-Identifier: MIT
#include "tuner_core/tuning_page_builder.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <map>
#include <set>
#include <string>

namespace tuner_core::tuning_page_builder {

namespace dl = tuner_core::definition_layout;
namespace tpg = tuner_core::tuning_page_grouping;

namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

// Find a scalar/array in the definition by name.
const IniScalar* find_scalar(const NativeEcuDefinition& def, const std::string& name) {
    for (const auto& s : def.constants.scalars)
        if (s.name == name) return &s;
    return nullptr;
}

const IniArray* find_array(const NativeEcuDefinition& def, const std::string& name) {
    for (const auto& a : def.constants.arrays)
        if (a.name == name) return &a;
    return nullptr;
}

PageParameter make_param(const std::string& name, const std::string& role,
                          const NativeEcuDefinition& def) {
    PageParameter p;
    p.name = name;
    p.role = role;
    // Try scalar first.
    if (auto* s = find_scalar(def, name)) {
        p.label = s->name; p.kind = "scalar"; p.units = s->units.value_or("");
        p.page = s->page; p.offset = s->offset;
    } else if (auto* a = find_array(def, name)) {
        p.label = a->name; p.kind = "array"; p.units = a->units.value_or("");
        p.page = a->page; p.offset = a->offset;
    } else {
        p.label = name; p.kind = "scalar";
    }
    return p;
}

}  // namespace

std::vector<TuningPageGroup> build_pages(const NativeEcuDefinition& definition) {
    // Step 1: compile layout pages.
    auto layouts = dl::compile_pages(definition.menus, definition.dialogs, definition.table_editors);

    // Step 2: build TuningPage from each layout + resolve parameters.
    std::vector<TuningPage> pages;
    std::set<std::string> covered_targets;

    for (const auto& layout : layouts) {
        TuningPage page;
        page.page_id = layout.target;
        page.title = layout.title.empty() ? layout.target : layout.title;
        page.group_id = layout.group_id;
        page.group_title = layout.group_title;

        if (!layout.table_editor_id.empty()) {
            page.kind = PageKind::TABLE;
            page.table_id = layout.table_editor_id;
            // Find the table editor to get axis info.
            for (const auto& ed : definition.table_editors.editors) {
                if (ed.table_id == layout.table_editor_id) {
                    if (ed.z_bins) {
                        page.table_name = *ed.z_bins;
                        page.parameters.push_back(make_param(*ed.z_bins, "table", definition));
                    }
                    if (ed.x_bins) {
                        page.x_axis_name = *ed.x_bins;
                        page.x_axis_label = ed.x_label.value_or("");
                        page.parameters.push_back(make_param(*ed.x_bins, "x_axis", definition));
                    }
                    if (ed.y_bins) {
                        page.y_axis_name = *ed.y_bins;
                        page.y_axis_label = ed.y_label.value_or("");
                        page.parameters.push_back(make_param(*ed.y_bins, "y_axis", definition));
                    }
                    break;
                }
            }
        } else {
            page.kind = PageKind::PARAMETER_LIST;
        }

        // Add parameters from layout sections.
        for (const auto& sec : layout.sections) {
            PageSection ps;
            ps.title = sec.title;
            for (const auto& n : sec.notes) {
                if (!ps.notes.empty()) ps.notes += "\n";
                ps.notes += n;
            }
            for (const auto& f : sec.fields) {
                if (f.parameter_name.empty()) continue;
                ps.parameter_names.push_back(f.parameter_name);
                // Don't duplicate params already added from table editor.
                bool exists = false;
                for (const auto& ep : page.parameters)
                    if (ep.name == f.parameter_name) { exists = true; break; }
                if (!exists)
                    page.parameters.push_back(make_param(f.parameter_name, "scalar", definition));
            }
            if (!ps.parameter_names.empty() || !ps.notes.empty())
                page.sections.push_back(std::move(ps));
        }

        // Summary.
        if (page.kind == PageKind::TABLE) {
            char buf[128];
            std::snprintf(buf, sizeof(buf), "Table: %s | %d field(s)",
                page.table_id.c_str(), static_cast<int>(page.parameters.size()));
            page.summary = buf;
        } else {
            char buf[128];
            std::snprintf(buf, sizeof(buf), "%d section(s), %d field(s)",
                static_cast<int>(page.sections.size()),
                static_cast<int>(page.parameters.size()));
            page.summary = buf;
        }

        covered_targets.insert(layout.target);
        pages.push_back(std::move(page));
    }

    // Step 3: group using tuning_page_grouping.
    // group_pages takes definition_layout::LayoutPage — pass the original layouts.
    auto groups = tpg::group_pages(layouts);

    // Step 4: build output groups with the full TuningPage objects.
    std::map<std::string, TuningPage*> page_by_target;
    for (auto& p : pages) page_by_target[p.page_id] = &p;

    std::vector<TuningPageGroup> result;
    for (const auto& grp : groups) {
        TuningPageGroup tpg_out;
        tpg_out.group_id = grp.group_id;
        tpg_out.title = grp.group_title;
        for (const auto& gp : grp.pages) {
            auto it = page_by_target.find(gp.target);
            if (it != page_by_target.end()) {
                auto& p = *it->second;
                p.group_id = grp.group_id;
                p.group_title = grp.group_title;
                tpg_out.pages.push_back(p);
            }
        }
        if (!tpg_out.pages.empty())
            result.push_back(std::move(tpg_out));
    }
    return result;
}

}  // namespace tuner_core::tuning_page_builder
