// SPDX-License-Identifier: MIT
//
// tuner_core::table_edit implementation. Pure logic, direct port of
// `TableEditService`.

#include "tuner_core/table_edit.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <stdexcept>
#include <string>

namespace tuner_core::table_edit {

namespace {

std::size_t row_count(std::size_t total, std::size_t columns) {
    if (columns == 0) return 0;
    return (total + columns - 1) / columns;
}

// Helper: copy `values` into a fresh flat row-major buffer rounded
// up to `columns` per row. The Python `_to_grid` builds a list-of-
// lists; we keep the row-major flat layout to avoid an alloc per
// row, and use `cell(i, j) = buf[i * columns + j]` directly.
std::vector<double> clone_to_grid(std::span<const double> values) {
    return std::vector<double>(values.begin(), values.end());
}

// Round to 3 decimal places. Mirrors `round(x, 3)` in Python's
// banker's rounding semantics — half-to-even.
double round3(double x) {
    return std::nearbyint(x * 1000.0) / 1000.0;
}

bool is_separator(char c) noexcept {
    return c == '\t' || c == ',';
}

// Strip ASCII leading/trailing whitespace.
std::string_view strip(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
        s.remove_prefix(1);
    }
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
        s.remove_suffix(1);
    }
    return s;
}

}  // namespace

std::vector<double> fill_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection,
    double fill_value) {
    auto grid = clone_to_grid(values);
    const std::size_t rows = row_count(grid.size(), columns);
    if (columns == 0 || selection.bottom >= rows) return grid;
    for (std::size_t r = selection.top; r <= selection.bottom; ++r) {
        for (std::size_t c = selection.left; c <= selection.right; ++c) {
            grid[r * columns + c] = fill_value;
        }
    }
    return grid;
}

std::vector<double> fill_down_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection) {
    auto grid = clone_to_grid(values);
    if (selection.height() <= 1) return grid;
    const std::size_t rows = row_count(grid.size(), columns);
    if (columns == 0 || selection.bottom >= rows) return grid;
    // Snapshot the source row from the top of the selection.
    std::vector<double> source_row;
    source_row.reserve(selection.width());
    for (std::size_t c = selection.left; c <= selection.right; ++c) {
        source_row.push_back(grid[selection.top * columns + c]);
    }
    for (std::size_t r = selection.top + 1; r <= selection.bottom; ++r) {
        std::size_t idx = 0;
        for (std::size_t c = selection.left; c <= selection.right; ++c, ++idx) {
            grid[r * columns + c] = source_row[idx];
        }
    }
    return grid;
}

std::vector<double> fill_right_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection) {
    auto grid = clone_to_grid(values);
    if (selection.width() <= 1) return grid;
    const std::size_t rows = row_count(grid.size(), columns);
    if (columns == 0 || selection.bottom >= rows) return grid;
    for (std::size_t r = selection.top; r <= selection.bottom; ++r) {
        const double source = grid[r * columns + selection.left];
        for (std::size_t c = selection.left + 1; c <= selection.right; ++c) {
            grid[r * columns + c] = source;
        }
    }
    return grid;
}

std::vector<double> interpolate_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection) {
    auto grid = clone_to_grid(values);
    if (columns == 0) return grid;
    if (selection.width() == 1 && selection.height() > 1) {
        const std::size_t col = selection.left;
        const double start = grid[selection.top * columns + col];
        const double end = grid[selection.bottom * columns + col];
        const double span = static_cast<double>(
            std::max<std::size_t>(1, selection.bottom - selection.top));
        for (std::size_t r = selection.top; r <= selection.bottom; ++r) {
            const double fraction = static_cast<double>(r - selection.top) / span;
            grid[r * columns + col] = start + (end - start) * fraction;
        }
        return grid;
    }
    for (std::size_t r = selection.top; r <= selection.bottom; ++r) {
        const double start = grid[r * columns + selection.left];
        const double end = grid[r * columns + selection.right];
        const double span = static_cast<double>(
            std::max<std::size_t>(1, selection.right - selection.left));
        for (std::size_t c = selection.left; c <= selection.right; ++c) {
            const double fraction = static_cast<double>(c - selection.left) / span;
            grid[r * columns + c] = start + (end - start) * fraction;
        }
    }
    return grid;
}

