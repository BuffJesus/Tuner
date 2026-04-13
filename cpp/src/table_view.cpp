// SPDX-License-Identifier: MIT
//
// tuner_core::table_view implementation. Pure logic.

#include "tuner_core/table_view.hpp"

#include "tuner_core/tune_value_preview.hpp"

#include <algorithm>
#include <cctype>
#include <stdexcept>
#include <string>

namespace tuner_core::table_view {

namespace {

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

}  // namespace

std::pair<std::size_t, std::size_t> resolve_shape(
    std::size_t value_count,
    const ShapeHints& hints) {
    if (hints.rows > 0 && hints.cols > 0) {
        return {static_cast<std::size_t>(hints.rows),
                static_cast<std::size_t>(hints.cols)};
    }
    if (hints.shape_text.has_value()) {
        // Mirror Python: the `"x" in shape` guard is case-sensitive
        // (only lowercase 'x' counts), but the actual split lowercases
        // the input first. So `"4X4"` fails the guard and falls through
        // to the default — quirk preserved here.
        const auto& raw = *hints.shape_text;
        if (raw.find('x') != std::string::npos) {
            auto lower = lowercase(raw);
            auto x_pos = lower.find('x');
            try {
                int rows = std::stoi(lower.substr(0, x_pos));
                int cols = std::stoi(lower.substr(x_pos + 1));
                return {static_cast<std::size_t>(std::max(1, rows)),
                        static_cast<std::size_t>(std::max(1, cols))};
            } catch (...) {
                // fall through to single-column default
            }
        }
    }
    // Mirror Python: count → (count, 1) for any list, else (1, 1).
    return {value_count > 0 ? value_count : 1, 1};
}

std::optional<ViewModel> build_table_model(
    std::span<const double> values,
    const ShapeHints& hints) {
    auto [rows, cols] = resolve_shape(values.size(), hints);

    ViewModel model;
    model.rows = rows;
    model.columns = cols;

    // Pre-format every value via tune_value_preview to match Python
    // `str(float)` byte-for-byte.
    std::vector<std::string> formatted;
    formatted.reserve(values.size());
    for (double v : values) {
        formatted.push_back(tune_value_preview::format_scalar_python_repr(v));
    }

    model.cells.reserve(rows);
    for (std::size_t row = 0; row < rows; ++row) {
        std::vector<std::string> row_values;
        row_values.reserve(cols);
        const std::size_t start = row * cols;
        const std::size_t end = std::min(start + cols, formatted.size());
        for (std::size_t i = start; i < end; ++i) {
            row_values.push_back(formatted[i]);
        }
        // Pad short rows with empty strings (mirrors the Python service).
        while (row_values.size() < cols) {
            row_values.emplace_back("");
        }
        model.cells.push_back(std::move(row_values));
    }
    return model;
}

}  // namespace tuner_core::table_view
