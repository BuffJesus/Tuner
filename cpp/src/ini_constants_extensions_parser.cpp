// SPDX-License-Identifier: MIT
//
// tuner_core::ini_constants_extensions_parser implementation. Direct
// port of `IniParser._parse_constants_extensions`.

#include "tuner_core/ini_constants_extensions_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <cctype>
#include <utility>

namespace tuner_core {

namespace {

using detail::strip;

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

// Mirror Python `value.split(";", 1)[0].split(",")`: drop a trailing
// `;` comment first, then CSV-split the head and return the trimmed
// non-empty tokens.
std::vector<std::string> parse_name_list(std::string_view value) {
    std::string head(value);
    auto semi = head.find(';');
    if (semi != std::string::npos) head = head.substr(0, semi);
    std::vector<std::string> out;
    std::string current;
    auto flush = [&]() {
        std::string trimmed = strip(current);
        if (!trimmed.empty()) out.push_back(std::move(trimmed));
        current.clear();
    };
    for (char c : head) {
        if (c == ',') { flush(); continue; }
        current.push_back(c);
    }
    flush();
    return out;
}

}  // namespace

IniConstantsExtensionsSection parse_constants_extensions_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_constants_extensions_lines(split_lines(text), defines);
}

IniConstantsExtensionsSection parse_constants_extensions_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    const auto lines = split_lines(text);
    const auto preprocessed = preprocess_ini_lines(lines, active_settings);
    const auto defines = collect_defines_lines(preprocessed);
    return parse_constants_extensions_lines(preprocessed, defines);
}

IniConstantsExtensionsSection parse_constants_extensions_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniConstantsExtensionsSection section;
    bool in_extensions = false;
    for (const auto& raw_line : lines) {
        const std::string stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';' || stripped[0] == '#') continue;
        if (stripped[0] == '[') {
            in_extensions = (lowercase(stripped) == "[constantsextensions]");
            continue;
        }
        if (!in_extensions) continue;
        const auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = strip(stripped.substr(0, eq));
        if (key != "requiresPowerCycle") continue;
        for (auto& name : parse_name_list(stripped.substr(eq + 1))) {
            section.requires_power_cycle.insert(std::move(name));
        }
    }
    return section;
}

}  // namespace tuner_core
