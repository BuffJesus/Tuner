// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniFrontPageParser. Mirrors the
// Python `_parse_front_page` test surface so cross-validation against
// the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_front_page_parser.hpp"

#include <string>

TEST_CASE("parse_front_page_section ignores lines outside the section") {
    auto section = tuner_core::parse_front_page_section(
        "[Other]\ngauge1 = rpmGauge\n");
    CHECK(section.gauges.empty());
    CHECK(section.indicators.empty());
}

TEST_CASE("parses ordered gauge slot list") {
    auto section = tuner_core::parse_front_page_section(
        "[FrontPage]\n"
        "gauge1 = rpmGauge\n"
        "gauge2 = mapGauge\n"
        "gauge3 = afrGauge\n"
        "gauge4 = cltGauge\n");
    REQUIRE(section.gauges.size() == 4);
    CHECK(section.gauges[0] == "rpmGauge");
    CHECK(section.gauges[1] == "mapGauge");
    CHECK(section.gauges[2] == "afrGauge");
    CHECK(section.gauges[3] == "cltGauge");
}

TEST_CASE("missing gauge slot indices are filled with empty strings") {
    auto section = tuner_core::parse_front_page_section(
        "[FrontPage]\n"
        "gauge1 = rpmGauge\n"
        "gauge4 = cltGauge\n");
    REQUIRE(section.gauges.size() == 4);
    CHECK(section.gauges[0] == "rpmGauge");
    CHECK(section.gauges[1] == "");
    CHECK(section.gauges[2] == "");
    CHECK(section.gauges[3] == "cltGauge");
}

TEST_CASE("parses an indicator entry") {
    auto section = tuner_core::parse_front_page_section(
        "[FrontPage]\n"
        "indicator = { ready }, \"Not Ready\", \"Ready\", "
        "black, white, green, white\n");
    REQUIRE(section.indicators.size() == 1);
    const auto& ind = section.indicators[0];
    CHECK(ind.expression == "ready");
    CHECK(ind.off_label == "Not Ready");
    CHECK(ind.on_label == "Ready");
    CHECK(ind.off_bg == "black");
    CHECK(ind.off_fg == "white");
    CHECK(ind.on_bg == "green");
    CHECK(ind.on_fg == "white");
}

TEST_CASE("indicator without braces around expression still parses") {
    auto section = tuner_core::parse_front_page_section(
        "[FrontPage]\n"
        "indicator = ready, \"Off\", \"On\", a, b, c, d\n");
    REQUIRE(section.indicators.size() == 1);
    CHECK(section.indicators[0].expression == "ready");
}

TEST_CASE("indicator with too few fields is dropped") {
    auto section = tuner_core::parse_front_page_section(
        "[FrontPage]\n"
        "indicator = { ready }, \"Off\", \"On\"\n");
    CHECK(section.indicators.empty());
}

TEST_CASE("inline comments are stripped") {
    auto section = tuner_core::parse_front_page_section(
        "[FrontPage]\n"
        "gauge1 = rpmGauge ; this is a comment\n");
    REQUIRE(section.gauges.size() == 1);
    CHECK(section.gauges[0] == "rpmGauge");
}

TEST_CASE("comment-only and blank lines are skipped") {
    auto section = tuner_core::parse_front_page_section(
        "[FrontPage]\n"
        "; just a comment\n"
        "\n"
        "gauge1 = rpmGauge\n");
    REQUIRE(section.gauges.size() == 1);
    CHECK(section.gauges[0] == "rpmGauge");
}

TEST_CASE("section header is matched case-insensitively") {
    auto section = tuner_core::parse_front_page_section(
        "[frontpage]\n"
        "gauge1 = rpmGauge\n");
    REQUIRE(section.gauges.size() == 1);
}

TEST_CASE("multiple gauges and indicators together") {
    auto section = tuner_core::parse_front_page_section(
        "[FrontPage]\n"
        "gauge1 = rpmGauge\n"
        "gauge2 = mapGauge\n"
        "indicator = { sync }, \"NoSync\", \"Sync\", red, white, green, white\n"
        "indicator = { warmup }, \"Cold\", \"Warm\", blue, white, orange, white\n");
    CHECK(section.gauges.size() == 2);
    CHECK(section.indicators.size() == 2);
    CHECK(section.indicators[0].expression == "sync");
    CHECK(section.indicators[1].expression == "warmup");
}

TEST_CASE("preprocessor pipeline gates the section") {
    std::string text =
        "#if FEATURE_X\n"
        "[FrontPage]\n"
        "gauge1 = rpmGauge\n"
        "#endif\n";
    auto enabled = tuner_core::parse_front_page_section_preprocessed(text, {"FEATURE_X"});
    CHECK(enabled.gauges.size() == 1);
    auto disabled = tuner_core::parse_front_page_section_preprocessed(text, {});
    CHECK(disabled.gauges.empty());
}
