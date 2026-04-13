// SPDX-License-Identifier: MIT
//
// tuner_core::flash_target_detection implementation. Direct port of
// the classification logic in Python `FlashTargetDetectionService`.

#include "tuner_core/flash_target_detection.hpp"

#include <cctype>
#include <cstdio>
#include <string>

namespace tuner_core::flash_target_detection {

std::optional<std::string> normalize_hex(std::string_view value) {
    // Mirror Python `_normalize_hex` exactly: for string inputs, run
    //   value.strip().removeprefix("0x").upper()
    // and return the result unconditionally (including empty string).
    // The Python `None` case (non-string input) is modeled by the
    // C++ `std::nullopt` return, but that path isn't reachable from
    // `string_view` callers. Empty string in → empty string out, not
    // nullopt.
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front())))
        value.remove_prefix(1);
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back())))
        value.remove_suffix(1);

    // Strip `0x` prefix — case-sensitive to match Python's
    // `.removeprefix("0x")`. Uppercase `0X` is deliberately NOT
    // stripped; the `.upper()` pass below turns `0X16c0` into
    // `0X16C0`, preserving the Python quirk exactly for parity.
    if (value.size() >= 2 && value[0] == '0' && value[1] == 'x') {
        value.remove_prefix(2);
    }

    // Uppercase every character (even empty string).
    std::string out;
    out.reserve(value.size());
    for (char c : value) {
        out.push_back(static_cast<char>(
            std::toupper(static_cast<unsigned char>(c))));
    }
    return out;
}

std::optional<TeensyIdentity> teensy_identity_from_pid_or_bcd(
    std::string_view pid, std::string_view bcd_device) {
    // bcdDevice → board_family map (HalfKay HID mode):
    //   0276 = Teensy 3.5
    //   0277 = Teensy 3.6
    //   0280 = Teensy 4.1
    if (bcd_device == "0276")
        return TeensyIdentity{BoardFamily::TEENSY35, "3.5"};
    if (bcd_device == "0277")
        return TeensyIdentity{BoardFamily::TEENSY36, "3.6"};
    if (bcd_device == "0280")
        return TeensyIdentity{BoardFamily::TEENSY41, "4.1"};

    // Serial-mode PIDs for Teensy 4.x — all map to TEENSY41 in the
    // Python side (Teensy 4.0 gets coalesced with 4.1 because the
    // Speeduino port doesn't distinguish them).
    if (pid == "0483" || pid == "0484" || pid == "0485" || pid == "0486")
        return TeensyIdentity{BoardFamily::TEENSY41, "4.1"};

    return std::nullopt;
}

std::optional<DetectedFlashTarget> classify_serial_port(
    std::string_view vid,
    std::string_view pid,
    std::string_view device,
    std::string_view description) {

    auto make_target = [&](BoardFamily family, const std::string& desc) {
        DetectedFlashTarget t;
        t.board_family = family;
        t.source = "serial";
        t.description = desc;
        t.serial_port = std::string(device);
        t.usb_vid = std::string(vid);
        t.usb_pid = std::string(pid);
        return t;
    };

    // 2341:0010 / 2341:0042 — Arduino Mega (official Atmel USB chip).
    if (vid == "2341" && (pid == "0010" || pid == "0042")) {
        std::string desc = std::string(device) + " (Arduino Mega)";
        return make_target(BoardFamily::ATMEGA2560, desc);
    }
    // 1A86:* — WCH CH340 USB-serial bridge on Arduino Mega clones.
    if (vid == "1A86") {
        std::string desc = std::string(device) + " (Arduino Mega CH340)";
        return make_target(BoardFamily::ATMEGA2560, desc);
    }
    // 16C0:* — PJRC vendor ID (Teensy serial mode). Look up the
    // specific Teensy by PID; fall back to TEENSY41 with the OS
    // description when PID is unknown (matches the Python fallback).
    if (vid == "16C0") {
        auto identity = teensy_identity_from_pid_or_bcd(pid, {});
        if (identity.has_value()) {
            std::string desc = std::string(device) + " (Teensy " + identity->label + ")";
            return make_target(identity->board_family, desc);
        }
        std::string desc = std::string(device) + " (" + std::string(description) + ")";
        return make_target(BoardFamily::TEENSY41, desc);
    }
    // 0483:5740 — STM32F407 in CDC-ACM serial mode. Flashing still
    // requires DFU, so surface it with a hint to the operator.
    if (vid == "0483" && pid == "5740") {
        std::string desc = std::string(device) +
            " (STM32F407 serial mode; use DFU for flashing)";
        return make_target(BoardFamily::STM32F407_DFU, desc);
    }

    return std::nullopt;
}

std::optional<DetectedFlashTarget> classify_usb_device(
    std::string_view vid,
    std::string_view pid,
    std::string_view bcd,
    bool has_hid_interface) {

    auto make_target = [&](BoardFamily family, const std::string& desc) {
        DetectedFlashTarget t;
        t.board_family = family;
        t.source = "usb";
        t.description = desc;
        // serial_port stays empty for USB-detected devices.
        t.usb_vid = std::string(vid);
        t.usb_pid = std::string(pid);
        return t;
    };

    // 16C0 + HID interface = Teensy in HalfKay flashing mode.
    if (vid == "16C0" && has_hid_interface) {
        auto identity = teensy_identity_from_pid_or_bcd(pid, bcd);
        if (!identity.has_value()) return std::nullopt;
        std::string desc = "Uninitialized Teensy " + identity->label;
        return make_target(identity->board_family, desc);
    }
    // 0483:* with bcdDevice 2200 = STM32F407 in DFU mode.
    if (vid == "0483" && bcd == "2200") {
        return make_target(BoardFamily::STM32F407_DFU, "STM32F407 in DFU mode");
    }

    return std::nullopt;
}

}  // namespace tuner_core::flash_target_detection
