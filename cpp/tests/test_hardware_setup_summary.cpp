// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/hardware_setup_summary.hpp"

#include <map>

namespace hss = tuner_core::hardware_setup_summary;

TEST_SUITE("hardware_setup_summary") {

TEST_CASE("injector page produces injector card") {
    std::map<std::string, double> vals = {{"injFlow1", 550}, {"injOpen", 1.2}, {"reqFuel", 8.5}};
    hss::Page page;
    page.page_kind = "injector";
    page.parameters = {
        {"injFlow1", "Injector Flow Rate"},
        {"injOpen", "Injector Dead Time"},
        {"reqFuel", "Required Fuel"},
    };
    auto cards = hss::build_cards(page, [&](const std::string& name) -> std::optional<double> {
        auto it = vals.find(name); return it != vals.end() ? std::optional(it->second) : std::nullopt;
    });
    REQUIRE(cards.size() == 1);
    CHECK(cards[0].key == "injector");
    CHECK(cards[0].title == "Injector Setup");
    CHECK(cards[0].detail_lines.size() >= 3);
    CHECK(cards[0].summary.find("550") != std::string::npos);
}

TEST_CASE("ignition page produces ignition card") {
    std::map<std::string, double> vals = {{"sparkMode", 2}, {"dwellRun", 3.5}};
    hss::Page page;
    page.page_kind = "ignition";
    page.parameters = {{"sparkMode", "Spark Mode"}, {"dwellRun", "Running Dwell"}};
    auto cards = hss::build_cards(page, [&](const std::string& name) -> std::optional<double> {
        auto it = vals.find(name); return it != vals.end() ? std::optional(it->second) : std::nullopt;
    });
    REQUIRE(cards.size() == 1);
    CHECK(cards[0].key == "ignition");
    CHECK(cards[0].detail_lines.size() >= 2);
}

TEST_CASE("trigger page produces trigger card") {
    std::map<std::string, double> vals = {{"TrigPattern", 0}, {"nTeeth", 36}, {"missingTeeth", 1}};
    hss::Page page;
    page.page_kind = "trigger";
    page.parameters = {
        {"TrigPattern", "Trigger Pattern"},
        {"nTeeth", "Tooth Count"},
        {"missingTeeth", "Missing Teeth"},
    };
    auto cards = hss::build_cards(page, [&](const std::string& name) -> std::optional<double> {
        auto it = vals.find(name); return it != vals.end() ? std::optional(it->second) : std::nullopt;
    });
    REQUIRE(cards.size() == 1);
    CHECK(cards[0].key == "trigger");
    CHECK(cards[0].summary.find("36") != std::string::npos);
}

TEST_CASE("sensor page produces sensor card") {
    std::map<std::string, double> vals = {{"egoType", 2}};
    hss::Page page;
    page.page_kind = "sensor";
    page.parameters = {{"egoType", "O2 Sensor Type"}};
    auto cards = hss::build_cards(page, [&](const std::string& name) -> std::optional<double> {
        auto it = vals.find(name); return it != vals.end() ? std::optional(it->second) : std::nullopt;
    });
    REQUIRE(cards.size() == 1);
    CHECK(cards[0].key == "sensor");
}

TEST_CASE("empty page produces fallback") {
    hss::Page page;
    page.page_kind = "injector";
    auto cards = hss::build_cards(page, [](const std::string&) -> std::optional<double> {
        return std::nullopt;
    });
    REQUIRE(cards.size() == 1);
    CHECK(cards[0].detail_lines[0].find("No injector") != std::string::npos);
}

TEST_CASE("unknown page kind tries injector") {
    hss::Page page;
    page.page_kind = "";
    page.parameters = {{"injFlow1", "Injector Flow"}};
    std::map<std::string, double> vals = {{"injFlow1", 440}};
    auto cards = hss::build_cards(page, [&](const std::string& name) -> std::optional<double> {
        auto it = vals.find(name); return it != vals.end() ? std::optional(it->second) : std::nullopt;
    });
    CHECK(cards.size() >= 1);
}

}  // TEST_SUITE
