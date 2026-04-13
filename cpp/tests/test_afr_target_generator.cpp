// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::afr_target_generator — forty-first sub-slice.

#include <doctest.h>

#include "tuner_core/afr_target_generator.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace ag = tuner_core::afr_target_generator;

// -----------------------------------------------------------------------
// 1. Default NA first-start generates 256 values
// -----------------------------------------------------------------------
TEST_CASE("afr: default generates 16x16 table") {
    ag::AfrGeneratorContext ctx;
    auto result = ag::generate(ctx);

    CHECK(result.values.size() == 256);
    CHECK(result.rows == 16);
    CHECK(result.columns == 16);
}

// -----------------------------------------------------------------------
// 2. All values within [10.0, 18.0] bounds
// -----------------------------------------------------------------------
TEST_CASE("afr: all values within AFR bounds") {
    ag::AfrGeneratorContext ctx;
    auto result = ag::generate(ctx);

    for (double v : result.values) {
        CHECK(v >= ag::AFR_MIN);
        CHECK(v <= ag::AFR_MAX);
    }
}

// -----------------------------------------------------------------------
// 3. NA idle cells near stoich (first row, first col)
// -----------------------------------------------------------------------
TEST_CASE("afr: NA idle cells near stoich minus first-start enrichment") {
    ag::AfrGeneratorContext ctx;
    auto result = ag::generate(ctx, ag::CalibrationIntent::FIRST_START);

    // Row 0, Col 0 = lowest load, lowest RPM.
    // NA cruise AFR = 14.7, first-start enrichment = -0.7 → 14.0.
    CHECK(result.values[0] == doctest::Approx(14.0).epsilon(0.01));
}

// -----------------------------------------------------------------------
// 4. NA WOT row is richer than idle row
// -----------------------------------------------------------------------
TEST_CASE("afr: NA WOT row richer than idle row") {
    ag::AfrGeneratorContext ctx;
    auto result = ag::generate(ctx, ag::CalibrationIntent::DRIVABLE_BASE);

    // Row 0 (idle) col 0 vs Row 15 (WOT) col 0.
    double idle = result.values[0];
    double wot = result.values[15 * 16];
    CHECK(wot < idle);  // richer = lower AFR
}

// -----------------------------------------------------------------------
// 5. First-start is richer than drivable across the board
// -----------------------------------------------------------------------
TEST_CASE("afr: first-start richer than drivable") {
    ag::AfrGeneratorContext ctx;
    auto first = ag::generate(ctx, ag::CalibrationIntent::FIRST_START);
    auto driv = ag::generate(ctx, ag::CalibrationIntent::DRIVABLE_BASE);

    for (std::size_t i = 0; i < first.values.size(); ++i) {
        CHECK(first.values[i] <= driv.values[i] + 0.001);
    }
}

// -----------------------------------------------------------------------
// 6. Boosted WOT is richer than NA WOT
// -----------------------------------------------------------------------
TEST_CASE("afr: boosted WOT richer than NA WOT") {
    ag::AfrGeneratorContext na_ctx;
    ag::AfrGeneratorContext boost_ctx;
    boost_ctx.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;

    auto na = ag::generate(na_ctx, ag::CalibrationIntent::DRIVABLE_BASE);
    auto boosted = ag::generate(boost_ctx, ag::CalibrationIntent::DRIVABLE_BASE);

    // WOT row (15), mid col (8).
    double na_wot = na.values[15 * 16 + 8];
    double boost_wot = boosted.values[15 * 16 + 8];
    CHECK(boost_wot < na_wot);
}

// -----------------------------------------------------------------------
// 7. High boost target makes WOT even richer
// -----------------------------------------------------------------------
TEST_CASE("afr: high boost target enriches WOT further") {
    ag::AfrGeneratorContext low_boost;
    low_boost.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    low_boost.boost_target_kpa = 150.0;

    ag::AfrGeneratorContext high_boost;
    high_boost.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    high_boost.boost_target_kpa = 250.0;  // above 200 threshold

    auto low = ag::generate(low_boost, ag::CalibrationIntent::DRIVABLE_BASE);
    auto high = ag::generate(high_boost, ag::CalibrationIntent::DRIVABLE_BASE);

    double low_wot = low.values[15 * 16 + 8];
    double high_wot = high.values[15 * 16 + 8];
    CHECK(high_wot < low_wot);
}

