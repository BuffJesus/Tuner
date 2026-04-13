// SPDX-License-Identifier: MIT
//
// tuner_core::definition_layout — port of DefinitionLayoutService.
// Forty-seventh sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Compiles raw INI dialogs, menus, and table editors into stable
// editor-facing layout pages. This is the bridge between the INI parser
// output and the workspace presenter — every page in the TUNE tab tree
// is produced by this service.

#pragma once

#include "ini_dialog_parser.hpp"
#include "ini_menu_parser.hpp"
#include "ini_table_editor_parser.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::definition_layout {

struct LayoutField {
    std::string label;
    std::string parameter_name;        // empty = static text
    std::string visibility_expression; // empty = always visible
    bool is_static_text = false;
};

struct LayoutSection {
    std::string title;
    std::vector<LayoutField> fields;
    std::vector<std::string> notes;
    std::string visibility_expression; // empty = always visible
};

struct LayoutPage {
    std::string target;
    std::string title;
    std::string group_id;
    std::string group_title;
    std::optional<int> page_number;
    std::string visibility_expression; // empty = always visible
    std::string table_editor_id;       // empty = not a table page
    std::string curve_editor_id;       // empty = not a curve page
    std::vector<LayoutSection> sections;
};

// Compile pages from the parsed INI sections.
std::vector<LayoutPage> compile_pages(
    const IniMenuSection& menus,
    const IniDialogSection& dialogs,
    const IniTableEditorSection& table_editors);

}  // namespace tuner_core::definition_layout
