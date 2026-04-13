// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::table_replay_context.

#include "doctest.h"

#include "tuner_core/table_replay_context.hpp"

#include <vector>

using namespace tuner_core::table_replay_context;

namespace {

TablePageSnapshot make_snapshot(
    std::string x_param,
    std::string y_param,
    std::vector<std::string> x_labels,
    std::vector<std::string> y_labels,
    std::vector<std::vector<std::string>> cells) {
    TablePageSnapshot s;
    s.x_parameter_name = std::move(x_param);
    s.y_parameter_name = std::move(y_param);
    s.x_labels = std::move(x_labels);
    s.y_labels = std::move(y_labels);
    s.cells = std::move(cells);
    return s;
}

RuntimeChannel ch(std::string name, double value) {
    return RuntimeChannel{std::move(name), value};
}

}  // namespace

TEST_CASE("build: empty cells returns nullopt") {
    TablePageSnapshot s;
    s.x_parameter_name = "rpmBins";
    s.y_parameter_name = "mapBins";
    auto r = build(s, {});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("build: missing axis channels return nullopt") {
    auto s = make_snapshot(
        "rpmBins", "mapBins",
        {"1000", "2000", "3000"},
        {"50", "100"},
        {{"a", "b", "c"}, {"d", "e", "f"}});
    auto r = build(s, {ch("clt", 90.0)});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("build: nearest cell is found and crosshair populated") {
    auto s = make_snapshot(
        "rpmBins", "mapBins",
        {"1000", "2000", "3000", "4000"},
        {"50", "100", "150"},
        {
            {"a1", "b1", "c1", "d1"},
            {"a2", "b2", "c2", "d2"},
            {"a3", "b3", "c3", "d3"},
        });
    std::vector<RuntimeChannel> rt{ch("rpm", 2900.0), ch("map", 95.0)};
    auto r = build(s, rt);
    REQUIRE(r.has_value());
    CHECK(r->column_index == 2);  // 3000 closest to 2900
    CHECK(r->row_index == 1);     // 100 closest to 95
    CHECK(r->x_value == doctest::Approx(2900.0));
    CHECK(r->y_value == doctest::Approx(95.0));
    REQUIRE(r->cell_value_text.has_value());
    CHECK(r->cell_value_text.value() == "c2");
}

TEST_CASE("build: summary and detail text format") {
    auto s = make_snapshot(
        "rpmBins", "mapBins",
        {"1000", "2000"},
        {"50", "100"},
        {{"x1", "x2"}, {"y1", "y2"}});
    auto r = build(s, {ch("rpm", 1500.0), ch("map", 75.0)});
    REQUIRE(r.has_value());
    CHECK(r->summary_text.find("nearest row") != std::string::npos);
    CHECK(r->detail_text.find("Axis match: X=1500.0") != std::string::npos);
    CHECK(r->detail_text.find("Y=75.0") != std::string::npos);
    CHECK(r->detail_text.find("Table cell value:") != std::string::npos);
}

TEST_CASE("build: axis hint table maps load → map fallback") {
    auto s = make_snapshot(
        "rpmBins", "loadBins",  // 'load' should hint at map then tps
        {"1000", "2000"},
        {"50", "100"},
        {{"a", "b"}, {"c", "d"}});
    // No 'load' channel, but a 'map' channel — the hint should pick it.
    auto r = build(s, {ch("rpm", 1500.0), ch("map", 60.0)});
    REQUIRE(r.has_value());
    CHECK(r->y_value == 60.0);
}

TEST_CASE("build: case-insensitive channel name matching") {
    auto s = make_snapshot(
        "rpmBins", "mapBins",
        {"1000", "2000"},
        {"50", "100"},
        {{"a", "b"}, {"c", "d"}});
    auto r = build(s, {ch("RPM", 1500.0), ch("MAP", 75.0)});
    REQUIRE(r.has_value());
    CHECK(r->x_value == 1500.0);
}

TEST_CASE("build: non-numeric axis labels return nullopt") {
    auto s = make_snapshot(
        "rpmBins", "mapBins",
        {"low", "mid", "high"},
        {"50", "100"},
        {{"a", "b", "c"}, {"d", "e", "f"}});
    auto r = build(s, {ch("rpm", 2000.0), ch("map", 75.0)});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("build: tie-breaking matches nearest_index semantics") {
    auto s = make_snapshot(
        "rpmBins", "mapBins",
        {"1000", "2000", "3000"},
        {"50", "100"},
        {{"a", "b", "c"}, {"d", "e", "f"}});
    // 1500 is exactly between 1000 and 2000 — earlier index wins.
    auto r = build(s, {ch("rpm", 1500.0), ch("map", 50.0)});
    REQUIRE(r.has_value());
    CHECK(r->column_index == 0);  // tie → earlier
}
