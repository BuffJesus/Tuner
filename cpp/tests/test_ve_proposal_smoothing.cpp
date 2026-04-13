// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::ve_proposal_smoothing.
// Phase 7 Slice 7.5 parity coverage on the C++ side.

#include "doctest.h"

#include "tuner_core/ve_proposal_smoothing.hpp"

#include <cmath>

namespace vps = tuner_core::ve_proposal_smoothing;

namespace {

vps::Proposal make(int r, int c, double cur, double prop, double cf, int n) {
    vps::Proposal p;
    p.row_index = r;
    p.col_index = c;
    p.current_ve = cur;
    p.proposed_ve = prop;
    p.correction_factor = cf;
    p.sample_count = n;
    p.raw_correction_factor = cf;
    p.clamp_applied = false;
    return p;
}

}  // namespace

TEST_CASE("empty proposals returns empty layer with no-op summary") {
    auto layer = vps::smooth({}, {});
    CHECK(layer.smoothed_proposals.empty());
    CHECK(layer.unchanged_count == 0);
    CHECK(layer.smoothed_count == 0);
    CHECK(layer.summary_text == "No proposals to smooth.");
}

TEST_CASE("kernel_radius < 1 is the documented identity transform") {
    std::vector<vps::Proposal> proposals{
        make(0, 0, 80.0, 82.0, 1.025, 5),
        make(0, 1, 81.0, 83.0, 1.024, 4),
    };
    vps::SmoothingConfig cfg;
    cfg.kernel_radius = 0;
    auto layer = vps::smooth(proposals, cfg);
    CHECK(layer.smoothed_proposals.size() == 2);
    CHECK(layer.unchanged_count == 2);
    CHECK(layer.smoothed_count == 0);
    CHECK(layer.summary_text.find("identity transform") != std::string::npos);
    // Pass-through must be byte-identical.
    CHECK(layer.smoothed_proposals[0].proposed_ve == doctest::Approx(82.0));
    CHECK(layer.smoothed_proposals[1].proposed_ve == doctest::Approx(83.0));
}

TEST_CASE("isolated cell with no neighbors is preserved unchanged") {
    std::vector<vps::Proposal> proposals{
        make(5, 5, 80.0, 84.0, 1.05, 3),
    };
    auto layer = vps::smooth(proposals, {});
    CHECK(layer.unchanged_count == 1);
    CHECK(layer.smoothed_count == 0);
    CHECK(layer.smoothed_proposals[0].proposed_ve == doctest::Approx(84.0));
}

TEST_CASE("min_neighbors gate preserves cells below the threshold") {
    // 1+1 layout: a cell with exactly one neighbor. min_neighbors=2
    // forces both to be preserved.
    std::vector<vps::Proposal> proposals{
        make(0, 0, 80.0, 84.0, 1.05, 3),
        make(0, 1, 80.0, 80.0, 1.00, 3),
    };
    vps::SmoothingConfig cfg;
    cfg.kernel_radius = 1;
    cfg.min_neighbors = 2;
    auto layer = vps::smooth(proposals, cfg);
    CHECK(layer.unchanged_count == 2);
    CHECK(layer.smoothed_count == 0);
}

TEST_CASE("3x3 spike is smoothed by uniform neighbors") {
    // Center cell at (1,1) is the spike (cf=1.10); 8 neighbors at cf=1.00.
    std::vector<vps::Proposal> proposals;
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 3; ++c) {
            if (r == 1 && c == 1) {
                proposals.push_back(make(r, c, 100.0, 110.0, 1.10, 1));
            } else {
                proposals.push_back(make(r, c, 100.0, 100.0, 1.00, 1));
            }
        }
    }
    auto layer = vps::smooth(proposals, {});
    // The center cell should be averaged toward the neighbors.
    // Window = 9 cells, all weight=1: avg_cf = (1.10 + 8*1.00)/9 ≈ 1.0111
    // new proposed = round(100 * 1.0111, 2) = 101.11
    // The 8 neighbor cells stay at proposed=100 (their window has 8
    // cells at 1.00 + the spike at 1.10: avg = (8*1.00 + 1.10)/9 ≈ 1.0111
    // → new proposed = 101.11 ≠ 100.00 → modified).
    // So all 9 cells are modified.
    CHECK(layer.smoothed_count == 9);
    CHECK(layer.unchanged_count == 0);
    // Center cell new proposed value:
    bool found_center = false;
    for (const auto& p : layer.smoothed_proposals) {
        if (p.row_index == 1 && p.col_index == 1) {
            CHECK(p.proposed_ve == doctest::Approx(101.11).epsilon(0.001));
            // raw_correction_factor preserves the original 1.10.
            CHECK(p.raw_correction_factor == doctest::Approx(1.10));
            found_center = true;
        }
    }
    CHECK(found_center);
}

