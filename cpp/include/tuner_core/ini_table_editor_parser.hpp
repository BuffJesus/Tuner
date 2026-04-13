// SPDX-License-Identifier: MIT
//
// tuner_core::IniTableEditorParser — port of `IniParser._parse_table_editors`.
// Parses the `[TableEditor]` section that defines how 3D maps are
// presented to the operator: which `[Constants]` array holds the cell
// data (zBins), which arrays hold the X/Y axes (xBins/yBins), which
// live output channels feed the operating-point overlay (xChannel/
// yChannel), display labels, and 3D-view orientation hints.
//
// `[TableEditor]` is a stateful grammar: `table = ...` lines open a
// new editor, and subsequent key=value lines populate fields on that
// editor until the next `table =` or section change. The parser
// mirrors that flow byte-for-byte against the Python implementation.
//
// Why this slice matters: every consumer of a 3D map (the 2D table
// editor widget, the future 3D surface view G2, the table generators
// in Phase 14 Slice 7, the live operating-point crosshair G3) needs
// to know the table-id → constant-name mapping plus the X/Y channel
// names for the runtime overlay. This is the section that publishes
// that mapping.
//
// Python is the oracle: every behaviour here matches the Python
// implementation byte-for-byte across the existing fixture suite,
// including the production INI.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <array>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// One `[TableEditor]` entry. Mirrors the Python `TableEditorDefinition`
// dataclass field-for-field.
struct IniTableEditor {
    std::string table_id;        // Operator-facing identifier (e.g. "veTblTbl")
    std::string map_id;          // Map identifier referenced by [Menu] entries
    std::string title;           // Display title shown above the table
    std::optional<int> page;     // Optional page number override
    // Axis bin references — these are constant names declared in [Constants]
    std::optional<std::string> x_bins;
    std::optional<std::string> y_bins;
    std::optional<std::string> z_bins;       // The actual table data array
    // Live output-channel names that drive the operating-point overlay
    // and the optional follow-mode crosshair (G3).
    std::optional<std::string> x_channel;
    std::optional<std::string> y_channel;
    // Display labels and help
    std::optional<std::string> x_label;
    std::optional<std::string> y_label;
    std::optional<std::string> topic_help;
    // 3D-view hints consumed by the future TableSurface3DView (G2)
    std::optional<double> grid_height;
    std::optional<std::array<double, 3>> grid_orient;
    // Operator-facing direction labels for value-direction tuning
    std::optional<std::string> up_label;
    std::optional<std::string> down_label;
};

struct IniTableEditorSection {
    std::vector<IniTableEditor> editors;
};

// Parse `[TableEditor]` from pre-preprocessed INI text. The optional
// `defines` map is currently unused (TableEditor doesn't have
// $macroName-style options) but the parameter is present so the
// signature is consistent with the other section parsers.
IniTableEditorSection parse_table_editor_section(
    std::string_view text,
    const IniDefines& defines = {});

IniTableEditorSection parse_table_editor_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse, mirroring
// the Python `IniParser.parse()` flow.
IniTableEditorSection parse_table_editor_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
