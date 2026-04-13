// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::ve_analyze_review — thirty-sixth sub-slice
// of the Phase 14 workspace-services port (Slice 4).
//
// Covers: summary text, detail text, confidence distribution, largest
// lean/rich corrections, cells_insufficient, rejection breakdown,
// clamp/boost surfacing, smoothing + diagnostics integration, and
// end-to-end composition with all three preceding Phase 7 slices.

#include <doctest.h>

#include "tuner_core/ve_analyze_review.hpp"
#include "tuner_core/ve_cell_hit_accumulator.hpp"
#include "tuner_core/ve_proposal_smoothing.hpp"
#include "tuner_core/ve_root_cause_diagnostics.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace var = tuner_core::ve_analyze_review;
namespace vca = tuner_core::ve_cell_hit_accumulator;
namespace vps = tuner_core::ve_proposal_smoothing;
namespace rcd = tuner_core::ve_root_cause_diagnostics;

// -----------------------------------------------------------------------
// Helper: build a cell accumulation with uniform samples.
// -----------------------------------------------------------------------
static vca::CellAccumulation make_cell(int row, int col, double current_ve,
                                        const std::vector<double>& cfs) {
    vca::CellAccumulation cell;
    cell.row_index = row;
    cell.col_index = col;
    cell.current_ve = current_ve;
    for (std::size_t i = 0; i < cfs.size(); ++i) {
        vca::CorrectionSample s;
        s.correction_factor = cfs[i];
        s.weight = 1.0;
        s.timestamp_seconds = 1000.0 + static_cast<double>(i);
        cell.samples.push_back(s);
    }
    return cell;
}

// -----------------------------------------------------------------------
// 1. Summary text — zero records
// -----------------------------------------------------------------------
TEST_CASE("summary text for zero records") {
    vca::Snapshot snap;
    snap.accepted_records = 0;
    snap.rejected_records = 0;
    auto review = var::build(snap);
    CHECK(review.summary_text.find("no records") != std::string::npos);
}

// -----------------------------------------------------------------------
// 2. Summary text — with data
// -----------------------------------------------------------------------
TEST_CASE("summary text contains counts") {
    auto cell = make_cell(0, 0, 100.0, {1.05, 1.05, 1.05});
    auto snap = vca::build_snapshot({cell}, 2, 2, 80, 20);
    auto review = var::build(snap);

    CHECK(review.summary_text.find("100") != std::string::npos);
    CHECK(review.summary_text.find("80") != std::string::npos);
    CHECK(review.summary_text.find("20") != std::string::npos);
}

// -----------------------------------------------------------------------
// 3. Confidence distribution counts
// -----------------------------------------------------------------------
TEST_CASE("confidence distribution counts") {
    std::vector<vca::CellAccumulation> cells = {
        make_cell(0, 0, 100.0, {1.0}),                    // 1 sample → insufficient
        make_cell(0, 1, 100.0, {1.0, 1.0, 1.0}),          // 3 samples → low
        make_cell(1, 0, 100.0, std::vector<double>(10, 1.0)),  // 10 → medium
        make_cell(1, 1, 100.0, std::vector<double>(30, 1.0)),  // 30 → high
    };
    auto snap = vca::build_snapshot(cells, 2, 2, 44, 0);
    auto review = var::build(snap);

    REQUIRE(review.confidence_distribution.size() == 4);
    CHECK(review.confidence_distribution[0] == std::make_pair(std::string("insufficient"), 1));
    CHECK(review.confidence_distribution[1] == std::make_pair(std::string("low"), 1));
    CHECK(review.confidence_distribution[2] == std::make_pair(std::string("medium"), 1));
    CHECK(review.confidence_distribution[3] == std::make_pair(std::string("high"), 1));
}

// -----------------------------------------------------------------------
// 4. Largest lean corrections sorted descending
// -----------------------------------------------------------------------
TEST_CASE("largest lean corrections sorted descending by CF") {
    std::vector<vca::CellAccumulation> cells = {
        make_cell(0, 0, 100.0, {1.05, 1.05, 1.05}),
        make_cell(0, 1, 100.0, {1.15, 1.15, 1.15}),
        make_cell(1, 0, 100.0, {1.10, 1.10, 1.10}),
    };
    auto snap = vca::build_snapshot(cells, 2, 2, 9, 0);
    auto review = var::build(snap);

    REQUIRE(review.largest_lean_corrections.size() == 3);
    CHECK(review.largest_lean_corrections[0].correction_factor > review.largest_lean_corrections[1].correction_factor);
    CHECK(review.largest_lean_corrections[1].correction_factor > review.largest_lean_corrections[2].correction_factor);
}

