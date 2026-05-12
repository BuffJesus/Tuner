// SPDX-License-Identifier: MIT
//
// tuner_core::bench_simulator::protocol — port of the host
// command/response byte shapes for the 13 single-char serial
// commands exchanged with the Ardu-Stim firmware at 115200 baud.
//
// Phase 17 Slice C. Pure-logic byte builders + line parsers; no
// transport, no I/O. Slice D (`controller`) sequences these over
// `SerialTransport`.
//
// Reference: `resources/Ardu-Stim-master/ardustim/ardustim/comms.cpp`
// (every `case 'X':` block in `commandParser()`).
//
// Command summary (host perspective, lowercase = parameterised,
// uppercase = single-byte request):
//
//   'a'  — no-op placeholder
//   'c'  — host sends the configTable payload (17 bytes v2,
//          10 bytes v1; version byte omitted per firmware quirk
//          documented in comms.cpp:68-73)
//   'C'  — firmware responds with sizeof(configTable) bytes
//          (18 v2 / 11 v1, version byte INCLUDED)
//   'L'  — firmware responds with `MAX_WHEELS` decoder names,
//          one per line (`Serial.println(buf)` ⇒ `\r\n`-terminated)
//   'n'  — firmware responds with one decimal line: `MAX_WHEELS`
//   'N'  — firmware responds with one decimal line: current wheel index
//   'p'  — firmware responds with one decimal line: current wheel max_edges
//   'P'  — firmware responds with two lines:
//             line 1: comma-separated edge state bytes (0..7 mask)
//             line 2: wheel_degrees (typically 360 or 720)
//   'R'  — firmware responds with one decimal line: current RPM
//   'r'  — host sends 6 bytes after 'r': sweep_low_rpm, sweep_high_rpm,
//          sweep_interval — each as little-endian u16. Firmware sets
//          mode = LINEAR_SWEPT_RPM as a side effect.
//   's'  — save current config to EEPROM (no response)
//   'S'  — host sends 1 byte after 'S': wheel index (`< MAX_WHEELS`)
//   'X'  — firmware advances to the next wheel and responds with
//          that wheel's name on one line

#pragma once

#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "tuner_core/bench_simulator_config_codec.hpp"