TEST_CASE("sample-count weighting prevents low-confidence pull") {
    // Anchor at (0,0): cf=1.20, sample_count=100 (high confidence).
    // Neighbor at (0,1): cf=1.00, sample_count=1 (low confidence).
    // Weighted avg from the anchor's POV: (1.20*100 + 1.00*1) / 101
    //                                    = 121 / 101 ≈ 1.198
    // → new proposed at anchor = round(100 * 1.198, 2) = 119.80,
    //   barely moved from the raw 120.00 → diff = 0.20 > 0.01 → modified.
    std::vector<vps::Proposal> proposals{
        make(0, 0, 100.0, 120.0, 1.20, 100),
        make(0, 1, 100.0, 100.0, 1.00, 1),
    };
    auto layer = vps::smooth(proposals, {});
    for (const auto& p : layer.smoothed_proposals) {
        if (p.row_index == 0 && p.col_index == 0) {
            CHECK(p.proposed_ve == doctest::Approx(119.80).epsilon(0.01));
        }
    }
}

TEST_CASE("preserve_edge_magnitude leaves the strongest deviation alone") {
    // Anchor (0,0) is the strongest deviation; with the flag set it
    // should stay raw while neighbors smooth toward it.
    std::vector<vps::Proposal> proposals{
        make(0, 0, 100.0, 130.0, 1.30, 5),
        make(0, 1, 100.0, 100.0, 1.00, 5),
    };
    vps::SmoothingConfig cfg;
    cfg.kernel_radius = 1;
    cfg.min_neighbors = 1;
    cfg.preserve_edge_magnitude = true;
    auto layer = vps::smooth(proposals, cfg);
    for (const auto& p : layer.smoothed_proposals) {
        if (p.row_index == 0 && p.col_index == 0) {
            // Strongest deviation — preserved.
            CHECK(p.proposed_ve == doctest::Approx(130.0));
            CHECK(p.correction_factor == doctest::Approx(1.30));
        }
    }
}

TEST_CASE("near-zero diff cells are preserved to keep the diff minimal") {
    // Two cells with identical cf — smoothing produces the same value
    // back, so the cell should pass through as unchanged rather than
    // being marked modified.
    std::vector<vps::Proposal> proposals{
        make(0, 0, 100.0, 105.0, 1.05, 5),
        make(0, 1, 100.0, 105.0, 1.05, 5),
    };
    auto layer = vps::smooth(proposals, {});
    CHECK(layer.smoothed_count == 0);
    CHECK(layer.unchanged_count == 2);
}

TEST_CASE("input proposals are never mutated") {
    std::vector<vps::Proposal> proposals;
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 3; ++c) {
            double cf = (r == 1 && c == 1) ? 1.10 : 1.00;
            double prop = (r == 1 && c == 1) ? 110.0 : 100.0;
            proposals.push_back(make(r, c, 100.0, prop, cf, 1));
        }
    }
    auto layer = vps::smooth(proposals, {});
    // The input vector still holds the spike at (1,1) with cf=1.10.
    CHECK(proposals[4].correction_factor == doctest::Approx(1.10));
    CHECK(proposals[4].proposed_ve == doctest::Approx(110.0));
    CHECK(layer.smoothed_proposals.size() == proposals.size());
}

TEST_CASE("summary text format pin") {
    std::vector<vps::Proposal> proposals;
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 3; ++c) {
            double cf = (r == 1 && c == 1) ? 1.10 : 1.00;
            double prop = (r == 1 && c == 1) ? 110.0 : 100.0;
            proposals.push_back(make(r, c, 100.0, prop, cf, 1));
        }
    }
    auto layer = vps::smooth(proposals, {});
    CHECK(layer.summary_text ==
          "Smoothed 9 proposal(s); 0 preserved unchanged "
          "(kernel radius 1, min_neighbors 1).");
}
