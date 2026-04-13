// SPDX-License-Identifier: MIT
//
// tuner_core::ini_setting_groups_parser — port of
// `IniParser._parse_setting_groups` from
// `src/tuner/parsers/ini_parser.py`. Parses the `[SettingGroups]`
// section into a list of `IniSettingGroup` records.
//
// `[SettingGroups]` declares project-level compile flags and their
// options — e.g. `mcu = mcu_teensy | mcu_mega2560 | mcu_stm32`,
// `LAMBDA = DEFAULT | LAMBDA`. Production INIs use these flags to
// gate `#if`/`#else`/`#endif` preprocessor blocks via
// `active_settings`.
//
// Each block looks like:
//
//   settingGroup = symbol, "label"
//   settingOption = option1, "Option 1 label"
//   settingOption = option2, "Option 2 label"
//
// A boolean flag (present = enabled, absent = disabled) is a
// `settingGroup` with zero `settingOption` lines.
//
// I/O — file read — stays in the caller. This module owns text-in,
// structure-out (same shape as the other `ini_*_parser` leaves).

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniSettingGroupOption {
    std::string symbol;  // e.g. "mcu_teensy", "LAMBDA"
    std::string label;   // e.g. "Teensy 3.5", "Lambda mode"
};

struct IniSettingGroup {
    std::string symbol;  // e.g. "mcu", "LAMBDA"
    std::string label;   // e.g. "Controller in use"
    std::vector<IniSettingGroupOption> options;
};

struct IniSettingGroupsSection {
    std::vector<IniSettingGroup> groups;
};

IniSettingGroupsSection parse_setting_groups_section(
    std::string_view text,
    const IniDefines& defines = {});

IniSettingGroupsSection parse_setting_groups_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse.
IniSettingGroupsSection parse_setting_groups_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
