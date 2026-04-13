// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::table_view.

#include "doctest.h"

#include "tuner_core/table_view.hpp"

#include <vector>

using namespace tuner_core::table_view;

namespace {

ShapeHints with_dims(int rows, int cols) {
    ShapeHints h;
    h.rows = rows;
    h.cols = cols;
    return h;
}

ShapeHints with_text(std::string text) {
    ShapeHints h;
    h.shape_text = std::move(text);
    return h;
}

}  // namespace

TEST_CASE("resolve_shape: explicit rows and cols win") {
    auto [r, c] = resolve_shape(16, with_dims(4, 4));
    CHECK(r == 4);
    CHECK(c == 4);
}

TEST_CASE("resolve_shape: shape text fallback") {
    auto [r, c] = resolve_shape(16, with_text("4x4"));
    CHECK(r == 4);
    CHECK(c == 4);
}

TEST_CASE("resolve_shape: case-sensitive 'x' guard mirrors Python") {
    // Python's `"x" in shape` guard is case-sensitive — `"4X4"`
    // does not contain a lowercase 'x' so it falls through to the
    // single-column default. This is a Python quirk we preserve.
    auto [r, c] = resolve_shape(16, with_text("4X4"));
    CHECK(r == 16);
    CHECK(c == 1);
}

TEST_CASE("resolve_shape: malformed shape text falls through to single column") {
    auto [r, c] = resolve_shape(8, with_text("garbage"));
    CHECK(r == 8);
    CHECK(c == 1);
}

TEST_CASE("resolve_shape: empty value list with no hints → (1, 1)") {
    auto [r, c] = resolve_shape(0, ShapeHints{});
    CHECK(r == 1);
    CHECK(c == 1);
}

TEST_CASE("resolve_shape: explicit dims override shape text") {
    auto [r, c] = resolve_shape(16, ShapeHints{4, 4, std::string("8x2")});
    CHECK(r == 4);
    CHECK(c == 4);
}

TEST_CASE("build_table_model: 4x4 grid round-trips through Python repr") {
    std::vector<double> values{
        1.0, 2.0, 3.0, 4.0,
        5.0, 6.0, 7.0, 8.0,
        9.0, 10.0, 11.0, 12.0,
        13.0, 14.0, 15.0, 16.0,
    };
    auto m = build_table_model(values, with_dims(4, 4));
    REQUIRE(m.has_value());
    CHECK(m->rows == 4);
    CHECK(m->columns == 4);
    REQUIRE(m->cells.size() == 4);
    REQUIRE(m->cells[0].size() == 4);
    CHECK(m->cells[0][0] == "1.0");
    CHECK(m->cells[0][3] == "4.0");
    CHECK(m->cells[3][3] == "16.0");
}

TEST_CASE("build_table_model: short row gets padded with empty strings") {
    std::vector<double> values{1.0, 2.0, 3.0};
    auto m = build_table_model(values, with_dims(2, 2));
    REQUIRE(m.has_value());
    REQUIRE(m->cells.size() == 2);
    CHECK(m->cells[0][0] == "1.0");
    CHECK(m->cells[0][1] == "2.0");
    CHECK(m->cells[1][0] == "3.0");
    CHECK(m->cells[1][1] == "");
}

TEST_CASE("build_table_model: fractional values use Python str(float)") {
    std::vector<double> values{0.5, 3.14, 0.1};
    auto m = build_table_model(values, with_dims(1, 3));
    REQUIRE(m.has_value());
    CHECK(m->cells[0][0] == "0.5");
    CHECK(m->cells[0][1] == "3.14");
    CHECK(m->cells[0][2] == "0.1");
}

TEST_CASE("build_table_model: shape-text fallback") {
    std::vector<double> values{1.0, 2.0, 3.0, 4.0, 5.0, 6.0};
    auto m = build_table_model(values, with_text("2x3"));
    REQUIRE(m.has_value());
    CHECK(m->rows == 2);
    CHECK(m->columns == 3);
    CHECK(m->cells[1][2] == "6.0");
}

TEST_CASE("build_table_model: single-column fallback for unset shape") {
    std::vector<double> values{1.0, 2.0, 3.0};
    auto m = build_table_model(values, ShapeHints{});
    REQUIRE(m.has_value());
    CHECK(m->rows == 3);
    CHECK(m->columns == 1);
    CHECK(m->cells[0][0] == "1.0");
    CHECK(m->cells[2][0] == "3.0");
}
