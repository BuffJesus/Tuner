// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/project_file.hpp"
#include <stdexcept>

namespace pf = tuner_core::project_file;

TEST_SUITE("project_file") {

TEST_CASE("export produces valid JSON") {
    pf::Project p;
    p.name = "Ford 300 Twin-GT28";
    p.definition_path = "speeduino-202501-T41.tunerdef";
    p.tune_path = "Ford300_TwinGT28.tuner";
    p.active_settings = {"LAMBDA", "mcu_teensy"};
    p.last_connected = "COM3:115200:SPEEDUINO";
    p.calibration_intent = "drivable_base";
    p.firmware_signature = "speeduino 202501-T41";
    auto json = pf::export_json(p);
    CHECK(json.find("tuner-project-v1") != std::string::npos);
    CHECK(json.find("Ford 300 Twin-GT28") != std::string::npos);
    CHECK(json.find("LAMBDA") != std::string::npos);
}

TEST_CASE("import round-trips export") {
    pf::Project orig;
    orig.name = "Test Project";
    orig.definition_path = "test.tunerdef";
    orig.tune_path = "test.tuner";
    orig.active_settings = {"LAMBDA"};
    orig.logging_profiles = {"default", "wideband"};
    orig.calibration_intent = "first_start";
    orig.firmware_signature = "speeduino 202501-T41";
    auto json = pf::export_json(orig);
    auto restored = pf::import_json(json);
    CHECK(restored.name == "Test Project");
    CHECK(restored.definition_path == "test.tunerdef");
    CHECK(restored.tune_path == "test.tuner");
    REQUIRE(restored.active_settings.size() == 1);
    CHECK(restored.active_settings[0] == "LAMBDA");
    REQUIRE(restored.logging_profiles.size() == 2);
    CHECK(restored.logging_profiles[1] == "wideband");
    CHECK(restored.firmware_signature == "speeduino 202501-T41");
}

TEST_CASE("import rejects invalid JSON") {
    CHECK_THROWS_AS(pf::import_json("NOT JSON"), std::invalid_argument);
}

TEST_CASE("import handles missing fields gracefully") {
    auto p = pf::import_json(R"({"name": "Minimal"})");
    CHECK(p.name == "Minimal");
    CHECK(p.definition_path.empty());
    CHECK(p.active_settings.empty());
}

TEST_CASE("empty project exports minimal JSON") {
    pf::Project p;
    auto json = pf::export_json(p);
    CHECK(json.find("tuner-project-v1") != std::string::npos);
    CHECK(json.find("active_settings") == std::string::npos);  // omitted when empty
}

}  // TEST_SUITE
