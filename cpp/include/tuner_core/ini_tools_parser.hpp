// SPDX-License-Identifier: MIT
//
// tuner_core::ini_tools_parser — port of `IniParser._parse_tools`
// from `src/tuner/parsers/ini_parser.py`. Parses the `[Tools]`
// section, which declares add-on operator tools that integrate
// with specific table editors (e.g. VE Analyze, Knock Analyze).
//
// Each recognised line is an `addTool = tool_id, label, target_table_id`
// declaration. The third field is optional — tools without a
// target_table_id apply globally. Other keys in the section are
// silently ignored.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniToolDeclaration {
    std::string tool_id;
    std::string label;
    // Target table editor id the tool integrates with. `nullopt`
    // means the tool is not scoped to any specific table editor
    // (e.g. a global "reset all" helper).
    std::optional<std::string> target_table_id;
};

struct IniToolsSection {
    std::vector<IniToolDeclaration> declarations;
};

IniToolsSection parse_tools_section(
    std::string_view text,
    const IniDefines& defines = {});

IniToolsSection parse_tools_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse.
IniToolsSection parse_tools_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
