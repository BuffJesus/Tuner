// SPDX-License-Identifier: MIT
//
// tuner_core::xcp_packets — pure-logic port of
// `src/tuner/comms/xcp/packets.py`. Builds and parses the XCP-on-CAN
// command/response byte shapes used by `XcpControllerClient`.
//
// XCP is **big-endian** on the wire (in contrast to the Speeduino raw
// protocol, which is little-endian — see speeduino_value_codec.hpp).
// All multi-byte integers in this module are encoded/decoded big-end-
// first to match the spec.
//
// I/O — sending/receiving the bytes over a real CAN-USB transport
// stays Python under `XcpControllerClient`. This module owns only
// the byte-shape primitives.

#pragma once

#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace tuner_core::xcp_packets {

// Packet identifier first byte values.
struct XcpPid {
    static constexpr std::uint8_t POSITIVE_RESPONSE = 0xFF;
    static constexpr std::uint8_t ERROR             = 0xFE;
};

// Command opcodes — first byte of any host-to-target command.
struct XcpCommand {
    static constexpr std::uint8_t CONNECT             = 0xFF;
    static constexpr std::uint8_t DISCONNECT          = 0xFE;
    static constexpr std::uint8_t GET_STATUS          = 0xFD;
    static constexpr std::uint8_t SYNCH               = 0xFC;
    static constexpr std::uint8_t GET_COMM_MODE_INFO  = 0xFB;
    static constexpr std::uint8_t GET_ID              = 0xFA;
    static constexpr std::uint8_t SET_MTA             = 0xF6;
    static constexpr std::uint8_t UPLOAD              = 0xF5;
};

// Decoded CONNECT response shape — mirrors `XcpConnectResponse`.
struct XcpConnectResponse {
    std::uint8_t  resource = 0;
    std::uint8_t  comm_mode_basic = 0;
    std::uint8_t  max_cto = 0;
    std::uint16_t max_dto = 0;
    std::uint8_t  protocol_layer_version = 0;
    std::uint8_t  transport_layer_version = 0;
};

// Decoded GET_STATUS response — mirrors `XcpStatusResponse`.
struct XcpStatusResponse {
    std::uint8_t  session_status = 0;
    std::uint8_t  protection_status = 0;
    std::uint16_t configuration_status = 0;
};

// Decoded GET_ID response — mirrors `XcpGetIdResponse`.
struct XcpGetIdResponse {
    std::uint8_t mode = 0;
    std::uint32_t identifier_length = 0;
    std::vector<std::uint8_t> identifier;

    // ASCII identifier text (replacement on undecodable bytes — same as
    // Python's `decode("ascii", errors="replace")`). Replacement char
    // is U+FFFD encoded as the 3-byte UTF-8 sequence `EF BF BD`.
    std::string identifier_text() const;
};

// ---------------------------------------------------------------------
// Command builders. Each returns the on-the-wire byte sequence the
// host should send. Defaults match the Python signatures exactly.
// ---------------------------------------------------------------------

std::vector<std::uint8_t> build_connect_command(std::uint8_t mode = 0x00);

std::vector<std::uint8_t> build_get_status_command();

std::vector<std::uint8_t> build_get_id_command(std::uint8_t identifier_type = 0x00);

// SET_MTA: 8-byte command with the 32-bit address packed big-endian
// in bytes 4..7. address_extension is the third payload byte.
std::vector<std::uint8_t> build_set_mta_command(std::uint32_t address,
                                                std::uint8_t address_extension = 0x00);

// UPLOAD: 2-byte command with the requested size. Throws if `size`
// is outside the inclusive range [1, 255] (matches the Python
// `ValueError`).
std::vector<std::uint8_t> build_upload_command(int size);

// ---------------------------------------------------------------------
// Response parsers. Each takes the raw response bytes and returns
// the decoded struct, throwing `std::runtime_error` (with the same
// message text the Python sources use) on length / PID mismatch.
// ---------------------------------------------------------------------

XcpConnectResponse parse_connect_response(std::span<const std::uint8_t> packet);
XcpStatusResponse  parse_status_response(std::span<const std::uint8_t> packet);
XcpGetIdResponse   parse_get_id_response(std::span<const std::uint8_t> packet);

// `parse_command_ack` is a void check — throws if `packet` is not
// exactly the single-byte `[POSITIVE_RESPONSE]`.
void parse_command_ack(std::span<const std::uint8_t> packet);

// `parse_upload_response` returns the payload bytes (the response
// minus the leading 0xFF PID). Throws on length / PID mismatch.
std::vector<std::uint8_t> parse_upload_response(std::span<const std::uint8_t> packet,
                                                int expected_size);

}  // namespace tuner_core::xcp_packets
