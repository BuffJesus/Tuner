// SPDX-License-Identifier: MIT
//
// tuner_core::IniCurveEditorParser implementation. Direct port of
// `IniParser._parse_curve_editors`.

#include "tuner_core/ini_curve_editor_parser.hpp"
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

// Mirror Python's behaviour: int(float(value)) — accepts "5.0" → 5.
std::optional<int> parse_int_via_double(std::string_view token) {
    auto v = parse_double(token);
    if (!v) return std::nullopt;
    return static_cast<int>(*v);
}

// Mirror Python's `_strip_quotes` for value strings: split on `;`
// (drops trailing comments), strip whitespace, then strip a single
// pair of surrounding double quotes if both ends have them.
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

// CSV-token-level quote stripping (matches Python `_strip_quotes`
// applied to a single token from `_parse_csv`). Tokens come from
// `parse_csv` already mostly clean, but a few production INI lines
// have trailing comments inside the token that need handling.
std::string strip_token_quotes(std::string_view token) {
    auto semi = token.find(';');
    auto truncated = (semi == std::string_view::npos) ? token : token.substr(0, semi);
    auto stripped = strip(truncated);
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

// Mirror Python's `_flush`: assign accumulated `pending_line_labels`
// onto the curve's y_bins_list positionally, then push the curve
// onto the section.
void flush_curve(
    IniCurveEditor& curve,
    std::vector<std::string>& pending_line_labels,
    IniCurveEditorSection& section) {
    for (std::size_t i = 0;
         i < pending_line_labels.size() && i < curve.y_bins_list.size();
         ++i) {
        curve.y_bins_list[i].label = pending_line_labels[i];
    }
    pending_line_labels.clear();
    section.curves.push_back(std::move(curve));
}

}  // namespace

IniCurveEditorSection parse_curve_editor_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_curve_editor_lines(split_lines(text), defines);
}

IniCurveEditorSection parse_curve_editor_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_curve_editor_lines(preprocessed_lines, defines);
}

IniCurveEditorSection parse_curve_editor_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniCurveEditorSection section;
    bool in_section = false;
    std::optional<IniCurveEditor> current;
    std::vector<std::string> pending_line_labels;

    for (const auto& raw_line : lines) {
        auto stripped = strip(raw_line);
        if (stripped.empty()) continue;
        // Note: Python's `_parse_curve_editors` only treats `;` as a
        // comment marker, not `#` (since `#define` lines etc. need to
        // pass through). Match that.
        if (stripped[0] == ';') continue;

        if (stripped[0] == '[') {
            bool was_in_section = in_section;
            in_section = lowercase(stripped) == "[curveeditor]";
            // Mirror Python: when we exit the section with an active
            // curve buffered, flush it before resetting.
            if (was_in_section && !in_section && current.has_value()) {
                flush_curve(*current, pending_line_labels, section);
                current.reset();
            }
            continue;
        }
        if (!in_section) continue;

        // Strip inline comments (`; ...`) — Python does this after
        // the section/comment guards.
        auto semi = stripped.find(';');
        if (semi != std::string::npos) {
            stripped = strip(stripped.substr(0, semi));
        }
        if (stripped.empty()) continue;

        auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        auto key = strip(std::string_view(stripped).substr(0, eq));
        auto value = strip(std::string_view(stripped).substr(eq + 1));

        if (key == "curve") {
            // New curve — flush the previous one first.
            if (current.has_value()) {
                flush_curve(*current, pending_line_labels, section);
            }
            auto parts = parse_csv(value);
            if (parts.empty()) {
                current.reset();
                continue;
            }
            IniCurveEditor c;
            c.name = strip(parts[0]);
            c.title = (parts.size() > 1) ? strip_token_quotes(parts[1]) : c.name;
            current = std::move(c);
            continue;
        }

        if (!current.has_value()) continue;

        if (key == "columnLabel") {
            auto parts = parse_csv(value);
            if (!parts.empty()) current->x_label = strip_token_quotes(parts[0]);
            if (parts.size() > 1) current->y_label = strip_token_quotes(parts[1]);
        } else if (key == "xAxis") {
            auto parts = parse_csv(value);
            if (parts.size() >= 3) {
                auto mn = parse_double(parts[0]);
                auto mx = parse_double(parts[1]);
                auto st = parse_int_via_double(parts[2]);
                if (mn && mx && st) {
                    current->x_axis = CurveAxisRange{*mn, *mx, *st};
                }
            }
        } else if (key == "yAxis") {
            auto parts = parse_csv(value);
            if (parts.size() >= 3) {
                auto mn = parse_double(parts[0]);
                auto mx = parse_double(parts[1]);
                auto st = parse_int_via_double(parts[2]);
                if (mn && mx && st) {
                    current->y_axis = CurveAxisRange{*mn, *mx, *st};
                }
            }
        } else if (key == "xBins") {
            auto parts = parse_csv(value);
            if (!parts.empty()) {
                current->x_bins_param = strip(parts[0]);
                if (parts.size() > 1) current->x_channel = strip(parts[1]);
            }
        } else if (key == "yBins") {
            auto parts = parse_csv(value);
            if (!parts.empty()) {
                CurveYBins yb;
                yb.param = strip(parts[0]);
                current->y_bins_list.push_back(std::move(yb));
            }
        } else if (key == "lineLabel") {
            auto label = strip_value_quotes(value);
            if (label) pending_line_labels.push_back(*label);
        } else if (key == "topicHelp") {
            current->topic_help = strip_value_quotes(value);
        } else if (key == "gauge") {
            current->gauge = strip(value);
        } else if (key == "size") {
            auto parts = parse_csv(value);
            if (parts.size() >= 2) {
                auto w = parse_int_via_double(parts[0]);
                auto h = parse_int_via_double(parts[1]);
                if (w && h) {
                    current->size = std::array<int, 2>{*w, *h};
                }
            }
        }
    }

    // Flush the final curve (mirrors Python's tail handling).
    if (current.has_value()) {
        flush_curve(*current, pending_line_labels, section);
    }

    return section;
}

}  // namespace tuner_core
