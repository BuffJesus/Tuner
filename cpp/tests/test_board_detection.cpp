// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::board_detection.

#include "doctest.h"

#include "tuner_core/board_detection.hpp"

using namespace tuner_core::board_detection;

TEST_CASE("empty input returns nullopt") {
    CHECK_FALSE(detect_from_text("").has_value());
}

TEST_CASE("Teensy 4.1 detection covers all separator forms") {
    CHECK(detect_from_text("speeduino 202501-T41").value() == BoardFamily::TEENSY41);
    CHECK(detect_from_text("Teensy 4.1 build").value() == BoardFamily::TEENSY41);
    CHECK(detect_from_text("teensy_4.1").value() == BoardFamily::TEENSY41);
    CHECK(detect_from_text("TEENSY-4.1").value() == BoardFamily::TEENSY41);
    CHECK(detect_from_text("teensy41 build").value() == BoardFamily::TEENSY41);
}

TEST_CASE("Teensy 3.5 / 3.6 detection") {
    CHECK(detect_from_text("Teensy 3.5").value() == BoardFamily::TEENSY35);
    CHECK(detect_from_text("Teensy 3.6").value() == BoardFamily::TEENSY36);
    CHECK(detect_from_text("T35").value() == BoardFamily::TEENSY35);
    CHECK(detect_from_text("T36").value() == BoardFamily::TEENSY36);
}

TEST_CASE("STM32 F407 detection") {
    CHECK(detect_from_text("STM32F407").value() == BoardFamily::STM32F407_DFU);
    CHECK(detect_from_text("Black Pill F407 build").value() == BoardFamily::STM32F407_DFU);
    CHECK(detect_from_text("dfu").value() == BoardFamily::STM32F407_DFU);
}

TEST_CASE("ATMega2560 / Arduino Mega detection") {
    CHECK(detect_from_text("ATmega2560").value() == BoardFamily::ATMEGA2560);
    CHECK(detect_from_text("MEGA2560 build").value() == BoardFamily::ATMEGA2560);
    CHECK(detect_from_text("Arduino   Mega").value() == BoardFamily::ATMEGA2560);
}

TEST_CASE("Unrelated text yields nullopt") {
    CHECK_FALSE(detect_from_text("ESP32-S3").has_value());
    CHECK_FALSE(detect_from_text("speeduino").has_value());
}

TEST_CASE("detect_from_capabilities prefers signature text over the U16P2 fallback") {
    auto r = detect_from_capabilities(/*experimental_u16p2=*/true,
                                      /*signature=*/"speeduino 202501-T36");
    REQUIRE(r.has_value());
    CHECK(*r == BoardFamily::TEENSY36);
}

TEST_CASE("detect_from_capabilities falls back to TEENSY41 on U16P2 alone") {
    auto r = detect_from_capabilities(true, "");
    REQUIRE(r.has_value());
    CHECK(*r == BoardFamily::TEENSY41);
}

TEST_CASE("detect_from_capabilities returns nullopt with no signal") {
    CHECK_FALSE(detect_from_capabilities(false, "").has_value());
    CHECK_FALSE(detect_from_capabilities(false, "unrelated").has_value());
}

TEST_CASE("to_string mirrors the Python BoardFamily enum identifiers") {
    CHECK(to_string(BoardFamily::ATMEGA2560) == "ATMEGA2560");
    CHECK(to_string(BoardFamily::TEENSY35) == "TEENSY35");
    CHECK(to_string(BoardFamily::TEENSY36) == "TEENSY36");
    CHECK(to_string(BoardFamily::TEENSY41) == "TEENSY41");
    CHECK(to_string(BoardFamily::STM32F407_DFU) == "STM32F407_DFU");
}