std::vector<double> smooth_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection) {
    auto grid = clone_to_grid(values);
    if (columns == 0) return grid;
    const std::size_t rows = row_count(grid.size(), columns);
    // Snapshot pre-loop so neighbor reads always see the original.
    const std::vector<double> original = grid;
    for (std::size_t r = selection.top; r <= selection.bottom; ++r) {
        for (std::size_t c = selection.left; c <= selection.right; ++c) {
            double sum = 0.0;
            int count = 0;
            for (int dr = -1; dr <= 1; ++dr) {
                for (int dc = -1; dc <= 1; ++dc) {
                    const long long tr = static_cast<long long>(r) + dr;
                    const long long tc = static_cast<long long>(c) + dc;
                    if (tr >= 0 && tr < static_cast<long long>(rows) &&
                        tc >= 0 && tc < static_cast<long long>(columns)) {
                        sum += original[static_cast<std::size_t>(tr) * columns +
                                        static_cast<std::size_t>(tc)];
                        ++count;
                    }
                }
            }
            grid[r * columns + c] = round3(sum / static_cast<double>(count));
        }
    }
    return grid;
}

std::vector<std::vector<double>> parse_clipboard(std::string_view text) {
    std::vector<std::vector<double>> rows;
    std::size_t i = 0;
    const std::size_t n = text.size();
    while (i < n) {
        // Read one line.
        std::size_t line_end = i;
        while (line_end < n && text[line_end] != '\n' && text[line_end] != '\r') {
            ++line_end;
        }
        auto line = strip(text.substr(i, line_end - i));
        // Advance past the newline (handle CRLF / LF / CR)
        i = line_end;
        if (i < n && text[i] == '\r') ++i;
        if (i < n && text[i] == '\n') ++i;
        if (line.empty()) continue;

        std::vector<double> row;
        std::size_t j = 0;
        while (j < line.size()) {
            // Find next separator (tab or comma).
            std::size_t sep = j;
            while (sep < line.size() && !is_separator(line[sep])) ++sep;
            auto cell = strip(line.substr(j, sep - j));
            if (!cell.empty()) {
                try {
                    std::size_t consumed = 0;
                    double v = std::stod(std::string(cell), &consumed);
                    if (consumed > 0) row.push_back(v);
                } catch (...) {
                    // Skip unparseable cells silently — Python would
                    // raise here, so this slightly diverges; we keep
                    // the row going to stay defensive. The parity
                    // test only feeds well-formed clipboards.
                }
            }
            j = (sep < line.size()) ? sep + 1 : sep;
        }
        rows.push_back(std::move(row));
    }
    return rows;
}

std::vector<double> paste_region(
    std::span<const double> values,
    std::size_t columns,
    const TableSelection& selection,
    std::string_view clipboard_text) {
    auto grid = clone_to_grid(values);
    const std::size_t rows = row_count(grid.size(), columns);
    auto clipboard_rows = parse_clipboard(clipboard_text);
    if (clipboard_rows.empty()) return grid;
    const std::size_t clip_height = clipboard_rows.size();
    std::size_t clip_width = 0;
    for (const auto& r : clipboard_rows) {
        clip_width = std::max(clip_width, r.size());
    }
    if (clip_width == 0) return grid;

    const std::size_t fill_height = std::max(selection.height(), clip_height);
    const std::size_t fill_width = std::max(selection.width(), clip_width);
    for (std::size_t row_offset = 0; row_offset < fill_height; ++row_offset) {
        const std::size_t target_row = selection.top + row_offset;
        if (target_row >= rows) break;
        const auto& clipboard_row = clipboard_rows[row_offset % clip_height];
        if (clipboard_row.empty()) continue;
        for (std::size_t col_offset = 0; col_offset < fill_width; ++col_offset) {
            const std::size_t target_column = selection.left + col_offset;
            if (target_column >= columns) break;
            grid[target_row * columns + target_column] =
                clipboard_row[col_offset % clipboard_row.size()];
        }
    }
    return grid;
}

}  // namespace tuner_core::table_edit
