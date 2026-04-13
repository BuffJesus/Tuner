// SPDX-License-Identifier: MIT
//
// Implementation of `xcp_simulator.hpp`. Direct port of the
// command-dispatch helpers in `XcpSimulatorServer`.

#include "tuner_core/xcp_simulator.hpp"

#include "tuner_core/xcp_packets.hpp"

#include <cstring>

namespace tuner_core::xcp_simulator {

namespace {

// Pack 32-bit `value` big-endian into the 4-byte buffer at `dest`.
void store_be_u32(std::uint8_t* dest, std::uint32_t value) {
    dest[0] = static_cast<std::uint8_t>((value >> 24) & 0xFF);
    dest[1] = static_cast<std::uint8_t>((value >> 16) & 0xFF);
    dest[2] = static_cast<std::uint8_t>((value >> 8) & 0xFF);
    dest[3] = static_cast<std::uint8_t>(value & 0xFF);
}

void store_be_u16(std::uint8_t* dest, std::uint16_t value) {
    dest[0] = static_cast<std::uint8_t>((value >> 8) & 0xFF);
    dest[1] = static_cast<std::uint8_t>(value & 0xFF);
}

std::uint32_t load_be_u32(std::span<const std::uint8_t> bytes) {
    return (static_cast<std::uint32_t>(bytes[0]) << 24) |
           (static_cast<std::uint32_t>(bytes[1]) << 16) |
           (static_cast<std::uint32_t>(bytes[2]) <<  8) |
           (static_cast<std::uint32_t>(bytes[3]));
}

const std::vector<std::uint8_t> kError = {0xFE, 0x20};

}  // namespace

XcpSimulatorState XcpSimulatorState::default_state() {
    XcpSimulatorState s;
    s.memory.resize(256, 0);
    // memory[0:4] = 0x12 0x34 0x56 0x78
    s.memory[0] = 0x12;
    s.memory[1] = 0x34;
    s.memory[2] = 0x56;
    s.memory[3] = 0x78;
    // memory[4:8] = u32 big-endian 3210
    store_be_u32(s.memory.data() + 4, 3210u);
    // memory[8:10] = u16 big-endian 875
    store_be_u16(s.memory.data() + 8, 875u);
    // memory[10:14] = f32 big-endian 14.7
    {
        const float f = 14.7f;
        std::uint32_t bits = 0;
        std::memcpy(&bits, &f, sizeof(bits));
        store_be_u32(s.memory.data() + 10, bits);
    }
    return s;
}

int expected_command_size(std::uint8_t opcode) noexcept {
    using xcp_packets::XcpCommand;
    if (opcode == XcpCommand::GET_STATUS) return 1;
    if (opcode == XcpCommand::CONNECT ||
        opcode == XcpCommand::GET_ID  ||
        opcode == XcpCommand::UPLOAD) return 2;
    if (opcode == XcpCommand::SET_MTA) return 8;
    return 1;
}

DispatchResult handle_command(const XcpSimulatorState& state,
                              std::span<const std::uint8_t> packet,
                              std::uint32_t mta_address) {
    using xcp_packets::XcpCommand;
    using xcp_packets::XcpPid;

    DispatchResult result;
    result.new_mta_address = mta_address;

    if (packet.empty()) {
        result.response = kError;
        return result;
    }

    const std::uint8_t command = packet[0];

    if (command == XcpCommand::CONNECT) {
        result.response = {
            XcpPid::POSITIVE_RESPONSE,
            state.resource,
            state.comm_mode_basic,
            state.max_cto,
            static_cast<std::uint8_t>((state.max_dto >> 8) & 0xFF),
            static_cast<std::uint8_t>(state.max_dto & 0xFF),
            state.protocol_layer_version,
            state.transport_layer_version,
        };
        return result;
    }

    if (command == XcpCommand::GET_STATUS) {
        result.response = {
            XcpPid::POSITIVE_RESPONSE,
            state.session_status,
            state.protection_status,
            static_cast<std::uint8_t>((state.configuration_status >> 8) & 0xFF),
            static_cast<std::uint8_t>(state.configuration_status & 0xFF),
            0x00,
        };
        return result;
    }

    if (command == XcpCommand::GET_ID) {
        const std::uint32_t length = static_cast<std::uint32_t>(state.identifier.size());
        result.response = {
            XcpPid::POSITIVE_RESPONSE,
            0x01,
            0x00,
            0x00,
            static_cast<std::uint8_t>((length >> 24) & 0xFF),
            static_cast<std::uint8_t>((length >> 16) & 0xFF),
            static_cast<std::uint8_t>((length >>  8) & 0xFF),
            static_cast<std::uint8_t>(length & 0xFF),
        };
        result.response.insert(result.response.end(),
                               state.identifier.begin(),
                               state.identifier.end());
        return result;
    }

    if (command == XcpCommand::SET_MTA) {
        if (packet.size() < 8) {
            result.response = kError;
            return result;
        }
        result.new_mta_address = load_be_u32(packet.subspan(4, 4));
        result.response = {XcpPid::POSITIVE_RESPONSE};
        return result;
    }

    if (command == XcpCommand::UPLOAD) {
        if (packet.size() < 2) {
            result.response = kError;
            return result;
        }
        const std::uint8_t size = packet[1];
        result.response.reserve(static_cast<std::size_t>(size) + 1);
        result.response.push_back(XcpPid::POSITIVE_RESPONSE);
        // Read up to `size` bytes from memory[mta..mta+size); zero-pad
        // anything past the end of the memory buffer (mirrors the
        // Python `data + b"\x00" * (size - len(data))`).
        const std::uint32_t mem_size = static_cast<std::uint32_t>(state.memory.size());
        for (std::uint32_t i = 0; i < size; ++i) {
            const std::uint32_t addr = mta_address + i;
            if (addr < mem_size) {
                result.response.push_back(state.memory[addr]);
            } else {
                result.response.push_back(0x00);
            }
        }
        result.new_mta_address = mta_address + size;
        return result;
    }

    result.response = kError;
    return result;
}

}  // namespace tuner_core::xcp_simulator
