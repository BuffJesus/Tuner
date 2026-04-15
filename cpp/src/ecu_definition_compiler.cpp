// SPDX-License-Identifier: MIT
//
// tuner_core::EcuDefinitionCompiler implementation. Single-pass
// preprocess + dispatch into every leaf parser. Mirrors the Python
// `IniParser.parse()` orchestration flow.

#include "tuner_core/ecu_definition_compiler.hpp"

#include "tuner_core/ini_defines_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace tuner_core {

namespace {

// Scan preprocessed lines for `endianness = <value>` inside the
// `[Constants]` section. Returns "little" (default) when absent or
// unrecognised. TN-007.
std::string extract_byte_order(const std::vector<std::string>& lines) {
    bool in_constants = false;
    for (const auto& raw : lines) {
        std::string_view line{raw};
        while (!line.empty() && std::isspace(static_cast<unsigned char>(line.front())))
            line.remove_prefix(1);
        if (line.empty() || line[0] == ';') continue;
        if (line.front() == '[') {
            auto end = line.find(']');
            if (end == std::string_view::npos) continue;
            auto section = line.substr(1, end - 1);
            std::string lower(section);
            for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            in_constants = (lower == "constants");
            continue;
        }
        if (!in_constants) continue;
        auto eq = line.find('=');
        if (eq == std::string_view::npos) continue;
        auto key = line.substr(0, eq);
        while (!key.empty() && std::isspace(static_cast<unsigned char>(key.back())))
            key.remove_suffix(1);
        std::string key_lower(key);
        for (auto& c : key_lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (key_lower != "endianness") continue;
        auto val = line.substr(eq + 1);
        while (!val.empty() && std::isspace(static_cast<unsigned char>(val.front())))
            val.remove_prefix(1);
        // Strip trailing whitespace / comment.
        auto semi = val.find(';');
        if (semi != std::string_view::npos) val = val.substr(0, semi);
        while (!val.empty() && std::isspace(static_cast<unsigned char>(val.back())))
            val.remove_suffix(1);
        std::string out(val);
        for (auto& c : out) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (out == "little" || out == "big") return out;
        return "little";  // unrecognised -> default
    }
    return "little";
}

}  // namespace

bool NativeEcuDefinition::is_little_endian() const noexcept {
    std::string lower = byte_order;
    for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return lower != "big";  // unknown values fall back to little
}

NativeEcuDefinition compile_ecu_definition_text(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    // One preprocessor pass: every leaf parser sees the same surviving
    // line set, identical to the Python `IniParser.parse()` flow.
    auto lines = preprocess_ini_text(text, active_settings);
    auto defines = collect_defines_lines(lines);

    NativeEcuDefinition definition;
    definition.constants = parse_constants_lines(lines, defines);
    // Merge PC variables into the constants catalog so downstream
    // services see a unified list (matches Python
    // `definition.scalars` / `definition.tables` behaviour where both
    // `_parse_constant_definitions` and `_parse_pc_variables` append
    // to the same domain list).
    {
        auto pc_vars = parse_pc_variables_lines(lines, defines);
        definition.constants.scalars.insert(
            definition.constants.scalars.end(),
            std::make_move_iterator(pc_vars.scalars.begin()),
            std::make_move_iterator(pc_vars.scalars.end()));
        definition.constants.arrays.insert(
            definition.constants.arrays.end(),
            std::make_move_iterator(pc_vars.arrays.begin()),
            std::make_move_iterator(pc_vars.arrays.end()));
    }
    definition.output_channels = parse_output_channels_lines(lines, defines);
    definition.table_editors = parse_table_editor_lines(lines, defines);
    definition.curve_editors = parse_curve_editor_lines(lines, defines);
    definition.menus = parse_menu_lines(lines, defines);
    definition.dialogs = parse_dialogs(lines);
    definition.gauge_configurations =
        parse_gauge_configurations_lines(lines, defines);
    definition.front_page = parse_front_page_lines(lines, defines);
    definition.logger_definitions =
        parse_logger_definition_lines(lines, defines);
    definition.controller_commands =
        parse_controller_commands_lines(lines, defines);
    definition.setting_groups =
        parse_setting_groups_lines(lines, defines);
    definition.setting_context_help =
        parse_setting_context_help_lines(lines, defines);
    definition.constants_extensions =
        parse_constants_extensions_lines(lines, defines);
    definition.tools =
        parse_tools_lines(lines, defines);
    definition.reference_tables =
        parse_reference_tables_lines(lines, defines);
    definition.autotune_sections =
        parse_autotune_sections_lines(lines, defines);
    definition.byte_order = extract_byte_order(lines);
    return definition;
}

NativeEcuDefinition compile_ecu_definition_file(
    const std::filesystem::path& path,
    const std::set<std::string>& active_settings) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw std::runtime_error(
            "compile_ecu_definition_file: cannot open " + path.string());
    }
    std::ostringstream buffer;
    buffer << stream.rdbuf();
    return compile_ecu_definition_text(buffer.str(), active_settings);
}

}  // namespace tuner_core
