// SPDX-License-Identifier: MIT
//
// tuner_core::ini_pc_variables_parser implementation. Direct port of
// `IniParser._parse_pc_variables`. Grammar is a subset of
// `[Constants]` — no page / offset / lastOffset / string kinds.

#include "tuner_core/ini_pc_variables_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <algorithm>
#include <cctype>
#include <regex>

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

// Mirror `_parse_float_token`: returns nullopt for empty, `{...}`
// placeholder, or non-numeric.
std::optional<double> parse_float_token(std::string_view token) {
    auto stripped = strip(token);
    if (stripped.empty()) return std::nullopt;
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

std::optional<int> parse_int_token(std::string_view token) {
    auto stripped = strip(token);
    if (stripped.empty()) return std::nullopt;
    if (stripped.front() == '{') return std::nullopt;
    try {
        std::size_t consumed = 0;
        double value = std::stod(stripped, &consumed);
        if (consumed == 0) return std::nullopt;
        return static_cast<int>(value);
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<std::string> parse_value_token(std::string_view token) {
    auto stripped = strip(token);
    if (stripped.empty()) return std::nullopt;
    return stripped;
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

std::pair<int, int> parse_shape(std::string_view shape) {
    auto stripped = strip(shape);
    if (stripped.size() < 2 || stripped.front() != '[' || stripped.back() != ']') {
        return {0, 0};
    }
    auto inner = strip(stripped.substr(1, stripped.size() - 2));
    auto x_pos = inner.find('x');
    if (x_pos != std::string::npos) {
        auto rows = parse_int_literal(strip(inner.substr(0, x_pos)));
        auto cols = parse_int_literal(strip(inner.substr(x_pos + 1)));
        if (!rows || !cols) return {0, 0};
        return {*rows, *cols};
    }
    auto count = parse_int_literal(inner);
    if (!count) return {0, 0};
    return {*count, 1};
}

std::pair<std::optional<int>, std::optional<int>> parse_bit_shape(std::string_view shape) {
    auto stripped = strip(shape);
    if (stripped.size() < 2 || stripped.front() != '[' || stripped.back() != ']') {
        return {std::nullopt, std::nullopt};
    }
    auto inner = strip(stripped.substr(1, stripped.size() - 2));
    auto colon = inner.find(':');
    if (colon == std::string::npos) {
        auto bit = parse_int_literal(inner);
        if (!bit) return {std::nullopt, std::nullopt};
        return {*bit, 1};
    }
    auto start = parse_int_literal(strip(inner.substr(0, colon)));
    auto end = parse_int_literal(strip(inner.substr(colon + 1)));
    if (!start || !end) return {std::nullopt, std::nullopt};
    int s = *start, e = *end;
    if (e < s) std::swap(s, e);
    return {s, e - s + 1};
}

}  // namespace

IniConstantsSection parse_pc_variables_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_pc_variables_lines(split_lines(text), defines);
}

IniConstantsSection parse_pc_variables_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    const auto lines = split_lines(text);
    const auto preprocessed = preprocess_ini_lines(lines, active_settings);
    const auto defines = collect_defines_lines(preprocessed);
    return parse_pc_variables_lines(preprocessed, defines);
}

IniConstantsSection parse_pc_variables_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines) {
    IniConstantsSection section;

    // Mirror the Python regex:
    //   ^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|bits)\s*,\s*([A-Za-z0-9]+)
    //   (?:\s*,\s*(\[[^\]]+\]))?\s*,\s*(.+)$
    //
    // Same shape as the `[Constants]` pattern but with `string` removed
    // from the kind alternation and no capture group for `offset`.
    static const std::regex pattern(
        R"(^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|bits)\s*,\s*([A-Za-z0-9]+)(?:\s*,\s*(\[[^\]]+\]))?\s*,\s*(.+)$)",
        std::regex::optimize);

    bool in_pc_vars = false;
    for (const auto& raw_line : lines) {
        const auto line = strip(raw_line);
        if (line.empty()) continue;
        if (line[0] == ';' || line[0] == '#') continue;
        if (line[0] == '[') {
            in_pc_vars = (lowercase(line) == "[pcvariables]");
            continue;
        }
        if (!in_pc_vars) continue;

        std::smatch match;
        if (!std::regex_match(raw_line, match, pattern)) continue;

        const std::string name = match[1].str();
        const std::string entry_kind = match[2].str();
        const std::string data_type = match[3].str();
        const std::string shape = match[4].matched ? match[4].str() : std::string();
        const std::string remainder = match[5].str();

        const auto parts = parse_csv(remainder);
        const auto units = parts.size() > 0 ? parse_value_token(parts[0]) : std::nullopt;
        const auto scale = parts.size() > 1 ? parse_float_token(parts[1]) : std::nullopt;
        const auto translate = parts.size() > 2 ? parse_float_token(parts[2]) : std::nullopt;
        const auto min_value = parts.size() > 3 ? parse_float_token(parts[3]) : std::nullopt;
        const auto max_value = parts.size() > 4 ? parse_float_token(parts[4]) : std::nullopt;
        const auto digits = parts.size() > 5 ? parse_int_token(parts[5]) : std::nullopt;

        if (entry_kind == "scalar") {
            IniScalar scalar;
            scalar.name = name;
            scalar.data_type = data_type;
            scalar.units = units;
            // PC variables have no ECU storage — leave page/offset unset.
            scalar.scale = scale;
            scalar.translate = translate;
            scalar.digits = digits;
            scalar.min_value = min_value;
            scalar.max_value = max_value;
            section.scalars.push_back(std::move(scalar));
        } else if (entry_kind == "bits") {
            auto [bit_offset, bit_length] = parse_bit_shape(shape);
            IniScalar scalar;
            scalar.name = name;
            scalar.data_type = data_type;
            scalar.bit_offset = bit_offset;
            scalar.bit_length = bit_length;
            auto expanded = expand_options(parts, defines);
            for (auto& part : expanded) {
                if (!part.empty()) scalar.options.push_back(std::move(part));
            }
            section.scalars.push_back(std::move(scalar));
        } else if (entry_kind == "array" && !shape.empty()) {
            auto [rows, cols] = parse_shape(shape);
            IniArray array;
            array.name = name;
            array.data_type = data_type;
            array.rows = rows;
            array.columns = cols;
            array.units = units;
            array.scale = scale;
            array.translate = translate;
            array.digits = digits;
            array.min_value = min_value;
            array.max_value = max_value;
            section.arrays.push_back(std::move(array));
        }
    }
    return section;
}

}  // namespace tuner_core
