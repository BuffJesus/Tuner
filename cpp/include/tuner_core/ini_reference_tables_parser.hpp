// SPDX-License-Identifier: MIT
//
// tuner_core::ini_reference_tables_parser — port of
// `IniParser._parse_reference_tables` from
// `src/tuner/parsers/ini_parser.py`. Parses reference-table
// declarations inside the `[UserDefined]` section — the same section
// `ini_dialog_parser` reads, but keyed off different property names
// so the two parsers co-exist without conflict.
//
// A reference table is a look-up table the operator can consult when
// they hit a tuning issue — e.g. "here are the most likely causes of
// lean running at WOT with their recommended corrections". Each table
// declares a block of:
//
//   referenceTable = id, "label"
//   topicHelp = "free-text help"
//   tableIdentifier = rows, cols
//   solutionsLabel = "Recommended Solutions"
//   solution = "symptom label", "expression"
//   solution = ...
//
// Missing block-level fields are tolerated — the parser only
// populates what it sees.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniReferenceTableSolution {
    std::string label;
    std::optional<std::string> expression;
};

struct IniReferenceTable {
    std::string table_id;
    std::string label;
    std::optional<std::string> topic_help;
    std::optional<std::string> table_identifier;
    std::optional<std::string> solutions_label;
    std::vector<IniReferenceTableSolution> solutions;
};

struct IniReferenceTablesSection {
    std::vector<IniReferenceTable> tables;
};

IniReferenceTablesSection parse_reference_tables_section(
    std::string_view text,
    const IniDefines& defines = {});

IniReferenceTablesSection parse_reference_tables_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse.
IniReferenceTablesSection parse_reference_tables_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
