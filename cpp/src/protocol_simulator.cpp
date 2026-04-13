// SPDX-License-Identifier: MIT
//
// Implementation of `protocol_simulator.hpp`. Direct port of
// `SimulatorState.runtime_values` and `_handle` from
// `src/tuner/simulator/protocol_simulator.py`.

#include "tuner_core/protocol_simulator.hpp"

#include "nlohmann/json.hpp"

#include <cmath>
#include <string>

namespace tuner_core::protocol_simulator {

namespace {

using nlohmann::json;

// Mirror Python's `round(value, 2)` which is banker's rounding
// (half-to-even). `std::nearbyint` defaults to FE_TONEAREST which
// is also half-to-even, so this matches.
double round_two(double value) {
    return std::nearbyint(value * 100.0) / 100.0;
}

// Internal handler that takes the parsed input and returns a parsed
// response. Lives in the .cpp so the public header doesn't depend on
// nlohmann::json.
json handle_command_json_object(SimulatorState& state, const json& payload) {
    if (!payload.contains("command")) {
        return json{
            {"status", "error"},
            {"message", "Unknown command: None"},
        };
    }
    const auto& command_node = payload.at("command");
    if (!command_node.is_string()) {
        return json{
            {"status", "error"},
            {"message", "Unknown command: " + command_node.dump()},
        };
    }
    const std::string command = command_node.get<std::string>();

    if (command == "hello") {
        return json{
            {"status", "ok"},
            {"controller", "tuner-py-sim"},
        };
    }
    if (command == "runtime") {
        json values = json::object();
        for (const auto& [k, v] : runtime_values(state)) {
            values[k] = v;
        }
        return json{
            {"status", "ok"},
            {"values", values},
        };
    }

    auto parameters = json::parse(state.parameters_json);

    if (command == "read_parameter") {
        std::string name = payload.at("name").is_string()
            ? payload.at("name").get<std::string>()
            : payload.at("name").dump();
        // Python: `state.parameters.get(name, 0.0)` — default is the
        // float 0.0, not the int 0. Preserve that.
        json value = 0.0;
        if (parameters.contains(name)) {
            value = parameters.at(name);
        }
        return json{
            {"status", "ok"},
            {"value", value},
        };
    }
    if (command == "write_parameter") {
        std::string name = payload.at("name").is_string()
            ? payload.at("name").get<std::string>()
            : payload.at("name").dump();
        parameters[name] = payload.at("value");
        state.parameters_json = parameters.dump();
        return json{{"status", "ok"}};
    }
    if (command == "burn") {
        return json{{"status", "ok"}};
    }
    if (command == "verify_crc") {
        return json{
            {"status", "ok"},
            {"match", true},
        };
    }
    return json{
        {"status", "error"},
        {"message", "Unknown command: " + command},
    };
}

}  // namespace

std::map<std::string, double> runtime_values(SimulatorState& state) {
    state.tick += 1;
    const double t = static_cast<double>(state.tick);
    return {
        {"rpm", round_two(900.0 + std::sin(t / 4.0) * 120.0)},
        {"map", round_two( 95.0 + std::cos(t / 5.0) *   4.0)},
        {"afr", round_two( 14.7 + std::sin(t / 6.0) *   0.4)},
    };
}

std::string handle_command_json(SimulatorState& state,
                                std::string_view payload_json) {
    const auto payload = json::parse(payload_json);
    const auto response = handle_command_json_object(state, payload);
    // Mirror Python `json.dumps(payload, separators=(",", ":"))` —
    // compact form, no spaces.
    return response.dump();
}

}  // namespace tuner_core::protocol_simulator
