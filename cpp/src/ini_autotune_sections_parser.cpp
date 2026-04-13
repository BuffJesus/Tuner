// SPDX-License-Identifier: MIT
//
// tuner_core::ini_autotune_sections_parser implementation. Port of
// `IniParser._parse_autotune_sections` with variant-based filter
// gates and validated operator enum.

#include "tuner_core/ini_autotune_sections_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "parse_helpers.hpp"

#include <cctype>
#include <cstdlib>
#include <utility>

namespace tuner_core {

// ---------------------------------------------------------------
// GateOperator helpers
// ---------------------------------------------------------------

const char* gate_operator_to_string(GateOperator op) {
    switch (op) {
        case GateOperator::Lt:      return "<";
        case GateOperator::Gt:      return ">";
        case GateOperator::Le:      return "<=";
        case GateOperator::Ge:      return ">=";
        case GateOperator::Eq:      return "==";
        case GateOperator::Ne:      return "!=";
        case GateOperator::BitAnd:  return "&";
        case GateOperator::Unknown: return "?";
    }
    return "?";
}

GateOperator parse_gate_operator(std::string_view text) {
    // Strip whitespace.
    auto begin = text.begin();
    auto end = text.end();
    while (begin != end && std::isspace(static_cast<unsigned char>(*begin))) ++begin;
    while (end != begin && std::isspace(static_cast<unsigned char>(*(end - 1)))) --end;
    std::string_view trimmed(begin, static_cast<std::size_t>(end - begin));

    if (trimmed == "<")  return GateOperator::Lt;
    if (trimmed == ">")  return GateOperator::Gt;
    if (trimmed == "<=") return GateOperator::Le;
    if (trimmed == ">=") return GateOperator::Ge;
    if (trimmed == "==" || trimmed == "=") return GateOperator::Eq;
    if (trimmed == "!=") return GateOperator::Ne;
    if (trimmed == "&")  return GateOperator::BitAnd;
    return GateOperator::Unknown;
}

// ---------------------------------------------------------------
// Variant accessor helpers
// ---------------------------------------------------------------

const std::string& gate_name(const FilterGate& gate) {
    return std::visit([](const auto& g) -> const std::string& { return g.name; }, gate);
}

bool gate_default_enabled(const FilterGate& gate) {
    return std::visit([](const auto& g) -> bool {
        if constexpr (std::is_same_v<std::decay_t<decltype(g)>, StandardGate>) {
            return true;  // standard gates always enabled
        } else {
            return g.default_enabled;
        }
    }, gate);
}

// ---------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------

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

// Mirror Python `_parse_float_token`: returns nullopt for empty,
// brace-expression, or unparseable tokens.
std::optional<double> parse_float_token(std::string_view token) {
    std::string s = strip(token);
    if (s.empty() || s[0] == '{') return std::nullopt;
    char* end = nullptr;
    double val = std::strtod(s.c_str(), &end);
    if (end == s.c_str()) return std::nullopt;  // no chars consumed
    return val;
}

// Recognised section names (lowercase).
bool is_autotune_section(const std::string& lower) {
    return lower == "[veanalyze]" || lower == "[wueanalyze]";
}

// The key that carries the map parts depends on the section name.
// VeAnalyze uses `veAnalyzeMap`, WueAnalyze uses `wueAnalyzeMap`.
// We accept both keys in either section to be lenient.
bool is_map_key(const std::string& key) {
    return key == "veAnalyzeMap" || key == "wueAnalyzeMap";
}

FilterGate parse_filter_line(const std::vector<std::string>& parts) {
    if (parts.empty()) return StandardGate{""};

    const std::string& name = parts[0];

    if (parts.size() >= 6) {
        // Parameterised gate:
        //   name, "label", channel, operator, threshold, default_enabled
        ParameterisedGate gate;
        gate.name = name;
        gate.label = parts[1].empty() ? name : parts[1];
        gate.channel = parts[2];
        gate.op = parse_gate_operator(parts[3]);
        auto thresh = parse_float_token(parts[4]);
        gate.threshold = thresh.value_or(0.0);
        // Python: `parts[5].strip().lower() != "false"`
        std::string enabled_str = lowercase(strip(parts[5]));
        gate.default_enabled = (enabled_str != "false");
        return gate;
    }

    // Standard named gate (1 part, or partial 2-5 parts treated as
    // name-only to match Python fallthrough).
    return StandardGate{name};
}

}  // namespace

// ---------------------------------------------------------------
// Parser entry points
// ---------------------------------------------------------------

IniAutotuneSectionsResult parse_autotune_sections(
    std::string_view text,
    const IniDefines& defines) {
    return parse_autotune_sections_lines(split_lines(text), defines);
}

IniAutotuneSectionsResult parse_autotune_sections_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    const auto lines = split_lines(text);
    const auto preprocessed = preprocess_ini_lines(lines, active_settings);
    const auto defines = collect_defines_lines(preprocessed);
    return parse_autotune_sections_lines(preprocessed, defines);
}

IniAutotuneSectionsResult parse_autotune_sections_lines(
    const std::vector<std::string>& lines,
    const IniDefines& /*defines*/) {
    IniAutotuneSectionsResult result;

    // State for the current section being accumulated.
    bool in_section = false;
    std::string current_section_name;
    std::vector<std::string> map_parts;
    std::vector<std::string> lambda_target_tables;
    std::vector<FilterGate> filter_gates;

    auto flush = [&]() {
        if (!in_section) return;
        AutotuneMapDefinition def;
        def.section_name = std::move(current_section_name);
        def.map_parts = std::move(map_parts);
        def.lambda_target_tables = std::move(lambda_target_tables);
        def.filter_gates = std::move(filter_gates);
        result.maps.push_back(std::move(def));
        // Reset accumulators.
        current_section_name.clear();
        map_parts.clear();
        lambda_target_tables.clear();
        filter_gates.clear();
        in_section = false;
    };

    for (const auto& raw_line : lines) {
        const std::string stripped = strip(raw_line);
        if (stripped.empty()) continue;
        if (stripped[0] == ';' || stripped[0] == '#') continue;

        if (stripped[0] == '[') {
            // Flush previous section if any.
            flush();
            const std::string lower = lowercase(stripped);
            if (is_autotune_section(lower)) {
                in_section = true;
                // Preserve original case, strip brackets.
                current_section_name = stripped.substr(1, stripped.size() - 2);
            }
            continue;
        }

        if (!in_section) continue;

        const auto eq = stripped.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = strip(stripped.substr(0, eq));
        const std::string value = strip(stripped.substr(eq + 1));

        if (is_map_key(key)) {
            map_parts.clear();
            auto parts = parse_csv(value);
            for (auto& p : parts) {
                p = strip(p);
                if (!p.empty()) map_parts.push_back(std::move(p));
            }
        } else if (key == "lambdaTargetTables") {
            lambda_target_tables.clear();
            auto parts = parse_csv(value);
            for (auto& p : parts) {
                p = strip(p);
                if (!p.empty()) lambda_target_tables.push_back(std::move(p));
            }
        } else if (key == "filter") {
            auto parts = parse_csv(value);
            if (!parts.empty()) {
                filter_gates.push_back(parse_filter_line(parts));
            }
        }
    }

    // Flush last section.
    flush();

    return result;
}

}  // namespace tuner_core
