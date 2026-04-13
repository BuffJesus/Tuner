// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_framing implementation. Standard zlib CRC-32
// (table-based) plus little-endian length-prefixed frame encode/decode.
// Pure logic — no I/O dependencies — so it links into both the test
// runner and the future C++ TcpTransport without dragging in sockets.

#include "tuner_core/speeduino_framing.hpp"

#include <array>
#include <cstring>

namespace tuner_core::speeduino_framing {

namespace {

// Build the standard 256-entry CRC-32 lookup table at startup. Uses
// the reflected polynomial 0xEDB88320 — same as zlib / PNG / Ethernet.
struct Crc32Table {
    std::array<std::uint32_t, 256> entries{};

    constexpr Crc32Table() {
        constexpr std::uint32_t poly = 0xEDB88320u;
        for (std::uint32_t i = 0; i < 256; ++i) {
            std::uint32_t c = i;
            for (int k = 0; k < 8; ++k) {
                c = (c & 1u) ? (poly ^ (c >> 1)) : (c >> 1);
            }
            entries[i] = c;
        }
    }
};

constexpr Crc32Table kCrc32Table{};

}  // namespace

std::uint32_t crc32(std::span<const std::uint8_t> data) noexcept {
    std::uint32_t c = 0xFFFFFFFFu;
    for (auto byte : data) {
        c = kCrc32Table.entries[(c ^ byte) & 0xFFu] ^ (c >> 8);
    }
    return c ^ 0xFFFFFFFFu;
}

std::array<std::uint8_t, 2> encode_length_prefix(std::uint16_t length) noexcept {
    return {
        static_cast<std::uint8_t>(length & 0xFFu),
        static_cast<std::uint8_t>((length >> 8) & 0xFFu),
    };
}

std::vector<std::uint8_t> encode_frame(std::span<const std::uint8_t> payload) {
    if (payload.size() > 0xFFFFu) {
        throw std::length_error(
            "speeduino_framing::encode_frame: payload exceeds 65535 bytes "
            "(u16 length-prefix limit)");
    }
    const auto len = static_cast<std::uint16_t>(payload.size());
    const std::uint32_t c = crc32(payload);

    std::vector<std::uint8_t> frame;
    frame.reserve(2 + payload.size() + 4);
    auto prefix = encode_length_prefix(len);
    frame.push_back(prefix[0]);
    frame.push_back(prefix[1]);
    frame.insert(frame.end(), payload.begin(), payload.end());
    frame.push_back(static_cast<std::uint8_t>(c & 0xFFu));
    frame.push_back(static_cast<std::uint8_t>((c >> 8) & 0xFFu));
    frame.push_back(static_cast<std::uint8_t>((c >> 16) & 0xFFu));
    frame.push_back(static_cast<std::uint8_t>((c >> 24) & 0xFFu));
    return frame;
}

DecodedFrame decode_frame(std::span<const std::uint8_t> buffer) {
    if (buffer.size() < 2) {
        throw std::length_error(
            "speeduino_framing::decode_frame: buffer shorter than 2-byte header");
    }
    const std::uint16_t length = static_cast<std::uint16_t>(
        buffer[0] | (static_cast<std::uint16_t>(buffer[1]) << 8));
    const std::size_t total = 2 + static_cast<std::size_t>(length) + 4;
    if (buffer.size() < total) {
        throw std::length_error(
            "speeduino_framing::decode_frame: buffer shorter than declared frame");
    }

    DecodedFrame out;
    out.payload.assign(buffer.begin() + 2, buffer.begin() + 2 + length);
    out.bytes_consumed = total;

    const std::uint32_t crc_field =
        static_cast<std::uint32_t>(buffer[2 + length]) |
        (static_cast<std::uint32_t>(buffer[2 + length + 1]) << 8) |
        (static_cast<std::uint32_t>(buffer[2 + length + 2]) << 16) |
        (static_cast<std::uint32_t>(buffer[2 + length + 3]) << 24);
    out.crc_valid = (crc_field == crc32(out.payload));
    return out;
}

}  // namespace tuner_core::speeduino_framing
