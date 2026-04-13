// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::ve_cell_hit_accumulator — thirty-fifth sub-slice
// of the Phase 14 workspace-services port (Slice 4).
//
// Covers: confidence labels, confidence scores, weighted mean, per-cell
// clamp, dwell weighting, age decay, coverage map, summary text, and
// Proposal output shape compatibility with sub-slices 33 & 34.

#include <doctest.h>

#include "tuner_core/ve_cell_hit_accumulator.hpp"
#include "tuner_core/ve_proposal_smoothing.hpp"
#include "tuner_core/ve_root_cause_diagnostics.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace vca = tuner_core::ve_cell_hit_accumulator;
namespace vps = tuner_core::ve_proposal_smoothing;
namespace rcd = tuner_core::ve_root_cause_diagnostics;

// -----------------------------------------------------------------------
// Helper: build a single cell with uniform correction samples.
// -----------------------------------------------------------------------
static vca::CellAccumulation make_cell(int row, int col, double current_ve,
                                        const std::vector<double>& cfs,
                                        double base_time = 1000.0) {
    vca::CellAccumulation cell;
    cell.row_index = row;
    cell.col_index = col;
    cell.current_ve = current_ve;
    for (std::size_t i = 0; i < cfs.size(); ++i) {
        vca::CorrectionSample s;
        s.correction_factor = cfs[i];
        s.weight = 1.0;
        s.timestamp_seconds = base_time + static_cast<double>(i);
        cell.samples.push_back(s);
    }
    return cell;
}

// -----------------------------------------------------------------------
// 1. Confidence label thresholds
// -----------------------------------------------------------------------
TEST_CASE("confidence_label thresholds") {
    CHECK(vca::confidence_label(0) == "insufficient");
    CHECK(vca::confidence_label(2) == "insufficient");
    CHECK(vca::confidence_label(3) == "low");
    CHECK(vca::confidence_label(9) == "low");
    CHECK(vca::confidence_label(10) == "medium");
    CHECK(vca::confidence_label(29) == "medium");
    CHECK(vca::confidence_label(30) == "high");
    CHECK(vca::confidence_label(1000) == "high");
}

// -----------------------------------------------------------------------
// 2. Continuous confidence score
// -----------------------------------------------------------------------
TEST_CASE("confidence_score continuous curve") {
    CHECK(vca::confidence_score(0) == 0.0);
    CHECK(vca::confidence_score(-1) == 0.0);
    // n=3 → 1 - exp(-0.3) ≈ 0.2592
    CHECK(vca::confidence_score(3) == doctest::Approx(0.2592).epsilon(0.0001));
    // n=10 → 1 - exp(-1.0) ≈ 0.6321
    CHECK(vca::confidence_score(10) == doctest::Approx(0.6321).epsilon(0.0001));
    // n=30 → 1 - exp(-3.0) ≈ 0.9502
    CHECK(vca::confidence_score(30) == doctest::Approx(0.9502).epsilon(0.0001));
}

// -----------------------------------------------------------------------
// 3. Empty accumulations → empty snapshot
// -----------------------------------------------------------------------
TEST_CASE("empty accumulations produce empty snapshot") {
    auto snap = vca::build_snapshot({}, 4, 4, 0, 0);
    CHECK(snap.cells_with_data == 0);
    CHECK(snap.cells_with_proposals == 0);
    CHECK(snap.proposals.empty());
    CHECK(snap.cell_corrections.empty());
    CHECK(snap.coverage.rows == 4);
    CHECK(snap.coverage.columns == 4);
    CHECK(snap.coverage.total_count == 16);
    CHECK(snap.coverage.visited_count == 0);
    CHECK(snap.coverage.coverage_ratio() == 0.0);
    // All cells unvisited.
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            CHECK(snap.coverage.cells[r][c].status == "unvisited");
        }
    }
}

// -----------------------------------------------------------------------
// 4. Basic arithmetic mean — Phase 6 baseline (no weighting config)
// -----------------------------------------------------------------------
TEST_CASE("arithmetic mean produces correct proposal") {
    // Cell (1,2) with 5 samples all at cf=1.10 → +10% VE.
    auto cell = make_cell(1, 2, 80.0, {1.10, 1.10, 1.10, 1.10, 1.10});
    auto snap = vca::build_snapshot({cell}, 4, 4, 5, 0);

    REQUIRE(snap.proposals.size() == 1);
    auto& p = snap.proposals[0];
    CHECK(p.row_index == 1);
    CHECK(p.col_index == 2);
    CHECK(p.current_ve == 80.0);
    CHECK(p.proposed_ve == doctest::Approx(88.0).epsilon(0.01));
    CHECK(p.correction_factor == doctest::Approx(1.1).epsilon(0.0001));
    CHECK(p.sample_count == 5);
    CHECK(p.clamp_applied == false);

    // CellCorrection
    REQUIRE(snap.cell_corrections.size() == 1);
    CHECK(snap.cell_corrections[0].confidence == "low");
    CHECK(snap.cell_corrections[0].confidence_score == doctest::Approx(0.3935).epsilon(0.0001));
}

