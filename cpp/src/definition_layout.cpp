// SPDX-License-Identifier: MIT
#include "tuner_core/definition_layout.hpp"

#include <cctype>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace tuner_core::definition_layout {

namespace {

std::string normalize_group_id(const std::string& title) {
    std::string out;
    for (char c : title) {
        if (std::isalnum(static_cast<unsigned char>(c)))
            out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        else
            out.push_back('-');
    }
    // Trim leading/trailing dashes.
    while (!out.empty() && out.front() == '-') out.erase(0, 1);
    while (!out.empty() && out.back() == '-') out.pop_back();
    return out.empty() ? "other" : out;
}

// Clean menu title: strip '&' mnemonics.
std::string clean_title(const std::string& title) {
    std::string out;
    for (char c : title) {
        if (c != '&') out.push_back(c);
    }
    // Trim.
    while (!out.empty() && std::isspace(static_cast<unsigned char>(out.front()))) out.erase(0, 1);
    while (!out.empty() && std::isspace(static_cast<unsigned char>(out.back()))) out.pop_back();
    return out.empty() ? "Other" : out;
}

struct CompileResult {
    std::string table_editor_id;
    std::vector<LayoutSection> sections;
};

CompileResult compile_dialog(
    const IniDialog& dialog,
    const std::unordered_map<std::string, const IniDialog*>& dialogs_by_id,
    const std::unordered_map<std::string, const IniTableEditor*>& editors_by_id,
    std::set<std::string>& active_stack)
{
    CompileResult result;
    if (active_stack.count(dialog.dialog_id)) return result;
    active_stack.insert(dialog.dialog_id);

    // Collect notes (static text fields with non-empty labels).
    std::vector<std::string> notes;
    for (const auto& f : dialog.fields) {
        if (f.is_static_text && !f.label.empty()) notes.push_back(f.label);
    }

    // Collect parameter fields.
    std::vector<LayoutField> fields;
    for (const auto& f : dialog.fields) {
        if (f.parameter_name.empty()) continue;
        LayoutField lf;
        lf.label = f.label;
        lf.parameter_name = f.parameter_name;
        lf.visibility_expression = f.visibility_expression;
        lf.is_static_text = false;
        fields.push_back(std::move(lf));
    }

    if (!fields.empty() || !notes.empty()) {
        LayoutSection sec;
        sec.title = dialog.title.empty() ? dialog.dialog_id : dialog.title;
        sec.fields = std::move(fields);
        sec.notes = std::move(notes);
        result.sections.push_back(std::move(sec));
    }

    // Process panel references.
    for (const auto& panel : dialog.panels) {
        // Check if panel target is a table editor.
        if (result.table_editor_id.empty()) {
            auto it = editors_by_id.find(panel.target);
            if (it != editors_by_id.end()) {
                result.table_editor_id = panel.target;
                continue;
            }
        }
        // Check if panel target is a nested dialog.
        auto it = dialogs_by_id.find(panel.target);
        if (it == dialogs_by_id.end()) continue;

        auto nested = compile_dialog(*it->second, dialogs_by_id, editors_by_id, active_stack);
        if (result.table_editor_id.empty() && !nested.table_editor_id.empty()) {
            result.table_editor_id = nested.table_editor_id;
        }
        for (auto& sec : nested.sections) {
            // Apply panel-level visibility if section doesn't have its own.
            if (sec.visibility_expression.empty() && !panel.visibility_expression.empty()) {
                sec.visibility_expression = panel.visibility_expression;
            }
            result.sections.push_back(std::move(sec));
        }
    }

    active_stack.erase(dialog.dialog_id);
    return result;
}

}  // namespace

std::vector<LayoutPage> compile_pages(
    const IniMenuSection& menus,
    const IniDialogSection& dialogs,
    const IniTableEditorSection& table_editors)
{
    // Build lookup maps.
    std::unordered_map<std::string, const IniDialog*> dialogs_by_id;
    for (const auto& d : dialogs.dialogs) {
        dialogs_by_id[d.dialog_id] = &d;
    }
    std::unordered_map<std::string, const IniTableEditor*> editors_by_id;
    for (const auto& e : table_editors.editors) {
        editors_by_id[e.table_id] = &e;
    }

    std::vector<LayoutPage> pages;
    std::set<std::string> seen_targets;

    for (const auto& menu : menus.menus) {
        std::string group_title = clean_title(menu.title);
        std::string group_id = normalize_group_id(group_title);

        for (const auto& item : menu.items) {
            if (seen_targets.count(item.target)) continue;

            LayoutPage page;
            page.target = item.target;
            page.group_id = group_id;
            page.group_title = group_title;
            page.page_number = item.page;
            page.visibility_expression = item.visibility_expression.value_or("");

            // Is it a table editor directly?
            if (editors_by_id.count(item.target)) {
                page.title = item.label.value_or(item.target);
                page.table_editor_id = item.target;
                pages.push_back(std::move(page));
                seen_targets.insert(item.target);
                continue;
            }

            // Is it a dialog?
            auto dit = dialogs_by_id.find(item.target);
            if (dit == dialogs_by_id.end()) continue;

            std::set<std::string> stack;
            auto compiled = compile_dialog(*dit->second, dialogs_by_id, editors_by_id, stack);

            if (compiled.sections.empty() && compiled.table_editor_id.empty()) continue;

            page.title = item.label.value_or(
                dit->second->title.empty() ? dit->second->dialog_id : dit->second->title);
            page.table_editor_id = compiled.table_editor_id;
            page.sections = std::move(compiled.sections);
            pages.push_back(std::move(page));
            seen_targets.insert(item.target);
        }
    }

    return pages;
}

}  // namespace tuner_core::definition_layout