// -----------------------------------------------------------------------
// 8. No intercooler makes WOT richer
// -----------------------------------------------------------------------
TEST_CASE("afr: no intercooler enriches WOT") {
    ag::AfrGeneratorContext with_ic;
    with_ic.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    with_ic.intercooler_present = true;

    ag::AfrGeneratorContext no_ic;
    no_ic.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    no_ic.intercooler_present = false;

    auto ic = ag::generate(with_ic, ag::CalibrationIntent::DRIVABLE_BASE);
    auto no = ag::generate(no_ic, ag::CalibrationIntent::DRIVABLE_BASE);

    double ic_wot = ic.values[15 * 16 + 8];
    double no_wot = no.values[15 * 16 + 8];
    CHECK(no_wot < ic_wot);
}

// -----------------------------------------------------------------------
// 9. Stoich ratio used correctly
// -----------------------------------------------------------------------
TEST_CASE("afr: stoich ratio flows into result") {
    ag::AfrGeneratorContext ctx;
    ctx.stoich_ratio = 9.8;  // E85
    auto result = ag::generate(ctx, ag::CalibrationIntent::DRIVABLE_BASE);

    CHECK(result.stoich == doctest::Approx(9.8));
}

// -----------------------------------------------------------------------
// 10. Summary text contains topology and intent
// -----------------------------------------------------------------------
TEST_CASE("afr: summary text content") {
    ag::AfrGeneratorContext ctx;
    ctx.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    auto result = ag::generate(ctx);

    CHECK(result.summary.find("Single Turbo") != std::string::npos);
    CHECK(result.summary.find("first-start") != std::string::npos);
    CHECK(result.summary.find("14.7") != std::string::npos);
}

// -----------------------------------------------------------------------
// 11. Boosted assumptions include boost target and intercooler
// -----------------------------------------------------------------------
TEST_CASE("afr: boosted assumptions populated") {
    ag::AfrGeneratorContext ctx;
    ctx.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    ctx.boost_target_kpa = 180.0;
    ctx.intercooler_present = true;
    auto result = ag::generate(ctx);

    bool found_boost = false, found_ic = false;
    for (const auto& a : result.assumptions) {
        if (a.label == "Boost target" && a.value_str == "180 kPa") found_boost = true;
        if (a.label == "Intercooler" && a.value_str == "present") found_ic = true;
    }
    CHECK(found_boost);
    CHECK(found_ic);
}

// -----------------------------------------------------------------------
// 12. Compound turbo has richest WOT
// -----------------------------------------------------------------------
TEST_CASE("afr: compound turbo has richest baseline WOT") {
    ag::AfrGeneratorContext compound;
    compound.forced_induction_topology = ag::ForcedInductionTopology::TWIN_TURBO_COMPOUND;
    compound.intercooler_present = true;

    ag::AfrGeneratorContext single;
    single.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    single.intercooler_present = true;

    auto c = ag::generate(compound, ag::CalibrationIntent::DRIVABLE_BASE);
    auto s = ag::generate(single, ag::CalibrationIntent::DRIVABLE_BASE);

    double c_wot = c.values[15 * 16 + 8];
    double s_wot = s.values[15 * 16 + 8];
    CHECK(c_wot < s_wot);  // compound is richer
}

// -----------------------------------------------------------------------
// 13. Boosted light-load cells are at stoich
// -----------------------------------------------------------------------
TEST_CASE("afr: boosted light-load at stoich") {
    ag::AfrGeneratorContext ctx;
    ctx.forced_induction_topology = ag::ForcedInductionTopology::SINGLE_TURBO;
    auto result = ag::generate(ctx, ag::CalibrationIntent::DRIVABLE_BASE);

    // Row 0 (idle), col 8 (mid RPM) should be at stoich (14.7).
    CHECK(result.values[8] == doctest::Approx(14.7).epsilon(0.01));
}

// -----------------------------------------------------------------------
// 14. All values rounded to 2 decimal places
// -----------------------------------------------------------------------
TEST_CASE("afr: values rounded to 2dp") {
    ag::AfrGeneratorContext ctx;
    auto result = ag::generate(ctx);

    for (double v : result.values) {
        double rounded = std::round(v * 100.0) / 100.0;
        CHECK(v == doctest::Approx(rounded).epsilon(0.001));
    }
}
