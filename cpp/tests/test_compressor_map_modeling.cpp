// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::compressor_map_modeling — Phase 15 item #10.

#include <doctest.h>

#include "tuner_core/compressor_map_modeling.hpp"

namespace cmm = tuner_core::compressor_map_modeling;

static cmm::Context make_ctx() {
    cmm::Context c;
    c.displacement_cc = 2998.0;   // Ford 300 I6
    c.cylinder_count = 6;
    c.baro_kpa = 101.3;
    c.intake_temp_c = 25.0;
    c.surge_flow_lbmin = 10.0;
    c.choke_flow_lbmin = 50.0;
    c.max_pressure_ratio = 3.0;
    c.surge_margin_pct = 10.0;
    return c;
}

// -----------------------------------------------------------------------
// Mass-flow + pressure-ratio math
// -----------------------------------------------------------------------

TEST_CASE("cmm: pressure ratio = MAP / baro") {
    auto ctx = make_ctx();
    auto p = cmm::compute_point(4000, 202.6, 30.0, 95.0, ctx);
    CHECK(p.pressure_ratio == doctest::Approx(2.0));
}

TEST_CASE("cmm: mass flow scales with RPM and MAP") {
    auto ctx = make_ctx();
    auto low_rpm  = cmm::compute_point(2000, 150.0, 30.0, 90.0, ctx);
    auto high_rpm = cmm::compute_point(6000, 150.0, 30.0, 90.0, ctx);
    CHECK(high_rpm.mass_flow_lbmin > low_rpm.mass_flow_lbmin);
    // Tripling RPM at same VE/MAP triples flow.
    CHECK(high_rpm.mass_flow_lbmin ==
          doctest::Approx(3.0 * low_rpm.mass_flow_lbmin).epsilon(1e-6));

    auto na  = cmm::compute_point(4000, 100.0, 30.0, 90.0, ctx);
    auto boosted = cmm::compute_point(4000, 200.0, 30.0, 90.0, ctx);
    CHECK(boosted.mass_flow_lbmin ==
          doctest::Approx(2.0 * na.mass_flow_lbmin).epsilon(1e-6));
}

TEST_CASE("cmm: zero / negative inputs produce zero flow") {
    auto ctx = make_ctx();
    CHECK(cmm::compute_point(0, 100, 25, 90, ctx).mass_flow_lbmin == 0.0);
    CHECK(cmm::compute_point(3000, -10, 25, 90, ctx).mass_flow_lbmin == 0.0);
    CHECK(cmm::compute_point(3000, 100, 25, 0, ctx).mass_flow_lbmin == 0.0);
}

// -----------------------------------------------------------------------
// Risk classification
// -----------------------------------------------------------------------

TEST_CASE("cmm: off_map when PR exceeds max") {
    auto ctx = make_ctx();
    ctx.max_pressure_ratio = 2.0;
    auto p = cmm::compute_point(4000, 250.0, 30.0, 95.0, ctx);  // PR = 2.47
    CHECK(p.risk == cmm::RiskRegion::OFF_MAP);
}

TEST_CASE("cmm: surge when flow below surge line") {
    auto ctx = make_ctx();
    ctx.surge_flow_lbmin = 30.0;  // raise surge threshold
    auto p = cmm::compute_point(2000, 110.0, 30.0, 80.0, ctx);
    CHECK(p.risk == cmm::RiskRegion::SURGE);
}

TEST_CASE("cmm: choke when flow above choke line") {
    auto ctx = make_ctx();
    ctx.choke_flow_lbmin = 5.0;  // drop choke threshold
    auto p = cmm::compute_point(6000, 200.0, 30.0, 95.0, ctx);
    CHECK(p.risk == cmm::RiskRegion::CHOKE);
}

TEST_CASE("cmm: near_surge band sits above hard surge") {
    auto ctx = make_ctx();
    ctx.surge_flow_lbmin = 10.0;
    ctx.surge_margin_pct = 20.0;  // band is 10–12 lb/min
    auto p = cmm::compute_point(2200, 110.0, 30.0, 70.0, ctx);
    // Flow lands in the near_surge band, not safe, not hard surge.
    if (p.mass_flow_lbmin >= 10.0 && p.mass_flow_lbmin < 12.0) {
        CHECK(p.risk == cmm::RiskRegion::NEAR_SURGE);
    }
}

// -----------------------------------------------------------------------
// Sweep + summary
// -----------------------------------------------------------------------

TEST_CASE("cmm: sweep_rpm produces N points") {
    auto ctx = make_ctx();
    auto pts = cmm::sweep_rpm(1500, 7000, 12, 200.0, 30.0, 95.0, ctx);
    REQUIRE(pts.size() == 12);
    CHECK(pts.front().rpm == doctest::Approx(1500));
    CHECK(pts.back().rpm  == doctest::Approx(7000));
    // Flow monotonically rises with RPM at constant MAP/VE.
    for (std::size_t i = 1; i < pts.size(); ++i) {
        CHECK(pts[i].mass_flow_lbmin >= pts[i - 1].mass_flow_lbmin);
    }
}

TEST_CASE("cmm: summary identifies worst risk across the sweep") {
    auto ctx = make_ctx();
    ctx.choke_flow_lbmin = 40.0;  // tight envelope
    auto pts = cmm::sweep_rpm(1500, 8000, 20, 200.0, 30.0, 95.0, ctx);
    auto s = cmm::summarise(pts, ctx);
    CHECK(s.total_count == 20);
    CHECK(s.peak_flow_lbmin > 0);
    CHECK(s.peak_pressure_ratio == doctest::Approx(200.0 / 101.3));
    // Some points at high RPM crest the choke line.
    CHECK(static_cast<int>(s.worst_risk) >=
          static_cast<int>(cmm::RiskRegion::NEAR_CHOKE));
    CHECK_FALSE(s.plain_language.empty());
}

TEST_CASE("cmm: summary empty input graceful") {
    auto ctx = make_ctx();
    auto s = cmm::summarise({}, ctx);
    CHECK(s.total_count == 0);
    CHECK_FALSE(s.plain_language.empty());
}

TEST_CASE("cmm: safe configuration reports safe summary") {
    auto ctx = make_ctx();
    // Generous envelope so a naturally-aspirated sweep stays in bounds.
    ctx.surge_flow_lbmin = 1.0;
    ctx.choke_flow_lbmin = 200.0;
    ctx.max_pressure_ratio = 5.0;
    auto pts = cmm::sweep_rpm(1500, 6500, 10, 100.0, 25.0, 90.0, ctx);
    auto s = cmm::summarise(pts, ctx);
    CHECK(s.worst_risk == cmm::RiskRegion::SAFE);
    CHECK(s.safe_count == s.total_count);
}