// -----------------------------------------------------------------------
// 5. Largest rich corrections sorted ascending
// -----------------------------------------------------------------------
TEST_CASE("largest rich corrections sorted ascending by CF") {
    std::vector<vca::CellAccumulation> cells = {
        make_cell(0, 0, 100.0, {0.95, 0.95, 0.95}),
        make_cell(0, 1, 100.0, {0.85, 0.85, 0.85}),
        make_cell(1, 0, 100.0, {0.90, 0.90, 0.90}),
    };
    auto snap = vca::build_snapshot(cells, 2, 2, 9, 0);
    auto review = var::build(snap);

    REQUIRE(review.largest_rich_corrections.size() == 3);
    CHECK(review.largest_rich_corrections[0].correction_factor < review.largest_rich_corrections[1].correction_factor);
    CHECK(review.largest_rich_corrections[1].correction_factor < review.largest_rich_corrections[2].correction_factor);
}

// -----------------------------------------------------------------------
// 6. Cells insufficient count
// -----------------------------------------------------------------------
TEST_CASE("cells_insufficient counts cells below min_samples") {
    std::vector<vca::CellAccumulation> cells = {
        make_cell(0, 0, 100.0, {1.05}),           // 1 sample < 3 → insufficient
        make_cell(0, 1, 100.0, {1.05, 1.05}),     // 2 < 3 → insufficient
        make_cell(1, 0, 100.0, {1.05, 1.05, 1.05}), // 3 ≥ 3 → has proposal
    };
    auto snap = vca::build_snapshot(cells, 2, 2, 6, 0);
    auto review = var::build(snap);

    CHECK(review.cells_insufficient == 2);
    CHECK(review.detail_text.find("Cells skipped") != std::string::npos);
}

// -----------------------------------------------------------------------
// 7. No corrections proposed text
// -----------------------------------------------------------------------
TEST_CASE("no corrections text when no proposals") {
    auto cell = make_cell(0, 0, 100.0, {1.0});  // 1 sample, cf=1.0
    auto snap = vca::build_snapshot({cell}, 1, 1, 1, 0);
    auto review = var::build(snap);

    CHECK(review.detail_text.find("No corrections proposed") != std::string::npos);
}

// -----------------------------------------------------------------------
// 8. Rejection breakdown in detail text
// -----------------------------------------------------------------------
TEST_CASE("rejection breakdown appears in detail text") {
    auto cell = make_cell(0, 0, 100.0, {1.05, 1.05, 1.05});
    auto snap = vca::build_snapshot({cell}, 2, 2, 3, 7);
    std::vector<std::pair<std::string, int>> rejections = {
        {"accelFilter", 4},
        {"std_DeadLambda", 3},
    };
    auto review = var::build(snap, rejections);

    CHECK(review.detail_text.find("accelFilter=4") != std::string::npos);
    CHECK(review.detail_text.find("std_DeadLambda=3") != std::string::npos);
}

// -----------------------------------------------------------------------
// 9. Coverage line in detail text
// -----------------------------------------------------------------------
TEST_CASE("coverage line in detail text") {
    auto cell = make_cell(0, 0, 100.0, {1.05, 1.05, 1.05});
    auto snap = vca::build_snapshot({cell}, 4, 4, 3, 0);
    auto review = var::build(snap);

    CHECK(review.detail_text.find("Coverage: 1/16") != std::string::npos);
}

// -----------------------------------------------------------------------
// 10. Clamp transparency surfacing
// -----------------------------------------------------------------------
TEST_CASE("clamp transparency surfaces in review") {
    auto cell = make_cell(0, 0, 100.0, {1.20, 1.20, 1.20});
    vca::WeightedCorrectionConfig config;
    config.max_correction_per_cell = 0.10;
    auto snap = vca::build_snapshot({cell}, 2, 2, 3, 0, 3, 0.0, 200.0, &config);
    auto review = var::build(snap);

    CHECK(review.clamp_count == 1);
    CHECK(review.detail_text.find("Clamp transparency") != std::string::npos);
}

