// SPDX-License-Identifier: MIT
//
// tuner_core::IniOutputChannelsParser implementation. Direct port of
// `IniParser._parse_output_channels`.

#include "tuner_core/ini_output_channels_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <cctype>
#include <regex>
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
    if (stripped.size() >= 2 && stripped.front() == '{' && stripped.back() == '}') {
        return stripped;
    }
    return stripped;
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
    auto start_v = parse_int_literal(strip(inner.substr(0, colon)));
    auto end_v = parse_int_literal(strip(inner.substr(colon + 1)));
    if (!start_v || !end_v) return {std::nullopt, std::nullopt};
    int s = *start_v, e = *end_v;
    if (e < s) std::swap(s, e);
    return {s, e - s + 1};
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

IniOutputChannelsSection parse_output_channels_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_output_channels_lines(split_lines(text), defines);
}

IniOutputChannelsSection parse_output_channels_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_output_channels_lines(preprocessed_lines, defines);
}

IniOutputChannelsSection parse_output_channels_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines) {
    IniOutputChannelsSection section;

    // Mirror the Python regex:
    //   ^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|bits)\s*,
    //   \s*([A-Za-z0-9]+)\s*,\s*([0-9]+)
    //   (?:\s*,\s*(\[[^\]]+\]))?(?:\s*,\s*(.+))?$
    static const std::regex pattern(
        R"(^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|bits)\s*,\s*([A-Za-z0-9]+)\s*,\s*([0-9]+)(?:\s*,\s*(\[[^\]]+\]))?(?:\s*,\s*(.+))?$)",
        std::regex::optimize);

    static const std::regex array_pattern(
        R"(^\s*([A-Za-z0-9_]+)\s*=\s*array\s*,\s*[A-Za-z0-9]+\s*,\s*\[([0-9]+)\])",
        std::regex::optimize);

    static const std::regex default_value_pattern(
        R"(^\s*defaultValue\s*=\s*([A-Za-z0-9_]+)\s*,\s*(.+)$)",
        std::regex::optimize);

    // Virtual / formula output channel:
    //   name = { expression } [, "units"] [, digits]
    // Mirrors the Python ``formula_pattern`` introduced in the same
    // slice. Must be checked *before* the scalar pattern so a bare
    // ``name = {...}`` line does not fall through to the scalar
    // branch (which requires the ``scalar|array|bits`` keyword and
    // would simply drop the line).
    static const std::regex formula_pattern(
        R"(^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{(.+?)\}\s*(?:,\s*(.+?))?\s*$)",
        std::regex::optimize);

    std::set<std::string> array_names;
    bool in_output_channels = false;

    for (const auto& raw_line : lines) {
        auto stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';' || stripped[0] == '#') continue;
        if (stripped[0] == '[') {
            in_output_channels = lowercase(stripped) == "[outputchannels]";
            continue;
        }
        if (!in_output_channels) continue;

        // Array-type output channel: `name = array, U08, [128], ...`
        // We don't promote these into `channels`, only record the name
        // so a later `defaultValue` line can be matched.
        std::smatch arr_match;
        if (std::regex_search(raw_line, arr_match, array_pattern)) {
            array_names.insert(arr_match[1].str());
            continue;
        }

        // `defaultValue = arrayName, v0 v1 v2 ...`
        std::smatch dv_match;
        if (std::regex_match(raw_line, dv_match, default_value_pattern)) {
            std::string arr_name = dv_match[1].str();
            if (array_names.count(arr_name) > 0) {
                std::string values_str = strip(dv_match[2].str());
                std::vector<double> values;
                std::string token;
                for (char c : values_str) {
                    if (std::isspace(static_cast<unsigned char>(c))) {
                        if (!token.empty()) {
                            try {
                                values.push_back(std::stod(token));
                            } catch (...) {
                                token.clear();
                                break;
                            }
                            token.clear();
                        }
                    } else {
                        token.push_back(c);
                    }
                }
                if (!token.empty()) {
                    try {
                        values.push_back(std::stod(token));
                    } catch (...) {
                        // Drop the dangling token if it's not numeric;
                        // matches the Python `break`-on-non-numeric path.
                    }
                }
                if (!values.empty()) {
                    section.arrays[arr_name] = std::move(values);
                }
            }
            continue;
        }

        // Virtual / formula output channel branch. Strip an inline
        // ``;``-comment first so trailing-comment lines like
        // ``coolant = { coolantRaw - 40 } ; Offset by 40`` reach the
        // formula regex as ``coolant = { coolantRaw - 40 }``.
        {
            std::string formula_candidate = raw_line;
            auto semi_pos = formula_candidate.find(';');
            if (semi_pos != std::string::npos) {
                formula_candidate.erase(semi_pos);
            }
            std::smatch fmatch;
            if (std::regex_match(formula_candidate, fmatch, formula_pattern)) {
                IniFormulaOutputChannel fc;
                fc.name = fmatch[1].str();
                fc.formula_expression = std::string(strip(fmatch[2].str()));
                if (fmatch[3].matched) {
                    auto trail_parts = parse_csv(fmatch[3].str());
                    if (!trail_parts.empty()) {
                        auto u = parse_value_token(trail_parts[0]);
                        if (u) fc.units = *u;
                    }
                    if (trail_parts.size() > 1) {
                        fc.digits = parse_int_token(trail_parts[1]);
                    }
                }
                section.formula_channels.push_back(std::move(fc));
                continue;
            }
        }

        // Scalar / bits entry — same regex as Python
        std::smatch match;
        if (!std::regex_match(raw_line, match, pattern)) continue;

        std::string name = match[1].str();
        std::string entry_kind = match[2].str();
        std::string data_type = match[3].str();
        std::string offset_str = match[4].str();
        std::string shape = match[5].matched ? match[5].str() : std::string();
        std::string remainder = match[6].matched ? match[6].str() : std::string();

        std::vector<std::string> parts;
        if (!remainder.empty()) parts = parse_csv(remainder);

        std::optional<std::string> units = parts.size() > 0 ? parse_value_token(parts[0]) : std::nullopt;
        std::optional<double> scale = parts.size() > 1 ? parse_float_token(parts[1]) : std::nullopt;
        std::optional<double> translate = parts.size() > 2 ? parse_float_token(parts[2]) : std::nullopt;

        auto offset_int_opt = parse_int_literal(offset_str);
        if (!offset_int_opt) continue;
        int offset_int = *offset_int_opt;

        if (entry_kind == "bits") {
            auto [bit_offset, bit_length] = parse_bit_shape(shape);
            IniOutputChannel ch;
            ch.name = name;
            ch.data_type = data_type;
            ch.units = units;
            ch.offset = offset_int;
            ch.scale = scale;
            ch.translate = translate;
            ch.bit_offset = bit_offset;
            ch.bit_length = bit_length;
            // Mirror Python: expand $macroName references via the
            // defines map, then keep every non-empty token verbatim
            // (no extra strip — matches the constants-parser fix).
            auto expanded = expand_options(parts, defines);
            for (auto& part : expanded) {
                if (!part.empty()) ch.options.push_back(std::move(part));
            }
            section.channels.push_back(std::move(ch));
            continue;
        }

        if (entry_kind != "scalar") continue;

        IniOutputChannel ch;
        ch.name = name;
        ch.data_type = data_type;
        ch.units = units;
        ch.offset = offset_int;
        ch.scale = scale;
        ch.translate = translate;
        ch.min_value = parts.size() > 3 ? parse_float_token(parts[3]) : std::nullopt;
        ch.max_value = parts.size() > 4 ? parse_float_token(parts[4]) : std::nullopt;
        ch.digits = parts.size() > 5 ? parse_int_token(parts[5]) : std::nullopt;
        section.channels.push_back(std::move(ch));
    }

    return section;
}

}  // namespace tuner_core
