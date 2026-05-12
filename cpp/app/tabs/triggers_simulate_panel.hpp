// SPDX-License-Identifier: MIT
//
// TRIGGERS-tab "Simulate" sub-panel — drives an Ardu-stim bench
// simulator over a separate serial port. Replaces the standalone
// Electron GUI (`resources/Ardu-Stim-master/UI/`).
//
// Phase 17 Slice E. Builds on the pure-logic
// `tuner_core::bench_simulator::{wheel_pattern_catalog,config_codec,
// protocol,controller}` services committed in Slices A–D.

#pragma once

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
QWidget* build_triggers_simulate_panel();
