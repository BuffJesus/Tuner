// SPDX-License-Identifier: MIT
//
// TRIGGERS-tab "Simulate" sub-panel — drives an Ardu-stim bench
// simulator over a separate serial port. Replaces the standalone
// Electron GUI (`resources/Ardu-Stim-master/UI/`).
//
// Phase 17 Slice E. Builds on the pure-logic
// `tuner_core::bench_simulator::{wheel_pattern_catalog,config_codec,
// protocol,controller}` services committed in Slices A–D.
//
// Phase 17 Slice F adds the `set_pending_prefill` /
// `take_pending_prefill` cross-tab handoff so the SETUP wizard can
// nudge the panel to pre-select a wheel + compression-type on next
// open.

#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>
#include <string>

class QWidget;

// External: serial port enumeration (defined in main.cpp).
std::vector<std::string> list_serial_ports();

// Builds the Simulate sub-panel. Returns a card-styled QWidget*
// ready to be inserted into the TRIGGERS tab layout. Owns its own
// SerialTransport (separate from the ECU connection) so the
// operator can drive the simulator and the ECU at the same time
// without port conflicts.
//
// On construction the panel consumes any pending prefill set via
// `set_pending_prefill` — see Phase 17 Slice F.
QWidget* build_triggers_simulate_panel();

// Cross-tab handoff. Slice F: SETUP wizard stashes "operator picked
// 8 cylinders + 36-1 trigger" via this setter; the next
// `build_triggers_simulate_panel()` call drains it on construction.
struct BenchSimulatorPrefill {
    std::optional<std::size_t> wheel_index;        // index into wheel_pattern_catalog
    std::optional<std::uint8_t> compression_cyl;   // 2/4/6/8 → CompressionType
};

void set_pending_prefill(const BenchSimulatorPrefill& prefill);

// Drains the pending prefill (returns it once, then resets to empty).
// Called automatically by `build_triggers_simulate_panel()` — exposed
// for tests / introspection only.
BenchSimulatorPrefill take_pending_prefill();
