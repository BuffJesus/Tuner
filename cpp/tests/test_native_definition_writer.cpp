// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/native_definition_writer.hpp"

#include <filesystem>

namespace ndw = tuner_core::native_definition_writer;

TEST_SUITE("native_definition_writer") {

TEST_CASE("empty definition produces minimal JSON") {
    tuner_core::NativeEcuDefinition def;
    auto json = ndw::export_json(def, "test", "1.0");
    CHECK(json.find("tuner-definition-v1") != std::string::npos);
    CHECK(json.find("\"firmware\": \"test\"") != std::string::npos);
    CHECK(json.find("\"version\": \"1.0\"") != std::string::npos);
}

TEST_CASE("validate accepts valid export") {
    tuner_core::NativeEcuDefinition def;
    auto json = ndw::export_json(def);
    CHECK(ndw::validate_json(json).empty());
}

TEST_CASE("validate rejects invalid JSON") {
    CHECK(!ndw::validate_json("NOT JSON").empty());
}

TEST_CASE("validate rejects missing format") {
    CHECK(!ndw::validate_json(R"({"firmware": "test"})").empty());
}

TEST_CASE("production INI exports with real scalar and table counts") {
    const char* paths[] = {
        "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
    };
    std::filesystem::path ini_path;
    for (const char* p : paths)
        if (std::filesystem::exists(p)) { ini_path = p; break; }
    if (ini_path.empty()) { MESSAGE("INI not found"); return; }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    auto json = ndw::export_json(def, "speeduino", "202501-T41");

    CHECK(json.find("speeduino") != std::string::npos);
    CHECK(json.find("202501-T41") != std::string::npos);
    // Should have scalars and tables.
    CHECK(json.find("\"scalars\"") != std::string::npos);
    CHECK(json.find("\"tables\"") != std::string::npos);
    CHECK(json.find("\"curves\"") != std::string::npos);
    // Validate round-trip.
    CHECK(ndw::validate_json(json).empty());
    // Stats should show real counts.
    CHECK(json.find("\"scalar_count\"") != std::string::npos);
}

}  // TEST_SUITE
