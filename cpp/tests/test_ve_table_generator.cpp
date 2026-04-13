// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::ve_table_generator — forty-third sub-slice.

#include <doctest.h>

#include "tuner_core/ve_table_generator.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace vg = tuner_core::ve_table_generator;

// -----------------------------------------------------------------------
// 1. Default generates 256 values
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: default generates 16x16 table") {
    vg::VeGeneratorContext ctx;
    auto result = vg::generate(ctx);
    CHECK(result.values.size() == 256);
    CHECK(result.rows == 16);
    CHECK(result.columns == 16);
}

// -----------------------------------------------------------------------
// 2. All values within [20.0, 100.0] bounds
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: all values within bounds") {
    vg::VeGeneratorContext ctx;
    auto result = vg::generate(ctx);
    for (double v : result.values) {
        CHECK(v >= vg::VE_MIN);
        CHECK(v <= vg::VE_MAX);
    }
}

// -----------------------------------------------------------------------
// 3. WOT row has higher VE than idle row
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: WOT higher than idle") {
    vg::VeGeneratorContext ctx;
    auto result = vg::generate(ctx);
    double idle = result.values[0 * 16 + 8];
    double wot = result.values[15 * 16 + 8];
    CHECK(wot > idle);
}

// -----------------------------------------------------------------------
// 4. High cam raises WOT/high-RPM VE
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: high cam raises WOT VE") {
    vg::VeGeneratorContext stock;
    vg::VeGeneratorContext cam;
    cam.cam_duration_deg = 280.0;

    auto stock_r = vg::generate(stock);
    auto cam_r = vg::generate(cam);

    // Row 15, col 12 (WOT, high RPM).
    double stock_wot = stock_r.values[15 * 16 + 12];
    double cam_wot = cam_r.values[15 * 16 + 12];
    CHECK(cam_wot > stock_wot);
}

// -----------------------------------------------------------------------
// 5. Turbo reduces pre-spool VE
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: turbo reduces pre-spool VE") {
    vg::VeGeneratorContext na;
    vg::VeGeneratorContext turbo;
    turbo.forced_induction_topology = vg::ForcedInductionTopology::SINGLE_TURBO;

    auto na_r = vg::generate(na);
    auto turbo_r = vg::generate(turbo);

    // Col 2 (pre-spool), mid load.
    double na_ve = na_r.values[8 * 16 + 2];
    double turbo_ve = turbo_r.values[8 * 16 + 2];
    CHECK(turbo_ve < na_ve);
}

// -----------------------------------------------------------------------
// 6. Supercharger boosts low-RPM VE (non-centrifugal)
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: supercharger boosts low RPM VE") {
    vg::VeGeneratorContext na;
    vg::VeGeneratorContext sc;
    sc.forced_induction_topology = vg::ForcedInductionTopology::SINGLE_SUPERCHARGER;

    auto na_r = vg::generate(na);
    auto sc_r = vg::generate(sc);

    // Col 2 (low RPM), high load.
    double na_ve = na_r.values[12 * 16 + 2];
    double sc_ve = sc_r.values[12 * 16 + 2];
    CHECK(sc_ve > na_ve);
}

// -----------------------------------------------------------------------
// 7. Low reqFuel reduces idle VE
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: low reqFuel reduces idle VE") {
    vg::VeGeneratorContext normal;
    normal.required_fuel_ms = 10.0;

    vg::VeGeneratorContext low_req;
    low_req.required_fuel_ms = 3.0;

    auto normal_r = vg::generate(normal);
    auto low_r = vg::generate(low_req);

    // Row 0, col 0 (idle corner).
    double normal_idle = normal_r.values[0];
    double low_idle = low_r.values[0];
    CHECK(low_idle < normal_idle);
}

// -----------------------------------------------------------------------
// 8. Race-ported head raises WOT VE
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: race-ported raises WOT VE") {
    vg::VeGeneratorContext stock;
    vg::VeGeneratorContext ported;
    ported.head_flow_class = "race_ported";

    auto stock_r = vg::generate(stock);
    auto ported_r = vg::generate(ported);

    // Row 15, col 12 (WOT, high RPM).
    double stock_wot = stock_r.values[15 * 16 + 12];
    double ported_wot = ported_r.values[15 * 16 + 12];
    CHECK(ported_wot > stock_wot);
}

// -----------------------------------------------------------------------
// 9. ITB reduces idle, raises high RPM
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: ITB effects") {
    vg::VeGeneratorContext stock;
    vg::VeGeneratorContext itb;
    itb.intake_manifold_style = "itb";

    auto stock_r = vg::generate(stock);
    auto itb_r = vg::generate(itb);

    // Idle corner reduced.
    CHECK(itb_r.values[0] < stock_r.values[0]);
    // High load, high RPM raised.
    CHECK(itb_r.values[12 * 16 + 12] > stock_r.values[12 * 16 + 12]);
}

// -----------------------------------------------------------------------
// 10. Missing inputs produce warnings
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: missing inputs produce warnings") {
    vg::VeGeneratorContext ctx;
    auto result = vg::generate(ctx);
    CHECK(result.warnings.size() >= 3);
}

// -----------------------------------------------------------------------
// 11. Summary text contains topology
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: summary contains topology") {
    vg::VeGeneratorContext ctx;
    ctx.forced_induction_topology = vg::ForcedInductionTopology::SINGLE_TURBO;
    auto result = vg::generate(ctx);
    CHECK(result.summary.find("Single Turbo") != std::string::npos);
}

// -----------------------------------------------------------------------
// 12. Values rounded to 1dp
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: values rounded to 1dp") {
    vg::VeGeneratorContext ctx;
    ctx.cam_duration_deg = 280.0;
    ctx.head_flow_class = "race_ported";
    auto result = vg::generate(ctx);
    for (double v : result.values) {
        double rounded = std::round(v * 10.0) / 10.0;
        CHECK(v == doctest::Approx(rounded).epsilon(0.001));
    }
}

// -----------------------------------------------------------------------
// 13. Centrifugal SC gets pre-spool reduction like a turbo
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: centrifugal SC reduces pre-spool") {
    vg::VeGeneratorContext na;
    vg::VeGeneratorContext cent;
    cent.forced_induction_topology = vg::ForcedInductionTopology::SINGLE_SUPERCHARGER;
    cent.supercharger_type = vg::SuperchargerType::CENTRIFUGAL;

    auto na_r = vg::generate(na);
    auto cent_r = vg::generate(cent);

    // Pre-spool col 2, mid load.
    double na_ve = na_r.values[8 * 16 + 2];
    double cent_ve = cent_r.values[8 * 16 + 2];
    CHECK(cent_ve < na_ve);
}

// -----------------------------------------------------------------------
// 14. Compound turbo has smaller pre-spool reduction than single
// -----------------------------------------------------------------------
TEST_CASE("ve_gen: compound less pre-spool than single turbo") {
    vg::VeGeneratorContext single;
    single.forced_induction_topology = vg::ForcedInductionTopology::SINGLE_TURBO;

    vg::VeGeneratorContext compound;
    compound.forced_induction_topology = vg::ForcedInductionTopology::TWIN_TURBO_COMPOUND;

    auto single_r = vg::generate(single);
    auto compound_r = vg::generate(compound);

    // Col 2 (pre-spool), mid load.
    double single_ve = single_r.values[8 * 16 + 2];
    double compound_ve = compound_r.values[8 * 16 + 2];
    CHECK(compound_ve > single_ve);  // less reduction
}
