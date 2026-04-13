// SPDX-License-Identifier: MIT
//
// tuner_core::protocol_simulator — pure-logic port of the
// command-dispatch + runtime-values half of
// `src/tuner/simulator/protocol_simulator.py`. Pairs with the JSON
// line packet codec under `tuner.comms.packet_codec` (still Python).
//
// The Python `ProtocolSimulatorServer` is half pure-logic (compute a
// deterministic runtime snapshot from a tick counter, dispatch a
// fully-parsed JSON payload to the right response shape) and half
// I/O (TCP socket accept loop, line-buffered `recv` / `sendall`).
// This module owns only the pure half — the bytes-on-the-wire half
// stays Python where the threading model lives.
//
// The public API speaks JSON via `std::string` so callers don't have
// to depend on the internal nlohmann/json single-header that backs
// the implementation.

#pragma once

#include <map>
#include <string>
#include <string_view>

namespace tuner_core::protocol_simulator {

// Mirror of `SimulatorState`. `parameters_json` is the live state of
// the parameters dict serialized as a compact JSON object string —
// keeps the public ABI free of any third-party type dependency. The
// dispatch loop parses + re-serializes around each `write_parameter`
// call, the same way the Python server effectively round-trips its
// dict through json.loads / json.dumps when it talks over the wire.
struct SimulatorState {
    int tick = 0;
    std::string parameters_json = "{}";
};

// `SimulatorState.runtime_values` parity. Increments `state.tick`,
// then returns `{rpm, map, afr}` computed from sin/cos of the tick
// counter, each rounded to 2 decimals via `std::nearbyint(x*100)/100`.
//
// Formulas (mirror the Python source):
//   rpm = round(900.0 + sin(tick / 4.0) * 120.0, 2)
//   map = round(95.0  + cos(tick / 5.0) * 4.0,   2)
//   afr = round(14.7  + sin(tick / 6.0) * 0.4,   2)
std::map<std::string, double> runtime_values(SimulatorState& state);

// `_handle` parity wrapper. Parses `payload_json`, dispatches it to
// the right response shape, returns the response serialized as a
// compact JSON string (same separators Python uses:
// `json.dumps(response, separators=(",", ":"))`). Mirrors every
// branch:
//   "hello"           -> {status: "ok", controller: "tuner-py-sim"}
//   "runtime"         -> {status: "ok", values: runtime_values()}
//   "read_parameter"  -> {status: "ok", value: state.parameters[name] or 0.0}
//   "write_parameter" -> {status: "ok"} (and writes to state.parameters)
//   "burn"            -> {status: "ok"}
//   "verify_crc"      -> {status: "ok", match: true}
//   anything else     -> {status: "error", message: "Unknown command: <name>"}
std::string handle_command_json(SimulatorState& state,
                                std::string_view payload_json);

}  // namespace tuner_core::protocol_simulator
