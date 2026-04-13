// SPDX-License-Identifier: MIT
//
// tuner_core::IniLoggerDefinitionParser — port of
// `IniParser._parse_logger_definitions`. Parses the
// `[LoggerDefinition]` section that describes one or more raw binary
// loggers (tooth log, composite log, etc.) — each block declares a
// header, key=value properties, and zero or more `recordField` lines
// describing how to bit-extract individual fields from a binary record.
//
// `dataReadCommand` strings are decoded to bytes: `\xNN` hex escapes
// become byte values, and the literal `$tsCanId` token is rewritten to
// `\x00\x00` (direct connection — CAN bus is not used). `calcField`
// lines are skipped (they're derived display expressions, not raw
// fields).
//
// `record_count` is computed kind-aware:
//   - tooth     → dataLength is in bytes      → count = dataLength / record_len
//   - composite → dataLength is record count  → count = dataLength

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <cstdint>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniLoggerRecordField {
    std::string name;
    std::string header;
    int start_bit = 0;
    int bit_count = 0;
    double scale = 0.0;
    std::string units;
};

struct IniLoggerDefinition {
    std::string name;
    std::string display_name;
    std::string kind;  // "tooth" / "composite" / etc., lowercased
    std::string start_command;
    std::string stop_command;
    std::vector<std::uint8_t> data_read_command;
    int data_read_timeout_ms = 5000;
    bool continuous_read = false;
    int record_header_len = 0;
    int record_footer_len = 0;
    int record_len = 0;
    int record_count = 0;
    std::vector<IniLoggerRecordField> record_fields;
};

struct IniLoggerDefinitionSection {
    std::vector<IniLoggerDefinition> loggers;
};

IniLoggerDefinitionSection parse_logger_definition_section(
    std::string_view text,
    const IniDefines& defines = {});

IniLoggerDefinitionSection parse_logger_definition_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse, mirroring
// the Python `IniParser.parse()` flow.
IniLoggerDefinitionSection parse_logger_definition_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
