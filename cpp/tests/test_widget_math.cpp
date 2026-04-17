// SPDX-License-Identifier: MIT
#include "tuner_core/widget_math.hpp"

#include <doctest.h>
#include <cmath>

namespace wm = tuner_core::widget_math;

// ---- screen_drag_to_time_range ----

TEST_CASE("zoom: full-width drag returns full view") {
    auto r = wm::screen_drag_to_time_range(50, 250, 50, 200, 0.0, 10.0);
    CHECK(r.start == doctest::Approx(0.0));
    CHECK(r.end == doctest::Approx(10.0));
}

TEST_CASE("zoom: left-half drag zooms to first half") {
    auto r = wm::screen_drag_to_time_range(50, 150, 50, 200, 0.0, 10.0);
    CHECK(r.start == doctest::Approx(0.0));
    CHECK(r.end == doctest::Approx(5.0));
}

TEST_CASE("zoom: right-half drag zooms to second half") {
    auto r = wm::screen_drag_to_time_range(150, 250, 50, 200, 0.0, 10.0);
    CHECK(r.start == doctest::Approx(5.0));
    CHECK(r.end == doctest::Approx(10.0));
}

TEST_CASE("zoom: reversed drag order produces same result") {
    auto r = wm::screen_drag_to_time_range(250, 150, 50, 200, 0.0, 10.0);
    CHECK(r.start == doctest::Approx(5.0));
    CHECK(r.end == doctest::Approx(10.0));
}

TEST_CASE("zoom: degenerate drag (< 1%) returns original view") {
    auto r = wm::screen_drag_to_time_range(100, 101, 50, 200, 0.0, 10.0);
    CHECK(r.start == doctest::Approx(0.0));
    CHECK(r.end == doctest::Approx(10.0));
}

TEST_CASE("zoom: drag clamped to plot bounds") {
    auto r = wm::screen_drag_to_time_range(0, 300, 50, 200, 2.0, 8.0);
    CHECK(r.start == doctest::Approx(2.0));
    CHECK(r.end == doctest::Approx(8.0));
}

TEST_CASE("zoom: zero plot width returns original view") {
    auto r = wm::screen_drag_to_time_range(50, 100, 50, 0, 0.0, 10.0);
    CHECK(r.start == doctest::Approx(0.0));
    CHECK(r.end == doctest::Approx(10.0));
}

TEST_CASE("zoom: non-zero view offset") {
    auto r = wm::screen_drag_to_time_range(50, 150, 50, 200, 5.0, 15.0);
    CHECK(r.start == doctest::Approx(5.0));
    CHECK(r.end == doctest::Approx(10.0));
}

// ---- build_square_wave_points ----

TEST_CASE("square wave: empty inputs") {
    auto pts = wm::build_square_wave_points({}, {}, 0, 100, 0, 1, 0, 50, 0, 1);
    CHECK(pts.empty());
}

TEST_CASE("square wave: single point") {
    auto pts = wm::build_square_wave_points({0.0}, {1.0}, 0, 100, 0, 1, 0, 50, 0, 1);
    REQUIRE(pts.size() == 1);
    CHECK(pts[0].first == doctest::Approx(0.0));
    CHECK(pts[0].second == doctest::Approx(0.0));  // y_at(1.0) = top
}

TEST_CASE("square wave: two points produce step") {
    // time=[0, 1], values=[0, 1], plot 0..100, time 0..1, track 0..50
    auto pts = wm::build_square_wave_points(
        {0.0, 1.0}, {0.0, 1.0}, 0, 100, 0, 1, 0, 50, 0, 1);
    REQUIRE(pts.size() == 3);
    // First point: x=0, y=50 (bottom, val=0)
    CHECK(pts[0].first == doctest::Approx(0.0));
    CHECK(pts[0].second == doctest::Approx(50.0));
    // Step: horizontal to x=100 at prev_y=50
    CHECK(pts[1].first == doctest::Approx(100.0));
    CHECK(pts[1].second == doctest::Approx(50.0));
    // Step: vertical to y=0 (top, val=1)
    CHECK(pts[2].first == doctest::Approx(100.0));
    CHECK(pts[2].second == doctest::Approx(0.0));
}

TEST_CASE("square wave: three points") {
    auto pts = wm::build_square_wave_points(
        {0.0, 0.5, 1.0}, {0.0, 1.0, 0.0},
        10, 200, 0, 1, 100, 80, 0, 1);
    // 3 input points → 1 + 2*2 = 5 output points
    REQUIRE(pts.size() == 5);
    // First point
    CHECK(pts[0].first == doctest::Approx(10.0));   // x_at(0)
    CHECK(pts[0].second == doctest::Approx(180.0));  // y_at(0) = bottom
    // Step to val=1 at t=0.5
    CHECK(pts[1].first == doctest::Approx(110.0));   // x_at(0.5)
    CHECK(pts[1].second == doctest::Approx(180.0));  // horizontal at prev_y
    CHECK(pts[2].first == doctest::Approx(110.0));   // same x
    CHECK(pts[2].second == doctest::Approx(100.0));  // y_at(1) = top
    // Step back to val=0 at t=1.0
    CHECK(pts[3].first == doctest::Approx(210.0));   // x_at(1.0)
    CHECK(pts[3].second == doctest::Approx(100.0));  // horizontal
    CHECK(pts[4].first == doctest::Approx(210.0));
    CHECK(pts[4].second == doctest::Approx(180.0));  // back to bottom
}

TEST_CASE("square wave: zero time span returns empty") {
    auto pts = wm::build_square_wave_points(
        {0.0, 1.0}, {0.0, 1.0}, 0, 100, 0, 0, 0, 50, 0, 1);
    CHECK(pts.empty());
}
