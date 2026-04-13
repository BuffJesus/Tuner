// SPDX-License-Identifier: MIT
//
// doctest cases for `xcp_simulator.hpp`.

#include "doctest.h"

#include "tuner_core/xcp_simulator.hpp"
#include "tuner_core/xcp_packets.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

using namespace tuner_core::xcp_simulator;
using xcp = tuner_core::xcp_packets::XcpCommand;
using xpid = tuner_core::xcp_packets::XcpPid;

namespace {

std::span<const std::uint8_t> as_span(const std::vector<std::uint8_t>& v) {
    return std::span<const std::uint8_t>(v.data(), v.size());
}

}  // namespace

TEST_CASE("expected_command_size: known opcodes") {
    CHECK(expected_command_size(xcp::CONNECT)    == 2);
    CHECK(expected_command_size(xcp::GET_STATUS) == 1);
    CHECK(expected_command_size(xcp::GET_ID)     == 2);
    CHECK(expected_command_size(xcp::UPLOAD)     == 2);
    CHECK(expected_command_size(xcp::SET_MTA)    == 8);
}

TEST_CASE("expected_command_size: unknown opcodes default to 1") {
    CHECK(expected_command_size(0x00) == 1);
    CHECK(expected_command_size(0x12) == 1);
    CHECK(expected_command_size(xcp::DISCONNECT) == 1);
}

TEST_CASE("default_state: memory pre-seeded with the fixture bytes") {
    auto s = XcpSimulatorState::default_state();
    REQUIRE(s.memory.size() == 256);
    // memory[0:4] = 12 34 56 78
    CHECK(s.memory[0] == 0x12);
    CHECK(s.memory[1] == 0x34);
    CHECK(s.memory[2] == 0x56);
    CHECK(s.memory[3] == 0x78);
    // memory[4:8] = big-endian u32 3210
    CHECK(s.memory[4] == 0x00);
    CHECK(s.memory[5] == 0x00);
    CHECK(s.memory[6] == 0x0C);
    CHECK(s.memory[7] == 0x8A);
    // memory[8:10] = big-endian u16 875
    CHECK(s.memory[8] == 0x03);
    CHECK(s.memory[9] == 0x6B);
    // memory[10:14] = big-endian f32 14.7
    {
        std::uint32_t bits =
            (static_cast<std::uint32_t>(s.memory[10]) << 24) |
            (static_cast<std::uint32_t>(s.memory[11]) << 16) |
            (static_cast<std::uint32_t>(s.memory[12]) <<  8) |
            (static_cast<std::uint32_t>(s.memory[13]));
        float f = 0;
        std::memcpy(&f, &bits, sizeof(f));
        CHECK(f == doctest::Approx(14.7f));
    }
}

TEST_CASE("handle_command CONNECT returns the 8-byte CONNECT response from state") {
    auto state = XcpSimulatorState::default_state();
    auto r = handle_command(state, std::vector<std::uint8_t>{xcp::CONNECT, 0x00}, 0);
    REQUIRE(r.response.size() == 8);
    CHECK(r.response[0] == xpid::POSITIVE_RESPONSE);
    CHECK(r.response[1] == state.resource);
    CHECK(r.response[2] == state.comm_mode_basic);
    CHECK(r.response[3] == state.max_cto);
    CHECK(r.response[4] == 0x01);  // (0x0100 >> 8) & 0xFF
    CHECK(r.response[5] == 0x00);  //  0x0100       & 0xFF
    CHECK(r.response[6] == state.protocol_layer_version);
    CHECK(r.response[7] == state.transport_layer_version);
    CHECK(r.new_mta_address == 0);  // CONNECT does not touch MTA
}

TEST_CASE("handle_command GET_STATUS returns the 6-byte STATUS response") {
    auto state = XcpSimulatorState::default_state();
    auto r = handle_command(state, std::vector<std::uint8_t>{xcp::GET_STATUS}, 7);
    REQUIRE(r.response.size() == 6);
    CHECK(r.response[0] == xpid::POSITIVE_RESPONSE);
    CHECK(r.response[1] == state.session_status);
    CHECK(r.response[2] == state.protection_status);
    CHECK(r.response[3] == 0x00);
    CHECK(r.response[4] == 0x01);  // configuration_status = 0x0001
    CHECK(r.response[5] == 0x00);
    CHECK(r.new_mta_address == 7);  // unchanged
}

TEST_CASE("handle_command GET_ID returns 8-byte header + identifier bytes") {
    auto state = XcpSimulatorState::default_state();
    auto r = handle_command(state, std::vector<std::uint8_t>{xcp::GET_ID, 0x00}, 0);
    REQUIRE(r.response.size() == 8 + state.identifier.size());
    CHECK(r.response[0] == xpid::POSITIVE_RESPONSE);
    CHECK(r.response[1] == 0x01);
    CHECK(r.response[2] == 0x00);
    CHECK(r.response[3] == 0x00);
    // identifier_length = state.identifier.size() big-endian u32
    const std::uint32_t length = static_cast<std::uint32_t>(state.identifier.size());
    CHECK(r.response[4] == ((length >> 24) & 0xFF));
    CHECK(r.response[5] == ((length >> 16) & 0xFF));
    CHECK(r.response[6] == ((length >>  8) & 0xFF));
    CHECK(r.response[7] == (length & 0xFF));
    // Identifier bytes follow.
    for (std::size_t i = 0; i < state.identifier.size(); ++i) {
        CHECK(r.response[8 + i] == state.identifier[i]);
    }
}

