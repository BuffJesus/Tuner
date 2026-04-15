// SPDX-License-Identifier: MIT
//
// tuner_core::EcuDefinitionCompiler — top-level INI ingestion. Mirrors
// what `IniParser.parse()` does on the Python side: take an INI source,
// run it through the slice-3 preprocessor with a caller-supplied
// `active_settings` set, then walk the surviving lines through every
// leaf section parser and aggregate the results into a single
// `NativeEcuDefinition`.
//
// This is the long-promised "EcuDefinition compiler" called out in
// docs/tuning-roadmap.md Phase 14 Slice 2 — the seam where the leaf
// catalogs (constants, output channels, table editor, curve editor,
// menu, gauge configurations, front page, logger definition,
// controller commands) become a single addressable definition object
// that downstream C++ services can consume directly.
//
// Layering note: this header pulls in every leaf parser header by
// design — it's the one place that knows about all of them. Downstream
// code that only needs one section should keep depending on the
// individual leaf header rather than this one.

#pragma once

#include "tuner_core/ini_constants_extensions_parser.hpp"
#include "tuner_core/ini_constants_parser.hpp"
#include "tuner_core/ini_controller_commands_parser.hpp"
#include "tuner_core/ini_curve_editor_parser.hpp"
#include "tuner_core/ini_dialog_parser.hpp"
#include "tuner_core/ini_front_page_parser.hpp"
#include "tuner_core/ini_gauge_configurations_parser.hpp"
#include "tuner_core/ini_logger_definition_parser.hpp"
#include "tuner_core/ini_menu_parser.hpp"
#include "tuner_core/ini_output_channels_parser.hpp"
#include "tuner_core/ini_pc_variables_parser.hpp"
#include "tuner_core/ini_reference_tables_parser.hpp"
#include "tuner_core/ini_setting_context_help_parser.hpp"
#include "tuner_core/ini_setting_groups_parser.hpp"
#include "tuner_core/ini_table_editor_parser.hpp"
#include "tuner_core/ini_tools_parser.hpp"
#include "tuner_core/ini_autotune_sections_parser.hpp"

#include <filesystem>
#include <set>
#include <string>
#include <string_view>

namespace tuner_core {

// Aggregated INI catalog. Mirrors the Python `EcuDefinition` shape at
// the section level — every field below corresponds to one leaf
// parser's output. Downstream Phase 14 services (workspace presenter,
// table generators, runtime decoder, dashboard) consume this object.
struct NativeEcuDefinition {
    IniConstantsSection constants;
    IniOutputChannelsSection output_channels;
    IniTableEditorSection table_editors;
    IniCurveEditorSection curve_editors;
    IniMenuSection menus;
    IniDialogSection dialogs;
    IniGaugeConfigurationsSection gauge_configurations;
    IniFrontPageSection front_page;
    IniLoggerDefinitionSection logger_definitions;
    IniControllerCommandsSection controller_commands;
    IniSettingGroupsSection setting_groups;
    IniSettingContextHelpSection setting_context_help;
    IniConstantsExtensionsSection constants_extensions;
    IniToolsSection tools;
    IniReferenceTablesSection reference_tables;
    IniAutotuneSectionsResult autotune_sections;

    // Byte order declared by the INI `[Constants]` section
    // (`endianness = little|big`). Defaults to "little" when absent or
    // unrecognised — every production Speeduino INI uses little-endian
    // and the value codec hardcodes that assumption (TN-007). The field
    // is exposed so downstream code can *check* the contract explicitly
    // rather than silently producing wrong bytes on a hypothetical
    // big-endian definition.
    std::string byte_order = "little";

    // TN-007: helper so consumers can cleanly branch on byte order
    // without string-matching. Case-insensitive; unknown values treated
    // as little-endian to match Speeduino's established contract.
    bool is_little_endian() const noexcept;
};

// Compile a NativeEcuDefinition from in-memory INI text. Runs the
// slice-3 preprocessor once with `active_settings`, collects defines
// once, then dispatches the surviving line set to each leaf parser
// in turn. The single-preprocessor-pass design matches the Python
// `IniParser.parse()` flow.
NativeEcuDefinition compile_ecu_definition_text(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

// Convenience overload that reads the INI file from disk first.
NativeEcuDefinition compile_ecu_definition_file(
    const std::filesystem::path& path,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
