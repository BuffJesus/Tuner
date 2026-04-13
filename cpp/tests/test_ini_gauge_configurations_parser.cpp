// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniGaugeConfigurationsParser.
// Mirrors the Python `_parse_gauge_configurations` test surface so
// cross-validation against the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_gauge_configurations_parser.hpp"

#include <string>

namespace {

const tuner_core::IniGaugeConfiguration* find_gauge(
    const tuner_core::IniGaugeConfigurationsSection& section,
    const std::string& name) {
    for (const auto& g : section.gauges) {
        if (g.name == name) return &g;
    }
    return nullptr;
}

}  // namespace

TEST_CASE("parse_gauge_configurations_section ignores lines outside the section") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[Other]\nrpmGauge = rpm, \"RPM\", \"rpm\", 0, 8000\n");
    CHECK(section.gauges.empty());
}

TEST_CASE("parses a single full-form gauge entry") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "rpmGauge = rpm, \"RPM\", \"rpm\", 0, 8000, 0, 0, 6500, 7500, 0, 0\n");
    REQUIRE(section.gauges.size() == 1);
    const auto& g = section.gauges[0];
    CHECK(g.name == "rpmGauge");
    CHECK(g.channel == "rpm");
    CHECK(g.title == "RPM");
    CHECK(g.units == "rpm");
    CHECK(g.lo.value() == doctest::Approx(0.0));
    CHECK(g.hi.value() == doctest::Approx(8000.0));
    CHECK(g.lo_danger.value() == doctest::Approx(0.0));
    CHECK(g.lo_warn.value() == doctest::Approx(0.0));
    CHECK(g.hi_warn.value() == doctest::Approx(6500.0));
    CHECK(g.hi_danger.value() == doctest::Approx(7500.0));
    CHECK(g.value_digits == 0);
    CHECK(g.label_digits == 0);
}

TEST_CASE("parses gauge entry with brace-expression thresholds as nullopt") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "rpmGauge = rpm, \"RPM\", \"rpm\", 0, 8000, {rpmlow}, {rpmwarn}, {rpmwarn}, {rpmhigh}\n");
    REQUIRE(section.gauges.size() == 1);
    const auto& g = section.gauges[0];
    // Numeric thresholds parse fine
    CHECK(g.lo.value() == doctest::Approx(0.0));
    CHECK(g.hi.value() == doctest::Approx(8000.0));
    // Brace expressions resolve to nullopt — they're frozen
    CHECK_FALSE(g.lo_danger.has_value());
    CHECK_FALSE(g.lo_warn.has_value());
    CHECK_FALSE(g.hi_warn.has_value());
    CHECK_FALSE(g.hi_danger.has_value());
}

TEST_CASE("gauge entries inherit the active gaugeCategory") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "gaugeCategory = \"Engine\"\n"
        "rpmGauge = rpm, \"RPM\", \"rpm\", 0, 8000\n"
        "mapGauge = map, \"MAP\", \"kPa\", 0, 250\n"
        "gaugeCategory = \"Sensors\"\n"
        "iatGauge = iat, \"IAT\", \"C\", -40, 215\n");
    REQUIRE(section.gauges.size() == 3);
    CHECK(find_gauge(section, "rpmGauge")->category.value() == "Engine");
    CHECK(find_gauge(section, "mapGauge")->category.value() == "Engine");
    CHECK(find_gauge(section, "iatGauge")->category.value() == "Sensors");
}

TEST_CASE("gauges declared before any category have no category") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "loneGauge = rpm, \"RPM\", \"rpm\", 0, 8000\n"
        "gaugeCategory = \"Engine\"\n"
        "rpmGauge = rpm, \"RPM\", \"rpm\", 0, 8000\n");
    REQUIRE(section.gauges.size() == 2);
    CHECK_FALSE(find_gauge(section, "loneGauge")->category.has_value());
    CHECK(find_gauge(section, "rpmGauge")->category.value() == "Engine");
}

TEST_CASE("entry with fewer than 3 parts is dropped") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "shortGauge = rpm, \"RPM\"\n"
        "goodGauge = rpm, \"RPM\", \"rpm\"\n");
    REQUIRE(section.gauges.size() == 1);
    CHECK(section.gauges[0].name == "goodGauge");
}

TEST_CASE("comments and blank lines are ignored") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "; comment\n"
        "\n"
        "rpmGauge = rpm, \"RPM\", \"rpm\"\n");
    REQUIRE(section.gauges.size() == 1);
    CHECK(section.gauges[0].name == "rpmGauge");
}

TEST_CASE("inline comments after a value are stripped") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "rpmGauge = rpm, \"RPM\", \"rpm\" ; trailing comment\n");
    REQUIRE(section.gauges.size() == 1);
    CHECK(section.gauges[0].title == "RPM");
    CHECK(section.gauges[0].units == "rpm");
}

TEST_CASE("value_digits and label_digits parse from float source values") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "afrGauge = afr, \"AFR\", \"\", 8.0, 22.0, 0, 10, 16, 18, 2, 1\n");
    REQUIRE(section.gauges.size() == 1);
    CHECK(section.gauges[0].value_digits == 2);
    CHECK(section.gauges[0].label_digits == 1);
}

TEST_CASE("multiple gauges in the same section all parsed") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "g1 = a, \"A\", \"\"\n"
        "g2 = b, \"B\", \"\"\n"
        "g3 = c, \"C\", \"\"\n");
    REQUIRE(section.gauges.size() == 3);
    CHECK(section.gauges[0].name == "g1");
    CHECK(section.gauges[1].name == "g2");
    CHECK(section.gauges[2].name == "g3");
}

TEST_CASE("section change ends gauge parsing without leaking") {
    auto section = tuner_core::parse_gauge_configurations_section(
        "[GaugeConfigurations]\n"
        "rpmGauge = rpm, \"RPM\", \"rpm\"\n"
        "[OtherSection]\n"
        "leakedGauge = leaked, \"Leaked\", \"\"\n");
    REQUIRE(section.gauges.size() == 1);
    CHECK(section.gauges[0].name == "rpmGauge");
}

TEST_CASE("preprocessed pipeline gates entries inside #if blocks") {
    auto disabled = tuner_core::parse_gauge_configurations_section_preprocessed(
        "[GaugeConfigurations]\n"
        "always = rpm, \"Always\", \"rpm\"\n"
        "#if FEATURE_X\n"
        "feature = rpm, \"Feature\", \"rpm\"\n"
        "#endif\n",
        {});
    REQUIRE(disabled.gauges.size() == 1);
    CHECK(disabled.gauges[0].name == "always");

    auto enabled = tuner_core::parse_gauge_configurations_section_preprocessed(
        "[GaugeConfigurations]\n"
        "always = rpm, \"Always\", \"rpm\"\n"
        "#if FEATURE_X\n"
        "feature = rpm, \"Feature\", \"rpm\"\n"
        "#endif\n",
        {"FEATURE_X"});
    REQUIRE(enabled.gauges.size() == 2);
}
