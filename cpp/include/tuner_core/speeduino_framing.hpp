// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_framing — pure-logic helpers for the Speeduino
// new-protocol frame format used by `TcpTransport.write_framed` and
// `TcpTransport.read_framed_response` on the Python side. First slice
// of the Phase 14 comms-layer port (Slice 3).
//
// Frame layout (little-endian throughout)::
//
//     [u16 LE payload_length] [payload_length bytes] [u32 LE CRC32(payload)]
//
// CRC algorithm: standard zlib/PNG CRC-32 (polynomial 0xEDB88320,
// reflected, init 0xFFFFFFFF, final XOR 0xFFFFFFFF). Matches Python
// `zlib.crc32(payload) & 0xFFFFFFFF` byte-for-byte; the parity test
// pins the equivalence on randomized payloads.

#pragma once

#include <array>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace tuner_core::speeduino_framing {

// Compute the standard zlib CRC32 of `data`. Equivalent to Python's
// `zlib.crc32(data) & 0xFFFFFFFF`.
std::uint32_t crc32(std::span<const std::uint8_t> data) noexcept;

// Build a Speeduino new-protocol frame from the given payload. Returns
// `[u16 LE len] [payload] [u32 LE CRC32(payload)]`. Throws
// `std::length_error` if payload exceeds `0xFFFF` bytes (the u16 limit).
std::vector<std::uint8_t> encode_frame(std::span<const std::uint8_t> payload);

// Result of a frame-decode call. `bytes_consumed` reports how many
// bytes from the input the decoder consumed (header + payload + CRC),
// which is useful when feeding a buffered stream byte source.
struct DecodedFrame {
    std::vector<std::uint8_t> payload;
    std::size_t bytes_consumed = 0;
    bool crc_valid = false;
};

// Decode one frame from the front of `buffer`. Mirrors
// `TcpTransport.read_framed_response`: the CRC field is read but not
// validated against the payload (the Python side leaves CRC validation
// to the protocol layer because the Airbear bridge does not check it
// before forwarding). The returned `crc_valid` flag is informational
// only — call sites that want strict validation can check it.
//
// Throws `std::length_error` if the buffer is too short to contain a
// complete frame.
DecodedFrame decode_frame(std::span<const std::uint8_t> buffer);

// Convenience: pack the four little-endian header bytes (just the
// length prefix) — exposed for tests that want to assemble partial
// frames.
std::array<std::uint8_t, 2> encode_length_prefix(std::uint16_t length) noexcept;

}  // namespace tuner_core::speeduino_framing
