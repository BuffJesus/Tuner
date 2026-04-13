// SPDX-License-Identifier: MIT
//
// tuner_core::IniTableEditorParser implementation. Direct port of
// `IniParser._parse_table_editors`.

#include "tuner_core/ini_table_editor_parser.hpp"
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

std::optional<double> parse_double(std::string_view token) {
    auto stripped = strip(token);
    if (stripped.empty()) return std::nullopt;
    try {
        std::size_t consumed = 0;
        double value = std::stod(stripped, &consumed);
        if (consumed == 0) return std::nullopt;
        return value;
    } catch (...) {
        return std::nullopt;
    }
}

// Mirror Python's `_strip_quotes` for value strings: split on `;`
// (drops trailing comments), strip whitespace, then strip a single
// pair of surrounding double quotes.
std::optional<std::string> strip_value_quotes(std::string_view value) {
    auto semi = value.find(';');
    auto truncated = (semi == std::string_view::npos) ? value : value.substr(0, semi);
    auto stripped = strip(truncated);
    if (stripped.empty()) return std::nullopt;
    if (stripped.size() >= 2 && stripped.front() == '"' && stripped.back() == '"') {
        return stripped.substr(1, stripped.size() - 2);
    }
    return stripped;
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

IniTableEditorSection parse_table_editor_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_table_editor_lines(split_lines(text), defines);
}

IniTableEditorSection parse_table_editor_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_table_editor_lines(preprocessed_lines, defines);
}

IniTableEditorSection parse_table_editor_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniTableEditorSection section;
    bool in_table_editor = false;
    IniTableEditor* current = nullptr;

    for (const auto& raw_line : lines) {
        auto stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';' || stripped[0] == '#') continue;
        if (stripped[0] == '[') {
            in_table_editor = lowercase(stripped) == "[tableeditor]";
            // Section change resets the active editor — mirrors Python.
            current = nullptr;
            continue;
        }
        if (!in_table_editor) continue;

        // key = value split on the first `=` only.
        auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        auto key = strip(std::string_view(stripped).substr(0, eq));
        auto value = strip(std::string_view(stripped).substr(eq + 1));

        if (key == "table") {
            auto parts = parse_csv(value);
            if (parts.size() < 3) continue;
            IniTableEditor editor;
            editor.table_id = parts[0];
            editor.map_id = parts[1];
            editor.title = parts[2];
            if (parts.size() > 3) {
                editor.page = parse_int_literal(parts[3]);
            }
            section.editors.push_back(std::move(editor));
            current = &section.editors.back();
            continue;
        }

        if (current == nullptr) continue;

        if (key == "topicHelp") {
            current->topic_help = strip_value_quotes(value);
            continue;
        }

        auto parts = parse_csv(value);

        if (key == "xBins" && !parts.empty()) {
            current->x_bins = parts[0];
            if (parts.size() > 1) current->x_channel = parts[1];
        } else if (key == "yBins" && !parts.empty()) {
            current->y_bins = parts[0];
            if (parts.size() > 1) current->y_channel = parts[1];
        } else if (key == "zBins" && !parts.empty()) {
            current->z_bins = parts[0];
        } else if (key == "xyLabels" && !parts.empty()) {
            current->x_label = parts[0];
            if (parts.size() > 1) current->y_label = parts[1];
        } else if (key == "gridHeight" && !parts.empty()) {
            auto v = parse_double(parts[0]);
            if (v) current->grid_height = v;
        } else if (key == "gridOrient" && parts.size() >= 3) {
            auto a = parse_double(parts[0]);
            auto b = parse_double(parts[1]);
            auto c = parse_double(parts[2]);
            if (a && b && c) {
                current->grid_orient = std::array<double, 3>{*a, *b, *c};
            }
        } else if (key == "upDownLabel" && !parts.empty()) {
            current->up_label = parts[0];
            if (parts.size() > 1) current->down_label = parts[1];
        }
    }

    return section;
}

}  // namespace tuner_core