TEST_CASE("handle_command SET_MTA captures the big-endian address into new_mta_address") {
    auto state = XcpSimulatorState::default_state();
    std::vector<std::uint8_t> packet = {
        xcp::SET_MTA, 0x00, 0x00, 0x00,
        0x12, 0x34, 0x56, 0x78,
    };
    auto r = handle_command(state, packet, 0);
    REQUIRE(r.response.size() == 1);
    CHECK(r.response[0] == xpid::POSITIVE_RESPONSE);
    CHECK(r.new_mta_address == 0x12345678);
}

TEST_CASE("handle_command SET_MTA truncated returns the error packet 0xFE 0x20") {
    auto state = XcpSimulatorState::default_state();
    std::vector<std::uint8_t> packet = {xcp::SET_MTA, 0x00, 0x00, 0x00, 0x12, 0x34};
    auto r = handle_command(state, packet, 5);
    CHECK(r.response == std::vector<std::uint8_t>{0xFE, 0x20});
    CHECK(r.new_mta_address == 5);  // unchanged on failure
}

TEST_CASE("handle_command UPLOAD reads from memory and advances MTA") {
    auto state = XcpSimulatorState::default_state();
    auto r = handle_command(state, std::vector<std::uint8_t>{xcp::UPLOAD, 4}, 0);
    REQUIRE(r.response.size() == 5);
    CHECK(r.response[0] == xpid::POSITIVE_RESPONSE);
    CHECK(r.response[1] == 0x12);
    CHECK(r.response[2] == 0x34);
    CHECK(r.response[3] == 0x56);
    CHECK(r.response[4] == 0x78);
    CHECK(r.new_mta_address == 4);
}

TEST_CASE("handle_command UPLOAD past the end zero-pads the tail") {
    auto state = XcpSimulatorState::default_state();
    // Read 4 bytes starting at the last 2 valid memory addresses.
    auto r = handle_command(state, std::vector<std::uint8_t>{xcp::UPLOAD, 4}, 254);
    REQUIRE(r.response.size() == 5);
    CHECK(r.response[0] == xpid::POSITIVE_RESPONSE);
    // memory[254..256) defaults to 0x00, plus two zero-pad bytes.
    CHECK(r.response[1] == 0x00);
    CHECK(r.response[2] == 0x00);
    CHECK(r.response[3] == 0x00);
    CHECK(r.response[4] == 0x00);
    CHECK(r.new_mta_address == 258);
}

TEST_CASE("handle_command UPLOAD truncated command returns 0xFE 0x20") {
    auto state = XcpSimulatorState::default_state();
    std::vector<std::uint8_t> packet = {xcp::UPLOAD};
    auto r = handle_command(state, packet, 9);
    CHECK(r.response == std::vector<std::uint8_t>{0xFE, 0x20});
    CHECK(r.new_mta_address == 9);
}

TEST_CASE("handle_command unknown opcode returns the error packet") {
    auto state = XcpSimulatorState::default_state();
    auto r = handle_command(state, std::vector<std::uint8_t>{0x42}, 0);
    CHECK(r.response == std::vector<std::uint8_t>{0xFE, 0x20});
    CHECK(r.new_mta_address == 0);
}

TEST_CASE("handle_command empty packet returns the error packet") {
    auto state = XcpSimulatorState::default_state();
    std::vector<std::uint8_t> empty;
    auto r = handle_command(state, as_span(empty), 0);
    CHECK(r.response == std::vector<std::uint8_t>{0xFE, 0x20});
}

TEST_CASE("handle_command UPLOAD reads big-endian u32 fixture from memory[4..8)") {
    auto state = XcpSimulatorState::default_state();
    auto r = handle_command(state, std::vector<std::uint8_t>{xcp::UPLOAD, 4}, 4);
    REQUIRE(r.response.size() == 5);
    CHECK(r.response[1] == 0x00);
    CHECK(r.response[2] == 0x00);
    CHECK(r.response[3] == 0x0C);
    CHECK(r.response[4] == 0x8A);
    // The 4 bytes encode big-endian u32 3210.
    const std::uint32_t v =
        (static_cast<std::uint32_t>(r.response[1]) << 24) |
        (static_cast<std::uint32_t>(r.response[2]) << 16) |
        (static_cast<std::uint32_t>(r.response[3]) <<  8) |
        (static_cast<std::uint32_t>(r.response[4]));
    CHECK(v == 3210u);
}

TEST_CASE("handle_command UPLOAD followed by SET_MTA threading") {
    auto state = XcpSimulatorState::default_state();
    // Start at 0, upload 4 -> mta=4. SET_MTA to 8 -> mta=8. Upload 2 -> reads memory[8..10).
    std::uint32_t mta = 0;
    auto r1 = handle_command(state, std::vector<std::uint8_t>{xcp::UPLOAD, 4}, mta);
    mta = r1.new_mta_address;
    CHECK(mta == 4);
    auto r2 = handle_command(state, std::vector<std::uint8_t>{
        xcp::SET_MTA, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08}, mta);
    mta = r2.new_mta_address;
    CHECK(mta == 8);
    auto r3 = handle_command(state, std::vector<std::uint8_t>{xcp::UPLOAD, 2}, mta);
    REQUIRE(r3.response.size() == 3);
    // memory[8..10) = big-endian u16 875 = 0x036B
    CHECK(r3.response[1] == 0x03);
    CHECK(r3.response[2] == 0x6B);
    CHECK(r3.new_mta_address == 10);
}
