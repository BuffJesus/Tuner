// SPDX-License-Identifier: MIT
//
// tuner_core::table_edit — pure-logic port of the numeric transforms
// in `tuner.services.table_edit_service.TableEditService`. Third
// sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Tables are passed as flat row-major `vector<double>` plus a
// `columns` count. A `TableSelection` is the inclusive
// (top, left, bottom, right) range the operator dragged in the
// editor. Every transform returns a *new* flat vector — no in-place
// mutation, mirroring the Python service so undo/redo capture stays
// straightforward.
//
// `copy_region` is intentionally left out of this slice because its
// Python implementation calls `str(value)`, whose float-formatting
// rules are non-trivial to mirror byte-for-byte in C++. Numeric
// transforms (which are what the workspace presenter actually
// dispatches) are fully covered.

#pragma once

#include <cstddef>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::table_edit {

struct TableSelection {
    std::size_t top = 0;
    std::size_t left = 0;
    std::size_t bottom = 0;
    std::size_t right = 0;

    constexpr std::size_t width() const noexcept { return right - left + 1; }
    constexpr std::size_t height() const noexcept { return bottom - top + 1; }
};

// Replace every cell in `selection` with `fill_value`.
std::vector<double> fill_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection,
    double fill_value);

// Copy the top row of `selection` down through every other row in
// the selection. Returns the input unchanged when the selection is
// only one row tall.
std::vector<double> fill_down_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection);

// Copy the left column of `selection` rightward through every other
// column in the selection. Returns the input unchanged when the
// selection is only one column wide.
std::vector<double> fill_right_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection);

// Linear interpolation between the endpoints of the selection. If
// the selection is exactly one column wide and more than one row
// tall, interpolates vertically (top → bottom). Otherwise
// interpolates horizontally (left → right) for every row in the
// selection.
std::vector<double> interpolate_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection);

// Box-blur every cell in the selection by averaging the cell with
// its 8 (or fewer, at the table edge) neighbors. Reads from a
// pre-loop snapshot so neighbor reads see the *original* values, not
// the partially-smoothed running result. Each cell is rounded to 3
// decimal places to match the Python implementation.
std::vector<double> smooth_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection);

// Tile a clipboard string across the selection. Clipboard rows are
// tab-or-comma separated; the parser strips empty cells and skips
// blank lines. The clipboard is tiled to fill the larger of the
// selection size and the clipboard size, but the paste stops at the
// table edge so the original table size is preserved.
std::vector<double> paste_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection,
    std::string_view clipboard_text);

// Exposed for tests; mirrors `_parse_clipboard`. Each line is split
// on tab/comma, blank cells are dropped, blank lines are skipped.
std::vector<std::vector<double>> parse_clipboard(std::string_view text);

}  // namespace tuner_core::table_edit
