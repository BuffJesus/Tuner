// SPDX-License-Identifier: MIT
//
// tuner_core::table_rendering — port of the Python
// `TableRenderingService`. Thirty-second sub-slice of the Phase 14
// workspace-services port (Slice 4).
//
// Turns a `table_view::ViewModel` into a renderable grid: each cell
// gets a foreground/background hex color derived from the value's
// position in the table's overall min/max range, plus the y-axis
// label order is reversed when `invert_y_axis` is true (the typical
// table editor presentation, with the lowest load row at the bottom).
//
// Pure logic — Python uses `QColor` for arithmetic and `.name()` for
// the hex string; the C++ port uses a flat `Rgb` struct and emits
// lowercase `#rrggbb` to match Qt's default `QColor::name()` output
// byte-for-byte. No Qt dependency.

#pragma once

#include "tuner_core/table_view.hpp"

#include <string>
#include <vector>

namespace tuner_core::table_rendering {

struct CellRender {
    std::string text;
    std::string background_hex;  // "#rrggbb" lowercase
    std::string foreground_hex;  // "#000000" or "#ffffff"
};

struct RenderModel {
    std::size_t rows = 0;
    std::size_t columns = 0;
    std::vector<std::string> x_labels;
    std::vector<std::string> y_labels;          // already in display order
    std::vector<std::size_t> row_index_map;     // model-row index per display row
    std::vector<std::vector<CellRender>> cells; // row-major in display order
};

// Mirror `TableRenderingService.build_render_model`. The cell text
// gradient runs across the table-wide numeric min/max; non-numeric
// cell text falls through to a white-on-black default.
RenderModel build_render_model(
    const tuner_core::table_view::ViewModel& table_model,
    const std::vector<std::string>& x_labels,
    const std::vector<std::string>& y_labels,
    bool invert_y_axis = true);

}  // namespace tuner_core::table_rendering
