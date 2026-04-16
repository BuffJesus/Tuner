// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/tune_storage_map.hpp"

#include <stdexcept>

namespace tsm = tuner_core::tune_storage_map;

TEST_CASE("tune_storage_map::parse — minimal starter header") {
    const char* text = R"(
/* comment */
#ifdef TUNE_SCALAR
TUNE_SCALAR ( reqFuel, 1, 24, U08, 0.1, 0.0, "ms", "Required Fuel" )
#endif

#ifdef TUNE_AXIS
TUNE_AXIS ( veRpmBins, 2, 256, 16, U08, 100.0, 0.0, "RPM", "VE RPM axis" )
TUNE_AXIS ( veMapBins, 2, 272, 16, U08, 1.0,   0.0, "kPa", "VE MAP axis" )
#endif

#ifdef TUNE_TABLE
TUNE_TABLE ( veTable, 2, 0, 16, 16, U08, 1.0, 0.0, veRpmBins, veMapBins, "%", "Volumetric Efficiency" )
#endif
)";

    auto map = tsm::parse(text);
    CHECK(map.entries.size() == 4);

    auto* req = map.find("reqFuel");
    REQUIRE(req != nullptr);
    CHECK(req->kind == tsm::Kind::Scalar);
    CHECK(req->page == 1);
    CHECK(req->offset == 24);
    CHECK(req->data_type == "U08");
    CHECK(req->scale.value_or(0.0) == doctest::Approx(0.1));
    CHECK(req->offset_v.value_or(-1.0) == doctest::Approx(0.0));
    CHECK(req->units == "ms");
    CHECK(req->label == "Required Fuel");

    auto* rpm = map.find("veRpmBins");
    REQUIRE(rpm != nullptr);
    CHECK(rpm->kind == tsm::Kind::Axis);
    CHECK(rpm->length.value_or(-1) == 16);
    CHECK(rpm->scale.value_or(0.0) == doctest::Approx(100.0));
    CHECK(rpm->offset_v.value_or(-1.0) == doctest::Approx(0.0));
    CHECK(rpm->units == "RPM");

    auto* ve = map.find("veTable");
    REQUIRE(ve != nullptr);
    CHECK(ve->kind == tsm::Kind::Table);
    CHECK(ve->rows.value_or(-1) == 16);
    CHECK(ve->cols.value_or(-1) == 16);
    CHECK(ve->scale.value_or(0.0) == doctest::Approx(1.0));
    CHECK(ve->offset_v.value_or(-1.0) == doctest::Approx(0.0));
    CHECK(ve->x_axis_id.value_or("") == "veRpmBins");
    CHECK(ve->y_axis_id.value_or("") == "veMapBins");
    CHECK(ve->units == "%");
}

TEST_CASE("tune_storage_map::of_kind — filters by kind") {
    const char* text = R"(
TUNE_SCALAR ( a, 1, 0, U08, 1.0, 0.0, "", "A" )
TUNE_SCALAR ( b, 1, 1, U08, 1.0, 0.0, "", "B" )
TUNE_AXIS   ( x, 2, 0, 8, U08, 100.0, 0.0, "RPM", "X axis" )
TUNE_TABLE  ( t, 2, 8, 8, 8, U08, 1.0, 0.0, x, x, "%", "Test" )
TUNE_CURVE  ( c, 3, 0, 8, U08, 1.0, 0.0, x, "kPa", "Test curve" )
)";
    auto map = tsm::parse(text);
    CHECK(map.of_kind(tsm::Kind::Scalar).size() == 2);
    CHECK(map.of_kind(tsm::Kind::Axis).size() == 1);
    CHECK(map.of_kind(tsm::Kind::Table).size() == 1);
    CHECK(map.of_kind(tsm::Kind::Curve).size() == 1);
}

TEST_CASE("tune_storage_map::parse — advTable scale+offset applies to tables") {
    // Ignition advance: raw U08 0..255 maps to -40°..215° via
    // scale=1.0 + offset_v=-40. Without offset_v support, the desktop
    // would render byte 0 as "0 deg" (wrong by 40°).
    const char* text = R"(
TUNE_TABLE ( advTable1, 3, 0, 16, 16, U08, 1.0, -40.0, rpm, load, "deg", "Ignition" )
)";
    auto map = tsm::parse(text);
    REQUIRE(map.entries.size() == 1);
    const auto& t = map.entries[0];
    CHECK(t.scale.value_or(0.0) == doctest::Approx(1.0));
    CHECK(t.offset_v.value_or(0.0) == doctest::Approx(-40.0));
}

TEST_CASE("tune_storage_map::parse — axis offset_v supports temperature shifts") {
    // wueBins: raw U08 stores coolant temp as Celsius + 40 so 0=-40C.
    const char* text = R"(
TUNE_AXIS ( wueBins, 2, 31, 10, U08, 1.0, -40.0, "C", "WUE coolant" )
)";
    auto map = tsm::parse(text);
    REQUIRE(map.entries.size() == 1);
    const auto& a = map.entries[0];
    CHECK(a.scale.value_or(0.0) == doctest::Approx(1.0));
    CHECK(a.offset_v.value_or(0.0) == doctest::Approx(-40.0));
}

TEST_CASE("tune_storage_map::find — returns nullptr when absent") {
    auto map = tsm::parse("");
    CHECK(map.find("nothere") == nullptr);
    CHECK(map.entries.empty());
}

