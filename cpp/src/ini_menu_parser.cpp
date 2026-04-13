// SPDX-License-Identifier: MIT
//
// tuner_core::IniMenuParser implementation. Direct port of
// `IniParser._parse_menus`.

#include "tuner_core/ini_menu_parser.hpp"
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

std::optional<int> parse_int_literal(std::string_view token) {
    auto stripped = strip(token);
    if (stripped.empty()) return std::nullopt;
    int base = 10;
    std::size_t start = 0;
    if (stripped.size() >= 2 && stripped[0] == '0' &&
        (stripped[1] == 'x' || stripped[1] == 'X')) {
        base = 16;
        start = 2;
    }
    try {
        std::size_t consumed = 0;
        int value = std::stoi(stripped.substr(start), &consumed, base);
        if (consumed != stripped.size() - start) return std::nullopt;
        return value;
    } catch (...) {
        return std::nullopt;
    }
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

IniMenuSection parse_menu_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_menu_lines(split_lines(text), defines);
}

IniMenuSection parse_menu_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_menu_lines(preprocessed_lines, defines);
}

IniMenuSection parse_menu_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniMenuSection section;
    bool in_menu = false;
    IniMenu* current = nullptr;

    for (const auto& raw_line : lines) {
        auto stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';' || stripped[0] == '#') continue;
        if (stripped[0] == '[') {
            in_menu = lowercase(stripped) == "[menu]";
            // Section change resets the active menu pointer (mirrors Python).
            current = nullptr;
            continue;
        }
        if (!in_menu) continue;

        auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        auto key = strip(std::string_view(stripped).substr(0, eq));
        auto value = strip(std::string_view(stripped).substr(eq + 1));

        if (key == "menu") {
            auto parts = parse_csv(value);
            if (parts.empty()) continue;
            IniMenu menu;
            menu.title = parts[0];
            section.menus.push_back(std::move(menu));
            current = &section.menus.back();
            continue;
        }

        if (current == nullptr) continue;
        if (key != "subMenu" && key != "groupChildMenu") continue;

        auto parts = parse_csv(value);
        if (parts.empty()) continue;
        // std_separator is a visual divider, not a navigable item.
        if (parts[0] == "std_separator") continue;

        IniMenuItem item;
        item.target = parts[0];
        item.label = (parts.size() > 1) ? parts[1] : parts[0];

        // Walk fields after the label looking for a {visibility expression}
        // and an optional page number. Either may appear before the other.
        for (std::size_t i = 2; i < parts.size(); ++i) {
            const auto& part = parts[i];
            if (part.size() >= 2 && part.front() == '{' && part.back() == '}') {
                item.visibility_expression = part;
                continue;
            }
            if (!item.page.has_value()) {
                auto p = parse_int_literal(part);
                if (p.has_value()) item.page = p;
            }
        }

        current->items.push_back(std::move(item));
    }

    return section;
}

}  // namespace tuner_core
