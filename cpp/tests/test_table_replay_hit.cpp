// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::table_replay_hit.

#include "doctest.h"

#include "tuner_core/table_replay_hit.hpp"

#include <vector>

// Argument-dependent lookup pulls `table_replay_context::build` into
// scope through the `TablePageSnapshot` argument type. Use a
// namespace alias and call `trh::build(...)` explicitly to disambiguate.
namespace trh = tuner_core::table_replay_hit;
using trh::HitCellSnapshot;
using trh::HitSummarySnapshot;
using trh::PreRejected;
using trh::Record;
using TablePageSnapshot = tuner_core::table_replay_context::TablePageSnapshot;

namespace {

TablePageSnapshot make_snapshot() {
    TablePageSnapshot s;
    s.x_parameter_name = "rpmBins";
    s.y_parameter_name = "mapBins";
    s.x_labels = {"1000", "2000", "3000", "4000"};
    s.y_labels = {"50", "100", "150"};
    s.cells = {
        {"a1", "a2", "a3", "a4"},
        {"b1", "b2", "b3", "b4"},
        {"c1", "c2", "c3", "c4"},
    };
    return s;
}

Record make_record(double rpm, double map, std::optional<double> afr = std::nullopt) {
    Record r;
    r.values = {{"rpm", rpm}, {"map", map}};
    if (afr.has_value()) r.values.push_back({"afr", *afr});
    return r;
}

}  // namespace

TEST_CASE("build: empty records returns nullopt") {
    auto r = trh::build(make_snapshot(), {});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("build: empty cells returns nullopt") {
    TablePageSnapshot s;
    s.x_parameter_name = "rpmBins";
    s.y_parameter_name = "mapBins";
    auto r = trh::build(s, {make_record(2000, 75)});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("build: non-numeric axis returns nullopt") {
    auto s = make_snapshot();
    s.x_labels = {"low", "mid", "high", "max"};
    auto r = trh::build(s, {make_record(2000, 75)});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("build: simple aggregation lands in nearest cell") {
    std::vector<Record> records{
        make_record(1900, 95),  // → row 1 (100), col 1 (2000)
        make_record(2100, 105), // → row 1 (100), col 1 (2000)
        make_record(3100, 145), // → row 2 (150), col 2 (3000)
    };
    auto r = trh::build(make_snapshot(), records);
    REQUIRE(r.has_value());
    CHECK(r->accepted_row_count == 3);
    CHECK(r->rejected_row_count == 0);
    REQUIRE(r->hot_cells.size() == 2);
    CHECK(r->hot_cells[0].hit_count == 2);  // top hot cell
    CHECK(r->hot_cells[0].row_index == 1);
    CHECK(r->hot_cells[0].column_index == 1);
}

TEST_CASE("build: AFR averages per cell") {
    std::vector<Record> records{
        make_record(2000, 100, 14.0),
        make_record(2000, 100, 14.4),
    };
    auto r = trh::build(make_snapshot(), records);
    REQUIRE(r.has_value());
    REQUIRE(r->hot_cells.size() == 1);
    REQUIRE(r->hot_cells[0].mean_afr.has_value());
    CHECK(*r->hot_cells[0].mean_afr == doctest::Approx(14.2));
}

TEST_CASE("build: unmappable axes accumulate as rejected") {
    Record bad;
    bad.values = {{"clt", 90}};  // no rpm/map
    std::vector<Record> records{
        make_record(2000, 100),
        bad,
        bad,
    };
    auto r = trh::build(make_snapshot(), records);
    REQUIRE(r.has_value());
    CHECK(r->accepted_row_count == 1);
    CHECK(r->rejected_row_count == 2);
    REQUIRE(r->rejected_reason_counts.size() == 1);
    CHECK(r->rejected_reason_counts[0].first == "unmappable_axes");
    CHECK(r->rejected_reason_counts[0].second == 2);
}

TEST_CASE("build: pre_rejected merges into the final summary") {
    PreRejected pre;
    pre.count = 5;
    pre.reasons["std_DeadLambda"] = 3;
    pre.reasons["minRPM"] = 2;
    auto r = trh::build(
        make_snapshot(), {make_record(2000, 100)}, pre);
    REQUIRE(r.has_value());
    CHECK(r->rejected_row_count == 5);
    REQUIRE(r->rejected_reason_counts.size() == 2);
    // sorted alphabetically
    CHECK(r->rejected_reason_counts[0].first == "minRPM");
    CHECK(r->rejected_reason_counts[1].first == "std_DeadLambda");
}

TEST_CASE("build: hot cells sorted descending by hit count") {
    std::vector<Record> records;
    // Cell (0,0): 5 hits  — at (rpm=1000, map=50)
    for (int i = 0; i < 5; ++i) records.push_back(make_record(1000, 50));
    // Cell (1,1): 3 hits
    for (int i = 0; i < 3; ++i) records.push_back(make_record(2000, 100));
    // Cell (2,2): 1 hit
    records.push_back(make_record(3000, 150));
    auto r = trh::build(make_snapshot(), records);
    REQUIRE(r.has_value());
    REQUIRE(r->hot_cells.size() == 3);
    CHECK(r->hot_cells[0].hit_count == 5);
    CHECK(r->hot_cells[1].hit_count == 3);
    CHECK(r->hot_cells[2].hit_count == 1);
}

TEST_CASE("build: top 3 cells only when more than 3 distinct cells") {
    std::vector<Record> records{
        make_record(1000, 50),
        make_record(2000, 50),
        make_record(3000, 50),
        make_record(4000, 50),
    };
    auto r = trh::build(make_snapshot(), records);
    REQUIRE(r.has_value());
    CHECK(r->hot_cells.size() == 3);
    CHECK(r->accepted_row_count == 4);
}

TEST_CASE("build: summary text format") {
    auto r = trh::build(make_snapshot(), {make_record(2000, 100, 14.7)});
    REQUIRE(r.has_value());
    CHECK(r->summary_text.find("found 1 mappable row(s) across 1 table cell(s)")
          != std::string::npos);
    CHECK(r->detail_text.find("mean AFR 14.70") != std::string::npos);
}
