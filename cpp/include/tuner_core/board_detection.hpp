// SPDX-License-Identifier: MIT
//
// tuner_core::board_detection — port of `BoardDetectionService`.
// Eighth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Two pure-logic detectors:
//   - detect_from_text(text): regex-driven board family detection from
//     a definition name, firmware signature, controller name, etc.
//   - detect_from_capabilities(experimental_u16p2, signature): the
//     authoritative path used when a live session has handshake data
//     — falls back to detect_from_text on the signature, then to a
//     single capability bit (U16P2 ⇒ Teensy 4.1).
//
// The full Python `detect()` entry point chains five candidate
// strings through `detect_from_text` plus a `detect_from_capabilities`
// pre-pass; that orchestration is left for the C++ workspace
// presenter to wire up once the surrounding domain types land.

#pragma once

#include <optional>
#include <string>
#include <string_view>

namespace tuner_core::board_detection {

enum class BoardFamily {
    ATMEGA2560,
    TEENSY35,
    TEENSY36,
    TEENSY41,
    STM32F407_DFU,
};

// Stringify the enum to the same identifier the Python `BoardFamily`
// StrEnum produces (e.g. `"TEENSY41"`). Useful for the parity test
// and for any future operator-facing surface that prints the family.
std::string_view to_string(BoardFamily family) noexcept;

// Run the regex-driven text detector. Returns nullopt when nothing
// matches. Mirrors `BoardDetectionService._detect_from_text` exactly:
// uppercases the input, then walks the same 5 word-boundary patterns
// in the same order.
std::optional<BoardFamily> detect_from_text(std::string_view text);

// Run the capability-driven detector. Mirrors
// `BoardDetectionService.detect_from_capabilities`: the firmware
// signature (when present) takes precedence via the text detector,
// then `experimental_u16p2` falls back to TEENSY41, then nullopt.
std::optional<BoardFamily> detect_from_capabilities(
    bool experimental_u16p2,
    std::string_view signature = {});

}  // namespace tuner_core::board_detection
