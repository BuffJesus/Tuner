// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::flash_target_detection. Mirrors
// tests/unit/test_flash_target_detection_service.py on the Python side.

#include "doctest.h"

#include "tuner_core/flash_target_detection.hpp"

namespace ftd = tuner_core::flash_target_detection;

TEST_CASE("normalize_hex strips lowercase 0x prefix and uppercases") {
    CHECK(ftd::normalize_hex("0x2341").value() == "2341");
    // Python's `.removeprefix("0x")` is case-sensitive — uppercase
    // `0X` is intentionally NOT stripped. Match that behaviour so
    // parity tests line up.
    CHECK(ftd::normalize_hex("0X16c0").value() == "0X16C0");
    CHECK(ftd::normalize_hex("16c0").value() == "16C0");
    CHECK(ftd::normalize_hex("  0483  ").value() == "0483");
}

TEST_CASE("normalize_hex returns empty string for empty input (Python parity)") {
    // Python `_normalize_hex("")` returns empty string via
    // `"".strip().removeprefix("0x").upper()`, NOT None. Mirror that.
    CHECK(ftd::normalize_hex("").value() == "");
    CHECK(ftd::normalize_hex("   ").value() == "");
    CHECK(ftd::normalize_hex("0x").value() == "");
}

TEST_CASE("teensy_identity_from_pid_or_bcd resolves HalfKay HID bcdDevice") {
    auto t35 = ftd::teensy_identity_from_pid_or_bcd("", "0276");
    REQUIRE(t35.has_value());
    CHECK(t35->board_family == ftd::BoardFamily::TEENSY35);
    CHECK(t35->label == "3.5");

    auto t36 = ftd::teensy_identity_from_pid_or_bcd("", "0277");
    REQUIRE(t36.has_value());
    CHECK(t36->board_family == ftd::BoardFamily::TEENSY36);
    CHECK(t36->label == "3.6");

    auto t41 = ftd::teensy_identity_from_pid_or_bcd("", "0280");
    REQUIRE(t41.has_value());
    CHECK(t41->board_family == ftd::BoardFamily::TEENSY41);
    CHECK(t41->label == "4.1");
}

TEST_CASE("teensy_identity_from_pid_or_bcd resolves Teensy 4.x serial PIDs") {
    for (const char* pid : {"0483", "0484", "0485", "0486"}) {
        auto id = ftd::teensy_identity_from_pid_or_bcd(pid, "");
        REQUIRE(id.has_value());
        CHECK(id->board_family == ftd::BoardFamily::TEENSY41);
        CHECK(id->label == "4.1");
    }
}

TEST_CASE("teensy_identity_from_pid_or_bcd returns nullopt for unknowns") {
    CHECK(!ftd::teensy_identity_from_pid_or_bcd("FFFF", "FFFF").has_value());
    CHECK(!ftd::teensy_identity_from_pid_or_bcd("", "").has_value());
}

TEST_CASE("classify_serial_port: Arduino Mega official VID/PID") {
    auto t = ftd::classify_serial_port("2341", "0010", "COM3", "Arduino Mega 2560");
    REQUIRE(t.has_value());
    CHECK(t->board_family == ftd::BoardFamily::ATMEGA2560);
    CHECK(t->source == "serial");
    CHECK(t->description == "COM3 (Arduino Mega)");
    CHECK(t->serial_port == "COM3");
    CHECK(t->usb_vid == "2341");
    CHECK(t->usb_pid == "0010");

    auto t2 = ftd::classify_serial_port("2341", "0042", "COM4", "Arduino Mega");
    REQUIRE(t2.has_value());
    CHECK(t2->board_family == ftd::BoardFamily::ATMEGA2560);
}

TEST_CASE("classify_serial_port: CH340 clone") {
    auto t = ftd::classify_serial_port("1A86", "7523", "COM5", "USB-SERIAL CH340");
    REQUIRE(t.has_value());
    CHECK(t->board_family == ftd::BoardFamily::ATMEGA2560);
    CHECK(t->description == "COM5 (Arduino Mega CH340)");
}

TEST_CASE("classify_serial_port: Teensy 4.1 via known PID") {
    auto t = ftd::classify_serial_port("16C0", "0483", "COM6", "USB Serial");
    REQUIRE(t.has_value());
    CHECK(t->board_family == ftd::BoardFamily::TEENSY41);
    CHECK(t->description == "COM6 (Teensy 4.1)");
}

TEST_CASE("classify_serial_port: 16C0 unknown PID falls back to TEENSY41") {
    auto t = ftd::classify_serial_port("16C0", "FFFF", "COM7", "PJRC Mystery");
    REQUIRE(t.has_value());
    CHECK(t->board_family == ftd::BoardFamily::TEENSY41);
    CHECK(t->description == "COM7 (PJRC Mystery)");
}

TEST_CASE("classify_serial_port: STM32F407 CDC-ACM flagged as DFU") {
    auto t = ftd::classify_serial_port("0483", "5740", "COM8", "STM32 Virtual COM");
    REQUIRE(t.has_value());
    CHECK(t->board_family == ftd::BoardFamily::STM32F407_DFU);
    CHECK(t->description.find("use DFU for flashing") != std::string::npos);
}

TEST_CASE("classify_serial_port: unknown VID returns nullopt") {
    CHECK(!ftd::classify_serial_port("FFFF", "0000", "COM9", "").has_value());
}

TEST_CASE("classify_usb_device: uninitialized Teensy 4.1 via HID + bcdDevice") {
    auto t = ftd::classify_usb_device("16C0", "0478", "0280", true);
    REQUIRE(t.has_value());
    CHECK(t->board_family == ftd::BoardFamily::TEENSY41);
    CHECK(t->source == "usb");
    CHECK(t->description == "Uninitialized Teensy 4.1");
    CHECK(t->usb_vid == "16C0");
    CHECK(t->serial_port.empty());
}

TEST_CASE("classify_usb_device: uninitialized Teensy 3.5 via HID + bcdDevice") {
    auto t = ftd::classify_usb_device("16C0", "0478", "0276", true);
    REQUIRE(t.has_value());
    CHECK(t->board_family == ftd::BoardFamily::TEENSY35);
    CHECK(t->description == "Uninitialized Teensy 3.5");
}

TEST_CASE("classify_usb_device: 16C0 without HID interface returns nullopt") {
    // No HID → not in HalfKay mode, even if bcdDevice would match.
    CHECK(!ftd::classify_usb_device("16C0", "0478", "0280", false).has_value());
}

TEST_CASE("classify_usb_device: 16C0 with HID but unknown bcd returns nullopt") {
    CHECK(!ftd::classify_usb_device("16C0", "0000", "FFFF", true).has_value());
}

TEST_CASE("classify_usb_device: STM32F407 DFU") {
    auto t = ftd::classify_usb_device("0483", "DF11", "2200", false);
    REQUIRE(t.has_value());
    CHECK(t->board_family == ftd::BoardFamily::STM32F407_DFU);
    CHECK(t->description == "STM32F407 in DFU mode");
}

TEST_CASE("classify_usb_device: unknown VID returns nullopt") {
    CHECK(!ftd::classify_usb_device("FFFF", "0000", "0000", true).has_value());
}

// BoardFamily enum round-trip lives in test_board_detection.cpp now —
// flash_target_detection reuses the same type via a `using` alias so
// there's no duplicate helper to test here.
