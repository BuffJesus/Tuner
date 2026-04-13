// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::startup_enrichment_generator — forty-fourth sub-slice.

#include <doctest.h>

#include "tuner_core/startup_enrichment_generator.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace seg = tuner_core::startup_enrichment_generator;

// =====================================================================
// WUE tests
// =====================================================================

TEST_CASE("wue_gen: generates 10 bins and rates") {
    seg::StartupContext ctx;
    auto r = seg::generate_wue(ctx);
    CHECK(r.clt_bins.size() == 10);
    CHECK(r.enrichment_pct.size() == 10);
}

TEST_CASE("wue_gen: last bin is 100% (warm = no enrichment)") {
    seg::StartupContext ctx;
    auto r = seg::generate_wue(ctx);
    CHECK(r.enrichment_pct.back() == doctest::Approx(100.0));
}

TEST_CASE("wue_gen: cold end is higher than warm end") {
    seg::StartupContext ctx;
    auto r = seg::generate_wue(ctx);
    CHECK(r.enrichment_pct.front() > r.enrichment_pct.back());
}

TEST_CASE("wue_gen: first-start has higher cold than drivable") {
    seg::StartupContext ctx;
    auto first = seg::generate_wue(ctx, seg::CalibrationIntent::FIRST_START);
    auto driv = seg::generate_wue(ctx, seg::CalibrationIntent::DRIVABLE_BASE);
    CHECK(first.enrichment_pct.front() > driv.enrichment_pct.front());
}

TEST_CASE("wue_gen: E85 stoich gives higher cold enrichment") {
    seg::StartupContext petrol;
    petrol.stoich_ratio = 14.7;
    seg::StartupContext e85;
    e85.stoich_ratio = 9.8;

    auto p = seg::generate_wue(petrol);
    auto e = seg::generate_wue(e85);
    CHECK(e.enrichment_pct.front() > p.enrichment_pct.front());
}

TEST_CASE("wue_gen: all values in [100, 255]") {
    seg::StartupContext ctx;
    auto r = seg::generate_wue(ctx);
    for (double v : r.enrichment_pct) {
        CHECK(v >= 100.0);
        CHECK(v <= 255.0);
    }
}

TEST_CASE("wue_gen: missing stoich produces warning") {
    seg::StartupContext ctx;
    auto r = seg::generate_wue(ctx);
    bool found = false;
    for (const auto& w : r.warnings) {
        if (w.find("Stoich ratio not set") != std::string::npos) found = true;
    }
    CHECK(found);
}

// =====================================================================
// Cranking tests
// =====================================================================

TEST_CASE("crank_gen: generates 4 bins and rates") {
    seg::StartupContext ctx;
    auto r = seg::generate_cranking(ctx);
    CHECK(r.clt_bins.size() == 4);
    CHECK(r.enrichment_pct.size() == 4);
}

TEST_CASE("crank_gen: high CR reduces cold enrichment") {
    seg::StartupContext low_cr;
    low_cr.compression_ratio = 8.0;
    seg::StartupContext high_cr;
    high_cr.compression_ratio = 12.0;

    auto low = seg::generate_cranking(low_cr);
    auto high = seg::generate_cranking(high_cr);
    CHECK(high.enrichment_pct.front() < low.enrichment_pct.front());
}

TEST_CASE("crank_gen: first-start richer than drivable") {
    seg::StartupContext ctx;
    auto first = seg::generate_cranking(ctx, seg::CalibrationIntent::FIRST_START);
    auto driv = seg::generate_cranking(ctx, seg::CalibrationIntent::DRIVABLE_BASE);
    CHECK(first.enrichment_pct.front() > driv.enrichment_pct.front());
}

TEST_CASE("crank_gen: all values in [100, 255]") {
    seg::StartupContext ctx;
    auto r = seg::generate_cranking(ctx);
    for (double v : r.enrichment_pct) {
        CHECK(v >= 100.0);
        CHECK(v <= 255.0);
    }
}

// =====================================================================
// ASE tests
// =====================================================================

TEST_CASE("ase_gen: generates 4 bins, pct, and durations") {
    seg::StartupContext ctx;
    auto r = seg::generate_ase(ctx);
    CHECK(r.clt_bins.size() == 4);
    CHECK(r.enrichment_pct.size() == 4);
    CHECK(r.duration_seconds.size() == 4);
}

TEST_CASE("ase_gen: first-start has higher enrichment than drivable") {
    seg::StartupContext ctx;
    auto first = seg::generate_ase(ctx, seg::CalibrationIntent::FIRST_START);
    auto driv = seg::generate_ase(ctx, seg::CalibrationIntent::DRIVABLE_BASE);
    CHECK(first.enrichment_pct.front() > driv.enrichment_pct.front());
    CHECK(first.duration_seconds.front() > driv.duration_seconds.front());
}

TEST_CASE("ase_gen: ITB raises enrichment and duration") {
    seg::StartupContext stock;
    seg::StartupContext itb;
    itb.intake_manifold_style = "itb";

    auto s = seg::generate_ase(stock);
    auto i = seg::generate_ase(itb);
    CHECK(i.enrichment_pct.front() > s.enrichment_pct.front());
}

TEST_CASE("ase_gen: boosted engine produces warning") {
    seg::StartupContext ctx;
    ctx.forced_induction_topology = seg::ForcedInductionTopology::SINGLE_TURBO;
    auto r = seg::generate_ase(ctx);
    bool found = false;
    for (const auto& w : r.warnings) {
        if (w.find("Forced-induction") != std::string::npos) found = true;
    }
    CHECK(found);
}

TEST_CASE("ase_gen: enrichment pct in [0, 155]") {
    seg::StartupContext ctx;
    auto r = seg::generate_ase(ctx);
    for (double v : r.enrichment_pct) {
        CHECK(v >= 0.0);
        CHECK(v <= 155.0);
    }
}

TEST_CASE("ase_gen: duration in [0, 255]") {
    seg::StartupContext ctx;
    auto r = seg::generate_ase(ctx);
    for (double v : r.duration_seconds) {
        CHECK(v >= 0.0);
        CHECK(v <= 255.0);
    }
}
