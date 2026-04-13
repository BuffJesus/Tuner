// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::spark_table_generator — forty-second sub-slice.

#include <doctest.h>

#include "tuner_core/spark_table_generator.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace sg = tuner_core::spark_table_generator;

// -----------------------------------------------------------------------
// 1. Default generates 256 values
// -----------------------------------------------------------------------
TEST_CASE("spark: default generates 16x16 table") {
    sg::SparkGeneratorContext ctx;
    auto result = sg::generate(ctx);

    CHECK(result.values.size() == 256);
    CHECK(result.rows == 16);
    CHECK(result.columns == 16);
}

// -----------------------------------------------------------------------
// 2. All values within [5.0, 45.0] bounds
// -----------------------------------------------------------------------
TEST_CASE("spark: all values within timing bounds") {
    sg::SparkGeneratorContext ctx;
    auto result = sg::generate(ctx);

    for (double v : result.values) {
        CHECK(v >= sg::CRANK_TIMING_FLOOR);
        CHECK(v <= sg::TIMING_MAX);
    }
}

// -----------------------------------------------------------------------
// 3. WOT has more advance than idle
// -----------------------------------------------------------------------
TEST_CASE("spark: WOT has more advance than idle") {
    sg::SparkGeneratorContext ctx;
    auto result = sg::generate(ctx);

    // Row 0, col 8 (idle, mid RPM) vs row 15, col 8 (WOT, mid RPM).
    double idle = result.values[0 * 16 + 8];
    double wot = result.values[15 * 16 + 8];
    CHECK(wot > idle);
}

// -----------------------------------------------------------------------
// 4. Drivable base has more advance than first-start
// -----------------------------------------------------------------------
TEST_CASE("spark: drivable has more advance than first-start") {
    sg::SparkGeneratorContext ctx;
    auto first = sg::generate(ctx, sg::CalibrationIntent::FIRST_START);
    auto driv = sg::generate(ctx, sg::CalibrationIntent::DRIVABLE_BASE);

    // WOT row should have more advance in drivable.
    double first_wot = first.values[15 * 16 + 8];
    double driv_wot = driv.values[15 * 16 + 8];
    CHECK(driv_wot > first_wot);
}

// -----------------------------------------------------------------------
// 5. High CR reduces WOT timing
// -----------------------------------------------------------------------
TEST_CASE("spark: high CR reduces WOT timing") {
    sg::SparkGeneratorContext low_cr;
    low_cr.compression_ratio = 9.0;

    sg::SparkGeneratorContext high_cr;
    high_cr.compression_ratio = 12.0;

    auto low = sg::generate(low_cr);
    auto high = sg::generate(high_cr);

    double low_wot = low.values[15 * 16 + 8];
    double high_wot = high.values[15 * 16 + 8];
    CHECK(high_wot < low_wot);
}

// -----------------------------------------------------------------------
// 6. Turbo retards WOT timing vs NA
// -----------------------------------------------------------------------
TEST_CASE("spark: turbo retards WOT vs NA") {
    sg::SparkGeneratorContext na;
    sg::SparkGeneratorContext turbo;
    turbo.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;

    auto na_r = sg::generate(na);
    auto turbo_r = sg::generate(turbo);

    double na_wot = na_r.values[15 * 16 + 8];
    double turbo_wot = turbo_r.values[15 * 16 + 8];
    CHECK(turbo_wot < na_wot);
}

// -----------------------------------------------------------------------
// 7. Supercharger retards less than turbo
// -----------------------------------------------------------------------
TEST_CASE("spark: supercharger retards less than turbo") {
    sg::SparkGeneratorContext turbo;
    turbo.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;

    sg::SparkGeneratorContext sc;
    sc.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_SUPERCHARGER;

    auto turbo_r = sg::generate(turbo);
    auto sc_r = sg::generate(sc);

    double turbo_wot = turbo_r.values[15 * 16 + 8];
    double sc_wot = sc_r.values[15 * 16 + 8];
    CHECK(sc_wot > turbo_wot);
}

