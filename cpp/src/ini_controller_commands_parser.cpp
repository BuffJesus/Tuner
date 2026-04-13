// SPDX-License-Identifier: MIT
//
// tuner_core::IniControllerCommandsParser implementation. Direct port
// of `IniParser._parse_controller_commands`.

#include "tuner_core/ini_controller_commands_parser.hpp"
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

std::string strip_outer_quotes(std::string_view value) {
    auto stripped = strip(value);
    std::size_t b = 0;
    std::size_t e = stripped.size();
    while (b < e && stripped[b] == '"') ++b;
    while (e > b && stripped[e - 1] == '"') --e;
    return std::string(std::string_view(stripped).substr(b, e - b));
}

std::vector<std::uint8_t> decode_command(std::string_view raw) {
    std::string s = strip_outer_quotes(raw);
    std::vector<std::uint8_t> result;
    result.reserve(s.size());
    std::size_t i = 0;
    while (i < s.size()) {
        if (s[i] == '\\' && i + 1 < s.size() && s[i + 1] == 'x') {
            if (i + 4 <= s.size()) {
                std::string hex_str = s.substr(i + 2, 2);
                bool ok = hex_str.size() == 2 &&
                          std::isxdigit(static_cast<unsigned char>(hex_str[0])) &&
                          std::isxdigit(static_cast<unsigned char>(hex_str[1]));
                if (ok) {
                    auto byte = static_cast<std::uint8_t>(
                        std::stoi(hex_str, nullptr, 16));
                    result.push_back(byte);
                    i += 4;
                    continue;
                }
            }
            result.push_back(static_cast<std::uint8_t>('\\'));
            i += 1;
            continue;
        }
        result.push_back(static_cast<std::uint8_t>(s[i]));
        ++i;
    }
    return result;
}

}  // namespace

IniControllerCommandsSection parse_controller_commands_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_controller_commands_lines(split_lines(text), defines);
}

IniControllerCommandsSection parse_controller_commands_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_controller_commands_lines(preprocessed_lines, defines);
}

IniControllerCommandsSection parse_controller_commands_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniControllerCommandsSection section;
    bool in_section = false;

    for (const auto& raw_line : lines) {
        auto stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';') continue;
        if (stripped[0] == '[') {
            in_section = lowercase(stripped).rfind("[controllercommands", 0) == 0;
            continue;
        }
        if (!in_section) continue;
        auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        auto key = strip(std::string_view(stripped).substr(0, eq));
        auto value_view = std::string_view(stripped).substr(eq + 1);
        // Drop the first `;` and anything after — mirrors Python.
        auto semi = value_view.find(';');
        if (semi != std::string_view::npos) value_view = value_view.substr(0, semi);
        auto value = strip(value_view);
        if (value.empty()) continue;

        auto parts = parse_csv(value);
        std::vector<std::uint8_t> payload;
        for (const auto& part : parts) {
            auto trimmed = strip(part);
            if (trimmed.empty()) continue;
            auto bytes = decode_command(part);
            payload.insert(payload.end(), bytes.begin(), bytes.end());
        }
        if (payload.empty()) continue;

        IniControllerCommand cmd;
        cmd.name = key;
        cmd.payload = std::move(payload);
        section.commands.push_back(std::move(cmd));
    }

    return section;
}

}  // namespace tuner_core
