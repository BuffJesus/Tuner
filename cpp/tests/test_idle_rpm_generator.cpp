// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::idle_rpm_generator — fortieth sub-slice.

#include <doctest.h>

#include "tuner_core/idle_rpm_generator.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace irg = tuner_core::idle_rpm_generator;

// -----------------------------------------------------------------------
// 1. Default NA first-start generates 10 bins and 10 targets
// -----------------------------------------------------------------------
TEST_CASE("idle: default NA first-start generates 10 bins and targets") {
    irg::GeneratorContext ctx;
    auto result = irg::generate(ctx);

    CHECK(result.clt_bins.size() == 10);
    CHECK(result.rpm_targets.size() == 10);
}

// -----------------------------------------------------------------------
// 2. Warm idle is last bin target
// -----------------------------------------------------------------------
TEST_CASE("idle: warm idle is at last bin") {
    irg::GeneratorContext ctx;
    auto result = irg::generate(ctx);

    // NA warm idle = 800 RPM, shape[9] = 0.0, so last bin = 800.
    CHECK(result.rpm_targets.back() == doctest::Approx(800.0));
}

// -----------------------------------------------------------------------
// 3. Cold idle is first bin and higher than warm
// -----------------------------------------------------------------------
TEST_CASE("idle: cold idle is higher than warm") {
    irg::GeneratorContext ctx;
    auto result = irg::generate(ctx);

    CHECK(result.rpm_targets.front() > result.rpm_targets.back());
}

// -----------------------------------------------------------------------
// 4. First-start cold bump is higher than drivable
// -----------------------------------------------------------------------
TEST_CASE("idle: first-start cold is higher than drivable") {
    irg::GeneratorContext ctx;
    auto first = irg::generate(ctx, irg::CalibrationIntent::FIRST_START);
    auto drivable = irg::generate(ctx, irg::CalibrationIntent::DRIVABLE_BASE);

    CHECK(first.rpm_targets.front() > drivable.rpm_targets.front());
}

// -----------------------------------------------------------------------
// 5. Boosted engine has higher warm idle than NA
// -----------------------------------------------------------------------
TEST_CASE("idle: boosted engine has higher warm idle") {
    irg::GeneratorContext na_ctx;
    irg::GeneratorContext boost_ctx;
    boost_ctx.forced_induction_topology = irg::ForcedInductionTopology::SINGLE_TURBO;

    auto na = irg::generate(na_ctx);
    auto boosted = irg::generate(boost_ctx);

    CHECK(boosted.rpm_targets.back() > na.rpm_targets.back());
}

// -----------------------------------------------------------------------
// 6. High cam raises both warm and cold targets
// -----------------------------------------------------------------------
TEST_CASE("idle: high cam raises targets") {
    irg::GeneratorContext stock;
    irg::GeneratorContext high_cam;
    high_cam.cam_duration_deg = 280.0;

    auto stock_r = irg::generate(stock);
    auto cam_r = irg::generate(high_cam);

    CHECK(cam_r.rpm_targets.back() > stock_r.rpm_targets.back());
    CHECK(cam_r.rpm_targets.front() > stock_r.rpm_targets.front());
}

// -----------------------------------------------------------------------
// 7. High cam produces warning
// -----------------------------------------------------------------------
TEST_CASE("idle: high cam produces warning") {
    irg::GeneratorContext ctx;
    ctx.cam_duration_deg = 280.0;
    auto result = irg::generate(ctx);

    bool found = false;
    for (const auto& w : result.warnings) {
        if (w.find("High cam duration") != std::string::npos) found = true;
    }
    CHECK(found);
}

// -----------------------------------------------------------------------
// 8. Missing cam produces warning
// -----------------------------------------------------------------------
TEST_CASE("idle: missing cam produces warning") {
    irg::GeneratorContext ctx;
    auto result = irg::generate(ctx);

    bool found = false;
    for (const auto& w : result.warnings) {
        if (w.find("Cam duration not set") != std::string::npos) found = true;
    }
    CHECK(found);
}

