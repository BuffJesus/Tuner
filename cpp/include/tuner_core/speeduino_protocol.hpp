// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_protocol — pure-logic command-shape helpers
// for the Speeduino raw command path. Second sub-slice of the Phase 14
// comms-layer port (Slice 3). Mirrors the byte-for-byte command shapes
// `SpeeduinoControllerClient` constructs on the Python side:
//
//   - page request header: [cmd, 0x00, page, off_lo, off_hi, len_lo, len_hi]
//   - page write request:  page request header + payload bytes
//   - runtime request:     ['r', 0x00, 0x30, off_lo, off_hi, len_lo, len_hi]
//   - burn request:        [burn_cmd, 0x00, page]
//
// All shapes are little-endian. The default command characters
// (`'p'` for read, `'M'` for write, `'b'` for burn) are used when the
// active definition does not override them — same fallback policy as
// `SpeeduinoControllerClient._command_char`.
//
// No I/O dependency; this header pairs with `speeduino_framing.hpp`
// to give the future C++ `SpeeduinoControllerClient` everything it
// needs to construct command bytes without poking individual fields.

#pragma once

#include <cstdint>
#include <span>
#include <vector>

namespace tuner_core::speeduino_protocol {

// Mirrors `SpeeduinoControllerClient.SEND_OUTPUT_CHANNELS = 0x30`.
inline constexpr std::uint8_t kSendOutputChannelsSelector = 0x30u;

// Default command characters when the active definition does not
// override them — see `SpeeduinoControllerClient._command_char`.
inline constexpr char kDefaultPageReadChar = 'p';
inline constexpr char kDefaultPageWriteChar = 'M';
inline constexpr char kDefaultBurnChar = 'b';
inline constexpr char kRuntimePollChar = 'r';

// Build a 7-byte page-request header. Used for both reads (default
// command `'p'`) and as the prefix for writes (default command `'M'`).
//
// Layout: [cmd, 0x00, page, off_lo, off_hi, len_lo, len_hi]
std::vector<std::uint8_t> page_request(
    char command,
    std::uint8_t page,
    std::uint16_t offset,
    std::uint16_t length);

// Convenience for the read-only path.
inline std::vector<std::uint8_t> page_read_request(
    std::uint8_t page,
    std::uint16_t offset,
    std::uint16_t length,
    char command = kDefaultPageReadChar) {
    return page_request(command, page, offset, length);
}

// Build a complete page-write request: 7-byte header followed by the
// raw `payload` bytes. Mirrors what
// `SpeeduinoControllerClient._write_page_chunk` constructs per chunk.
std::vector<std::uint8_t> page_write_request(
    std::uint8_t page,
    std::uint16_t offset,
    std::span<const std::uint8_t> payload,
    char command = kDefaultPageWriteChar);

// Build the 7-byte runtime poll request:
// ['r', 0x00, 0x30, off_lo, off_hi, len_lo, len_hi]
std::vector<std::uint8_t> runtime_request(std::uint16_t offset, std::uint16_t length);

// Build the 3-byte burn-page request: [burn_cmd, 0x00, page].
std::vector<std::uint8_t> burn_request(
    std::uint8_t page,
    char command = kDefaultBurnChar);

// TN-005: build the 3-byte page-CRC request: [cmd, tsCanId=0, page].
// Firmware replies with 4 big-endian bytes of the computed CRC32 of
// the current RAM contents of the page. Default command is `'d'`
// (legacy `comms_legacy.cpp:917..939`).
inline constexpr char kDefaultPageCrcChar = 'd';
std::vector<std::uint8_t> page_crc_request(
    std::uint8_t page,
    char command = kDefaultPageCrcChar);

// Parse the 4-byte big-endian CRC32 response. Throws on short input.
std::uint32_t parse_page_crc_response(std::span<const std::uint8_t> response);

// Pick the active command character: returns the first character of
// `raw` if it's non-empty, otherwise `fallback`. Mirrors
// `SpeeduinoControllerClient._command_char`.
char select_command_char(const char* raw, char fallback) noexcept;

}  // namespace tuner_core::speeduino_protocol