TEST_CASE("tune_storage_map::parse — quoted strings survive commas inside") {
    const char* text =
        R"(TUNE_SCALAR ( silly, 1, 0, U08, 1.0, 0.0, "a, b", "has, commas" ))";
    auto map = tsm::parse(text);
    REQUIRE(map.entries.size() == 1);
    CHECK(map.entries[0].units == "a, b");
    CHECK(map.entries[0].label == "has, commas");
}

TEST_CASE("tune_storage_map::parse — wrong arg count throws") {
    // TUNE_SCALAR wants 8 args; 5 should throw.
    CHECK_THROWS_AS(
        tsm::parse("TUNE_SCALAR(a, 1, 0, U08, 1.0)"),
        std::invalid_argument);
    // TUNE_TABLE wants 12 args; 5 should throw.
    CHECK_THROWS_AS(
        tsm::parse("TUNE_TABLE(t, 1, 0, 8, 8)"),
        std::invalid_argument);
}

TEST_CASE("tune_storage_map::parse — curve has single x_axis, no y") {
    const char* text =
        R"(TUNE_CURVE ( wueCurve, 4, 0, 10, U08, 1.0, 0.0, wueCltBins, "%", "WUE" ))";
    auto map = tsm::parse(text);
    REQUIRE(map.entries.size() == 1);
    const auto& e = map.entries[0];
    CHECK(e.kind == tsm::Kind::Curve);
    CHECK(e.length.value_or(-1) == 10);
    CHECK(e.x_axis_id.value_or("") == "wueCltBins");
    CHECK_FALSE(e.y_axis_id.has_value());  // curves have no y axis
}

TEST_CASE("tune_storage_map::parse — comments and blank lines ignored") {
    const char* text = R"(
// file header
/* multi-line
   comment */
#ifdef TUNE_SCALAR

TUNE_SCALAR ( a, 1, 0, U08, 1.0, 0.0, "", "A" )

#endif
)";
    auto map = tsm::parse(text);
    CHECK(map.entries.size() == 1);
    CHECK(map.entries[0].semantic_id == "a");
}

TEST_CASE("tune_storage_map::parse — growing header holds its shape") {
    // As entries are added to the firmware's tune_storage_map.h, this
    // test pins the post-parse entry-count invariants rather than the
    // specific count (which bumps every bite). Checks that the four
    // kinds remain present and cross-referenced by semantic ID.
    const char* text = R"(
/* Simulates a populated header with entries across all 4 kinds. */
TUNE_SCALAR ( reqFuel,      1,  24, U08, 0.1,  0.0,   "ms", "Required Fuel" )
TUNE_SCALAR ( dwellrun,     2,  14, U08, 0.1,  0.0,   "ms", "Dwell running" )
TUNE_SCALAR ( stagedInjSizePri, 10, 28, U16, 1.0, 0.0, "cc/min", "Staged Pri" )

TUNE_AXIS   ( veRpmBins,    2, 256, 16, U08, 100.0,   0.0, "RPM", "VE RPM" )
TUNE_AXIS   ( veMapBins,    2, 272, 16, U08,   1.0,   0.0, "kPa", "VE MAP" )
TUNE_AXIS   ( advRpmBins,   3, 256, 16, U08, 100.0,   0.0, "RPM", "Adv RPM" )
TUNE_AXIS   ( advLoadBins,  3, 272, 16, U08,   1.0,   0.0, "kPa", "Adv Load" )
TUNE_AXIS   ( wueBins,      2,  31, 10, U08,   1.0, -40.0, "C",   "WUE" )

TUNE_TABLE  ( veTable,      2,   0, 16, 16, U08, 1.0,   0.0, veRpmBins,  veMapBins,  "%",   "VE" )
TUNE_TABLE  ( advTable1,    3,   0, 16, 16, U08, 1.0, -40.0, advRpmBins, advLoadBins, "deg", "Adv" )

TUNE_CURVE  ( wueRates,     1,   4, 10, U08, 1.0,   0.0, wueBins, "%", "WUE Rates" )
)";
    auto map = tsm::parse(text);
    // 3 scalars + 5 axes + 2 tables + 1 curve = 11.
    CHECK(map.entries.size() == 11);
    CHECK(map.of_kind(tsm::Kind::Scalar).size() == 3);
    CHECK(map.of_kind(tsm::Kind::Axis).size() == 5);
    CHECK(map.of_kind(tsm::Kind::Table).size() == 2);
    CHECK(map.of_kind(tsm::Kind::Curve).size() == 1);

    // Cross-references by semantic ID resolve correctly.
    auto* ve = map.find("veTable");
    REQUIRE(ve != nullptr);
    auto* vex = map.find(*ve->x_axis_id);
    REQUIRE(vex != nullptr);
    CHECK(vex->kind == tsm::Kind::Axis);
    CHECK(vex->length.value_or(-1) == 16);

    auto* wue = map.find("wueRates");
    REQUIRE(wue != nullptr);
    auto* wuex = map.find(*wue->x_axis_id);
    REQUIRE(wuex != nullptr);
    CHECK(wuex->kind == tsm::Kind::Axis);
    // Cross-page reference: curve on page 1, axis on page 2.
    CHECK(wuex->page == 2);
    CHECK(wue->page == 1);
}
