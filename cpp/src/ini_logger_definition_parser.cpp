// SPDX-License-Identifier: MIT
//
// tuner_core::IniLoggerDefinitionParser implementation. Direct port of
// `IniParser._parse_logger_definitions`.

#include "tuner_core/ini_logger_definition_parser.hpp"
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

// Mirrors Python's `value.split(';',1)[0].strip()` — drops the first
// `;` and any trailing comment.
std::string strip_inline_comment(std::string_view value) {
    auto semi = value.find(';');
    if (semi == std::string_view::npos) return strip(value);
    return strip(value.substr(0, semi));
}

// Strip a single pair of leading/trailing `"` chars (not all of them).
// Mirrors Python's `s.strip().strip('"')` for single-quoted-pair tokens
// — but Python's `.strip('"')` strips ALL leading/trailing quotes; we
// match that here.
std::string strip_outer_quotes(std::string_view value) {
    auto stripped = strip(value);
    std::size_t b = 0;
    std::size_t e = stripped.size();
    while (b < e && stripped[b] == '"') ++b;
    while (e > b && stripped[e - 1] == '"') --e;
    return std::string(std::string_view(stripped).substr(b, e - b));
}

// Decode a legacy command string to raw bytes. Handles `\xNN` hex
// escapes and rewrites `$tsCanId` (with or without leading `\`) to
// `\x00\x00`. Direct port of the Python helper.
std::vector<std::uint8_t> decode_command(std::string_view raw) {
    std::string s = strip_outer_quotes(raw);
    // Replace `\$tsCanId` and `$tsCanId` with the literal hex escape
    // sequence `\x00\x00`, then let the unified hex-escape pass below
    // expand them. Process the longer form first so we don't double-
    // substitute the trailing `$tsCanId`.
    auto replace_all = [](std::string& haystack,
                          std::string_view needle,
                          std::string_view repl) {
        std::size_t pos = 0;
        while ((pos = haystack.find(needle, pos)) != std::string::npos) {
            haystack.replace(pos, needle.size(), repl);
            pos += repl.size();
        }
    };
    replace_all(s, "\\$tsCanId", "\\x00\\x00");
    replace_all(s, "$tsCanId", "\\x00\\x00");

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
            // Malformed escape: emit literal backslash and advance one.
            result.push_back(static_cast<std::uint8_t>('\\'));
            i += 1;
            continue;
        }
        result.push_back(static_cast<std::uint8_t>(s[i]));
        ++i;
    }
    return result;
}

// Mirrors `int(float(token.split(';',1)[0].strip()))` from the Python
// fallback paths — returns `fallback` if anything goes wrong.
int parse_int_via_float_or(std::string_view token, int fallback) {
    auto stripped = strip_inline_comment(token);
    if (stripped.empty()) return fallback;
    try {
        std::size_t consumed = 0;
        double v = std::stod(stripped, &consumed);
        if (consumed == 0) return fallback;
        return static_cast<int>(v);
    } catch (...) {
        return fallback;
    }
}

}  // namespace

IniLoggerDefinitionSection parse_logger_definition_section(
    std::string_view text,
    const IniDefines& defines) {
    return parse_logger_definition_lines(split_lines(text), defines);
}

IniLoggerDefinitionSection parse_logger_definition_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    auto preprocessed_lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(preprocessed_lines);
    return parse_logger_definition_lines(preprocessed_lines, defines);
}

IniLoggerDefinitionSection parse_logger_definition_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniLoggerDefinitionSection section;
    bool in_section = false;

    // Active block state.
    bool have_current = false;
    std::string current_name;
    std::string current_display;
    std::string current_kind = "tooth";
    std::map<std::string, std::string> props;
    std::vector<IniLoggerRecordField> fields;

    auto reset_block = [&]() {
        have_current = false;
        current_name.clear();
        current_display.clear();
        current_kind = "tooth";
        props.clear();
        fields.clear();
    };

    auto flush = [&]() {
        if (!have_current) return;
        IniLoggerDefinition logger;
        logger.name = current_name;
        logger.display_name = current_display;
        logger.kind = current_kind;
        logger.start_command = strip_outer_quotes(props["startCommand"]);
        logger.stop_command = strip_outer_quotes(props["stopCommand"]);
        logger.data_read_command = decode_command(props["dataReadCommand"]);
        logger.data_read_timeout_ms = parse_int_via_float_or(
            props["dataReadTimeout"], 5000);
        // continuousRead = "true" (case-insensitive)
        std::string cont = strip_inline_comment(props["continuousRead"]);
        logger.continuous_read = lowercase(cont) == "true";

        // recordDef = headerLen, footerLen, recordLen
        const std::string& raw_rec = props["recordDef"];
        // Split on commas (no quote handling needed — these are bare numbers).
        std::vector<std::string> rec_parts;
        {
            std::string current;
            for (char c : raw_rec) {
                if (c == ',') {
                    rec_parts.push_back(strip_inline_comment(current));
                    current.clear();
                } else {
                    current.push_back(c);
                }
            }
            rec_parts.push_back(strip_inline_comment(current));
        }
        if (rec_parts.size() >= 3) {
            try {
                logger.record_header_len = std::stoi(rec_parts[0]);
                logger.record_footer_len = std::stoi(rec_parts[1]);
                logger.record_len = std::stoi(rec_parts[2]);
            } catch (...) {
                // leave at defaults
            }
        }

        int data_length_val = parse_int_via_float_or(props["dataLength"], 0);
        if (logger.record_len > 0 && data_length_val > 0) {
            if (logger.kind == "tooth") {
                logger.record_count = data_length_val / logger.record_len;
            } else {
                logger.record_count = data_length_val;
            }
        }

        logger.record_fields = std::move(fields);
        section.loggers.push_back(std::move(logger));
        reset_block();
    };

    for (const auto& raw_line : lines) {
        auto stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';') continue;
        if (stripped[0] == '[') {
            if (in_section) flush();
            in_section = lowercase(stripped).rfind("[loggerdefinition", 0) == 0;
            continue;
        }
        if (!in_section) continue;
        auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        auto key = strip(std::string_view(stripped).substr(0, eq));
        auto value = strip_inline_comment(
            std::string_view(stripped).substr(eq + 1));

        if (key == "loggerDef") {
            // Flush any in-flight block before starting a new one.
            flush();
            auto parts = parse_csv(value);
            if (parts.size() < 3) continue;
            have_current = true;
            current_name = strip(parts[0]);
            current_display = parts[1];  // parse_csv already strips quotes
            current_kind = lowercase(strip(parts[2]));
            continue;
        }
        if (key == "recordField") {
            auto parts = parse_csv(value);
            if (parts.size() < 6) continue;
            try {
                IniLoggerRecordField field;
                field.name = strip(parts[0]);
                field.header = parts[1];  // parse_csv strips quotes
                field.start_bit = std::stoi(strip(parts[2]));
                field.bit_count = std::stoi(strip(parts[3]));
                field.scale = std::stod(strip(parts[4]));
                field.units = parts[5];
                fields.push_back(std::move(field));
            } catch (...) {
                // mismatch — skip the field
            }
            continue;
        }
        if (key == "calcField") {
            // derived/display field — skip
            continue;
        }
        // Generic property: store the raw value.
        props[std::string(key)] = std::string(value);
    }

    // Flush the final block.
    flush();
    return section;
}

}  // namespace tuner_core
