// SPDX-License-Identifier: MIT
//
// tuner_core::ini_dialog_parser — port of `IniParser._parse_dialogs`.
// Forty-sixth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Parses the [UserDefined] section of a Speeduino INI file into a list
// of DialogDefinition objects. Each dialog has fields (parameter bindings
// with labels and visibility expressions) and panel references (nested
// dialog targets). This is the prerequisite for DefinitionLayoutService.

#pragma once

#include <optional>
#include <string>
#include <vector>

namespace tuner_core {

struct IniDialogField {
    std::string label;
    std::string parameter_name;      // empty = static text
    std::string visibility_expression; // empty = always visible
    bool is_static_text = false;
};

struct IniDialogPanelRef {
    std::string target;
    std::string position;             // empty = not set
    std::string visibility_expression; // empty = always visible
};

struct IniDialog {
    std::string dialog_id;
    std::string title;
    std::string axis_hint;            // empty = not set
    std::vector<IniDialogField> fields;
    std::vector<IniDialogPanelRef> panels;
};

struct IniDialogSection {
    std::vector<IniDialog> dialogs;
};

// Parse dialogs from pre-processed INI lines.
IniDialogSection parse_dialogs(const std::vector<std::string>& lines);

}  // namespace tuner_core
