// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::gauge_color_zones.

#include "doctest.h"

#include "tuner_core/gauge_color_zones.hpp"

using namespace tuner_core::gauge_color_zones;

TEST_CASE("derive_zones: no thresholds yields no zones") {
    Thresholds t;
    auto z = derive_zones(0.0, 8000.0, t);
    CHECK(z.empty());
}

TEST_CASE("derive_zones: only hi_warn + hi_danger yields warning + danger + ok") {
    Thresholds t;
    t.hi_warn = 6500.0;
    t.hi_danger = 7500.0;
    auto z = derive_zones(0.0, 8000.0, t);
    REQUIRE(z.size() == 3);
    // ok band first (lo to hi_warn), then warning (hi_warn..hi_danger), then danger
    CHECK(z[0].lo == 0.0);
    CHECK(z[0].hi == 6500.0);
    CHECK(z[0].color == "ok");
    CHECK(z[1].lo == 6500.0);
    CHECK(z[1].hi == 7500.0);
    CHECK(z[1].color == "warning");
    CHECK(z[2].lo == 7500.0);
    CHECK(z[2].hi == 8000.0);
    CHECK(z[2].color == "danger");
}

TEST_CASE("derive_zones: low + high warn/danger yields full 5-band layout") {
    Thresholds t;
    t.lo_danger = 8.0;
    t.lo_warn = 11.0;
    t.hi_warn = 14.0;
    t.hi_danger = 15.0;
    auto z = derive_zones(0.0, 16.0, t);
    REQUIRE(z.size() == 5);
    CHECK(z[0].color == "danger");  // [0, 8)
    CHECK(z[0].lo == 0.0); CHECK(z[0].hi == 8.0);
    CHECK(z[1].color == "warning"); // [8, 11)
    CHECK(z[1].lo == 8.0); CHECK(z[1].hi == 11.0);
    CHECK(z[2].color == "ok");      // [11, 14)
    CHECK(z[2].lo == 11.0); CHECK(z[2].hi == 14.0);
    CHECK(z[3].color == "warning"); // [14, 15)
    CHECK(z[3].lo == 14.0); CHECK(z[3].hi == 15.0);
    CHECK(z[4].color == "danger");  // [15, 16)
    CHECK(z[4].lo == 15.0); CHECK(z[4].hi == 16.0);
}

TEST_CASE("derive_zones: lo_danger == lo is dropped (strict inequality)") {
    Thresholds t;
    t.lo_danger = 0.0;
    t.lo_warn = 11.0;
    auto z = derive_zones(0.0, 16.0, t);
    // lo_danger > lo is false → no low danger band
    bool has_low_danger = false;
    for (const auto& zn : z) {
        if (zn.color == "danger" && zn.lo == 0.0) has_low_danger = true;
    }
    CHECK_FALSE(has_low_danger);
}

TEST_CASE("derive_zones: hi_danger == hi is dropped") {
    Thresholds t;
    t.hi_warn = 6500.0;
    t.hi_danger = 8000.0;
    auto z = derive_zones(0.0, 8000.0, t);
    // hi_danger < hi is false → no high danger band
    bool has_high_danger = false;
    for (const auto& zn : z) {
        if (zn.color == "danger") has_high_danger = true;
    }
    CHECK_FALSE(has_high_danger);
}

TEST_CASE("derive_zones: only lo_warn yields warning + ok") {
    Thresholds t;
    t.lo_warn = 11.0;
    auto z = derive_zones(0.0, 16.0, t);
    REQUIRE(z.size() == 2);
    CHECK(z[0].color == "warning");
    CHECK(z[0].lo == 0.0);
    CHECK(z[0].hi == 11.0);
    CHECK(z[1].color == "ok");
    CHECK(z[1].lo == 11.0);
    CHECK(z[1].hi == 16.0);
}

TEST_CASE("derive_zones: zero-width bands are dropped") {
    // lo_warn == lo_danger → low warning band has zero width → dropped
    Thresholds t;
    t.lo_danger = 5.0;
    t.lo_warn = 5.0;
    auto z = derive_zones(0.0, 10.0, t);
    bool has_warning = false;
    for (const auto& zn : z) {
        if (zn.color == "warning") has_warning = true;
    }
    CHECK_FALSE(has_warning);
}