namespace tuner_core::bench_simulator {

// Serial port configuration the firmware speaks (comms.cpp:51).
inline constexpr std::uint32_t kBaudRate = 115200;

// Single-char command identifiers, exposed as named constants so
// call sites read like "send Command::REQUEST_CONFIG" rather than
// "send byte 0x43".
struct Command {
    static constexpr std::uint8_t NOOP                  = 'a';
    static constexpr std::uint8_t SEND_CONFIG           = 'c';
    static constexpr std::uint8_t REQUEST_CONFIG        = 'C';
    static constexpr std::uint8_t REQUEST_WHEEL_LIST    = 'L';
    static constexpr std::uint8_t REQUEST_WHEEL_COUNT   = 'n';
    static constexpr std::uint8_t REQUEST_CURRENT_WHEEL = 'N';
    static constexpr std::uint8_t REQUEST_WHEEL_SIZE    = 'p';
    static constexpr std::uint8_t REQUEST_WHEEL_PATTERN = 'P';
    static constexpr std::uint8_t REQUEST_CURRENT_RPM   = 'R';
    static constexpr std::uint8_t SET_SWEEP_RPM         = 'r';
    static constexpr std::uint8_t SAVE_CONFIG           = 's';
    static constexpr std::uint8_t SET_WHEEL             = 'S';
    static constexpr std::uint8_t NEXT_WHEEL            = 'X';
};

// ---------------------------------------------------------------
// Command builders — produce the exact bytes the host writes.
// ---------------------------------------------------------------

inline std::vector<std::uint8_t> build_noop()                   { return {Command::NOOP}; }
inline std::vector<std::uint8_t> build_request_config()         { return {Command::REQUEST_CONFIG}; }
inline std::vector<std::uint8_t> build_request_wheel_list()     { return {Command::REQUEST_WHEEL_LIST}; }
inline std::vector<std::uint8_t> build_request_wheel_count()    { return {Command::REQUEST_WHEEL_COUNT}; }
inline std::vector<std::uint8_t> build_request_current_wheel()  { return {Command::REQUEST_CURRENT_WHEEL}; }
inline std::vector<std::uint8_t> build_request_wheel_size()     { return {Command::REQUEST_WHEEL_SIZE}; }
inline std::vector<std::uint8_t> build_request_wheel_pattern()  { return {Command::REQUEST_WHEEL_PATTERN}; }
inline std::vector<std::uint8_t> build_request_current_rpm()    { return {Command::REQUEST_CURRENT_RPM}; }
inline std::vector<std::uint8_t> build_save_config()            { return {Command::SAVE_CONFIG}; }
inline std::vector<std::uint8_t> build_next_wheel()             { return {Command::NEXT_WHEEL}; }

// 'S' + 1-byte wheel index. Caller is responsible for bounding
// `index < MAX_WHEELS`; the firmware silently ignores out-of-range
// indices (comms.cpp:143).
std::vector<std::uint8_t> build_set_wheel(std::uint8_t wheel_index);

// 'r' + 6 bytes: 3 × little-endian u16 (low_rpm, high_rpm,
// interval_ms). Sets `config.mode = LINEAR_SWEPT_RPM` as a
// firmware side effect.
std::vector<std::uint8_t> build_set_sweep_rpm(std::uint16_t low_rpm,
                                              std::uint16_t high_rpm,
                                              std::uint16_t interval_ms);

// 'c' + configTable payload **without** the leading version byte.
// Firmware reads `sizeof(configTable)-1` bytes starting at struct
// offset 1 (comms.cpp:69-73). For v2 firmware this emits 'c' + 17
// bytes; for v1 firmware, 'c' + 10 bytes. Caller selects schema
// via `wire_version` (kSchemaVersionV1 or kSchemaVersionV2).
//
// Returns an empty vector if `wire_version` is unrecognised.
std::vector<std::uint8_t> build_send_config(const BenchSimulatorConfig& config,
                                            std::uint8_t wire_version);

// ---------------------------------------------------------------
// Response parsers — decode the firmware's reply bytes.
// ---------------------------------------------------------------

// Parse a `C` response payload — passes through to `decode_auto`
// in the config codec.
std::optional<BenchSimulatorConfig> parse_config_response(std::span<const std::uint8_t> payload);

// Parse an `L` response: line-delimited decoder names (`Serial.println`
// emits `\r\n`). Handles trailing `\r\n`, bare `\n`, and a trailing
// empty line gracefully. Returns the names in order.
std::vector<std::string> parse_wheel_list_response(std::string_view text);

// Parse a single decimal-line response (`n`, `N`, `p`, `R`).
// Strips trailing `\r\n` or `\n`, then parses the leading
// decimal token. Returns nullopt on empty / non-numeric input.
std::optional<std::uint32_t> parse_decimal_line(std::string_view text);

struct WheelPatternResponse {
    std::vector<std::uint8_t> edge_states;  // each entry in [0, 7] mask
    std::uint16_t             wheel_degrees = 0;
};

// Parse a `P` response: two lines.
// Line 1: comma-separated decimal edge states.
// Line 2: wheel_degrees as decimal.
// Returns nullopt when fewer than 2 lines exist, line 2 isn't
// decimal, or any line-1 token isn't decimal.
std::optional<WheelPatternResponse> parse_wheel_pattern_response(std::string_view text);

// Parse the single-line response to an `X` command — just the
// trimmed decoder name. Empty input returns an empty string.
std::string parse_next_wheel_response(std::string_view text);

}  // namespace tuner_core::bench_simulator
