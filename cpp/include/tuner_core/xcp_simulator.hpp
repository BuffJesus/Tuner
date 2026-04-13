// SPDX-License-Identifier: MIT
//
// tuner_core::xcp_simulator — pure-logic port of the command-dispatch
// half of `src/tuner/simulator/xcp_simulator.py`. Pairs with the XCP
// packet layer ported in sub-slice 104 (`xcp_packets.hpp`).
//
// The Python `XcpSimulatorServer` is half pure-logic (decide how
// many bytes a command needs, dispatch a fully-buffered command to
// the right response shape, mutate the MTA pointer on SET_MTA /
// UPLOAD) and half I/O (TCP socket accept loop, `recv` / `sendall`).
// This module owns only the pure half — the socket bytes shuttling
// stays Python.
//
// `XcpSimulatorState` mirrors the Python dataclass field-for-field;
// `handle_command` returns the response bytes plus the new MTA
// pointer so the caller can thread it through successive calls.

#pragma once

#include <cstdint>
#include <span>
#include <vector>

namespace tuner_core::xcp_simulator {

// Mirror of `XcpSimulatorState`. Default values match the Python
// `__post_init__` behaviour exactly: 256-byte memory pre-seeded with
// the same fixture bytes (12 34 56 78 / big-endian u32 3210 / big-
// endian u16 875 / big-endian f32 14.7).
struct XcpSimulatorState {
    std::uint8_t  session_status = 0x05;
    std::uint8_t  protection_status = 0x00;
    std::uint16_t configuration_status = 0x0001;
    std::uint8_t  resource = 0x01;
    std::uint8_t  comm_mode_basic = 0x02;
    std::uint8_t  max_cto = 0x08;
    std::uint16_t max_dto = 0x0100;
    std::uint8_t  protocol_layer_version = 0x01;
    std::uint8_t  transport_layer_version = 0x01;
    std::vector<std::uint8_t> identifier = {
        'T','U','N','E','R','P','Y','-','X','C','P','-','S','I','M'
    };
    std::vector<std::uint8_t> memory;  // 256 bytes after default_state()

    static XcpSimulatorState default_state();
};

// Result of dispatching one command. `response` is the bytes the
// simulator should send back over the socket; `new_mta_address` is
// the MTA pointer after the command (only SET_MTA and UPLOAD mutate
// it — every other branch just returns the input value).
struct DispatchResult {
    std::vector<std::uint8_t> response;
    std::uint32_t new_mta_address = 0;
};

// `_expected_command_size` parity. Returns the total byte count the
// transport should buffer for `opcode` before invoking
// `handle_command`. Unknown opcodes return 1 (matches the Python
// fall-through).
int expected_command_size(std::uint8_t opcode) noexcept;

// `_handle` parity. Dispatch a fully-buffered command and return the
// response bytes + the updated MTA pointer. Mirrors every branch:
//   CONNECT     -> 8-byte CONNECT response from `state`
//   GET_STATUS  -> 6-byte STATUS response from `state`
//   GET_ID      -> 8 + identifier.size() bytes from `state.identifier`
//   SET_MTA     -> ack + new MTA from packet[4..8) (big-endian u32)
//   UPLOAD      -> ack + size bytes from `state.memory[mta..mta+size)`,
//                  zero-padded if the read exceeds the memory bounds
//                  (matches the Python `data + b"\x00" * (size - len(data))`),
//                  with new MTA = mta + size
//   anything else -> 2-byte error packet `0xFE 0x20`
//
// Unknown / truncated CONNECT / GET_STATUS / GET_ID return their
// normal happy-path response — the Python original does no length
// validation on these branches. SET_MTA / UPLOAD that arrive
// truncated return `0xFE 0x20`.
DispatchResult handle_command(const XcpSimulatorState& state,
                              std::span<const std::uint8_t> packet,
                              std::uint32_t mta_address);

}  // namespace tuner_core::xcp_simulator
