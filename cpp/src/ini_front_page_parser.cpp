// SPDX-License-Identifier: MIT
//
// tuner_core::IniFrontPageParser implementation. Direct port of
// `IniParser._parse_front_page`.

#include "tuner_core/ini_front_page_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <cctype>
#include <map>
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

// Mirrors `re.match(r"^gauge\d+$", key, IGNORECASE)` and returns the
// trailing index, or -1 if the key isn't a gauge slot.
int parse_gauge_slot_index(const std::string& key) {
    if (key.size() < 6) return -1;
    // Compare "gauge" prefix case-insensitively.
    static const char prefix[] = "gauge";
    for (int i = 0; i < 5; ++i) {
        if (std::tolower(static_cast<unsigned char>(key[i])) != prefix[i]) return -1;
    }
    // Remainder must be all digits.
    int idx = 0;
    bool any = false;
    for (std::size_t i = 5; i < key.size(); ++i) {
        char c = key[i];
        if (c < '0' || c > '9') return -1;
        idx = idx * 10 + (c - '0');
        any = true;
    }
    return any ? idx : -1;
}

}  // namespace

IniFrontPageSection parse_front_page_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_front_page_lines(split_lines(text), defines);
}

IniFrontPageSection parse_front_page_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_front_page_lines(preprocessed_lines, defines);
}

IniFrontPageSection parse_front_page_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniFrontPageSection section;
    bool in_section = false;
    std::map<int, std::string> gauges;

    for (const auto& raw_line : lines) {
        auto stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';') continue;
        if (stripped[0] == '[') {
            in_section = lowercase(stripped) == "[frontpage]";
            continue;
        }
        if (!in_section) continue;

        // Strip inline `; ...` comments.
        auto semi = stripped.find(';');
        if (semi != std::string::npos) {
            stripped = strip(stripped.substr(0, semi));
        }
        if (stripped.empty()) continue;

        auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        auto key = strip(std::string_view(stripped).substr(0, eq));
        auto value = strip(std::string_view(stripped).substr(eq + 1));

        // gauge1 ... gaugeN
        int slot = parse_gauge_slot_index(key);
        if (slot > 0) {
            gauges[slot] = strip(value);
            continue;
        }

        if (key == "indicator") {
            auto parts = parse_csv(value);
            if (parts.size() < 7) continue;

            // First token still carries `{ ... }` braces — strip them
            // if present, mirroring the Python `_parse_front_page`.
            std::string expr = strip(parts[0]);
            if (expr.size() >= 2 && expr.front() == '{' && expr.back() == '}') {
                expr = strip(expr.substr(1, expr.size() - 2));
            }

            IniFrontPageIndicator ind;
            ind.expression = expr;
            // parse_csv already strips outer quotes and whitespace, so
            // these tokens come through ready to use.
            ind.off_label = parts[1];
            ind.on_label = parts[2];
            ind.off_bg = parts[3];
            ind.off_fg = parts[4];
            ind.on_bg = parts[5];
            ind.on_fg = parts[6];
            section.indicators.push_back(std::move(ind));
        }
    }

    // Build positional gauge list from gauge1..gaugeN, filling missing
    // slots with empty strings (mirrors the Python builder).
    if (!gauges.empty()) {
        int max_slot = gauges.rbegin()->first;
        section.gauges.resize(static_cast<std::size_t>(max_slot));
        for (const auto& [idx, name] : gauges) {
            section.gauges[static_cast<std::size_t>(idx - 1)] = name;
        }
    }

    return section;
}

}  // namespace tuner_core
