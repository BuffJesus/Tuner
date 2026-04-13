// SPDX-License-Identifier: MIT
//
// tuner_core::IniCurveEditorParser — port of `IniParser._parse_curve_editors`.
// Parses the `[CurveEditor]` section that defines 1D correction curves
// (37 of them in the production INI): warm-up enrichment vs CLT,
// cranking enrichment vs CLT, AFR target vs RPM, idle PID gain
// schedules, etc.
//
// `[CurveEditor]` is a stateful grammar like `[TableEditor]`:
// `curve = name, "Title"` opens a new curve, and subsequent
// key=value lines populate fields on the active curve until the
// next `curve =` line or section change. Multi-line curves
// (e.g. WUE Analyze "current vs recommended") use multiple `yBins`
// lines, and `lineLabel` lines that may appear after all the yBins
// are matched up positionally on flush.
//
// Why this slice matters:
//   - The C++ curve editor widget (Phase 14 Slice 8) needs the
//     name → x_bins_param / y_bins_list mapping to know which
//     constant arrays back the editable axes
//   - The runtime overlay (G3 cursor for curves) reads `x_channel`
//   - The C++ generators (Phase 14 Slice 7) for warm-up enrichment,
//     cranking, ASE etc. produce values into the y_bins_list arrays
//
// Python is the oracle: every behaviour here matches the Python
// implementation byte-for-byte across the existing fixture suite,
// including the production INI's 37 curves.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <array>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// One y-axis (editable) bin reference. Multi-line curves have
// multiple of these — e.g. a WUE-style "current vs recommended"
// curve has two CurveYBins entries with separate labels.
struct CurveYBins {
    std::string param;                  // [Constants] array name (the editable values)
    std::optional<std::string> label;   // optional line label for multi-line curves
};

// Display-range hint for one axis of a curve. Used by the editor
// widget to scale the plot, not for storage.
struct CurveAxisRange {
    double min = 0.0;
    double max = 0.0;
    int steps = 0;
};

// One `[CurveEditor]` entry. Mirrors the Python `CurveDefinition`
// dataclass field-for-field.
struct IniCurveEditor {
    std::string name;                       // operator-facing identifier
    std::string title;                      // display title
    std::string x_bins_param;               // parameter name for x-axis bin values
    std::optional<std::string> x_channel;   // live output channel for runtime cursor
    std::vector<CurveYBins> y_bins_list;    // editable y-axis arrays (one per line)
    std::string x_label;
    std::string y_label;
    std::optional<CurveAxisRange> x_axis;   // display range hint for x axis
    std::optional<CurveAxisRange> y_axis;   // display range hint for y axis
    std::optional<std::string> topic_help;
    std::optional<std::string> gauge;       // named gauge for live cursor display
    std::optional<std::array<int, 2>> size; // (width, height) hint for the editor
};

struct IniCurveEditorSection {
    std::vector<IniCurveEditor> curves;
};

// Parse `[CurveEditor]` from pre-preprocessed INI text. The optional
// `defines` map is currently unused (`[CurveEditor]` doesn't have
// `$macroName` option lists) but the parameter is present so the
// signature is consistent with the other section parsers.
IniCurveEditorSection parse_curve_editor_section(
    std::string_view text,
    const IniDefines& defines = {});

IniCurveEditorSection parse_curve_editor_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse, mirroring
// the Python `IniParser.parse()` flow.
IniCurveEditorSection parse_curve_editor_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