// -----------------------------------------------------------------------
// 8. High boost target retards more
// -----------------------------------------------------------------------
TEST_CASE("spark: high boost target retards more") {
    sg::SparkGeneratorContext low;
    low.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;
    low.boost_target_kpa = 160.0;

    sg::SparkGeneratorContext high;
    high.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;
    high.boost_target_kpa = 250.0;

    auto low_r = sg::generate(low);
    auto high_r = sg::generate(high);

    double low_wot = low_r.values[15 * 16 + 8];
    double high_wot = high_r.values[15 * 16 + 8];
    CHECK(high_wot < low_wot);
}

// -----------------------------------------------------------------------
// 9. No intercooler retards more
// -----------------------------------------------------------------------
TEST_CASE("spark: no intercooler retards more") {
    sg::SparkGeneratorContext ic;
    ic.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;
    ic.boost_target_kpa = 200.0;
    ic.intercooler_present = true;

    sg::SparkGeneratorContext no_ic;
    no_ic.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;
    no_ic.boost_target_kpa = 200.0;
    no_ic.intercooler_present = false;

    auto ic_r = sg::generate(ic);
    auto no_r = sg::generate(no_ic);

    double ic_wot = ic_r.values[15 * 16 + 8];
    double no_wot = no_r.values[15 * 16 + 8];
    CHECK(no_wot < ic_wot);
}

// -----------------------------------------------------------------------
// 10. Missing CR/cyl/dwell produces warnings
// -----------------------------------------------------------------------
TEST_CASE("spark: missing inputs produce warnings") {
    sg::SparkGeneratorContext ctx;
    auto result = sg::generate(ctx);

    CHECK(result.warnings.size() >= 3);
    bool found_cr = false, found_cyl = false, found_dwell = false;
    for (const auto& w : result.warnings) {
        if (w.find("Compression ratio") != std::string::npos) found_cr = true;
        if (w.find("Cylinder count") != std::string::npos) found_cyl = true;
        if (w.find("Dwell") != std::string::npos) found_dwell = true;
    }
    CHECK(found_cr);
    CHECK(found_cyl);
    CHECK(found_dwell);
}

// -----------------------------------------------------------------------
// 11. Summary text contains topology and intent
// -----------------------------------------------------------------------
TEST_CASE("spark: summary contains key info") {
    sg::SparkGeneratorContext ctx;
    ctx.compression_ratio = 10.5;
    ctx.cylinder_count = 6;
    auto result = sg::generate(ctx);

    CHECK(result.summary.find("Na") != std::string::npos);
    CHECK(result.summary.find("First Start") != std::string::npos);
    CHECK(result.summary.find("10.5:1") != std::string::npos);
    CHECK(result.summary.find("6") != std::string::npos);
}

// -----------------------------------------------------------------------
// 12. Cranking columns have reduced advance
// -----------------------------------------------------------------------
TEST_CASE("spark: cranking columns have reduced advance") {
    sg::SparkGeneratorContext ctx;
    auto result = sg::generate(ctx);

    // Col 0 (cranking) at mid load should be less than col 5 at same load.
    double crank = result.values[8 * 16 + 0];
    double mid = result.values[8 * 16 + 5];
    CHECK(crank < mid);
}

// -----------------------------------------------------------------------
// 13. Values rounded to 1 decimal place
// -----------------------------------------------------------------------
TEST_CASE("spark: values rounded to 1dp") {
    sg::SparkGeneratorContext ctx;
    ctx.compression_ratio = 11.5;
    ctx.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;
    auto result = sg::generate(ctx);

    for (double v : result.values) {
        double rounded = std::round(v * 10.0) / 10.0;
        CHECK(v == doctest::Approx(rounded).epsilon(0.001));
    }
}

// -----------------------------------------------------------------------
// 14. Boosted assumptions include boost and intercooler
// -----------------------------------------------------------------------
TEST_CASE("spark: boosted assumptions populated") {
    sg::SparkGeneratorContext ctx;
    ctx.forced_induction_topology = sg::ForcedInductionTopology::SINGLE_TURBO;
    ctx.boost_target_kpa = 180.0;
    ctx.intercooler_present = true;
    auto result = sg::generate(ctx);

    bool found_boost = false, found_ic = false;
    for (const auto& a : result.assumptions) {
        if (a.label == "Boost target") found_boost = true;
        if (a.label == "Intercooler" && a.value_str == "present") found_ic = true;
    }
    CHECK(found_boost);
    CHECK(found_ic);
}