// -----------------------------------------------------------------------
// 11. Boost penalty surfacing
// -----------------------------------------------------------------------
TEST_CASE("boost penalty surfaces in review") {
    vca::CellAccumulation cell;
    cell.row_index = 0;
    cell.col_index = 0;
    cell.current_ve = 100.0;
    cell.boost_penalty_applied = 0.25;
    for (int i = 0; i < 3; ++i) {
        cell.samples.push_back({1.05, 1.0, 1000.0 + i});
    }
    auto snap = vca::build_snapshot({cell}, 1, 1, 3, 0);
    auto review = var::build(snap);

    CHECK(review.boost_penalty_count == 1);
    CHECK(review.detail_text.find("Boost penalty") != std::string::npos);
}

// -----------------------------------------------------------------------
// 12. Smoothed layer summary text forwarded
// -----------------------------------------------------------------------
TEST_CASE("smoothed layer summary text forwarded") {
    auto cell = make_cell(0, 0, 100.0, {1.05, 1.05, 1.05});
    auto snap = vca::build_snapshot({cell}, 1, 1, 3, 0);

    vps::SmoothedProposalLayer layer;
    layer.summary_text = "Smoothed 1 proposal(s); 0 preserved unchanged (kernel radius 1, min_neighbors 1).";
    layer.smoothed_count = 1;
    layer.unchanged_count = 0;

    auto review = var::build(snap, {}, &layer);
    CHECK(review.smoothed_summary_text == layer.summary_text);
    CHECK(review.detail_text.find("Smoothed layer:") != std::string::npos);
}

// -----------------------------------------------------------------------
// 13. Diagnostic lines forwarded
// -----------------------------------------------------------------------
TEST_CASE("diagnostic lines forwarded from report") {
    // Build a 4x4 uniform lean bias → injector_flow_error fires.
    std::vector<vca::CellAccumulation> cells;
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c)
            cells.push_back(make_cell(r, c, 100.0, {1.08, 1.08, 1.08}));
    auto snap = vca::build_snapshot(cells, 4, 4, 48, 0);
    auto report = rcd::diagnose(snap.proposals);
    auto review = var::build(snap, {}, nullptr, &report);

    CHECK(!review.diagnostic_lines.empty());
    CHECK(review.detail_text.find("Root-cause diagnostics:") != std::string::npos);
    // Check that injector_flow_error appears.
    bool found = false;
    for (const auto& line : review.diagnostic_lines) {
        if (line.find("injector_flow_error") != std::string::npos) found = true;
    }
    CHECK(found);
}

// -----------------------------------------------------------------------
// 14. End-to-end: accumulator → smoothing → diagnostics → review
// -----------------------------------------------------------------------
TEST_CASE("full Phase 7 pipeline flows into review") {
    // 4x4 grid with a single lean spike.
    std::vector<vca::CellAccumulation> cells;
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            double cf = (r == 1 && c == 1) ? 1.15 : 1.00;
            cells.push_back(make_cell(r, c, 100.0, {cf, cf, cf, cf, cf}));
        }
    }
    auto snap = vca::build_snapshot(cells, 4, 4, 80, 5);
    auto layer = vps::smooth(snap.proposals, {});
    auto report = rcd::diagnose(snap.proposals);
    auto review = var::build(snap, {{"std_DeadLambda", 5}}, &layer, &report);

    // Summary should have all the counts.
    CHECK(review.summary_text.find("85") != std::string::npos);  // total=80+5
    CHECK(review.summary_text.find("80") != std::string::npos);  // accepted
    CHECK(review.summary_text.find("5") != std::string::npos);   // rejected

    // Detail should have rejection, coverage, smoothing, and diagnostics.
    CHECK(review.detail_text.find("std_DeadLambda=5") != std::string::npos);
    CHECK(review.detail_text.find("Coverage:") != std::string::npos);
    CHECK(review.detail_text.find("Smoothed layer:") != std::string::npos);

    // Lean correction preview should show the (1,1) spike.
    CHECK(!review.largest_lean_corrections.empty());
    CHECK(review.largest_lean_corrections[0].correction_factor > 1.0);
}

// -----------------------------------------------------------------------
// 15. Preview capped at 5 entries
// -----------------------------------------------------------------------
TEST_CASE("lean/rich previews capped at 5") {
    std::vector<vca::CellAccumulation> cells;
    for (int i = 0; i < 8; ++i) {
        double cf = 1.0 + 0.01 * (i + 1);  // 1.01 to 1.08
        cells.push_back(make_cell(0, i, 100.0, {cf, cf, cf}));
    }
    auto snap = vca::build_snapshot(cells, 1, 8, 24, 0);
    auto review = var::build(snap);

    CHECK(review.largest_lean_corrections.size() == 5);
    CHECK(review.max_preview_entries == 5);
}
