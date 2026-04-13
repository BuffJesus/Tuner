// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/wue_analyze_accumulator.hpp"

namespace waa = tuner_core::wue_analyze_accumulator;

TEST_SUITE("wue_analyze_accumulator") {

TEST_CASE("detect_clt_axis from y parameter name") {
    auto axis = waa::detect_clt_axis("rpmBins", "coolantBins",
        {"500", "1000", "2000"}, {"-20", "0", "20", "40", "60", "80"});
    REQUIRE(axis.has_value());
    CHECK(axis->along_y == true);
    CHECK(axis->bins.size() == 6);
}

TEST_CASE("detect_clt_axis from x parameter name") {
    auto axis = waa::detect_clt_axis("cltBins", "values",
        {"-20", "0", "20", "40"}, {"100"});
    REQUIRE(axis.has_value());
    CHECK(axis->along_y == false);
    CHECK(axis->bins.size() == 4);
}

TEST_CASE("detect_clt_axis returns nullopt for non-CLT axes") {
    auto axis = waa::detect_clt_axis("rpmBins", "loadBins",
        {}, {});
    CHECK_FALSE(axis.has_value());
}

TEST_CASE("accumulator rejects record without lambda") {
    waa::Accumulator acc;
    waa::TableAxis axis; axis.bins = {-20, 0, 20, 40, 60, 80}; axis.along_y = true;
    waa::Record rec; rec.values = {{"coolant", 35.0}};  // no lambda
    CHECK_FALSE(acc.add_record(rec, axis, {}));
    CHECK(acc.rejected_count() == 1);
}

TEST_CASE("accumulator rejects record without CLT") {
    waa::Accumulator acc;
    waa::TableAxis axis; axis.bins = {-20, 0, 20, 40, 60, 80}; axis.along_y = true;
    waa::Record rec; rec.values = {{"lambda1", 1.05}};  // no CLT
    CHECK_FALSE(acc.add_record(rec, axis, {}));
    CHECK(acc.rejected_count() == 1);
}

TEST_CASE("accumulator accepts valid record") {
    waa::Accumulator acc;
    waa::TableAxis axis; axis.bins = {-20, 0, 20, 40, 60, 80}; axis.along_y = true;
    waa::Record rec; rec.values = {{"lambda1", 1.05}, {"coolant", 35.0}};
    CHECK(acc.add_record(rec, axis, {}));
    CHECK(acc.accepted_count() == 1);
}

TEST_CASE("snapshot produces proposals for cells above min samples") {
    waa::Accumulator acc;
    waa::TableAxis axis; axis.bins = {-20, 0, 20, 40, 60, 80}; axis.along_y = true;
    std::vector<std::string> cells = {"180", "160", "140", "120", "110", "100"};

    // Feed 5 records at CLT=35 (nearest bin index 3 = 40°C)
    for (int i = 0; i < 5; ++i) {
        waa::Record rec; rec.values = {{"lambda1", 1.08}, {"coolant", 35.0}};
        acc.add_record(rec, axis, cells);
    }

    auto snap = acc.snapshot(cells, 3, 100.0, 250.0);
    CHECK(snap.proposals.size() == 1);
    CHECK(snap.proposals[0].row_index == 3);
    // correction = 1.08/1.0 = 1.08, current = 120, proposed = 120 * 1.08 = 129.6
    CHECK(snap.proposals[0].proposed_enrichment > 125);
    CHECK(snap.proposals[0].proposed_enrichment < 135);
}

TEST_CASE("snapshot gates below min samples") {
    waa::Accumulator acc;
    waa::TableAxis axis; axis.bins = {-20, 0, 20}; axis.along_y = true;
    std::vector<std::string> cells = {"180", "150", "120"};

    // Only 1 record — below min_samples=3
    waa::Record rec; rec.values = {{"lambda1", 1.1}, {"coolant", 15.0}};
    acc.add_record(rec, axis, cells);

    auto snap = acc.snapshot(cells, 3);
    CHECK(snap.proposals.empty());
    CHECK(snap.row_corrections.size() == 1);
    CHECK(snap.row_corrections[0].confidence == "insufficient");
}

TEST_CASE("reset clears all state") {
    waa::Accumulator acc;
    waa::TableAxis axis; axis.bins = {0, 50, 100}; axis.along_y = true;
    waa::Record rec; rec.values = {{"lambda1", 1.0}, {"coolant", 50.0}};
    acc.add_record(rec, axis, {});
    CHECK(acc.accepted_count() == 1);
    acc.reset();
    CHECK(acc.accepted_count() == 0);
    CHECK(acc.rejected_count() == 0);
}

TEST_CASE("AFR auto-converts to lambda") {
    waa::Accumulator acc;
    waa::TableAxis axis; axis.bins = {0, 50}; axis.along_y = true;
    // AFR 14.7 / 14.7 = lambda 1.0
    waa::Record rec; rec.values = {{"afr1", 14.7}, {"coolant", 25.0}};
    CHECK(acc.add_record(rec, axis, {}));
}

TEST_CASE("summary text format") {
    waa::Accumulator acc;
    waa::TableAxis axis; axis.bins = {0, 50}; axis.along_y = true;
    for (int i = 0; i < 10; ++i) {
        waa::Record rec; rec.values = {{"lambda1", 1.05}, {"coolant", 25.0}};
        acc.add_record(rec, axis, {"150", "100"});
    }
    auto snap = acc.snapshot({"150", "100"}, 3);
    CHECK(snap.summary_text.find("10 record(s)") != std::string::npos);
    CHECK(snap.summary_text.find("10 accepted") != std::string::npos);
}

}  // TEST_SUITE