// -----------------------------------------------------------------------
// 5. Below min_samples → no proposal but cell correction present
// -----------------------------------------------------------------------
TEST_CASE("below min_samples produces cell correction but no proposal") {
    auto cell = make_cell(0, 0, 50.0, {1.05, 1.05});  // 2 < 3 default
    auto snap = vca::build_snapshot({cell}, 2, 2, 2, 0);

    CHECK(snap.proposals.empty());
    CHECK(snap.cells_with_proposals == 0);
    REQUIRE(snap.cell_corrections.size() == 1);
    CHECK(snap.cell_corrections[0].sample_count == 2);
    CHECK(snap.cell_corrections[0].confidence == "insufficient");
}

// -----------------------------------------------------------------------
// 6. Per-cell clamp (max_correction_per_cell)
// -----------------------------------------------------------------------
TEST_CASE("per-cell clamp limits correction factor") {
    // cf=1.20 with clamp=0.10 → clamped to 1.10.
    auto cell = make_cell(0, 0, 100.0, {1.20, 1.20, 1.20});
    vca::WeightedCorrectionConfig config;
    config.max_correction_per_cell = 0.10;

    auto snap = vca::build_snapshot({cell}, 2, 2, 3, 0, 3, 0.0, 200.0, &config);

    REQUIRE(snap.proposals.size() == 1);
    auto& p = snap.proposals[0];
    CHECK(p.correction_factor == doctest::Approx(1.10).epsilon(0.0001));
    CHECK(p.clamp_applied == true);
    // raw_correction_factor should be the pre-clamp value.
    CHECK(p.raw_correction_factor == doctest::Approx(1.20).epsilon(0.0001));
    // proposed_ve = 100 × 1.10 = 110.
    CHECK(p.proposed_ve == doctest::Approx(110.0).epsilon(0.01));
}

// -----------------------------------------------------------------------
// 7. Clamp not applied when within bounds
// -----------------------------------------------------------------------
TEST_CASE("clamp not applied when correction is within bounds") {
    auto cell = make_cell(0, 0, 100.0, {1.05, 1.05, 1.05});
    vca::WeightedCorrectionConfig config;
    config.max_correction_per_cell = 0.10;

    auto snap = vca::build_snapshot({cell}, 2, 2, 3, 0, 3, 0.0, 200.0, &config);

    REQUIRE(snap.proposals.size() == 1);
    CHECK(snap.proposals[0].clamp_applied == false);
    CHECK(snap.proposals[0].correction_factor == doctest::Approx(1.05).epsilon(0.0001));
}

// -----------------------------------------------------------------------
// 8. VE min/max clamping
// -----------------------------------------------------------------------
TEST_CASE("proposed VE clamped to ve_min/ve_max") {
    // cf=0.50 on ve=10 → proposed=5, but ve_min=8 → clamped to 8.
    auto cell = make_cell(0, 0, 10.0, {0.50, 0.50, 0.50});
    auto snap = vca::build_snapshot({cell}, 1, 1, 3, 0, 3, 8.0, 200.0);

    REQUIRE(snap.proposals.size() == 1);
    CHECK(snap.proposals[0].proposed_ve == doctest::Approx(8.0).epsilon(0.01));
}

// -----------------------------------------------------------------------
// 9. Sample-age decay weighting
// -----------------------------------------------------------------------
TEST_CASE("sample age decay downweights older samples") {
    vca::CellAccumulation cell;
    cell.row_index = 0;
    cell.col_index = 0;
    cell.current_ve = 100.0;
    // Old sample (t=0): cf=0.90 (rich), recent sample (t=10): cf=1.10 (lean).
    // With decay=0.5/s, the old sample's weight decays by exp(-10*0.5)=exp(-5)≈0.0067.
    // So the recent sample dominates.
    cell.samples.push_back({0.90, 1.0, 0.0});
    cell.samples.push_back({1.10, 1.0, 10.0});

    vca::WeightedCorrectionConfig config;
    config.sample_age_decay_per_second = 0.5;

    auto snap = vca::build_snapshot({cell}, 1, 1, 2, 0, 1, 0.0, 200.0, &config);

    REQUIRE(snap.proposals.size() == 1);
    // The recent sample (1.10) should dominate heavily.
    CHECK(snap.proposals[0].correction_factor > 1.09);
}

