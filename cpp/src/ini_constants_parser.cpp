// SPDX-License-Identifier: MIT
//
// tuner_core::IniConstantsParser implementation. Direct port of
// `IniParser._parse_constant_definitions`.

#include "tuner_core/ini_constants_parser.hpp"
#include "tuner_core/ini_defines_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <algorithm>
#include <cctype>
#include <regex>
#include <stdexcept>

namespace tuner_core {

namespace {

// `strip` and `strip_quotes` come from `parse_helpers.hpp` (shared
// with the defines parser). The bare names are re-exported here so
// the rest of this file reads as it did before the refactor.
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

// Parse a possibly-hex / possibly-decimal integer literal. Returns
// nullopt on failure. Mirrors Python `int(token, 0)` semantics.
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

// Mirror Python `_parse_float_token`: returns nullopt for empty,
// `{...}` placeholder, or non-numeric.
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

// Mirror Python `_parse_int_token` — accepts numeric strings even when
// they're written as floats (e.g. "5.0" → 5).
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

// Mirror Python `_parse_value_token`: trim, drop empties, preserve
// `{expression}` payloads verbatim.
std::optional<std::string> parse_value_token(std::string_view token) {
    auto stripped = strip(token);
    if (stripped.empty()) return std::nullopt;
    if (stripped.size() >= 2 && stripped.front() == '{' && stripped.back() == '}') {
        return stripped;
    }
    return stripped;
}

// Parse `[N]` or `[NxM]` shape into (rows, columns). Returns (0, 0)
// when the input doesn't match either form so the caller can skip the
// entry. Mirrors `_parse_shape` plus the 1D fallback.
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

// Parse `[bit_offset]` or `[bit_offset:bit_end]`. Returns (nullopt, nullopt)
// on failure. Mirrors `_parse_bit_shape`.
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

// Mirror `_constant_storage_size`.
int constant_storage_size(std::string_view data_type, std::string_view shape, std::string_view entry_kind) {
    auto upper = data_type;
    int width = 1;
    auto upper_str = std::string(upper);
    for (char& c : upper_str) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    if (upper_str == "U16" || upper_str == "S16") width = 2;
    else if (upper_str == "U32" || upper_str == "S32" || upper_str == "F32") width = 4;
    else width = 1;

    if (entry_kind == "array" && !shape.empty()) {
        auto [rows, cols] = parse_shape(shape);
        return width * rows * cols;
    }
    return width;
}

// Mirror `_resolve_constant_offset`.
std::optional<int> resolve_constant_offset(std::string_view token, int current_page_next_offset) {
    auto stripped = strip(token);
    auto lower = lowercase(stripped);
    if (lower == "lastoffset") return current_page_next_offset;
    return parse_int_literal(stripped);
}

}  // namespace

IniConstantsSection parse_constants_section(
    std::string_view text,
    const IniDefines& defines) {
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
    return parse_constants_lines(lines, defines);
}

IniConstantsSection parse_constants_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    // Composed pipeline: preprocess → collect defines → parse, mirroring
    // the Python `IniParser.parse()` flow.
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_constants_lines(preprocessed_lines, defines);
}

