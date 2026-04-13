// SPDX-License-Identifier: MIT
//
// doctest cases for `protocol_simulator.hpp`. The public API speaks
// JSON via `std::string`, so the test pokes at the response shape
// via plain substring checks rather than parsing it back through
// nlohmann/json (which would re-introduce the third-party include
// the public header deliberately avoids).

#include "doctest.h"

#include "tuner_core/protocol_simulator.hpp"

#include <cmath>
#include <string>

using namespace tuner_core::protocol_simulator;

TEST_CASE("runtime_values: increments tick first") {
    SimulatorState state;
    auto v = runtime_values(state);
    CHECK(state.tick == 1);
    CHECK(v.size() == 3);
}

TEST_CASE("runtime_values: tick=1 produces the documented sin/cos shape") {
    SimulatorState state;
    auto v = runtime_values(state);
    const double t = 1.0;
    const double rpm = std::nearbyint((900.0 + std::sin(t / 4.0) * 120.0) * 100.0) / 100.0;
    const double map = std::nearbyint(( 95.0 + std::cos(t / 5.0) *   4.0) * 100.0) / 100.0;
    const double afr = std::nearbyint(( 14.7 + std::sin(t / 6.0) *   0.4) * 100.0) / 100.0;
    CHECK(v.at("rpm") == doctest::Approx(rpm));
    CHECK(v.at("map") == doctest::Approx(map));
    CHECK(v.at("afr") == doctest::Approx(afr));
}

TEST_CASE("runtime_values: monotonic tick across successive calls") {
    SimulatorState state;
    runtime_values(state);
    runtime_values(state);
    runtime_values(state);
    CHECK(state.tick == 3);
}

TEST_CASE("runtime_values: rpm bounded within sin amplitude window") {
    SimulatorState state;
    for (int i = 0; i < 50; ++i) {
        auto v = runtime_values(state);
        CHECK(v.at("rpm") >= 780.0 - 0.01);
        CHECK(v.at("rpm") <= 1020.0 + 0.01);
    }
}

TEST_CASE("handle_command_json: hello shape") {
    SimulatorState state;
    auto out = handle_command_json(state, R"({"command":"hello"})");
    CHECK(out.find("\"status\":\"ok\"") != std::string::npos);
    CHECK(out.find("\"controller\":\"tuner-py-sim\"") != std::string::npos);
}

TEST_CASE("handle_command_json: runtime branch advances state.tick") {
    SimulatorState state;
    auto out = handle_command_json(state, R"({"command":"runtime"})");
    CHECK(state.tick == 1);
    CHECK(out.find("\"status\":\"ok\"") != std::string::npos);
    CHECK(out.find("\"values\":{") != std::string::npos);
    CHECK(out.find("\"rpm\":") != std::string::npos);
    CHECK(out.find("\"map\":") != std::string::npos);
    CHECK(out.find("\"afr\":") != std::string::npos);
}

TEST_CASE("handle_command_json: read_parameter on missing key returns 0.0") {
    SimulatorState state;
    auto out = handle_command_json(state, R"({"command":"read_parameter","name":"missing"})");
    CHECK(out.find("\"status\":\"ok\"") != std::string::npos);
    CHECK(out.find("\"value\":0.0") != std::string::npos);
}

TEST_CASE("handle_command_json: write_parameter then read_parameter round-trip") {
    SimulatorState state;
    auto w = handle_command_json(state,
        R"({"command":"write_parameter","name":"boost","value":18.5})");
    CHECK(w.find("\"status\":\"ok\"") != std::string::npos);
    auto r = handle_command_json(state, R"({"command":"read_parameter","name":"boost"})");
    CHECK(r.find("\"value\":18.5") != std::string::npos);
}

TEST_CASE("handle_command_json: write_parameter accepts heterogeneous value types") {
    SimulatorState state;
    handle_command_json(state, R"({"command":"write_parameter","name":"i","value":42})");
    handle_command_json(state, R"({"command":"write_parameter","name":"s","value":"hi"})");
    handle_command_json(state, R"({"command":"write_parameter","name":"b","value":true})");
    auto r_i = handle_command_json(state, R"({"command":"read_parameter","name":"i"})");
    auto r_s = handle_command_json(state, R"({"command":"read_parameter","name":"s"})");
    auto r_b = handle_command_json(state, R"({"command":"read_parameter","name":"b"})");
    CHECK(r_i.find("\"value\":42") != std::string::npos);
    CHECK(r_s.find("\"value\":\"hi\"") != std::string::npos);
    CHECK(r_b.find("\"value\":true") != std::string::npos);
}

TEST_CASE("handle_command_json: burn returns ok") {
    SimulatorState state;
    auto out = handle_command_json(state, R"({"command":"burn"})");
    CHECK(out.find("\"status\":\"ok\"") != std::string::npos);
}

TEST_CASE("handle_command_json: verify_crc returns match=true") {
    SimulatorState state;
    auto out = handle_command_json(state, R"({"command":"verify_crc"})");
    CHECK(out.find("\"status\":\"ok\"") != std::string::npos);
    CHECK(out.find("\"match\":true") != std::string::npos);
}

TEST_CASE("handle_command_json: unknown command returns error shape") {
    SimulatorState state;
    auto out = handle_command_json(state, R"({"command":"wat"})");
    CHECK(out.find("\"status\":\"error\"") != std::string::npos);
    CHECK(out.find("\"message\":\"Unknown command: wat\"") != std::string::npos);
}

TEST_CASE("handle_command_json: missing command key falls through to error") {
    SimulatorState state;
    auto out = handle_command_json(state, R"({})");
    CHECK(out.find("\"status\":\"error\"") != std::string::npos);
    CHECK(out.find("\"message\":\"Unknown command: None\"") != std::string::npos);
}

TEST_CASE("handle_command_json: dump uses compact separators") {
    SimulatorState state;
    auto out = handle_command_json(state, R"({"command":"burn"})");
    // Compact form has no spaces between separators.
    CHECK(out.find(' ') == std::string::npos);
}
