// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::wue_analyze_review — thirty-eighth sub-slice.

#include <doctest.h>

#include "tuner_core/wue_analyze_review.hpp"
#include "tuner_core/wue_analyze_snapshot.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace war = tuner_core::wue_analyze_review;
namespace was = tuner_core::wue_analyze_snapshot;

static was::RowAccumulation make_row(int index, double current,
                                      const std::vector<double>& cfs) {
    was::RowAccumulation row;
    row.row_index = index;
    row.current_enrichment = current;
    row.correction_factors = cfs;
    return row;
}

// -----------------------------------------------------------------------
// 1. Zero records summary
// -----------------------------------------------------------------------
TEST_CASE("wue review: zero records summary") {
    was::Snapshot snap;
    snap.summary_text = "WUE Analyze: no records to review.";
    auto review = war::build(snap);
    CHECK(review.summary_text.find("no records") != std::string::npos);
}

// -----------------------------------------------------------------------
// 2. Summary text forwarded from snapshot
// -----------------------------------------------------------------------
TEST_CASE("wue review: summary text forwarded") {
    auto row = make_row(0, 120.0, {1.05, 1.05, 1.05});
    auto snap = was::build_snapshot({row}, 3, 1);
    auto review = war::build(snap);

    CHECK(review.summary_text == snap.summary_text);
}

// -----------------------------------------------------------------------
// 3. Confidence distribution
// -----------------------------------------------------------------------
TEST_CASE("wue review: confidence distribution") {
    std::vector<was::RowAccumulation> rows = {
        make_row(0, 100.0, {1.0}),                             // insufficient
        make_row(1, 100.0, {1.0, 1.0, 1.0}),                   // low
        make_row(2, 100.0, std::vector<double>(10, 1.0)),       // medium
        make_row(3, 100.0, std::vector<double>(30, 1.0)),       // high
    };
    auto snap = was::build_snapshot(rows, 44, 0);
    auto review = war::build(snap);

    REQUIRE(review.confidence_distribution.size() == 4);
    CHECK(review.confidence_distribution[0] == std::make_pair(std::string("insufficient"), 1));
    CHECK(review.confidence_distribution[1] == std::make_pair(std::string("low"), 1));
    CHECK(review.confidence_distribution[2] == std::make_pair(std::string("medium"), 1));
    CHECK(review.confidence_distribution[3] == std::make_pair(std::string("high"), 1));
}

// -----------------------------------------------------------------------
// 4. Largest lean corrections sorted descending
// -----------------------------------------------------------------------
TEST_CASE("wue review: lean corrections sorted descending") {
    std::vector<was::RowAccumulation> rows = {
        make_row(0, 120.0, {1.05, 1.05, 1.05}),
        make_row(1, 120.0, {1.15, 1.15, 1.15}),
        make_row(2, 120.0, {1.10, 1.10, 1.10}),
    };
    auto snap = was::build_snapshot(rows, 9, 0);
    auto review = war::build(snap);

    REQUIRE(review.largest_lean_corrections.size() == 3);
    CHECK(review.largest_lean_corrections[0].correction_factor >
          review.largest_lean_corrections[1].correction_factor);
    CHECK(review.largest_lean_corrections[1].correction_factor >
          review.largest_lean_corrections[2].correction_factor);
}

// -----------------------------------------------------------------------
// 5. Largest rich corrections sorted ascending
// -----------------------------------------------------------------------
TEST_CASE("wue review: rich corrections sorted ascending") {
    std::vector<was::RowAccumulation> rows = {
        make_row(0, 120.0, {0.95, 0.95, 0.95}),
        make_row(1, 120.0, {0.85, 0.85, 0.85}),
        make_row(2, 120.0, {0.90, 0.90, 0.90}),
    };
    auto snap = was::build_snapshot(rows, 9, 0, {}, 3, 50.0, 250.0);
    auto review = war::build(snap);

    REQUIRE(review.largest_rich_corrections.size() == 3);
    CHECK(review.largest_rich_corrections[0].correction_factor <
          review.largest_rich_corrections[1].correction_factor);
}

// -----------------------------------------------------------------------
// 6. Rows insufficient count
// -----------------------------------------------------------------------
TEST_CASE("wue review: rows_insufficient counts") {
    std::vector<was::RowAccumulation> rows = {
        make_row(0, 120.0, {1.05}),                // insufficient
        make_row(1, 120.0, {1.05, 1.05}),           // insufficient
        make_row(2, 120.0, {1.05, 1.05, 1.05}),     // has proposal
    };
    auto snap = was::build_snapshot(rows, 6, 0);
    auto review = war::build(snap);

    CHECK(review.rows_insufficient == 2);
    CHECK(review.detail_text.find("Rows skipped") != std::string::npos);
}

// -----------------------------------------------------------------------
// 7. No corrections text
// -----------------------------------------------------------------------
TEST_CASE("wue review: no corrections text") {
    auto row = make_row(0, 100.0, {1.0});
    auto snap = was::build_snapshot({row}, 1, 0);
    auto review = war::build(snap);

    CHECK(review.detail_text.find("No corrections proposed") != std::string::npos);
}

// -----------------------------------------------------------------------
// 8. Detail text contains lean preview
// -----------------------------------------------------------------------
TEST_CASE("wue review: detail has lean correction preview") {
    auto row = make_row(0, 120.0, {1.10, 1.10, 1.10});
    auto snap = was::build_snapshot({row}, 3, 0);
    auto review = war::build(snap);

    CHECK(review.detail_text.find("Largest lean corrections:") != std::string::npos);
}

// -----------------------------------------------------------------------
// 9. Preview capped at 5
// -----------------------------------------------------------------------
TEST_CASE("wue review: preview capped at 5") {
    std::vector<was::RowAccumulation> rows;
    for (int i = 0; i < 8; ++i) {
        double cf = 1.0 + 0.01 * (i + 1);
        rows.push_back(make_row(i, 120.0, {cf, cf, cf}));
    }
    auto snap = was::build_snapshot(rows, 24, 0);
    auto review = war::build(snap);

    CHECK(review.largest_lean_corrections.size() == 5);
    CHECK(review.max_preview_entries == 5);
}