IniConstantsSection parse_constants_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines) {
    IniConstantsSection section;

    // Mirror the Python regex:
    //   ^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|string|bits)\s*,
    //   \s*([A-Za-z0-9]+)\s*,\s*([A-Za-z0-9_]+)
    //   (?:\s*,\s*(\[[^\]]+\]))?\s*,\s*(.+)$
    static const std::regex pattern(
        R"(^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|string|bits)\s*,\s*([A-Za-z0-9]+)\s*,\s*([A-Za-z0-9_]+)(?:\s*,\s*(\[[^\]]+\]))?\s*,\s*(.+)$)",
        std::regex::optimize);

    std::optional<int> current_page;
    int current_page_next_offset = 0;
    bool in_constants = false;

    for (const auto& raw_line : lines) {
        auto line = strip(raw_line);
        if (line.empty()) continue;
        if (line[0] == ';') continue;
        if (line[0] == '#') continue;
        if (line[0] == '[') {
            in_constants = lowercase(line) == "[constants]";
            continue;
        }
        if (!in_constants) continue;

        // page = N
        if (line.rfind("page", 0) == 0 && line.size() > 4 &&
            (std::isspace(static_cast<unsigned char>(line[4])) || line[4] == '=')) {
            auto eq = line.find('=');
            if (eq != std::string::npos) {
                auto value = strip(std::string_view(line).substr(eq + 1));
                auto parsed = parse_int_literal(value);
                current_page = parsed;  // None when unparseable
                current_page_next_offset = 0;
            }
            continue;
        }

        std::smatch match;
        if (!std::regex_match(raw_line, match, pattern)) continue;

        std::string name = match[1].str();
        std::string entry_kind = match[2].str();
        std::string data_type = match[3].str();
        std::string offset_str = match[4].str();
        std::string shape = match[5].matched ? match[5].str() : std::string();
        std::string remainder = match[6].str();

        auto parts = parse_csv(remainder);
        std::optional<std::string> units = parts.size() > 0 ? parse_value_token(parts[0]) : std::nullopt;
        std::optional<double> scale = parts.size() > 1 ? parse_float_token(parts[1]) : std::nullopt;
        std::optional<double> translate = parts.size() > 2 ? parse_float_token(parts[2]) : std::nullopt;
        std::optional<double> min_value = parts.size() > 3 ? parse_float_token(parts[3]) : std::nullopt;
        std::optional<double> max_value = parts.size() > 4 ? parse_float_token(parts[4]) : std::nullopt;
        std::optional<int> digits = parts.size() > 5 ? parse_int_token(parts[5]) : std::nullopt;

        auto offset_int = resolve_constant_offset(offset_str, current_page_next_offset);
        if (!offset_int) continue;

        if (entry_kind == "scalar" || entry_kind == "string") {
            IniScalar scalar;
            scalar.name = name;
            scalar.data_type = data_type;
            scalar.units = units;
            scalar.page = current_page;
            scalar.offset = offset_int;
            scalar.scale = scale;
            scalar.translate = translate;
            scalar.min_value = min_value;
            scalar.max_value = max_value;
            scalar.digits = digits;
            section.scalars.push_back(std::move(scalar));
            current_page_next_offset = std::max(
                current_page_next_offset,
                *offset_int + constant_storage_size(data_type, "", entry_kind));
        } else if (entry_kind == "bits") {
            auto [bit_offset, bit_length] = parse_bit_shape(shape);
            IniScalar scalar;
            scalar.name = name;
            scalar.data_type = data_type;
            scalar.page = current_page;
            scalar.offset = offset_int;
            scalar.bit_offset = bit_offset;
            scalar.bit_length = bit_length;
            // Bit option labels: expand `$macroName` references via the
            // defines map (slice 5 composition). Python appends the
            // expanded list verbatim — do NOT call strip() again here
            // or trailing whitespace inside quoted labels (e.g.
            // `"Relative "`) gets eaten and parity breaks.
            auto expanded = expand_options(parts, defines);
            for (auto& part : expanded) {
                if (!part.empty()) scalar.options.push_back(std::move(part));
            }
            section.scalars.push_back(std::move(scalar));
            current_page_next_offset = std::max(
                current_page_next_offset,
                *offset_int + constant_storage_size(data_type, "", entry_kind));
        } else if (entry_kind == "array" && !shape.empty()) {
            auto [rows, cols] = parse_shape(shape);
            IniArray array;
            array.name = name;
            array.data_type = data_type;
            array.rows = rows;
            array.columns = cols;
            array.units = units;
            array.page = current_page;
            array.offset = offset_int;
            array.scale = scale;
            array.translate = translate;
            array.digits = digits;
            array.min_value = min_value;
            array.max_value = max_value;
            section.arrays.push_back(std::move(array));
            current_page_next_offset = std::max(
                current_page_next_offset,
                *offset_int + constant_storage_size(data_type, shape, entry_kind));
        }
    }

    return section;
}

}  // namespace tuner_core
