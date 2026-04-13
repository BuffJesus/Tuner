// SPDX-License-Identifier: MIT
//
// tuner_core::ini_autotune_sections_parser — port of
// `IniParser._parse_autotune_sections` from
// `src/tuner/parsers/ini_parser.py`. Parses the `[VeAnalyze]` and
// `[WueAnalyze]` sections into `AutotuneMapDefinition` objects.
//
// Improvement over the Python original: filter gates use a
// discriminated variant (`StandardGate` vs `ParameterisedGate`)
// instead of a single struct with five nullable fields. The gate
// operator is validated into a `GateOperator` enum at parse time
// instead of stored as a raw string.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

namespace tuner_core {

// ---------------------------------------------------------------
// Gate operator enum — validated at parse time
// ---------------------------------------------------------------

enum class GateOperator {
    Lt,       // "<"
    Gt,       // ">"
    Le,       // "<="
    Ge,       // ">="
    Eq,       // "==" or "="
    Ne,       // "!="
    BitAnd,   // "&"
    Unknown,  // unrecognised operator string
};

// Round-trip: enum → canonical string representation.
const char* gate_operator_to_string(GateOperator op);

// Parse: string → enum. Unknown strings map to `Unknown`.
GateOperator parse_gate_operator(std::string_view text);

// ---------------------------------------------------------------
// Filter gate variants
// ---------------------------------------------------------------

// Standard named gate — e.g. `std_xAxisMin`, `std_DeadLambda`,
// `std_Custom`. No channel/operator/threshold.
struct StandardGate {
    std::string name;
};

// Parameterised gate — carries channel, operator, threshold, and
// an optional label. e.g.
//   filter = minCltFilter, "Minimum CLT", coolant, <, 71, true
struct ParameterisedGate {
    std::string name;
    std::string label;       // defaults to name when missing
    std::string channel;
    GateOperator op = GateOperator::Unknown;
    double threshold = 0.0;
    bool default_enabled = true;
};

using FilterGate = std::variant<StandardGate, ParameterisedGate>;

// Accessor helpers — work on either variant.
const std::string& gate_name(const FilterGate& gate);
bool gate_default_enabled(const FilterGate& gate);

// ---------------------------------------------------------------
// Autotune map definition
// ---------------------------------------------------------------

struct AutotuneMapDefinition {
    std::string section_name;  // "VeAnalyze" or "WueAnalyze"
    std::vector<std::string> map_parts;
    std::vector<std::string> lambda_target_tables;
    std::vector<FilterGate> filter_gates;
};

struct IniAutotuneSectionsResult {
    std::vector<AutotuneMapDefinition> maps;
};

// ---------------------------------------------------------------
// Parser entry points
// ---------------------------------------------------------------

IniAutotuneSectionsResult parse_autotune_sections(
    std::string_view text,
    const IniDefines& defines = {});

IniAutotuneSectionsResult parse_autotune_sections_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse.
IniAutotuneSectionsResult parse_autotune_sections_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
