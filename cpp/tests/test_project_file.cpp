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

// ----- Phase 18 firmware_family additions -----

TEST_CASE("default firmware_family is SPEEDUINO") {
    pf::Project p;
    CHECK(p.firmware_family == pf::FirmwareFamily::SPEEDUINO);
}

TEST_CASE("firmware_family_to_string emits canonical lowercase wire form") {
    CHECK(pf::firmware_family_to_string(pf::FirmwareFamily::SPEEDUINO) == "speeduino");
    CHECK(pf::firmware_family_to_string(pf::FirmwareFamily::RUSEFI)    == "rusefi");
}

TEST_CASE("firmware_family_from_string parses both canonical wire forms") {
    CHECK(pf::firmware_family_from_string("speeduino") == pf::FirmwareFamily::SPEEDUINO);
    CHECK(pf::firmware_family_from_string("rusefi")    == pf::FirmwareFamily::RUSEFI);
}

TEST_CASE("firmware_family_from_string is case-insensitive") {
    CHECK(pf::firmware_family_from_string("SPEEDUINO") == pf::FirmwareFamily::SPEEDUINO);
    CHECK(pf::firmware_family_from_string("Speeduino") == pf::FirmwareFamily::SPEEDUINO);
    CHECK(pf::firmware_family_from_string("RUSEFI")    == pf::FirmwareFamily::RUSEFI);
    CHECK(pf::firmware_family_from_string("RusEFI")    == pf::FirmwareFamily::RUSEFI);
}

TEST_CASE("firmware_family_from_string defaults to SPEEDUINO on unknown / empty") {
    CHECK(pf::firmware_family_from_string("")        == pf::FirmwareFamily::SPEEDUINO);
    CHECK(pf::firmware_family_from_string("unknown") == pf::FirmwareFamily::SPEEDUINO);
    CHECK(pf::firmware_family_from_string("megasquirt") == pf::FirmwareFamily::SPEEDUINO);
}

TEST_CASE("export_json always emits firmware_family field") {
    pf::Project p;
    p.firmware_family = pf::FirmwareFamily::SPEEDUINO;
    auto json = pf::export_json(p);
    CHECK(json.find("\"firmware_family\"") != std::string::npos);
    CHECK(json.find("\"speeduino\"") != std::string::npos);
}

TEST_CASE("export_json emits 'rusefi' when family is RUSEFI") {
    pf::Project p;
    p.firmware_family = pf::FirmwareFamily::RUSEFI;
    p.name = "RusEFI bench project";
    auto json = pf::export_json(p);
    CHECK(json.find("\"firmware_family\"") != std::string::npos);
    CHECK(json.find("\"rusefi\"") != std::string::npos);
}

TEST_CASE("import_json parses firmware_family field") {
    auto p = pf::import_json(R"({"name":"X","firmware_family":"rusefi"})");
    CHECK(p.firmware_family == pf::FirmwareFamily::RUSEFI);

    p = pf::import_json(R"({"name":"X","firmware_family":"speeduino"})");
    CHECK(p.firmware_family == pf::FirmwareFamily::SPEEDUINO);
}

TEST_CASE("import_json missing firmware_family defaults to SPEEDUINO (forward compat)") {
    // Legacy projects from before Phase 18 don't carry the field;
    // they must load as Speeduino without complaint.
    auto p = pf::import_json(R"({"name":"Legacy Project"})");
    CHECK(p.firmware_family == pf::FirmwareFamily::SPEEDUINO);
}

TEST_CASE("import_json with bogus firmware_family value defaults to SPEEDUINO") {
    auto p = pf::import_json(R"({"firmware_family":"megasquirt"})");
    CHECK(p.firmware_family == pf::FirmwareFamily::SPEEDUINO);
}

TEST_CASE("firmware_family round-trips through export → import for both values") {
    for (auto f : {pf::FirmwareFamily::SPEEDUINO, pf::FirmwareFamily::RUSEFI}) {
        pf::Project orig;
        orig.firmware_family = f;
        orig.name = "Round-trip test";
        auto restored = pf::import_json(pf::export_json(orig));
        CHECK(restored.firmware_family == f);
    }
}

}  // TEST_SUITE