// -----------------------------------------------------------------------
// 10. No decay when disabled (default config reproduces Phase 6 mean)
// -----------------------------------------------------------------------
TEST_CASE("default config reproduces Phase 6 arithmetic mean") {
    vca::CellAccumulation cell;
    cell.row_index = 0;
    cell.col_index = 0;
    cell.current_ve = 100.0;
    // Two samples: cf=0.90 and cf=1.10, timestamps differ by 10s.
    cell.samples.push_back({0.90, 1.0, 0.0});
    cell.samples.push_back({1.10, 1.0, 10.0});

    // No config → Phase 6 baseline.
    auto snap = vca::build_snapshot({cell}, 1, 1, 2, 0, 1, 0.0, 200.0);

    REQUIRE(snap.proposals.size() == 1);
    // Arithmetic mean of 0.90 and 1.10 = 1.00.
    CHECK(snap.proposals[0].correction_factor == doctest::Approx(1.0).epsilon(0.0001));
    CHECK(snap.proposals[0].proposed_ve == doctest::Approx(100.0).epsilon(0.01));
}

// -----------------------------------------------------------------------
// 11. Coverage map marks visited and unvisited cells
// -----------------------------------------------------------------------
TEST_CASE("coverage map reflects visited cells") {
    auto cell_00 = make_cell(0, 0, 50.0, {1.05, 1.05, 1.05});
    auto cell_11 = make_cell(1, 1, 60.0, {0.95, 0.95, 0.95});

    auto snap = vca::build_snapshot({cell_00, cell_11}, 2, 2, 6, 0);

    CHECK(snap.coverage.rows == 2);
    CHECK(snap.coverage.columns == 2);
    CHECK(snap.coverage.visited_count == 2);
    CHECK(snap.coverage.total_count == 4);
    CHECK(snap.coverage.coverage_ratio() == doctest::Approx(0.5));

    CHECK(snap.coverage.cells[0][0].status == "visited");
    CHECK(snap.coverage.cells[0][0].sample_count == 3);
    CHECK(snap.coverage.cells[0][1].status == "unvisited");
    CHECK(snap.coverage.cells[1][0].status == "unvisited");
    CHECK(snap.coverage.cells[1][1].status == "visited");
    CHECK(snap.coverage.cells[1][1].sample_count == 3);
}

// -----------------------------------------------------------------------
// 12. Summary text format pin
// -----------------------------------------------------------------------
TEST_CASE("summary text format pinned") {
    auto cell = make_cell(0, 0, 100.0, {1.05, 1.05, 1.05, 1.05, 1.05});
    auto snap = vca::build_snapshot({cell}, 2, 2, 5, 3);

    CHECK(snap.summary_text ==
          "VE Analyze: 5 accepted samples across 1 cell(s); "
          "3 rejected; 1 cell(s) have correction proposals.");
}

// -----------------------------------------------------------------------
// 13. Proposals compose with smoothing service (sub-slice 33)
// -----------------------------------------------------------------------
TEST_CASE("proposals feed directly into ve_proposal_smoothing::smooth") {
    // Build a 2x2 grid with proposals.
    std::vector<vca::CellAccumulation> cells;
    for (int r = 0; r < 2; ++r) {
        for (int c = 0; c < 2; ++c) {
            double cf = (r == 0 && c == 0) ? 1.10 : 1.02;
            cells.push_back(make_cell(r, c, 100.0, {cf, cf, cf}));
        }
    }
    auto snap = vca::build_snapshot(cells, 2, 2, 12, 0);
    REQUIRE(snap.proposals.size() == 4);

    // Feed proposals directly into the smoothing service.
    auto layer = vps::smooth(snap.proposals, {});
    CHECK(layer.smoothed_proposals.size() == 4);
    // The (0,0) spike should be smoothed toward its neighbors.
    for (const auto& p : layer.smoothed_proposals) {
        if (p.row_index == 0 && p.col_index == 0) {
            // Should be pulled from 1.10 toward the 1.02 neighbors.
            CHECK(p.correction_factor < 1.10);
            CHECK(p.correction_factor > 1.02);
        }
    }
}

// -----------------------------------------------------------------------
// 14. Proposals compose with diagnostics service (sub-slice 34)
// -----------------------------------------------------------------------
TEST_CASE("proposals feed directly into ve_root_cause_diagnostics::diagnose") {
    // Build a 4x4 grid with uniform lean bias → should fire injector_flow_error.
    std::vector<vca::CellAccumulation> cells;
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            cells.push_back(make_cell(r, c, 100.0, {1.08, 1.08, 1.08}));
        }
    }
    auto snap = vca::build_snapshot(cells, 4, 4, 48, 0);
    REQUIRE(snap.proposals.size() == 16);

    auto report = rcd::diagnose(snap.proposals);
    // With 16 proposals (≥ MIN_PROPOSALS=6) all uniformly biased at +8%,
    // the injector_flow_error rule should fire.
    CHECK(report.has_findings());
    bool found_injector = false;
    for (const auto& d : report.diagnostics) {
        if (d.rule == "injector_flow_error") found_injector = true;
    }
    CHECK(found_injector);
}

