// SPDX-License-Identifier: MIT
//
// tuner_core::flash_target_detection — pure-logic classifier half of
// the Python `FlashTargetDetectionService`. Ports the VID/PID/BCD
// lookup tables and `DetectedFlashTarget` construction logic without
// the Python side's I/O (`serial.tools.list_ports` / `usb.core`),
// which the C++ app's future transport layer will supply through
// caller-injected inputs.
//
// Python is the parity oracle. Every classification decision here
// matches `FlashTargetDetectionService._detect_serial_targets` /
// `_detect_usb_targets` / `_teensy_identity_from_pid_or_bcd` /
// `_normalize_hex` byte-for-byte on the same VID/PID inputs.

#pragma once

#include "tuner_core/board_detection.hpp"

#include <optional>
#include <string>
#include <string_view>

namespace tuner_core::flash_target_detection {

// Reuse the canonical `BoardFamily` enum from the earlier-ported
// board_detection service — both services decode the same concept
// (which Speeduino-compatible board this hardware is), so keeping
// a single type avoids duplicate enum registrations in the nanobind
// bindings and lets downstream code pass families between the two
// services without conversion.
using BoardFamily = tuner_core::board_detection::BoardFamily;

// Detected target POD. Mirrors `DetectedFlashTarget` on the Python
// side. Empty strings mean "field absent" (Python equivalent: None).
struct DetectedFlashTarget {
    BoardFamily board_family = BoardFamily::TEENSY41;
    std::string source;        // "serial" | "usb"
    std::string description;
    std::string serial_port;   // empty when source == "usb"
    std::string usb_vid;       // uppercase 4-hex-digit
    std::string usb_pid;       // uppercase 4-hex-digit
};

// Normalize a VID/PID/BCD value to the uppercase 4-hex-digit string
// form the classifier expects. Accepts:
//   - uppercase / lowercase hex strings with optional `0x` prefix
//   - raw integer values (pass as string form of the int; callers
//     that hold ints should format with `"%04X"` before calling)
// Returns std::nullopt for empty input.
//
// Mirrors `FlashTargetDetectionService._normalize_hex` behaviour —
// intentionally does NOT zero-pad short strings (Python only
// normalizes case and strips the `0x` prefix for string inputs).
std::optional<std::string> normalize_hex(std::string_view value);

// Subset of a Teensy's identity that the Python side returns as an
// inline dataclass. Kept separate from `DetectedFlashTarget` so
// callers can distinguish "recognised Teensy" (identity present)
// from "16C0 device that isn't a known Teensy" (identity absent).
struct TeensyIdentity {
    BoardFamily board_family;
    std::string label;  // "3.5" | "3.6" | "4.1"
};

// Look up a Teensy's board family from its USB PID (serial mode) or
// bcdDevice (HalfKay HID mode). Mirrors
// `FlashTargetDetectionService._teensy_identity_from_pid_or_bcd`.
//
// Returns std::nullopt when neither PID nor BCD match a known Teensy.
// Empty strings count as absent — pass through via optional chain.
std::optional<TeensyIdentity> teensy_identity_from_pid_or_bcd(
    std::string_view pid, std::string_view bcd_device);

// Classify a single serial-port descriptor. `vid` and `pid` must
// already be normalized to the uppercase 4-hex-digit form via
// `normalize_hex`. `device` is the OS device path (e.g. `COM3` or
// `/dev/ttyUSB0`). `description` is the human-readable port label.
//
// Returns std::nullopt when the VID/PID combination isn't a known
// Speeduino-compatible board — callers should skip such ports.
std::optional<DetectedFlashTarget> classify_serial_port(
    std::string_view vid,
    std::string_view pid,
    std::string_view device,
    std::string_view description);

// Classify a USB device in a non-serial mode (HalfKay HID, DFU, etc).
// `has_hid_interface` must reflect whether the device exposes a USB
// HID interface (bInterfaceClass == 3) — the Python equivalent of
// `_device_has_hid_interface`. `vid`, `pid`, and `bcd` must be
// normalized via `normalize_hex`.
//
// Returns std::nullopt when the device isn't a known uninitialized
// Teensy or STM32 in DFU mode.
std::optional<DetectedFlashTarget> classify_usb_device(
    std::string_view vid,
    std::string_view pid,
    std::string_view bcd,
    bool has_hid_interface);

}  // namespace tuner_core::flash_target_detection
