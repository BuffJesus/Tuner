// SPDX-License-Identifier: MIT
//
// tuner_core::table_view — port of `TableViewService.build_table_model`
// and `_resolve_shape`. Fourteenth sub-slice of the Phase 14
// workspace-services port (Slice 4).
//
// Turns a flat list of table values into a 2D string grid the table
// editor widget can render. Shape resolution mirrors the Python
// service exactly:
//   1. If the tune value carries explicit `rows` and `cols`, use them.
//   2. Otherwise, parse a `"NxM"` shape hint string.
//   3. Otherwise, fall back to `(value_count, 1)` (single-column shape).
//
// The string conversion of each cell goes through
// `tune_value_preview::format_scalar_python_repr` so the rendered
// table matches Python's `str(float)` byte-for-byte.

#pragma once

#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::table_view {

struct ViewModel {
    std::size_t rows = 0;
    std::size_t columns = 0;
    // Row-major: `cells[row][column]`. Rows are padded with empty
    // strings if the value list is shorter than `rows * columns`.
    std::vector<std::vector<std::string>> cells;
};

struct ShapeHints {
    // -1 means "unset" — same semantics as Python's `tune_value.rows
    // is None`. Both must be > 0 for them to take precedence.
    int rows = -1;
    int cols = -1;
    // Optional `"NxM"` text fallback when `rows` / `cols` aren't set.
    std::optional<std::string> shape_text;
};

// Mirror `_resolve_shape`. The Python signature takes a `tune_value`
// and an optional shape string; we split that into the explicit
// `rows`/`cols` integers + a `value_count` + an optional shape text.
std::pair<std::size_t, std::size_t> resolve_shape(
    std::size_t value_count,
    const ShapeHints& hints);

// Mirror `build_table_model`. Returns nullopt when the input list
// would not produce a useful grid (mirrors Python's `if not isinstance(...)`
// guard, which we satisfy here by always being given a list — empty
// lists still produce a `(0, 1)` model with no rows).
std::optional<ViewModel> build_table_model(
    std::span<const double> values,
    const ShapeHints& hints);

}  // namespace tuner_core::table_view