// -----------------------------------------------------------------------
// 15. NaN current_ve → no proposal but cell correction present
// -----------------------------------------------------------------------
TEST_CASE("NaN current_ve produces cell correction but no proposal") {
    vca::CellAccumulation cell;
    cell.row_index = 0;
    cell.col_index = 0;
    cell.current_ve = std::nan("");
    cell.samples.push_back({1.05, 1.0, 0.0});
    cell.samples.push_back({1.05, 1.0, 1.0});
    cell.samples.push_back({1.05, 1.0, 2.0});

    auto snap = vca::build_snapshot({cell}, 1, 1, 3, 0);

    CHECK(snap.proposals.empty());
    REQUIRE(snap.cell_corrections.size() == 1);
    CHECK(snap.cell_corrections[0].sample_count == 3);
    CHECK(std::isnan(snap.cell_corrections[0].current_ve));
}

// -----------------------------------------------------------------------
// 16. Boost penalty applied surfaced in cell correction
// -----------------------------------------------------------------------
TEST_CASE("boost_penalty_applied surfaces in cell correction") {
    vca::CellAccumulation cell;
    cell.row_index = 0;
    cell.col_index = 0;
    cell.current_ve = 100.0;
    cell.boost_penalty_applied = 0.35;
    cell.samples.push_back({1.05, 1.0, 0.0});
    cell.samples.push_back({1.05, 1.0, 1.0});
    cell.samples.push_back({1.05, 1.0, 2.0});

    auto snap = vca::build_snapshot({cell}, 1, 1, 3, 0);

    REQUIRE(snap.cell_corrections.size() == 1);
    CHECK(snap.cell_corrections[0].boost_penalty_applied == doctest::Approx(0.35).epsilon(0.0001));
}

// -----------------------------------------------------------------------
// 17. Input not mutated
// -----------------------------------------------------------------------
TEST_CASE("build_snapshot does not mutate input") {
    auto cell = make_cell(0, 0, 100.0, {1.10, 1.10, 1.10});
    auto copy = cell;

    vca::build_snapshot({cell}, 2, 2, 3, 0);

    CHECK(cell.row_index == copy.row_index);
    CHECK(cell.col_index == copy.col_index);
    CHECK(cell.current_ve == copy.current_ve);
    CHECK(cell.samples.size() == copy.samples.size());
    for (std::size_t i = 0; i < cell.samples.size(); ++i) {
        CHECK(cell.samples[i].correction_factor == copy.samples[i].correction_factor);
        CHECK(cell.samples[i].weight == copy.samples[i].weight);
    }
}

// -----------------------------------------------------------------------
// 18. Multiple cells sorted by (row, col)
// -----------------------------------------------------------------------
TEST_CASE("cells sorted by row then column in output") {
    auto c_12 = make_cell(1, 2, 80.0, {1.05, 1.05, 1.05});
    auto c_00 = make_cell(0, 0, 90.0, {1.02, 1.02, 1.02});
    auto c_10 = make_cell(1, 0, 85.0, {0.98, 0.98, 0.98});

    // Feed in non-sorted order.
    auto snap = vca::build_snapshot({c_12, c_00, c_10}, 2, 3, 9, 0);

    REQUIRE(snap.cell_corrections.size() == 3);
    CHECK(snap.cell_corrections[0].row_index == 0);
    CHECK(snap.cell_corrections[0].col_index == 0);
    CHECK(snap.cell_corrections[1].row_index == 1);
    CHECK(snap.cell_corrections[1].col_index == 0);
    CHECK(snap.cell_corrections[2].row_index == 1);
    CHECK(snap.cell_corrections[2].col_index == 2);
}

// -----------------------------------------------------------------------
// 19. Dwell weight via sample weights
// -----------------------------------------------------------------------
TEST_CASE("dwell weight via sample weights influences mean") {
    // Two samples with different weights: heavy weight on rich sample.
    vca::CellAccumulation cell;
    cell.row_index = 0;
    cell.col_index = 0;
    cell.current_ve = 100.0;
    cell.samples.push_back({1.10, 1.0, 0.0});   // lean, low weight
    cell.samples.push_back({0.90, 5.0, 1.0});   // rich, high weight

    auto snap = vca::build_snapshot({cell}, 1, 1, 2, 0, 1, 0.0, 200.0);

    REQUIRE(snap.proposals.size() == 1);
    // Weighted mean: (1.10*1 + 0.90*5) / (1+5) = 5.60/6 ≈ 0.9333.
    CHECK(snap.proposals[0].correction_factor == doctest::Approx(0.9333).epsilon(0.001));
}
