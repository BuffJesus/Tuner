// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/ve_analyze_accumulator.hpp"

namespace vaa = tuner_core::ve_analyze_accumulator;

static vaa::TableSnapshot make_4x4_table() {
    vaa::TableSnapshot t;
    t.x_param_name = "rpmBins";
    t.y_param_name = "mapBins";
    t.x_labels = {"1000", "2000", "3000", "4000"};
    t.y_labels = {"30", "50", "70", "100"};
    t.cells.resize(4);
    for (int r = 0; r < 4; ++r) {
        t.cells[r].resize(4);
        for (int c = 0; c < 4; ++c) {
            t.cells[r][c] = std::to_string(60 + r * 5 + c * 3);
        }
    }
    return t;
}

TEST_SUITE("ve_analyze_accumulator") {

TEST_CASE("rejects record without lambda") {
    vaa::Accumulator acc;
    auto table = make_4x4_table();
    vaa::Record rec; rec.values = {{"rpm", 2500}, {"map", 60}};
    CHECK_FALSE(acc.add_record(rec, table));
    CHECK(acc.rejected_count() == 1);
}

TEST_CASE("accepts valid record with lambda") {
    vaa::Accumulator acc;
    auto table = make_4x4_table();
    vaa::Record rec; rec.values = {{"rpm", 2500}, {"map", 60}, {"lambda1", 1.05}};
    rec.timestamp_seconds = 100.0;
    CHECK(acc.add_record(rec, table));
    CHECK(acc.accepted_count() == 1);
}

TEST_CASE("AFR auto-converts to lambda") {
    vaa::Accumulator acc;
    auto table = make_4x4_table();
    vaa::Record rec; rec.values = {{"rpm", 2500}, {"map", 60}, {"afr1", 15.4}};
    CHECK(acc.add_record(rec, table));
}

TEST_CASE("snapshot produces proposals above min samples") {
    vaa::Accumulator acc;
    auto table = make_4x4_table();
    // Feed 5 records at rpm=2500, map=60 (should land near cell [1][1])
    for (int i = 0; i < 5; ++i) {
        vaa::Record rec;
        rec.values = {{"rpm", 2500}, {"map", 60}, {"lambda1", 1.10}};
        rec.timestamp_seconds = 100.0 + i;
        acc.add_record(rec, table);
    }
    auto snap = acc.snapshot(table, 3, 0, 200);
    CHECK(snap.proposals.size() >= 1);
    // Correction should be ~1.10 (10% lean)
    bool found_lean = false;
    for (const auto& p : snap.proposals) {
        if (p.correction_factor > 1.05) found_lean = true;
    }
    CHECK(found_lean);
}

TEST_CASE("snapshot gates below min samples") {
    vaa::Accumulator acc;
    auto table = make_4x4_table();
    vaa::Record rec; rec.values = {{"rpm", 2500}, {"map", 60}, {"lambda1", 1.05}};
    acc.add_record(rec, table);
    auto snap = acc.snapshot(table, 3);
    CHECK(snap.proposals.empty());
}

TEST_CASE("reset clears state") {
    vaa::Accumulator acc;
    auto table = make_4x4_table();
    vaa::Record rec; rec.values = {{"rpm", 2500}, {"map", 60}, {"lambda1", 1.0}};
    acc.add_record(rec, table);
    CHECK(acc.accepted_count() == 1);
    acc.reset();
    CHECK(acc.accepted_count() == 0);
}

TEST_CASE("coverage includes all table cells") {
    vaa::Accumulator acc;
    auto table = make_4x4_table();
    for (int i = 0; i < 5; ++i) {
        vaa::Record rec; rec.values = {{"rpm", 2500}, {"map", 60}, {"lambda1", 1.0}};
        acc.add_record(rec, table);
    }
    auto snap = acc.snapshot(table, 1);
    CHECK(snap.coverage.total_count == 16);
    CHECK(snap.coverage.visited_count >= 1);
}

TEST_CASE("summary text contains record counts") {
    vaa::Accumulator acc;
    auto table = make_4x4_table();
    for (int i = 0; i < 10; ++i) {
        vaa::Record rec; rec.values = {{"rpm", 2500}, {"map", 60}, {"lambda1", 1.05}};
        acc.add_record(rec, table);
    }
    // Also reject some
    vaa::Record bad; bad.values = {{"rpm", 2500}};
    acc.add_record(bad, table);
    acc.add_record(bad, table);

    auto snap = acc.snapshot(table, 3);
    CHECK(snap.summary_text.find("10 accepted") != std::string::npos);
}

}  // TEST_SUITE
