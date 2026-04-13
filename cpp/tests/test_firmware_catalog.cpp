// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/firmware_catalog.hpp"

namespace fc = tuner_core::firmware_catalog;

TEST_SUITE("firmware_catalog") {

TEST_CASE("board_from_filename detects Teensy 4.1") {
    CHECK(fc::board_from_filename("speeduino-dropbear-v2.0.1-teensy41.hex") == fc::BoardFamily::TEENSY41);
    CHECK(fc::board_from_filename("firmware-t41.hex") == fc::BoardFamily::TEENSY41);
}

TEST_CASE("board_from_filename detects STM32") {
    CHECK(fc::board_from_filename("stm32f407-firmware.hex") == fc::BoardFamily::STM32F407_DFU);
    CHECK(fc::board_from_filename("f407-test.hex") == fc::BoardFamily::STM32F407_DFU);
}

TEST_CASE("board_from_filename detects AVR") {
    CHECK(fc::board_from_filename("speeduino-atmega2560.hex") == fc::BoardFamily::ATMEGA2560);
    CHECK(fc::board_from_filename("mega-firmware.hex") == fc::BoardFamily::ATMEGA2560);
}

TEST_CASE("board_from_filename unknown") {
    CHECK(fc::board_from_filename("generic-firmware.hex") == fc::BoardFamily::UNKNOWN);
}

TEST_CASE("version_from_filename extracts version") {
    auto v = fc::version_from_filename("speeduino-dropbear-v2.0.1-teensy41.hex");
    REQUIRE(v.has_value());
    CHECK(*v == "v2.0.1");
}

TEST_CASE("version_from_filename no version") {
    CHECK_FALSE(fc::version_from_filename("no-version-here.hex").has_value());
}

TEST_CASE("score_entry excludes diagnostic when not requested") {
    fc::CatalogEntry e;
    e.artifact_kind = fc::ArtifactKind::DIAGNOSTIC;
    fc::ScoringContext ctx;
    CHECK(fc::score_entry(e, ctx) == 0);
}

TEST_CASE("score_entry includes diagnostic when requested") {
    fc::CatalogEntry e;
    e.artifact_kind = fc::ArtifactKind::DIAGNOSTIC;
    fc::ScoringContext ctx;
    ctx.include_diagnostic = true;
    CHECK(fc::score_entry(e, ctx) > 0);
}

TEST_CASE("score_entry board mismatch returns 0") {
    fc::CatalogEntry e;
    e.board_family = fc::BoardFamily::ATMEGA2560;
    fc::ScoringContext ctx;
    ctx.preferred_board = fc::BoardFamily::TEENSY41;
    CHECK(fc::score_entry(e, ctx) == 0);
}

TEST_CASE("score_entry matching board gets high score") {
    fc::CatalogEntry e;
    e.board_family = fc::BoardFamily::TEENSY41;
    fc::ScoringContext ctx;
    ctx.preferred_board = fc::BoardFamily::TEENSY41;
    CHECK(fc::score_entry(e, ctx) > 100);
}

TEST_CASE("score_entry signature match boosts score") {
    fc::CatalogEntry e;
    e.firmware_signature = "speeduino 202501-T41";
    fc::ScoringContext ctx;
    ctx.definition_signature = "speeduino 202501-T41";
    int with_match = fc::score_entry(e, ctx);

    fc::CatalogEntry e2;
    e2.firmware_signature = "speeduino 202501-T41";
    fc::ScoringContext ctx2;
    ctx2.definition_signature = "something-else";
    int without = fc::score_entry(e2, ctx2);

    CHECK(with_match > without);
}

TEST_CASE("score_entry experimental preference") {
    fc::CatalogEntry e;
    e.is_experimental = true;
    fc::ScoringContext ctx;
    ctx.definition_signature = "speeduino 202501-T41-U16P2";  // experimental
    int exp_score = fc::score_entry(e, ctx);

    fc::CatalogEntry e2;
    e2.is_experimental = true;
    fc::ScoringContext ctx2;
    ctx2.definition_signature = "speeduino 202501-T41";  // non-experimental
    int non_exp_score = fc::score_entry(e2, ctx2);

    CHECK(exp_score > non_exp_score);
}

}  // TEST_SUITE
