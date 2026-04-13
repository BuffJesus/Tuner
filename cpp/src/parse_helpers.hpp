// SPDX-License-Identifier: MIT
//
// Internal helpers shared between INI section parsers. NOT a public
// API — kept under `cpp/src/` rather than `cpp/include/` so the
// header isn't installed alongside the published `tuner_core/*.hpp`
// surface.
//
// All functions in this header mirror the corresponding helpers in
// `src/tuner/parsers/ini_parser.py` and `src/tuner/parsers/common.py`
// byte-for-byte; the parity harnesses depend on that.

#pragma once

#include <algorithm>
#include <cctype>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::detail {

inline std::string strip(std::string_view text) {
    auto begin = text.begin();
    auto end = text.end();
    while (begin != end && std::isspace(static_cast<unsigned char>(*begin))) ++begin;
    while (end != begin && std::isspace(static_cast<unsigned char>(*(end - 1)))) --end;
    return std::string(begin, end);
}

// Mirrors Python's `str.strip('"')`: strips ANY leading and trailing
// `"` characters independently. NOT the same as removing a paired
// pair of quotes — `'"foo` becomes `foo`, `foo"` becomes `foo`,
// `"foo"` becomes `foo`. The Python `_parse_csv` relies on this
// behaviour for tokens that span malformed quote regions or trailing
// `;` comments inside option lists.
//
// Crucially: this helper does NOT strip whitespace. The caller is
// responsible for `strip()`-ing first if they want outer whitespace
// removed. Python sequences these as `token.strip().strip('"')`.
inline std::string strip_quotes(std::string_view text) {
    std::size_t begin = 0;
    std::size_t end = text.size();
    while (begin < end && text[begin] == '"') ++begin;
    while (end > begin && text[end - 1] == '"') --end;
    return std::string(text.substr(begin, end - begin));
}

// CSV splitter that respects quoted strings, brace expressions, and
// parenthesized groups. Direct port of `IniParser._parse_csv`.
inline std::vector<std::string> parse_csv(std::string_view value) {
    std::vector<std::string> tokens;
    std::string current;
    bool in_quotes = false;
    int brace_depth = 0;
    int paren_depth = 0;
    for (char c : value) {
        if (c == '"') {
            in_quotes = !in_quotes;
            current.push_back(c);
            continue;
        }
        if (!in_quotes) {
            if (c == '{') ++brace_depth;
            else if (c == '}') brace_depth = std::max(0, brace_depth - 1);
            else if (c == '(') ++paren_depth;
            else if (c == ')') paren_depth = std::max(0, paren_depth - 1);
            else if (c == ',' && brace_depth == 0 && paren_depth == 0) {
                // Mirror Python's `_parse_csv`: strip outer whitespace
                // first, then strip *any* leading/trailing `"` chars.
                auto token = strip(current);
                if (!token.empty()) tokens.push_back(strip_quotes(token));
                current.clear();
                continue;
            }
        }
        current.push_back(c);
    }
    auto final_token = strip(current);
    if (!final_token.empty()) tokens.push_back(strip_quotes(final_token));
    return tokens;
}

}  // namespace tuner_core::detail
