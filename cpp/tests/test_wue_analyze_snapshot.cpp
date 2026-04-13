// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::wue_analyze_snapshot — thirty-seventh sub-slice
// of the Phase 14 workspace-services port (Slice 4).
//
// Covers: arithmetic mean, min_samples gating, wue_min/max clamping,
// confidence labels, sorted output, summary text, detail text, NaN
// handling, empty input, and rejection breakdown.

#include <doctest.h>

#include "tuner_core/wue_analyze_snapshot.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace was = tuner_core::wue_analyze_snapshot;

// Helper: build a row accumulation with uniform correction factors.
static was::RowAccumulation make_row(int index, double current,
                                      const std::vector<double>& cfs) {
    was::RowAccumulation row;
    row.row_index = index;
    row.current_enrichment = current;
    row.correction_factors = cfs;
    return row;
}

// -----------------------------------------------------------------------
// 1. Empty accumulations → empty snapshot
// -----------------------------------------------------------------------
TEST_CASE("wue: empty accumulations produce empty snapshot") {
    auto snap = was::build_snapshot({}, 0, 0);
    CHECK(snap.rows_with_data == 0);
    CHECK(snap.rows_with_proposals == 0);
    CHECK(snap.proposals.empty());
    CHECK(snap.row_corrections.empty());
    CHECK(snap.summary_text.find("no records") != std::string::npos);
}

// -----------------------------------------------------------------------
// 2. Basic arithmetic mean → correct proposal
// -----------------------------------------------------------------------
TEST_CASE("wue: arithmetic mean produces correct proposal") {
    // Row 2 with 5 samples at cf=1.10 → +10% enrichment.
    auto row = make_row(2, 120.0, {1.10, 1.10, 1.10, 1.10, 1.10});
    auto snap = was::build_snapshot({row}, 5, 0);

    REQUIRE(snap.proposals.size() == 1);
    auto& p = snap.proposals[0];
    CHECK(p.row_index == 2);
    CHECK(p.current_enrichment == 120.0);
    CHECK(p.proposed_enrichment == doctest::Approx(132.0).epsilon(0.01));
    CHECK(p.correction_factor == doctest::Approx(1.1).epsilon(0.0001));
    CHECK(p.sample_count == 5);
}

// -----------------------------------------------------------------------
// 3. Below min_samples → no proposal
// -----------------------------------------------------------------------
TEST_CASE("wue: below min_samples produces no proposal") {
    auto row = make_row(0, 150.0, {1.05, 1.05});  // 2 < 3 default
    auto snap = was::build_snapshot({row}, 2, 0);

    CHECK(snap.proposals.empty());
    REQUIRE(snap.row_corrections.size() == 1);
    CHECK(snap.row_corrections[0].confidence == "insufficient");
}

// -----------------------------------------------------------------------
// 4. WUE min/max clamping
// -----------------------------------------------------------------------
TEST_CASE("wue: proposed enrichment clamped to wue_min/max") {
    // cf=0.50 on 120 → 60, but wue_min=100 → clamped to 100.
    auto row = make_row(0, 120.0, {0.50, 0.50, 0.50});
    auto snap = was::build_snapshot({row}, 3, 0, {}, 3, 100.0, 250.0);

    REQUIRE(snap.proposals.size() == 1);
    CHECK(snap.proposals[0].proposed_enrichment == doctest::Approx(100.0).epsilon(0.01));
}

TEST_CASE("wue: proposed enrichment clamped to wue_max") {
    // cf=2.0 on 150 → 300, but wue_max=250 → clamped to 250.
    auto row = make_row(0, 150.0, {2.0, 2.0, 2.0});
    auto snap = was::build_snapshot({row}, 3, 0, {}, 3, 100.0, 250.0);

    REQUIRE(snap.proposals.size() == 1);
    CHECK(snap.proposals[0].proposed_enrichment == doctest::Approx(250.0).epsilon(0.01));
}

// -----------------------------------------------------------------------
// 5. Confidence labels at thresholds
// -----------------------------------------------------------------------
TEST_CASE("wue: confidence labels match thresholds") {
    std::vector<was::RowAccumulation> rows = {
        make_row(0, 100.0, {1.0}),                             // 1 → insufficient
        make_row(1, 100.0, {1.0, 1.0, 1.0}),                   // 3 → low
        make_row(2, 100.0, std::vector<double>(10, 1.0)),       // 10 → medium
        make_row(3, 100.0, std::vector<double>(30, 1.0)),       // 30 → high
    };
    auto snap = was::build_snapshot(rows, 44, 0);

    REQUIRE(snap.row_corrections.size() == 4);
    CHECK(snap.row_corrections[0].confidence == "insufficient");
    CHECK(snap.row_corrections[1].confidence == "low");
    CHECK(snap.row_corrections[2].confidence == "medium");
    CHECK(snap.row_corrections[3].confidence == "high");
}

