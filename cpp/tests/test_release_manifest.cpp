// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::release_manifest.

#include "doctest.h"

#include "tuner_core/release_manifest.hpp"

#include <stdexcept>
#include <string>

using namespace tuner_core::release_manifest;
using BoardFamily = tuner_core::board_detection::BoardFamily;

TEST_CASE("parse_manifest_text: empty firmware list yields empty manifest") {
    auto m = parse_manifest_text(R"({"firmware": []})");
    CHECK(m.firmware.empty());
}

TEST_CASE("parse_manifest_text: minimal entry uses defaults") {
    auto m = parse_manifest_text(R"({
        "firmware": [
            {"file": "speeduino.hex"}
        ]
    })");
    REQUIRE(m.firmware.size() == 1);
    const auto& e = m.firmware[0];
    CHECK(e.file_name == "speeduino.hex");
    CHECK_FALSE(e.board_family.has_value());
    CHECK_FALSE(e.version_label.has_value());
    CHECK_FALSE(e.is_experimental);
    CHECK(e.artifact_kind == ArtifactKind::STANDARD);
    CHECK_FALSE(e.preferred);
    CHECK_FALSE(e.definition_file_name.has_value());
    CHECK_FALSE(e.tune_file_name.has_value());
    CHECK_FALSE(e.firmware_signature.has_value());
}

TEST_CASE("parse_manifest_text: full entry populates every field") {
    auto m = parse_manifest_text(R"({
        "firmware": [
            {
                "file": "speeduino-dropbear-v2.0.1.hex",
                "board_family": "TEENSY41",
                "version": "v2.0.1",
                "is_experimental": false,
                "artifact_kind": "standard",
                "preferred": true,
                "definition_file": "speeduino-dropbear-v2.0.1.ini",
                "tune_file": "Ford300_TwinGT28_BaseStartup.msq",
                "firmware_signature": "speeduino 202501-T41"
            }
        ]
    })");
    REQUIRE(m.firmware.size() == 1);
    const auto& e = m.firmware[0];
    CHECK(e.file_name == "speeduino-dropbear-v2.0.1.hex");
    REQUIRE(e.board_family.has_value());
    CHECK(*e.board_family == BoardFamily::TEENSY41);
    CHECK(e.version_label.value() == "v2.0.1");
    CHECK_FALSE(e.is_experimental);
    CHECK(e.artifact_kind == ArtifactKind::STANDARD);
    CHECK(e.preferred);
    CHECK(e.definition_file_name.value() == "speeduino-dropbear-v2.0.1.ini");
    CHECK(e.tune_file_name.value() == "Ford300_TwinGT28_BaseStartup.msq");
    CHECK(e.firmware_signature.value() == "speeduino 202501-T41");
}

TEST_CASE("parse_manifest_text: experimental entry with diagnostic kind") {
    auto m = parse_manifest_text(R"({
        "firmware": [
            {
                "file": "diag.hex",
                "is_experimental": true,
                "artifact_kind": "diagnostic"
            }
        ]
    })");
    REQUIRE(m.firmware.size() == 1);
    CHECK(m.firmware[0].is_experimental);
    CHECK(m.firmware[0].artifact_kind == ArtifactKind::DIAGNOSTIC);
}

TEST_CASE("parse_manifest_text: missing 'file' raises") {
    CHECK_THROWS_AS(
        parse_manifest_text(R"({"firmware": [{"board_family": "TEENSY41"}]})"),
        std::runtime_error);
}

TEST_CASE("parse_manifest_text: blank 'file' raises") {
    CHECK_THROWS_AS(
        parse_manifest_text(R"({"firmware": [{"file": "  "}]})"),
        std::runtime_error);
}

TEST_CASE("parse_manifest_text: unknown board_family raises") {
    CHECK_THROWS_AS(
        parse_manifest_text(R"({"firmware": [{"file":"a.hex","board_family":"NOT_A_BOARD"}]})"),
        std::runtime_error);
}

TEST_CASE("parse_manifest_text: unknown artifact_kind raises") {
    CHECK_THROWS_AS(
        parse_manifest_text(R"({"firmware": [{"file":"a.hex","artifact_kind":"weird"}]})"),
        std::runtime_error);
}

TEST_CASE("parse_manifest_text: 'firmware' must be a list") {
    CHECK_THROWS_AS(
        parse_manifest_text(R"({"firmware": "not-a-list"})"),
        std::runtime_error);
}

TEST_CASE("parse_manifest_text: malformed JSON raises") {
    CHECK_THROWS_AS(parse_manifest_text("{ invalid"), std::runtime_error);
}

TEST_CASE("to_string mirrors the Python FirmwareArtifactKind values") {
    CHECK(to_string(ArtifactKind::STANDARD) == "standard");
    CHECK(to_string(ArtifactKind::DIAGNOSTIC) == "diagnostic");
}
