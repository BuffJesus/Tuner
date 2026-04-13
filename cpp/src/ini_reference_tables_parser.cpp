// SPDX-License-Identifier: MIT
//
// tuner_core::ini_reference_tables_parser implementation. Direct
// port of `IniParser._parse_reference_tables`.

#include "tuner_core/ini_reference_tables_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <cctype>
#include <utility>

namespace tuner_core {

namespace {

using detail::strip;
using detail::strip_quotes;
using detail::parse_csv;

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

std::vector<std::string> split_lines(std::string_view text) {
    std::vector<std::string> lines;
    std::string current;
    for (std::size_t i = 0; i < text.size(); ++i) {
        char c = text[i];
        if (c == '\r') {
            lines.push_back(std::move(current));
            current.clear();
            if (i + 1 < text.size() && text[i + 1] == '\n') ++i;
        } else if (c == '\n') {
            lines.push_back(std::move(current));
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    if (!current.empty()) lines.push_back(std::move(current));
    return lines;
}

// Mirror Python `IniParser._strip_quotes(value)`: drop trailing `;`
// comment first, then strip paired/leading/trailing `"` chars.
std::string strip_quotes_and_comment(std::string_view value) {
    std::string s = strip(value);
    auto semi = s.find(';');
    if (semi != std::string::npos) s = s.substr(0, semi);
    s = strip(s);
    return strip_quotes(s);
}

}  // namespace

IniReferenceTablesSection parse_reference_tables_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_reference_tables_lines(split_lines(text), defines);
}

IniReferenceTablesSection parse_reference_tables_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    const auto lines = split_lines(text);
    const auto preprocessed = preprocess_ini_lines(lines, active_settings);
    const auto defines = collect_defines_lines(preprocessed);
    return parse_reference_tables_lines(preprocessed, defines);
}

IniReferenceTablesSection parse_reference_tables_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniReferenceTablesSection section;
    bool in_user_defined = false;
    // `current_table` points into `section.tables` once a block is
    // open. Leaving the section or starting a new block drops the
    // pointer (Python uses `current_table = None`). Using an index
    // avoids invalidation when `section.tables` grows.
    int current_index = -1;
    auto current = [&]() -> IniReferenceTable* {
        if (current_index < 0) return nullptr;
        return &section.tables[current_index];
    };

    for (const auto& raw_line : lines) {
        const std::string stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';' || stripped[0] == '#') continue;
        if (stripped[0] == '[') {
            in_user_defined = (lowercase(stripped) == "[userdefined]");
            if (!in_user_defined) current_index = -1;
            continue;
        }
        if (!in_user_defined) continue;
        const auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = strip(stripped.substr(0, eq));
        const std::string value = strip(stripped.substr(eq + 1));

        if (key == "referenceTable") {
            const auto parts = parse_csv(value);
            if (parts.empty()) continue;
            IniReferenceTable table;
            table.table_id = parts[0];
            table.label = parts.size() > 1 ? parts[1] : parts[0];
            section.tables.push_back(std::move(table));
            current_index = static_cast<int>(section.tables.size()) - 1;
            continue;
        }
        if (current_index < 0) continue;

        if (key == "topicHelp") {
            current()->topic_help = strip_quotes_and_comment(value);
        } else if (key == "tableIdentifier") {
            // Python: `current_table.table_identifier = parts[1] if len(parts) > 1 else (parts[0] if parts else None)`
            const auto parts = parse_csv(value);
            if (parts.size() > 1) {
                current()->table_identifier = parts[1];
            } else if (!parts.empty()) {
                current()->table_identifier = parts[0];
            }
        } else if (key == "solutionsLabel") {
            current()->solutions_label = strip_quotes_and_comment(value);
        } else if (key == "solution") {
            const auto parts = parse_csv(value);
            if (parts.empty()) continue;
            IniReferenceTableSolution solution;
            solution.label = parts[0];
            if (parts.size() > 1) solution.expression = parts[1];
            current()->solutions.push_back(std::move(solution));
        }
    }
    return section;
}

}  // namespace tuner_core
