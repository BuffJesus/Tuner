// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::pressure_sensor_calibration.

#include "doctest.h"

#include "tuner_core/pressure_sensor_calibration.hpp"

#include <vector>

using namespace tuner_core::pressure_sensor_calibration;

namespace {

Preset make_preset(
    std::string key, std::string label, double lo, double hi,
    std::string units, std::string source_note,
    std::optional<std::string> source_url = std::nullopt) {
    Preset p;
    p.key = std::move(key);
    p.label = std::move(label);
    p.minimum_value = lo;
    p.maximum_value = hi;
    p.units = std::move(units);
    p.source_note = std::move(source_note);
    p.source_url = std::move(source_url);
    return p;
}

}  // namespace

TEST_CASE("source_confidence_label returns Starter for inferred notes") {
    CHECK(source_confidence_label("Inferred from typical OEM range", std::nullopt)
          == "Starter");
    CHECK(source_confidence_label("Conservative inferred starter preset",
                                  std::optional<std::string>{"https://example.com"})
          == "Starter");
}

TEST_CASE("source_confidence_label returns Starter when no URL is supplied") {
    CHECK(source_confidence_label("From datasheet", std::nullopt) == "Starter");
}

TEST_CASE("source_confidence_label recognises official domains") {
    CHECK(source_confidence_label("ID datasheet", std::optional<std::string>{
        "https://injectordynamics.com/products/whatever"}) == "Official");
    CHECK(source_confidence_label("Holley", std::optional<std::string>{
        "https://documents.holley.com/some.pdf"}) == "Official");
    CHECK(source_confidence_label("NXP", std::optional<std::string>{
        "https://www.nxp.com/docs/en/data-sheet/MPX4250AP.pdf"}) == "Official");
}

TEST_CASE("source_confidence_label recognises trusted secondary domains") {
    CHECK(source_confidence_label("Community", std::optional<std::string>{
        "https://www.ms4x.net/index.php?title=Air_Sensors"})
        == "Trusted Secondary");
    CHECK(source_confidence_label("Forum", std::optional<std::string>{
        "https://www.msextra.com/forums/viewtopic.php?t=12345"})
        == "Trusted Secondary");
}

TEST_CASE("source_confidence_label falls through to Sourced") {
    CHECK(source_confidence_label("Some note", std::optional<std::string>{
        "https://random-blog.example/post/123"}) == "Sourced");
}

TEST_CASE("find_matching_preset returns first preset within tolerance") {
    std::vector<Preset> presets{
        make_preset("a", "100 kPa MAP", 10, 100, "kPa", "Inferred"),
        make_preset("b", "250 kPa MAP", 10, 250, "kPa", "Inferred"),
    };
    auto m = find_matching_preset(10.4, 250.5, presets);
    REQUIRE(m.has_value());
    CHECK(m->key == "b");
}

TEST_CASE("find_matching_preset returns nullopt when out of tolerance") {
    std::vector<Preset> presets{
        make_preset("a", "100 kPa MAP", 10, 100, "kPa", "Inferred"),
    };
    CHECK_FALSE(find_matching_preset(10.0, 105.0, presets).has_value());
}

TEST_CASE("assess: missing inputs returns 'no calibration available' guidance") {
    auto a = assess(std::nullopt, std::nullopt, {}, SensorKind::MAP);
    CHECK(a.guidance == "No MAP calibration range is available yet.");
    CHECK_FALSE(a.matching_preset.has_value());
    CHECK_FALSE(a.warning.has_value());
}

TEST_CASE("assess: matched preset produces guidance with confidence label") {
    std::vector<Preset> presets{
        make_preset("a", "250 kPa MAP", 10, 250, "kPa",
                    "From OEM datasheet",
                    std::optional<std::string>{"https://nxp.com/docs/MPX4250AP.pdf"}),
    };
    auto a = assess(10.0, 250.0, presets, SensorKind::MAP);
    REQUIRE(a.matching_preset.has_value());
    CHECK(a.matching_preset->key == "a");
    CHECK(a.guidance.find("Current MAP calibration matches 250 kPa MAP") != std::string::npos);
    CHECK(a.guidance.find("(10-250 kPa)") != std::string::npos);
    CHECK(a.guidance.find("[Official]") != std::string::npos);
    CHECK(a.guidance.find("From OEM datasheet") != std::string::npos);
}

TEST_CASE("assess: unmatched range produces 'does not match' guidance") {
    std::vector<Preset> presets{
        make_preset("a", "100 kPa MAP", 10, 100, "kPa", "Inferred"),
    };
    auto a = assess(10.0, 250.0, presets, SensorKind::MAP);
    CHECK_FALSE(a.matching_preset.has_value());
    CHECK(a.guidance.find("Current MAP calibration is 10-250 kPa") != std::string::npos);
    CHECK(a.guidance.find("does not match a curated preset") != std::string::npos);
}

TEST_CASE("assess: baro overrange produces a warning") {
    auto a = assess(0.0, 200.0, {}, SensorKind::BARO);
    REQUIRE(a.warning.has_value());
    CHECK(a.warning->find("External baro calibration") != std::string::npos);
}

TEST_CASE("assess: baro within atmospheric range has no warning") {
    auto a = assess(0.0, 110.0, {}, SensorKind::BARO);
    CHECK_FALSE(a.warning.has_value());
}
