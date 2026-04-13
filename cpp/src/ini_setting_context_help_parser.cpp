// SPDX-License-Identifier: MIT
//
// tuner_core::ini_setting_context_help_parser implementation. Direct
// port of `IniParser._parse_setting_context_help`.

#include "tuner_core/ini_setting_context_help_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <cctype>
#include <utility>

namespace tuner_core {

namespace {

using detail::strip;
using detail::strip_quotes;

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

// Mirrors `IniParser._strip_quotes(value)`: strips a trailing `;`
// comment first, then strips paired/leading/trailing `"` characters.
std::string clean_help_value(std::string_view value) {
    std::string s = strip(value);
    // Strip trailing `;` comment (if any).
    auto semi = s.find(';');
    if (semi != std::string::npos) s = s.substr(0, semi);
    s = strip(s);
    return strip_quotes(s);
}

}  // namespace

IniSettingContextHelpSection parse_setting_context_help_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_setting_context_help_lines(split_lines(text), defines);
}

IniSettingContextHelpSection parse_setting_context_help_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    const auto lines = split_lines(text);
    const auto preprocessed = preprocess_ini_lines(lines, active_settings);
    const auto defines = collect_defines_lines(preprocessed);
    return parse_setting_context_help_lines(preprocessed, defines);
}

IniSettingContextHelpSection parse_setting_context_help_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniSettingContextHelpSection section;
    bool in_help = false;
    for (const auto& raw_line : lines) {
        const std::string stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';' || stripped[0] == '#') continue;
        if (stripped[0] == '[') {
            in_help = (lowercase(stripped) == "[settingcontexthelp]");
            continue;
        }
        if (!in_help) continue;
        const auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = strip(stripped.substr(0, eq));
        if (key.empty()) continue;
        section.help_by_name[key] = clean_help_value(stripped.substr(eq + 1));
    }
    return section;
}

}  // namespace tuner_core
