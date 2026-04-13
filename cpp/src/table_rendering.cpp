// SPDX-License-Identifier: MIT
//
// tuner_core::table_rendering implementation. Pure logic.

#include "tuner_core/table_rendering.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <optional>
#include <utility>

namespace tuner_core::table_rendering {

namespace {

struct Rgb {
    int r;
    int g;
    int b;
};

// Mirror Qt `QColor("#rrggbb").name()` lowercase output.
std::string format_hex(const Rgb& c) {
    char buf[8];
    std::snprintf(buf, sizeof(buf), "#%02x%02x%02x", c.r & 0xff, c.g & 0xff, c.b & 0xff);
    return buf;
}

// Banker's rounding to match Python `round(x)`. The default IEEE-754
// rounding mode (`FE_TONEAREST`) is round-half-to-even, which is
// what `std::nearbyint` honors and what Python uses.
int banker_round(double x) {
    return static_cast<int>(std::nearbyint(x));
}

std::optional<double> parse_double(const std::string& text) {
    if (text.empty()) return std::nullopt;
    try {
        std::size_t consumed = 0;
        double v = std::stod(text, &consumed);
        if (consumed != text.size()) return std::nullopt;
        return v;
    } catch (...) {
        return std::nullopt;
    }
}

// Mirror of the Python gradient stop list. Hex-decoded once at
// startup so the cell render path stays in arithmetic.
const std::vector<std::pair<double, Rgb>>& gradient_stops() {
    static const std::vector<std::pair<double, Rgb>> stops = {
        {0.00, Rgb{0x8a, 0xa8, 0xff}},
        {0.25, Rgb{0x9d, 0xd9, 0xff}},
        {0.50, Rgb{0x9a, 0xf0, 0xa0}},
        {0.75, Rgb{0xe4, 0xee, 0x8e}},
        {0.90, Rgb{0xf3, 0xb0, 0x7b}},
        {1.00, Rgb{0xe5, 0x8e, 0x8e}},
    };
    return stops;
}

Rgb gradient_color(double value, double minimum, double maximum) {
    double ratio;
    if (maximum <= minimum) {
        ratio = 0.5;
    } else {
        ratio = std::max(0.0, std::min(1.0, (value - minimum) / (maximum - minimum)));
    }
    const auto& stops = gradient_stops();
    for (std::size_t i = 0; i + 1 < stops.size(); ++i) {
        const auto& [left_ratio, left] = stops[i];
        const auto& [right_ratio, right] = stops[i + 1];
        if (ratio <= right_ratio) {
            double span = right_ratio - left_ratio;
            if (span == 0.0) span = 1.0;
            double local = (ratio - left_ratio) / span;
            return Rgb{
                banker_round(left.r + (right.r - left.r) * local),
                banker_round(left.g + (right.g - left.g) * local),
                banker_round(left.b + (right.b - left.b) * local),
            };
        }
    }
    return stops.back().second;
}

double perceived_brightness(const Rgb& c) {
    return c.r * 0.299 + c.g * 0.587 + c.b * 0.114;
}

CellRender render_cell(const std::string& text, double minimum, double maximum) {
    auto numeric = parse_double(text);
    if (!numeric) {
        return CellRender{text, "#ffffff", "#000000"};
    }
    Rgb bg = gradient_color(*numeric, minimum, maximum);
    std::string fg = perceived_brightness(bg) < 120.0 ? "#ffffff" : "#000000";
    return CellRender{text, format_hex(bg), std::move(fg)};
}

std::vector<double> collect_numeric_values(const std::vector<std::vector<std::string>>& rows) {
    std::vector<double> out;
    for (const auto& row : rows) {
        for (const auto& cell : row) {
            auto v = parse_double(cell);
            if (v) out.push_back(*v);
        }
    }
    return out;
}

}  // namespace

RenderModel build_render_model(
    const tuner_core::table_view::ViewModel& table_model,
    const std::vector<std::string>& x_labels,
    const std::vector<std::string>& y_labels,
    bool invert_y_axis)
{
    RenderModel out;
    out.rows = table_model.rows;
    out.columns = table_model.columns;
    out.x_labels = x_labels;

    out.row_index_map.reserve(table_model.rows);
    if (invert_y_axis) {
        for (std::size_t i = table_model.rows; i > 0; --i) {
            out.row_index_map.push_back(i - 1);
        }
    } else {
        for (std::size_t i = 0; i < table_model.rows; ++i) {
            out.row_index_map.push_back(i);
        }
    }

    out.y_labels.reserve(out.row_index_map.size());
    for (auto idx : out.row_index_map) {
        if (idx < y_labels.size()) {
            out.y_labels.push_back(y_labels[idx]);
        } else {
            out.y_labels.emplace_back();
        }
    }

    auto numeric = collect_numeric_values(table_model.cells);
    double minimum = 0.0;
    double maximum = 0.0;
    if (!numeric.empty()) {
        minimum = *std::min_element(numeric.begin(), numeric.end());
        maximum = *std::max_element(numeric.begin(), numeric.end());
    }

    out.cells.reserve(out.row_index_map.size());
    for (auto model_row : out.row_index_map) {
        std::vector<CellRender> rendered;
        if (model_row < table_model.cells.size()) {
            const auto& source_row = table_model.cells[model_row];
            rendered.reserve(source_row.size());
            for (const auto& cell : source_row) {
                rendered.push_back(render_cell(cell, minimum, maximum));
            }
        }
        out.cells.push_back(std::move(rendered));
    }

    return out;
}

}  // namespace tuner_core::table_rendering