// -----------------------------------------------------------------------
// 9. Race-ported head raises targets and warns
// -----------------------------------------------------------------------
TEST_CASE("idle: race-ported head raises targets") {
    irg::GeneratorContext stock;
    irg::GeneratorContext ported;
    ported.head_flow_class = "race_ported";

    auto stock_r = irg::generate(stock);
    auto ported_r = irg::generate(ported);

    CHECK(ported_r.rpm_targets.back() > stock_r.rpm_targets.back());

    bool found = false;
    for (const auto& w : ported_r.warnings) {
        if (w.find("Race-ported") != std::string::npos) found = true;
    }
    CHECK(found);
}

// -----------------------------------------------------------------------
// 10. ITB manifold raises targets and warns
// -----------------------------------------------------------------------
TEST_CASE("idle: ITB manifold raises targets") {
    irg::GeneratorContext stock;
    irg::GeneratorContext itb;
    itb.intake_manifold_style = "itb";

    auto stock_r = irg::generate(stock);
    auto itb_r = irg::generate(itb);

    CHECK(itb_r.rpm_targets.back() > stock_r.rpm_targets.back());

    bool found = false;
    for (const auto& w : itb_r.warnings) {
        if (w.find("ITB") != std::string::npos) found = true;
    }
    CHECK(found);
}

// -----------------------------------------------------------------------
// 11. RPM targets are all multiples of 10
// -----------------------------------------------------------------------
TEST_CASE("idle: RPM targets are multiples of 10") {
    irg::GeneratorContext ctx;
    ctx.cam_duration_deg = 280.0;
    ctx.head_flow_class = "race_ported";
    ctx.intake_manifold_style = "itb";
    auto result = irg::generate(ctx);

    for (double rpm : result.rpm_targets) {
        double rem = std::fmod(rpm, 10.0);
        CHECK(rem == doctest::Approx(0.0));
    }
}

// -----------------------------------------------------------------------
// 12. RPM targets are within [500, 2550] bounds
// -----------------------------------------------------------------------
TEST_CASE("idle: RPM targets within bounds") {
    irg::GeneratorContext ctx;
    ctx.cam_duration_deg = 300.0;
    ctx.head_flow_class = "race_ported";
    ctx.intake_manifold_style = "itb";
    ctx.forced_induction_topology = irg::ForcedInductionTopology::SINGLE_TURBO;
    auto result = irg::generate(ctx);

    for (double rpm : result.rpm_targets) {
        CHECK(rpm >= irg::RPM_MIN);
        CHECK(rpm <= irg::RPM_MAX);
    }
}

// -----------------------------------------------------------------------
// 13. Assumptions are populated
// -----------------------------------------------------------------------
TEST_CASE("idle: assumptions are populated") {
    irg::GeneratorContext ctx;
    ctx.cam_duration_deg = 250.0;
    auto result = irg::generate(ctx);

    CHECK(result.assumptions.size() == 5);
    // First assumption is calibration intent.
    CHECK(result.assumptions[0].label == "Calibration intent");
    CHECK(result.assumptions[0].value_str == "first_start");
    CHECK(result.assumptions[0].source == irg::AssumptionSource::FROM_CONTEXT);
}

// -----------------------------------------------------------------------
// 14. Summary text contains key information
// -----------------------------------------------------------------------
TEST_CASE("idle: summary text contains warm and cold RPM") {
    irg::GeneratorContext ctx;
    auto result = irg::generate(ctx);

    CHECK(result.summary.find("Warm idle: 800 RPM") != std::string::npos);
    CHECK(result.summary.find("first-start") != std::string::npos);
}

// -----------------------------------------------------------------------
// 15. Monotonically decreasing from cold to warm
// -----------------------------------------------------------------------
TEST_CASE("idle: targets decrease from cold to warm") {
    irg::GeneratorContext ctx;
    auto result = irg::generate(ctx);

    for (std::size_t i = 1; i < result.rpm_targets.size(); ++i) {
        CHECK(result.rpm_targets[i] <= result.rpm_targets[i - 1]);
    }
}
