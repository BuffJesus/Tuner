// SPDX-License-Identifier: MIT
//
// tuner_core::IniGaugeConfigurationsParser implementation. Direct
// port of `IniParser._parse_gauge_configurations`.

#include "tuner_core/ini_gauge_configurations_parser.hpp"
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

std::optional<double> try_float(std::string_view token) {
    auto stripped = strip(token);
    if (stripped.empty()) return std::nullopt;
    // Brace expressions like `{rpmhigh}` cannot be evaluated at parse
    // time and resolve to None on the Python side.
    if (stripped.front() == '{') return std::nullopt;
    try {
        std::size_t consumed = 0;
        double value = std::stod(stripped, &consumed);
        if (consumed == 0) return std::nullopt;
        return value;
    } catch (...) {
        return std::nullopt;
    }
}

// Mirrors `int(_try_float(parts[N]) or 0)` from the Python source.
int try_int_via_float(std::string_view token) {
    auto v = try_float(token);
    if (!v.has_value()) return 0;
    return static_cast<int>(*v);
}

// Mirror Python's `_strip_quotes` for value strings: split on `;`
// (drops trailing comments), strip whitespace, then strip a single
// pair of surrounding double quotes if both ends have them. Used
// for the `gaugeCategory = "Name"` lines.
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

// CSV-token-level quote strip — used for the title and units fields
// inside a gauge entry, which come through `parse_csv` as individual
// tokens that may still carry surrounding quotes.
std::string strip_token_quotes(std::string_view token) {
    auto stripped = strip(token);
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

IniGaugeConfigurationsSection parse_gauge_configurations_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_gauge_configurations_lines(split_lines(text), defines);
}

IniGaugeConfigurationsSection parse_gauge_configurations_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_gauge_configurations_lines(preprocessed_lines, defines);
}

IniGaugeConfigurationsSection parse_gauge_configurations_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniGaugeConfigurationsSection section;
    bool in_section = false;
    std::optional<std::string> current_category;

    for (const auto& raw_line : lines) {
        auto stripped = strip(raw_line);
        if (stripped.empty()) continue;
        // Note: Python only treats `;` as a comment marker here, not `#`.
        if (stripped[0] == ';') continue;
        if (stripped[0] == '[') {
            in_section = lowercase(stripped) == "[gaugeconfigurations]";
            continue;
        }
        if (!in_section) continue;

        // Strip inline `; ...` comments after the section/comment guards.
        auto semi = stripped.find(';');
        if (semi != std::string::npos) {
            stripped = strip(stripped.substr(0, semi));
        }
        if (stripped.empty()) continue;

        auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        auto key = strip(std::string_view(stripped).substr(0, eq));
        auto value = strip(std::string_view(stripped).substr(eq + 1));

        if (key == "gaugeCategory") {
            current_category = strip_value_quotes(value);
            continue;
        }

        auto parts = parse_csv(value);
        if (parts.size() < 3) continue;

        IniGaugeConfiguration g;
        g.name = key;
        g.channel = strip(parts[0]);
        g.title = (parts.size() > 1) ? strip_token_quotes(parts[1]) : "";
        g.units = (parts.size() > 2) ? strip_token_quotes(parts[2]) : "";
        g.lo        = (parts.size() > 3) ? try_float(parts[3]) : std::nullopt;
        g.hi        = (parts.size() > 4) ? try_float(parts[4]) : std::nullopt;
        g.lo_danger = (parts.size() > 5) ? try_float(parts[5]) : std::nullopt;
        g.lo_warn   = (parts.size() > 6) ? try_float(parts[6]) : std::nullopt;
        g.hi_warn   = (parts.size() > 7) ? try_float(parts[7]) : std::nullopt;
        g.hi_danger = (parts.size() > 8) ? try_float(parts[8]) : std::nullopt;
        g.value_digits = (parts.size() > 9) ? try_int_via_float(parts[9]) : 0;
        g.label_digits = (parts.size() > 10) ? try_int_via_float(parts[10]) : 0;
        g.category = current_category;

        section.gauges.push_back(std::move(g));
    }

    return section;
}

}  // namespace tuner_core
