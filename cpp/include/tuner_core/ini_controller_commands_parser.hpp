// SPDX-License-Identifier: MIT
//
// tuner_core::IniControllerCommandsParser — port of
// `IniParser._parse_controller_commands`. Parses the
// `[ControllerCommands]` section, where each line declares a named
// command whose value is a (possibly comma-separated) sequence of
// quoted strings containing `\xNN` hex escapes. The decoded bytes are
// stored verbatim — no framing is applied here.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <cstdint>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniControllerCommand {
    std::string name;
    std::vector<std::uint8_t> payload;
};

struct IniControllerCommandsSection {
    std::vector<IniControllerCommand> commands;
};

IniControllerCommandsSection parse_controller_commands_section(
    std::string_view text,
    const IniDefines& defines = {});

IniControllerCommandsSection parse_controller_commands_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

IniControllerCommandsSection parse_controller_commands_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
