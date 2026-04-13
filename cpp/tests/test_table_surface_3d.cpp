// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/table_surface_3d.hpp"

namespace ts3d = tuner_core::table_surface_3d;

TEST_SUITE("table_surface_3d") {

TEST_CASE("empty values produce empty surface") {
    auto s = ts3d::project({}, 0, 0);
    CHECK(s.rows == 0);
    CHECK(s.points.empty());
}

TEST_CASE("4x4 surface has correct dimensions") {
    std::vector<double> vals(16, 50.0);
    auto s = ts3d::project(vals, 4, 4);
    CHECK(s.rows == 4);
    CHECK(s.cols == 4);
    REQUIRE(s.points.size() == 4);
    CHECK(s.points[0].size() == 4);
}

TEST_CASE("all points within output bounds") {
    std::vector<double> vals;
    for (int i = 0; i < 256; ++i) vals.push_back(i * 0.4);
    auto s = ts3d::project(vals, 16, 16, 225, 30, 400, 300);
    for (const auto& row : s.points)
        for (const auto& pt : row) {
            CHECK(pt.x >= -10);
            CHECK(pt.x <= 410);
            CHECK(pt.y >= -10);
            CHECK(pt.y <= 310);
        }
}

TEST_CASE("different azimuth produces different projection") {
    std::vector<double> vals = {0, 10, 20, 30, 40, 50, 60, 70, 80};
    auto s1 = ts3d::project(vals, 3, 3, 0, 30);
    auto s2 = ts3d::project(vals, 3, 3, 90, 30);
    // At least some points should differ.
    bool any_diff = false;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c)
            if (std::abs(s1.points[r][c].x - s2.points[r][c].x) > 1.0)
                any_diff = true;
    CHECK(any_diff);
}

TEST_CASE("min/max values tracked") {
    std::vector<double> vals = {10, 20, 30, 40};
    auto s = ts3d::project(vals, 2, 2);
    CHECK(s.min_value == doctest::Approx(10));
    CHECK(s.max_value == doctest::Approx(40));
}

TEST_CASE("interpolate_screen_point rejects empty surface") {
    ts3d::ProjectedSurface empty;
    auto pt = ts3d::interpolate_screen_point(empty, 0.0, 0.0);
    CHECK_FALSE(pt.has_value());
}

TEST_CASE("interpolate_screen_point rejects out-of-range fracs") {
    std::vector<double> vals(16, 10.0);
    auto s = ts3d::project(vals, 4, 4, 225, 30, 400, 300);
    CHECK_FALSE(ts3d::interpolate_screen_point(s, -0.1, 0.0).has_value());
    CHECK_FALSE(ts3d::interpolate_screen_point(s, 0.0, -0.1).has_value());
    CHECK_FALSE(ts3d::interpolate_screen_point(s, 3.01, 0.0).has_value());
    CHECK_FALSE(ts3d::interpolate_screen_point(s, 0.0, 3.01).has_value());
}

TEST_CASE("interpolate_screen_point returns exact vertex for integer fracs") {
    std::vector<double> vals;
    for (int i = 0; i < 16; ++i) vals.push_back(i * 5.0);
    auto s = ts3d::project(vals, 4, 4, 225, 30, 400, 300);
    auto pt = ts3d::interpolate_screen_point(s, 2.0, 3.0);
    REQUIRE(pt.has_value());
    CHECK(pt->x == doctest::Approx(s.points[2][3].x));
    CHECK(pt->y == doctest::Approx(s.points[2][3].y));
}

TEST_CASE("interpolate_screen_point midpoint is average of four corners") {
    // Use a flat table so projection is deterministic in-plane.
    std::vector<double> vals(4, 10.0);
    auto s = ts3d::project(vals, 2, 2, 225, 30, 400, 300);
    auto pt = ts3d::interpolate_screen_point(s, 0.5, 0.5);
    REQUIRE(pt.has_value());
    double ex = (s.points[0][0].x + s.points[0][1].x
               + s.points[1][0].x + s.points[1][1].x) / 4.0;
    double ey = (s.points[0][0].y + s.points[0][1].y
               + s.points[1][0].y + s.points[1][1].y) / 4.0;
    CHECK(pt->x == doctest::Approx(ex));
    CHECK(pt->y == doctest::Approx(ey));
}

TEST_CASE("interpolate_screen_point bilinear on row edge") {
    std::vector<double> vals(4, 10.0);
    auto s = ts3d::project(vals, 2, 2, 225, 30, 400, 300);
    // Halfway along column direction on row 0.
    auto pt = ts3d::interpolate_screen_point(s, 0.0, 0.5);
    REQUIRE(pt.has_value());
    double ex = (s.points[0][0].x + s.points[0][1].x) / 2.0;
    double ey = (s.points[0][0].y + s.points[0][1].y) / 2.0;
    CHECK(pt->x == doctest::Approx(ex));
    CHECK(pt->y == doctest::Approx(ey));
}

}  // TEST_SUITE
