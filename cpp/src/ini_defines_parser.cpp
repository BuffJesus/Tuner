// SPDX-License-Identifier: MIT
//
// tuner_core::IniDefinesParser implementation. Direct port of
// `IniParser._collect_defines` and `_expand_options`.

#include "tuner_core/ini_defines_parser.hpp"
#include "parse_helpers.hpp"

namespace tuner_core {

namespace {

constexpr int kMaxExpandDepth = 10;  // matches Python guard

void expand_options_recursive(
    const std::vector<std::string>& parts,
    const IniDefines& defines,
    int depth,
    std::vector<std::string>& out) {
    if (depth > kMaxExpandDepth) return;
    for (const auto& part : parts) {
        if (part.empty()) continue;
        if (part.front() == '{') {
            // Inline condition expression — not an option label; skip.
            continue;
        }
        if (part.front() == '$') {
            std::string macro_name = part.substr(1);
            auto it = defines.find(macro_name);
            if (it != defines.end()) {
                expand_options_recursive(it->second, defines, depth + 1, out);
            }
            // If macro not found, drop the token silently rather than
            // surfacing a raw "$undefined" label.
            continue;
        }
        out.push_back(part);
    }
}

}  // namespace

IniDefines collect_defines(std::string_view text) {
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
    return collect_defines_lines(lines);
}

IniDefines collect_defines_lines(const std::vector<std::string>& lines) {
    IniDefines defines;
    constexpr std::string_view kPrefix = "#define";
    for (const auto& raw_line : lines) {
        auto stripped = detail::strip(raw_line);
        if (stripped.size() < kPrefix.size()) continue;
        if (stripped.compare(0, kPrefix.size(), kPrefix) != 0) continue;

        // Skip past the `#define` keyword and any leading whitespace
        // before the name.
        auto rest = detail::strip(std::string_view(stripped).substr(kPrefix.size()));
        auto eq = rest.find('=');
        if (eq == std::string::npos) continue;

        auto name = detail::strip(std::string_view(rest).substr(0, eq));
        if (name.empty()) continue;
        auto value = detail::strip(std::string_view(rest).substr(eq + 1));

        auto tokens = detail::parse_csv(value);
        if (!tokens.empty()) {
            defines[name] = std::move(tokens);
        }
    }
    return defines;
}

std::vector<std::string> expand_options(
    const std::vector<std::string>& parts,
    const IniDefines& defines) {
    std::vector<std::string> out;
    expand_options_recursive(parts, defines, 0, out);
    return out;
}

}  // namespace tuner_core
