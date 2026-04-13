// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::table_edit.

#include "doctest.h"

#include "tuner_core/table_edit.hpp"

#include <cmath>
#include <vector>

using namespace tuner_core::table_edit;

namespace {

TableSelection sel(std::size_t t, std::size_t l, std::size_t b, std::size_t r) {
    return TableSelection{t, l, b, r};
}

}  // namespace

TEST_CASE("fill_region replaces only the selected cells") {
    std::vector<double> values{
        1, 2, 3,
        4, 5, 6,
        7, 8, 9,
    };
    auto out = fill_region(values, 3, sel(0, 1, 1, 2), 99.0);
    REQUIRE(out.size() == 9);
    CHECK(out[0] == 1);
    CHECK(out[1] == 99);
    CHECK(out[2] == 99);
    CHECK(out[3] == 4);
    CHECK(out[4] == 99);
    CHECK(out[5] == 99);
    CHECK(out[6] == 7);
    CHECK(out[7] == 8);
    CHECK(out[8] == 9);
}

TEST_CASE("fill_down_region copies the top row down") {
    std::vector<double> values{
        10, 20, 30,
        0,  0,  0,
        0,  0,  0,
    };
    auto out = fill_down_region(values, 3, sel(0, 0, 2, 2));
    CHECK(out[3] == 10); CHECK(out[4] == 20); CHECK(out[5] == 30);
    CHECK(out[6] == 10); CHECK(out[7] == 20); CHECK(out[8] == 30);
}

TEST_CASE("fill_down_region with single-row selection is a no-op") {
    std::vector<double> values{1, 2, 3, 4};
    auto out = fill_down_region(values, 2, sel(0, 0, 0, 1));
    CHECK(out == values);
}

TEST_CASE("fill_right_region copies the leftmost column rightward") {
    std::vector<double> values{
        5, 0, 0,
        9, 0, 0,
    };
    auto out = fill_right_region(values, 3, sel(0, 0, 1, 2));
    CHECK(out[0] == 5); CHECK(out[1] == 5); CHECK(out[2] == 5);
    CHECK(out[3] == 9); CHECK(out[4] == 9); CHECK(out[5] == 9);
}

TEST_CASE("interpolate_region linearly interpolates horizontally") {
    std::vector<double> values{
        0, 99, 99, 99, 100,
    };
    auto out = interpolate_region(values, 5, sel(0, 0, 0, 4));
    CHECK(out[0] == doctest::Approx(0.0));
    CHECK(out[1] == doctest::Approx(25.0));
    CHECK(out[2] == doctest::Approx(50.0));
    CHECK(out[3] == doctest::Approx(75.0));
    CHECK(out[4] == doctest::Approx(100.0));
}

TEST_CASE("interpolate_region with single column interpolates vertically") {
    std::vector<double> values{
        10,
        99,
        99,
        99,
        50,
    };
    auto out = interpolate_region(values, 1, sel(0, 0, 4, 0));
    CHECK(out[0] == doctest::Approx(10.0));
    CHECK(out[1] == doctest::Approx(20.0));
    CHECK(out[2] == doctest::Approx(30.0));
    CHECK(out[3] == doctest::Approx(40.0));
    CHECK(out[4] == doctest::Approx(50.0));
}

TEST_CASE("smooth_region averages over neighbors with edge clamping") {
    std::vector<double> values{
        1, 2, 3,
        4, 5, 6,
        7, 8, 9,
    };
    auto out = smooth_region(values, 3, sel(1, 1, 1, 1));
    // Center cell has all 9 neighbors → mean = 5
    CHECK(out[4] == doctest::Approx(5.0));
}

TEST_CASE("smooth_region rounds to 3 decimal places") {
    std::vector<double> values{
        1, 2,
        3, 4,
    };
    auto out = smooth_region(values, 2, sel(0, 0, 1, 1));
    // Each cell averages over its <=4 in-bounds neighbors. Smoothed values
    // should be precisely-representable thirds → rounded to 3 decimals.
    for (double v : out) {
        // Round-trip check: value × 1000 should be a near-integer.
        double scaled = v * 1000.0;
        CHECK(std::abs(scaled - std::nearbyint(scaled)) < 1e-9);
    }
}

TEST_CASE("paste_region tiles a single value across the selection") {
    std::vector<double> values{
        0, 0, 0,
        0, 0, 0,
    };
    auto out = paste_region(values, 3, sel(0, 0, 1, 2), "7");
    for (double v : out) CHECK(v == doctest::Approx(7.0));
}

TEST_CASE("paste_region honors a tab-separated 2x2 clipboard") {
    std::vector<double> values{
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0,
    };
    auto out = paste_region(values, 4, sel(0, 0, 1, 1), "1\t2\n3\t4");
    CHECK(out[0] == 1); CHECK(out[1] == 2);
    CHECK(out[4] == 3); CHECK(out[5] == 4);
    // Cells outside the selection stay zero.
    CHECK(out[2] == 0); CHECK(out[8] == 0);
}

TEST_CASE("paste_region tiles a 1x2 clipboard across a 3x4 selection") {
    std::vector<double> values{
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0,
    };
    auto out = paste_region(values, 4, sel(0, 0, 2, 3), "9\t8");
    // Pattern wraps both rows and columns.
    for (std::size_t r = 0; r < 3; ++r) {
        for (std::size_t c = 0; c < 4; ++c) {
            double expected = (c % 2 == 0) ? 9.0 : 8.0;
            CHECK(out[r * 4 + c] == doctest::Approx(expected));
        }
    }
}

TEST_CASE("parse_clipboard handles tabs commas and blank lines") {
    auto rows = parse_clipboard("1, 2, 3\n\n4\t5\t6\n");
    REQUIRE(rows.size() == 2);
    REQUIRE(rows[0].size() == 3);
    CHECK(rows[0][0] == 1);
    CHECK(rows[0][1] == 2);
    CHECK(rows[0][2] == 3);
    REQUIRE(rows[1].size() == 3);
    CHECK(rows[1][0] == 4);
    CHECK(rows[1][1] == 5);
    CHECK(rows[1][2] == 6);
}
