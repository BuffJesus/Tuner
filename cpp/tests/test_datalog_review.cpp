// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::datalog_review.

#include "doctest.h"

#include "tuner_core/datalog_review.hpp"

#include <stdexcept>

namespace dr = tuner_core::datalog_review;

namespace {

dr::Record make_record(double t, std::initializer_list<std::pair<std::string, double>> values) {
    dr::Record r;
    r.timestamp_seconds = t;
    for (const auto& kv : values) r.values.push_back(kv);
    return r;
}

}  // namespace

TEST_CASE("build throws on empty records") {
    CHECK_THROWS_AS(dr::build({}, 0), std::invalid_argument);
}

TEST_CASE("build clamps selected_index into range") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"rpm", 1000.0}}),
        make_record(0.5, {{"rpm", 1500.0}}),
    };
    auto snap = dr::build(records, 99);
    CHECK(snap.selected_index == 1);
    CHECK(snap.marker_x == doctest::Approx(0.5));
}

TEST_CASE("priority heuristic picks rpm/map/tps in priority order") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"misc", 1.0}, {"tps", 0.0}, {"rpm", 1000.0}, {"map", 30.0}}),
        make_record(0.1, {{"misc", 2.0}, {"tps", 5.0}, {"rpm", 1500.0}, {"map", 35.0}}),
    };
    auto snap = dr::build(records, 0);
    REQUIRE(snap.traces.size() == 3);
    CHECK(snap.traces[0].name == "rpm");
    CHECK(snap.traces[1].name == "map");
    CHECK(snap.traces[2].name == "tps");
    CHECK(snap.traces[0].x_values.size() == 2);
    CHECK(snap.traces[0].y_values[1] == doctest::Approx(1500.0));
}

TEST_CASE("priority heuristic is case-insensitive") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"RPM", 1000.0}, {"MAP", 30.0}}),
    };
    auto snap = dr::build(records, 0);
    REQUIRE(snap.traces.size() == 2);
    CHECK(snap.traces[0].name == "RPM");
    CHECK(snap.traces[1].name == "MAP");
}

TEST_CASE("heuristic falls back to insertion order when nothing matches priority") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"alpha", 1.0}, {"beta", 2.0}, {"gamma", 3.0}, {"delta", 4.0}}),
    };
    auto snap = dr::build(records, 0);
    REQUIRE(snap.traces.size() == 3);
    CHECK(snap.traces[0].name == "alpha");
    CHECK(snap.traces[1].name == "beta");
    CHECK(snap.traces[2].name == "gamma");
}

TEST_CASE("profile selection wins over heuristic") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"rpm", 1000.0}, {"map", 30.0}, {"tps", 0.0}, {"egt", 500.0}}),
    };
    dr::Profile profile;
    profile.enabled_channels = {"egt", "map"};
    auto snap = dr::build(records, 0, &profile);
    REQUIRE(snap.traces.size() == 2);
    CHECK(snap.traces[0].name == "egt");
    CHECK(snap.traces[1].name == "map");
}

TEST_CASE("profile selection caps at three channels") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"a", 1.0}, {"b", 2.0}, {"c", 3.0}, {"d", 4.0}, {"e", 5.0}}),
    };
    dr::Profile profile;
    profile.enabled_channels = {"a", "b", "c", "d", "e"};
    auto snap = dr::build(records, 0, &profile);
    CHECK(snap.traces.size() == 3);
}

TEST_CASE("profile with no matching channels falls through to heuristic") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"rpm", 1000.0}, {"map", 30.0}}),
    };
    dr::Profile profile;
    profile.enabled_channels = {"nonexistent"};
    auto snap = dr::build(records, 0, &profile);
    REQUIRE(snap.traces.size() == 2);
    CHECK(snap.traces[0].name == "rpm");
    CHECK(snap.traces[1].name == "map");
}

TEST_CASE("trace skips records that lack the channel") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"rpm", 1000.0}, {"map", 30.0}}),
        make_record(0.1, {{"rpm", 1500.0}}),  // missing map
        make_record(0.2, {{"rpm", 2000.0}, {"map", 40.0}}),
    };
    auto snap = dr::build(records, 0);
    REQUIRE(snap.traces.size() == 2);
    CHECK(snap.traces[0].name == "rpm");
    CHECK(snap.traces[0].x_values.size() == 3);
    CHECK(snap.traces[1].name == "map");
    CHECK(snap.traces[1].x_values.size() == 2);
    CHECK(snap.traces[1].x_values[1] == doctest::Approx(0.2));
}

TEST_CASE("summary text format matches Python pin") {
    std::vector<dr::Record> records = {
        make_record(0.0, {{"rpm", 1000.0}}),
        make_record(0.5, {{"rpm", 1500.0}}),
    };
    auto snap = dr::build(records, 1);
    CHECK(snap.summary_text == "Datalog review shows 1 trace(s) across 2 row(s). Selected replay row 2 is at +0.500s.");
    CHECK(snap.marker_x == doctest::Approx(0.5));
}

TEST_CASE("x_values are deltas from the first record's timestamp") {
    std::vector<dr::Record> records = {
        make_record(100.0, {{"rpm", 1000.0}}),
        make_record(100.25, {{"rpm", 1500.0}}),
        make_record(100.75, {{"rpm", 2000.0}}),
    };
    auto snap = dr::build(records, 2);
    REQUIRE(snap.traces.size() == 1);
    CHECK(snap.traces[0].x_values[0] == doctest::Approx(0.0));
    CHECK(snap.traces[0].x_values[1] == doctest::Approx(0.25));
    CHECK(snap.traces[0].x_values[2] == doctest::Approx(0.75));
    CHECK(snap.marker_x == doctest::Approx(0.75));
}
