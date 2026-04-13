// SPDX-License-Identifier: MIT
//
// tuner_core::ini_setting_groups_parser implementation. Direct port
// of `IniParser._parse_setting_groups`.

#include "tuner_core/ini_setting_groups_parser.hpp"
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

}  // namespace

IniSettingGroupsSection parse_setting_groups_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_setting_groups_lines(split_lines(text), defines);
}

IniSettingGroupsSection parse_setting_groups_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    const auto lines = split_lines(text);
    const auto preprocessed = preprocess_ini_lines(lines, active_settings);
    const auto defines = collect_defines_lines(preprocessed);
    return parse_setting_groups_lines(preprocessed, defines);
}

IniSettingGroupsSection parse_setting_groups_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniSettingGroupsSection section;
    bool in_section = false;
    IniSettingGroup current;
    bool has_current = false;

    auto flush = [&]() {
        if (has_current) {
            section.groups.push_back(std::move(current));
            current = IniSettingGroup{};
            has_current = false;
        }
    };

    for (const auto& raw_line : lines) {
        const std::string stripped = strip(raw_line);
        if (stripped.empty()) continue;
        // Comment lines start with ; or #.
        if (stripped[0] == ';' || stripped[0] == '#') continue;
        // Section header.
        if (stripped[0] == '[') {
            const bool was_in = in_section;
            in_section = (lowercase(stripped) == "[settinggroups]");
            // Exiting the section: flush any in-flight block.
            if (was_in && !in_section) flush();
            continue;
        }
        if (!in_section) continue;
        // key = value split on first `=` only.
        const auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = strip(stripped.substr(0, eq));
        const std::string value = stripped.substr(eq + 1);
        const auto parts = parse_csv(value);
        if (key == "settingGroup") {
            // New block — flush previous.
            flush();
            current = IniSettingGroup{};
            has_current = true;
            current.symbol = parts.empty() ? "" : parts[0];
            // Python: `label = value_parts[1] if len(value_parts) > 1 else symbol`
            // then `_strip_quotes(label)` — which strips a trailing `;`
            // comment and any paired quotes. `parse_csv` already
            // strips quotes, so the label comes through pre-cleaned
            // for the comma-split case. The `symbol` fallback keeps
            // its quotes stripped the same way.
            current.label = parts.size() > 1 ? parts[1] : current.symbol;
        } else if (key == "settingOption" && has_current) {
            IniSettingGroupOption option;
            option.symbol = parts.empty() ? "" : parts[0];
            option.label = parts.size() > 1 ? parts[1] : option.symbol;
            current.options.push_back(std::move(option));
        }
    }
    // End of input — flush the in-flight block.
    flush();
    return section;
}

}  // namespace tuner_core
