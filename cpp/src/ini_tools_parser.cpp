// SPDX-License-Identifier: MIT
//
// tuner_core::ini_tools_parser implementation. Direct port of
// `IniParser._parse_tools`.

#include "tuner_core/ini_tools_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <cctype>
#include <utility>

namespace tuner_core {

namespace {

using detail::strip;
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

}  // namespace

IniToolsSection parse_tools_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_tools_lines(split_lines(text), defines);
}

IniToolsSection parse_tools_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    const auto lines = split_lines(text);
    const auto preprocessed = preprocess_ini_lines(lines, active_settings);
    const auto defines = collect_defines_lines(preprocessed);
    return parse_tools_lines(preprocessed, defines);
}

IniToolsSection parse_tools_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniToolsSection section;
    bool in_tools = false;
    for (const auto& raw_line : lines) {
        const std::string stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';' || stripped[0] == '#') continue;
        if (stripped[0] == '[') {
            in_tools = (lowercase(stripped) == "[tools]");
            continue;
        }
        if (!in_tools) continue;
        const auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = strip(stripped.substr(0, eq));
        if (key != "addTool") continue;
        const auto parts = parse_csv(stripped.substr(eq + 1));
        if (parts.empty()) continue;
        IniToolDeclaration decl;
        decl.tool_id = parts[0];
        decl.label = parts.size() > 1 ? parts[1] : decl.tool_id;
        if (parts.size() > 2) decl.target_table_id = parts[2];
        section.declarations.push_back(std::move(decl));
    }
    return section;
}

}  // namespace tuner_core
