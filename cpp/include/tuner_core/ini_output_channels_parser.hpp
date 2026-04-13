// SPDX-License-Identifier: MIT
//
// tuner_core::IniOutputChannelsParser — port of
// `IniParser._parse_output_channels`. Parses the `[OutputChannels]`
// section that defines the byte layout of the live-data block.
//
// Output channels are structurally similar to `[Constants]` entries
// but simpler: no page tracking (the live-data block is one
// contiguous slab) and only `scalar` / `bits` / `array` kinds. Array
// entries are paired with subsequent `defaultValue = name, v0 v1 ...`
// lines that populate `defaultValue` arrays the visibility-expression
// engine consumes via `arrayValue(...)`.
//
// Python is the oracle: every behaviour here matches the Python
// implementation byte-for-byte across the existing fixture suite,
// including the production INI.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <map>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// One scalar or bits entry from `[OutputChannels]`. Mirrors the
// Python `ScalarParameterDefinition` shape used by
// `EcuDefinition.output_channel_definitions`, restricted to the
// fields the section actually carries.
struct IniOutputChannel {
    std::string name;
    std::string data_type;
    int offset = 0;
    std::optional<std::string> units;
    std::optional<double> scale;
    std::optional<double> translate;
    std::optional<double> min_value;
    std::optional<double> max_value;
    std::optional<int> digits;
    // Bit-field-only fields (empty for scalar entries)
    std::optional<int> bit_offset;
    std::optional<int> bit_length;
    std::vector<std::string> options;
};

// A virtual / computed output channel defined as
// ``name = { expression } [, "units"] [, digits]``. Mirrors
// ``FormulaOutputChannel`` on the Python side. Evaluation of the
// expression is deferred to a later slice — this slice only captures
// catalog state.
struct IniFormulaOutputChannel {
    std::string name;
    std::string formula_expression;
    std::optional<std::string> units;
    std::optional<int> digits;
};

// Aggregate result of parsing `[OutputChannels]`.
struct IniOutputChannelsSection {
    std::vector<IniOutputChannel> channels;
    // Array-typed output channels are not promoted into `channels`;
    // they live here paired with their `defaultValue` payload (if
    // present in the INI). The visibility-expression engine consumes
    // these via `arrayValue(name, index)`.
    std::map<std::string, std::vector<double>> arrays;
    // Virtual / formula-defined output channels — see
    // ``IniFormulaOutputChannel`` above.
    std::vector<IniFormulaOutputChannel> formula_channels;
};

// Parse `[OutputChannels]` from pre-preprocessed INI text. The
// optional `defines` map enables `$macroName` expansion in bit-field
// option label lists; pass `{}` to skip expansion (matches Python
// when `defines=None`).
IniOutputChannelsSection parse_output_channels_section(
    std::string_view text,
    const IniDefines& defines = {});

IniOutputChannelsSection parse_output_channels_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse, mirroring
// the Python `IniParser.parse()` flow exactly.
IniOutputChannelsSection parse_output_channels_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
