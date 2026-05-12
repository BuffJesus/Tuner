// SPDX-License-Identifier: MIT
//
// tuner_core::bench_simulator::controller — orchestration layer
// over `transport::Transport`. Sequences the Slice C protocol
// builders/parsers across a real (or mock) serial connection.
//
// Phase 17 Slice D. The TRIGGERS-tab Simulate panel (Slice E)
// drives the bench through this surface. The controller stays
// stateless — every function takes the transport reference as a
// parameter — so the UI can decide its own lifecycle.

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "tuner_core/bench_simulator_config_codec.hpp"
#include "tuner_core/bench_simulator_protocol.hpp"
#include "tuner_core/transport.hpp"

namespace tuner_core::bench_simulator::controller {

// Default timeouts. The firmware is an Arduino with a single-byte
// command parser, so responses arrive within milliseconds. Pad
// the line-aggregating commands (`L`, `P`) for slower buses.
inline constexpr double kQuickTimeoutS    = 0.25;
inline constexpr double kListTimeoutS     = 2.0;
inline constexpr double kPatternTimeoutS  = 1.5;

// ---------------------------------------------------------------
// Write-side: fire-and-forget commands.
// ---------------------------------------------------------------

// 'S' + 1-byte index. Caller is responsible for bounding the
// index against the firmware's MAX_WHEELS (use list_wheel_names
// or read_wheel_count to query).
void set_wheel(transport::Transport& t, std::uint8_t wheel_index);

// 'c' + 17-byte v2 (or 10-byte v1) configTable payload. Caller
// supplies the wire version that matches the connected firmware
// (detect via `read_config` and inspect the result's `version`
// field).
void send_config(transport::Transport& t,
                 const BenchSimulatorConfig& config,
                 std::uint8_t wire_version);

// 'r' + 6 LE bytes. Firmware switches `config.mode` to
// LINEAR_SWEPT_RPM as a side effect.
void set_sweep(transport::Transport& t,
               std::uint16_t low_rpm,
               std::uint16_t high_rpm,
               std::uint16_t interval_ms);

// 's' — save the firmware's in-memory config to EEPROM. No
// response; persistence is observable only on next power-up.
void save_to_eeprom(transport::Transport& t);

// ---------------------------------------------------------------
// Read-side: request-and-read-response.
// ---------------------------------------------------------------

// 'C' — request full configTable. Reads the firmware's response,
// dispatches to `decode_v1` (11 bytes) or `decode_v2` (18 bytes)
// via `decode_auto`. Returns nullopt on transport or parse error.
//
// This is the first command operators should call after connect —
// the response's `version` byte tells the host whether the
// firmware supports the compression-cycle simulator.
std::optional<BenchSimulatorConfig> read_config(
    transport::Transport& t,
    double timeout_s = kQuickTimeoutS);

// 'L' — request line-delimited list of decoder names. Reads
// chunks until `expected_count` lines have arrived or the
// timeout exhausts. Returns whatever lines were collected (may
// be fewer than `expected_count` on timeout).
//
// Pass the result of `read_wheel_count` as `expected_count` for
// best-effort completion; pass 0 to read until timeout regardless.
std::vector<std::string> list_wheel_names(
    transport::Transport& t,
    std::size_t expected_count = 0,
    double timeout_s = kListTimeoutS);

// 'n' — request MAX_WHEELS (the firmware's compiled-in pattern count).
std::optional<std::uint32_t> read_wheel_count(
    transport::Transport& t,
    double timeout_s = kQuickTimeoutS);

// 'N' — request the firmware's current wheel index.
std::optional<std::uint32_t> read_current_wheel_index(
    transport::Transport& t,
    double timeout_s = kQuickTimeoutS);

// 'p' — request the current wheel's max_edges (pattern length).
std::optional<std::uint32_t> read_current_wheel_size(
    transport::Transport& t,
    double timeout_s = kQuickTimeoutS);

// 'P' — request the current wheel's edge state pattern (CSV)
// plus the wheel_degrees count (typically 360 or 720). Reads
// until both lines arrive or the timeout exhausts.
std::optional<WheelPatternResponse> read_current_wheel_pattern(
    transport::Transport& t,
    double timeout_s = kPatternTimeoutS);

// 'R' — request the firmware's current synthesized RPM.
std::optional<std::uint32_t> read_current_rpm(
    transport::Transport& t,
    double timeout_s = kQuickTimeoutS);

// 'X' — advance the firmware to the next wheel index and read
// back the name of the now-selected wheel. Test command intended
// for jog-through-the-catalog operator workflows.
std::string select_next_wheel(
    transport::Transport& t,
    double timeout_s = kQuickTimeoutS);

// ---------------------------------------------------------------
// Helpers for building common configs.
// ---------------------------------------------------------------

// Build a config sized for fixed-RPM operation. `wheel` defaults
// to 0 so the caller can pre-select via `set_wheel`.
BenchSimulatorConfig make_fixed_rpm_config(std::uint16_t rpm,
                                           std::uint8_t wheel = 0);

// Build a config sized for linear-swept-RPM operation. Note that
// sending this via `send_config` does NOT set the mode flag (the
// firmware sets it only on receipt of an `r` command); pair with
// an explicit `set_sweep` call to enable sweep mode.
BenchSimulatorConfig make_sweep_config(std::uint16_t low_rpm,
                                       std::uint16_t high_rpm,
                                       std::uint16_t interval_ms,
                                       std::uint8_t wheel = 0);

// Build a config with the v2 compression-cycle simulator enabled.
// `type` must be a firmware-supported value (see
// `is_compression_type_firmware_supported`). Operator-facing UI
// should gate selection through `compression_type_from_cylinders`.
BenchSimulatorConfig make_compression_enabled_config(
    CompressionType type,
    std::uint16_t target_rpm,
    std::uint16_t offset = 0,
    bool dynamic = false,
    std::uint8_t wheel = 0);

}  // namespace tuner_core::bench_simulator::controller
