// SPDX-License-Identifier: MIT
//
// Implementation of `xcp_packets.hpp`. Direct port of
// `src/tuner/comms/xcp/packets.py`.

#include "tuner_core/xcp_packets.hpp"

#include <cstdio>
#include <stdexcept>
#include <string>

namespace tuner_core::xcp_packets {

namespace {

[[noreturn]] void fail(const std::string& msg) {
    throw std::runtime_error(msg);
}

std::string format_hex_byte(std::uint8_t b) {
    char buf[8];
    std::snprintf(buf, sizeof(buf), "0x%02X", b);
    return buf;
}

}  // namespace

std::string XcpGetIdResponse::identifier_text() const {
    // Mirror Python `bytes.decode("ascii", errors="replace")`. ASCII
    // bytes (0x00..0x7F) pass through; anything >= 0x80 becomes the
    // U+FFFD replacement character (3-byte UTF-8: 0xEF 0xBF 0xBD).
    std::string out;
    out.reserve(identifier.size());
    for (std::uint8_t b : identifier) {
        if (b < 0x80) {
            out.push_back(static_cast<char>(b));
        } else {
            out.push_back('\xEF');
            out.push_back('\xBF');
            out.push_back('\xBD');
        }
    }
    return out;
}

// ---------------------------------------------------------------------
// Builders
// ---------------------------------------------------------------------

std::vector<std::uint8_t> build_connect_command(std::uint8_t mode) {
    return { XcpCommand::CONNECT, mode };
}

std::vector<std::uint8_t> build_get_status_command() {
    return { XcpCommand::GET_STATUS };
}

std::vector<std::uint8_t> build_get_id_command(std::uint8_t identifier_type) {
    return { XcpCommand::GET_ID, identifier_type };
}

std::vector<std::uint8_t> build_set_mta_command(std::uint32_t address,
                                                std::uint8_t address_extension) {
    return {
        XcpCommand::SET_MTA,
        0x00,
        0x00,
        static_cast<std::uint8_t>(address_extension & 0xFF),
        static_cast<std::uint8_t>((address >> 24) & 0xFF),
        static_cast<std::uint8_t>((address >> 16) & 0xFF),
        static_cast<std::uint8_t>((address >> 8) & 0xFF),
        static_cast<std::uint8_t>(address & 0xFF),
    };
}

std::vector<std::uint8_t> build_upload_command(int size) {
    if (size <= 0 || size > 255) {
        fail("XCP UPLOAD size must be between 1 and 255 bytes");
    }
    return {
        XcpCommand::UPLOAD,
        static_cast<std::uint8_t>(size & 0xFF),
    };
}

// ---------------------------------------------------------------------
// Parsers
// ---------------------------------------------------------------------

XcpConnectResponse parse_connect_response(std::span<const std::uint8_t> packet) {
    if (packet.size() != 8) {
        fail("XCP CONNECT response must be 8 bytes, got " +
             std::to_string(packet.size()));
    }
    if (packet[0] != XcpPid::POSITIVE_RESPONSE) {
        fail("XCP CONNECT response must start with 0xFF, got " +
             format_hex_byte(packet[0]));
    }
    XcpConnectResponse out;
    out.resource = packet[1];
    out.comm_mode_basic = packet[2];
    out.max_cto = packet[3];
    // Big-endian u16 at packet[4..6).
    out.max_dto = static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(packet[4]) << 8) | packet[5]);
    out.protocol_layer_version = packet[6];
    out.transport_layer_version = packet[7];
    return out;
}

XcpStatusResponse parse_status_response(std::span<const std::uint8_t> packet) {
    if (packet.size() != 6) {
        fail("XCP GET_STATUS response must be 6 bytes, got " +
             std::to_string(packet.size()));
    }
    if (packet[0] != XcpPid::POSITIVE_RESPONSE) {
        fail("XCP GET_STATUS response must start with 0xFF, got " +
             format_hex_byte(packet[0]));
    }
    XcpStatusResponse out;
    out.session_status = packet[1];
    out.protection_status = packet[2];
    // Big-endian u16 at packet[3..5).
    out.configuration_status = static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(packet[3]) << 8) | packet[4]);
    return out;
}

XcpGetIdResponse parse_get_id_response(std::span<const std::uint8_t> packet) {
    if (packet.size() < 8) {
        fail("XCP GET_ID response must be at least 8 bytes, got " +
             std::to_string(packet.size()));
    }
    if (packet[0] != XcpPid::POSITIVE_RESPONSE) {
        fail("XCP GET_ID response must start with 0xFF, got " +
             format_hex_byte(packet[0]));
    }
    // Python: `payload = packet[1:]` and then indexes off `payload`.
    // We index directly off `packet` with the +1 offset baked in.
    const std::uint8_t mode = packet[1];
    // Big-endian u32 at payload[3..7) == packet[4..8).
    const std::uint32_t identifier_length =
        (static_cast<std::uint32_t>(packet[4]) << 24) |
        (static_cast<std::uint32_t>(packet[5]) << 16) |
        (static_cast<std::uint32_t>(packet[6]) <<  8) |
        (static_cast<std::uint32_t>(packet[7]));
    if (identifier_length == 0) {
        // Python uses `<= 0` but the value is unsigned in the spec —
        // mirror the meaningful branch (zero rejected).
        fail("XCP GET_ID length must be greater than zero");
    }
    if (mode != 1) {
        fail("XCP GET_ID mode " + std::to_string(static_cast<int>(mode)) +
             " is not supported yet");
    }
    // Python: `identifier = payload[7 : 7 + identifier_length]`,
    // where payload[7] == packet[8]. Then it asserts the slice is the
    // full requested length (Python slicing is forgiving — it returns
    // a short slice instead of throwing — so the explicit length check
    // is what catches truncation).
    const std::size_t start = 8;
    const std::size_t end = start + identifier_length;
    XcpGetIdResponse out;
    out.mode = mode;
    out.identifier_length = identifier_length;
    if (end > packet.size()) {
        fail("XCP GET_ID response did not include the full identifier payload");
    }
    out.identifier.assign(packet.begin() + start, packet.begin() + end);
    return out;
}

void parse_command_ack(std::span<const std::uint8_t> packet) {
    if (packet.size() != 1 || packet[0] != XcpPid::POSITIVE_RESPONSE) {
        // Python prints `repr(packet)` (e.g. `b'\\xfe'`) — the C++ side
        // produces a hex sequence with the same intent.
        std::string hex;
        for (std::uint8_t b : packet) {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "\\x%02x", b);
            hex += buf;
        }
        fail("XCP command acknowledgement must be 0xFF, got b'" + hex + "'");
    }
}

std::vector<std::uint8_t> parse_upload_response(std::span<const std::uint8_t> packet,
                                                int expected_size) {
    const std::size_t want = static_cast<std::size_t>(expected_size + 1);
    if (packet.size() != want) {
        fail("XCP UPLOAD response must be " + std::to_string(want) +
             " bytes, got " + std::to_string(packet.size()));
    }
    if (packet[0] != XcpPid::POSITIVE_RESPONSE) {
        fail("XCP UPLOAD response must start with 0xFF, got " +
             format_hex_byte(packet[0]));
    }
    return std::vector<std::uint8_t>(packet.begin() + 1, packet.end());
}

}  // namespace tuner_core::xcp_packets
