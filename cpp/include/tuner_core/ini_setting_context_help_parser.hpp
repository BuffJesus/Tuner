// SPDX-License-Identifier: MIT
//
// tuner_core::ini_setting_context_help_parser — port of
// `IniParser._parse_setting_context_help` from
// `src/tuner/parsers/ini_parser.py`. Parses the
// `[SettingContextHelp]` section into a `name → help_text` map that
// downstream services use to populate tooltips on every tunable
// parameter.
//
// Each line in the section is a simple `key = "help text"` pair.
// The parser strips any trailing `;` comment from the value and
// strips paired quotes via the shared `strip_quotes` helper.
// Missing-equals lines are skipped.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <map>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniSettingContextHelpSection {
    // name → help text. `std::map` (sorted) so iteration is
    // deterministic across implementations.
    std::map<std::string, std::string> help_by_name;
};

IniSettingContextHelpSection parse_setting_context_help_section(
    std::string_view text,
    const IniDefines& defines = {});

IniSettingContextHelpSection parse_setting_context_help_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse.
IniSettingContextHelpSection parse_setting_context_help_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
