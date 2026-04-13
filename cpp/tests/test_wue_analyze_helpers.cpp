// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::wue_analyze_helpers.

#include "doctest.h"

#include "tuner_core/wue_analyze_helpers.hpp"

#include <string>
#include <vector>

using namespace tuner_core::wue_analyze_helpers;

TEST_CASE("confidence_label buckets sample counts") {
    CHECK(confidence_label(0) == "insufficient");
    CHECK(confidence_label(2) == "insufficient");
    CHECK(confidence_label(3) == "low");
    CHECK(confidence_label(9) == "low");
    CHECK(confidence_label(10) == "medium");
    CHECK(confidence_label(29) == "medium");
    CHECK(confidence_label(30) == "high");
    CHECK(confidence_label(1000) == "high");
}

TEST_CASE("is_clt_axis matches CLT/warmup keywords case-insensitively") {
    CHECK(is_clt_axis("clt"));
    CHECK(is_clt_axis("Coolant"));
    CHECK(is_clt_axis("warmupTemp"));
    CHECK(is_clt_axis("wueBins"));
    CHECK(is_clt_axis("ColdEnrich"));
    CHECK(is_clt_axis("intakeTemp"));  // matches "temp"
}

TEST_CASE("is_clt_axis rejects non-matching names") {
    CHECK_FALSE(is_clt_axis(""));
    CHECK_FALSE(is_clt_axis("rpm"));
    CHECK_FALSE(is_clt_axis("map"));
}

TEST_CASE("clt_from_record finds the first matching channel") {
    ValueMap v{{"rpm", 5500.0}, {"clt", 90.0}};
    auto c = clt_from_record(v);
    REQUIRE(c.has_value());
    CHECK(*c == 90.0);
}

TEST_CASE("clt_from_record falls through to coolantTemp") {
    ValueMap v{{"coolantTemp", 75.0}};
    auto c = clt_from_record(v);
    REQUIRE(c.has_value());
    CHECK(*c == 75.0);
}

TEST_CASE("clt_from_record returns nullopt with no match") {
    ValueMap v{{"rpm", 5500.0}};
    CHECK_FALSE(clt_from_record(v).has_value());
}

TEST_CASE("nearest_index finds the closest axis bin") {
    std::vector<double> axis{-40, -20, 0, 20, 40, 60, 80};
    CHECK(nearest_index(axis, -50) == 0);
    CHECK(nearest_index(axis, 30) == 3);  // tie → earlier index wins (Python parity)
    CHECK(nearest_index(axis, 19) == 3);
    CHECK(nearest_index(axis, 1000) == 6);
}

TEST_CASE("nearest_index handles single-element axis") {
    std::vector<double> axis{42.0};
    CHECK(nearest_index(axis, 0.0) == 0);
}

TEST_CASE("numeric_axis parses well-formed labels") {
    std::vector<std::string> labels{"-40", "0", "40", "80"};
    auto out = numeric_axis(labels);
    REQUIRE(out.size() == 4);
    CHECK(out[0] == -40);
    CHECK(out[3] == 80);
}

TEST_CASE("numeric_axis returns empty on any parse failure") {
    std::vector<std::string> labels{"0", "20", "not-a-number"};
    auto out = numeric_axis(labels);
    CHECK(out.empty());
}

TEST_CASE("parse_cell_float happy path") {
    auto v = parse_cell_float("3.14");
    REQUIRE(v.has_value());
    CHECK(*v == doctest::Approx(3.14));
}

TEST_CASE("parse_cell_float returns nullopt on bad input") {
    CHECK_FALSE(parse_cell_float("").has_value());
    CHECK_FALSE(parse_cell_float("nope").has_value());
}

TEST_CASE("target_lambda_from_cell handles AFR values") {
    // 14.7 → 1.0
    CHECK(target_lambda_from_cell(14.7, 1.0) == doctest::Approx(1.0));
    // 12.5 → 0.85
    CHECK(target_lambda_from_cell(12.5, 1.0) == doctest::Approx(12.5 / 14.7));
}

TEST_CASE("target_lambda_from_cell handles lambda values directly") {
    CHECK(target_lambda_from_cell(0.85, 1.0) == doctest::Approx(0.85));
    CHECK(target_lambda_from_cell(1.05, 1.0) == doctest::Approx(1.05));
}

TEST_CASE("target_lambda_from_cell falls back on non-positive raw") {
    CHECK(target_lambda_from_cell(0.0, 1.0) == 1.0);
    CHECK(target_lambda_from_cell(-1.0, 0.95) == 0.95);
}