// -----------------------------------------------------------------------
// 6. Rows sorted by index in output
// -----------------------------------------------------------------------
TEST_CASE("wue: rows sorted by index") {
    auto r3 = make_row(3, 100.0, {1.05, 1.05, 1.05});
    auto r0 = make_row(0, 100.0, {1.02, 1.02, 1.02});
    auto r1 = make_row(1, 100.0, {0.98, 0.98, 0.98});

    // Feed in non-sorted order.
    auto snap = was::build_snapshot({r3, r0, r1}, 9, 0);

    REQUIRE(snap.row_corrections.size() == 3);
    CHECK(snap.row_corrections[0].row_index == 0);
    CHECK(snap.row_corrections[1].row_index == 1);
    CHECK(snap.row_corrections[2].row_index == 3);
}

// -----------------------------------------------------------------------
// 7. Summary text format pin
// -----------------------------------------------------------------------
TEST_CASE("wue: summary text format pinned") {
    auto row = make_row(0, 100.0, {1.05, 1.05, 1.05});
    auto snap = was::build_snapshot({row}, 3, 2);

    CHECK(snap.summary_text ==
          "WUE Analyze reviewed 5 record(s): "
          "3 accepted, 2 rejected, "
          "1 row proposal(s) of 1 with data.");
}

// -----------------------------------------------------------------------
// 8. NaN current_enrichment → no proposal
// -----------------------------------------------------------------------
TEST_CASE("wue: NaN current_enrichment produces no proposal") {
    was::RowAccumulation row;
    row.row_index = 0;
    row.current_enrichment = std::nan("");
    row.correction_factors = {1.05, 1.05, 1.05};

    auto snap = was::build_snapshot({row}, 3, 0);

    CHECK(snap.proposals.empty());
    REQUIRE(snap.row_corrections.size() == 1);
    CHECK(std::isnan(snap.row_corrections[0].current_enrichment));
}

// -----------------------------------------------------------------------
// 9. Rejection breakdown in detail lines
// -----------------------------------------------------------------------
TEST_CASE("wue: rejection breakdown in detail lines") {
    auto row = make_row(0, 100.0, {1.05, 1.05, 1.05});
    std::vector<std::pair<std::string, int>> rejections = {
        {"accelFilter", 4},
        {"std_DeadLambda", 2},
    };
    auto snap = was::build_snapshot({row}, 3, 6, rejections);

    bool found_rejections = false;
    for (const auto& line : snap.detail_lines) {
        if (line.find("accelFilter=4") != std::string::npos &&
            line.find("std_DeadLambda=2") != std::string::npos) {
            found_rejections = true;
        }
    }
    CHECK(found_rejections);
}

// -----------------------------------------------------------------------
// 10. No corrections proposed text
// -----------------------------------------------------------------------
TEST_CASE("wue: no corrections text when no proposals") {
    auto row = make_row(0, 100.0, {1.0});  // 1 < 3, cf=1.0
    auto snap = was::build_snapshot({row}, 1, 0);

    bool found = false;
    for (const auto& line : snap.detail_lines) {
        if (line.find("No corrections proposed") != std::string::npos) found = true;
    }
    CHECK(found);
}

// -----------------------------------------------------------------------
// 11. Detail lines contain lean correction preview
// -----------------------------------------------------------------------
TEST_CASE("wue: detail lines contain lean correction preview") {
    auto row = make_row(0, 120.0, {1.10, 1.10, 1.10});
    auto snap = was::build_snapshot({row}, 3, 0);

    bool found = false;
    for (const auto& line : snap.detail_lines) {
        if (line.find("Largest lean corrections:") != std::string::npos) found = true;
    }
    CHECK(found);
}

// -----------------------------------------------------------------------
// 12. Input not mutated
// -----------------------------------------------------------------------
TEST_CASE("wue: build_snapshot does not mutate input") {
    auto row = make_row(0, 100.0, {1.10, 1.10, 1.10});
    auto copy = row;

    was::build_snapshot({row}, 3, 0);

    CHECK(row.row_index == copy.row_index);
    CHECK(row.current_enrichment == copy.current_enrichment);
    CHECK(row.correction_factors.size() == copy.correction_factors.size());
}
