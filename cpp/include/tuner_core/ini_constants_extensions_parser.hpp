// SPDX-License-Identifier: MIT
//
// tuner_core::ini_constants_extensions_parser — port of
// `IniParser._parse_constants_extensions` from
// `src/tuner/parsers/ini_parser.py`. Parses the
// `[ConstantsExtensions]` section, which carries extra per-constant
// metadata that didn't fit in the main `[Constants]` grammar.
//
// In production INIs, the only recognised key is `requiresPowerCycle`
// — a comma-separated list of parameter names that require a full
// ECU power cycle before the change takes effect (as opposed to the
// normal "write to RAM, burn to flash" flow where the change is
// live immediately). The workspace presenter reads this set and
// shows a "restart required" warning on the relevant edits so the
// operator knows to cycle power after burning.
//
// Other keys in the section are silently ignored for now — future
// INIs may add new metadata keys that this parser can extend to
// pick up without breaking existing production artifacts.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniConstantsExtensionsSection {
    // Set of parameter names that require a full ECU power cycle
    // before the change takes effect. Mirrors
    // `EcuDefinition.requires_power_cycle`.
    std::set<std::string> requires_power_cycle;
};

IniConstantsExtensionsSection parse_constants_extensions_section(
    std::string_view text,
    const IniDefines& defines = {});

IniConstantsExtensionsSection parse_constants_extensions_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse.
IniConstantsExtensionsSection parse_constants_extensions_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
