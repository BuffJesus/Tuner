// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::speeduino_framing.

#include "doctest.h"

#include "tuner_core/speeduino_framing.hpp"

#include <cstdint>
#include <string>
#include <vector>

using tuner_core::speeduino_framing::crc32;
using tuner_core::speeduino_framing::decode_frame;
using tuner_core::speeduino_framing::encode_frame;

namespace {

std::vector<std::uint8_t> bytes(std::initializer_list<std::uint8_t> il) {
    return std::vector<std::uint8_t>(il);
}

std::vector<std::uint8_t> str_bytes(std::string_view s) {
    return std::vector<std::uint8_t>(s.begin(), s.end());
}

}  // namespace

TEST_CASE("crc32 of empty input is 0") {
    std::vector<std::uint8_t> empty;
    CHECK(crc32(empty) == 0u);
}

TEST_CASE("crc32 matches the well-known zlib value for '123456789'") {
    // Standard CRC-32 check value from the CRC-32 spec.
    auto data = str_bytes("123456789");
    CHECK(crc32(data) == 0xCBF43926u);
}

TEST_CASE("crc32 matches the zlib value for the ASCII letter 'a'") {
    auto data = str_bytes("a");
    CHECK(crc32(data) == 0xE8B7BE43u);
}

TEST_CASE("encode_frame produces the documented layout for a small payload") {
    auto payload = bytes({'A', 'B', 'C'});
    auto frame = encode_frame(payload);
    REQUIRE(frame.size() == 2 + 3 + 4);
    // u16 LE length
    CHECK(frame[0] == 0x03);
    CHECK(frame[1] == 0x00);
    // payload
    CHECK(frame[2] == 'A');
    CHECK(frame[3] == 'B');
    CHECK(frame[4] == 'C');
    // CRC32 of "ABC" = 0xA3830348 little-endian
    const std::uint32_t expected = crc32(payload);
    CHECK(frame[5] == static_cast<std::uint8_t>(expected & 0xFF));
    CHECK(frame[6] == static_cast<std::uint8_t>((expected >> 8) & 0xFF));
    CHECK(frame[7] == static_cast<std::uint8_t>((expected >> 16) & 0xFF));
    CHECK(frame[8] == static_cast<std::uint8_t>((expected >> 24) & 0xFF));
}

TEST_CASE("encode_frame allows empty payload") {
    std::vector<std::uint8_t> empty;
    auto frame = encode_frame(empty);
    REQUIRE(frame.size() == 6);
    CHECK(frame[0] == 0x00);
    CHECK(frame[1] == 0x00);
    // CRC32("") == 0
    CHECK(frame[2] == 0x00);
    CHECK(frame[3] == 0x00);
    CHECK(frame[4] == 0x00);
    CHECK(frame[5] == 0x00);
}

TEST_CASE("decode_frame round-trips an encoded frame") {
    auto payload = bytes({0x01, 0x02, 0x03, 0xAB, 0xCD, 0xEF});
    auto frame = encode_frame(payload);
    auto decoded = decode_frame(frame);
    CHECK(decoded.payload == payload);
    CHECK(decoded.bytes_consumed == frame.size());
    CHECK(decoded.crc_valid == true);
}

TEST_CASE("decode_frame flags a corrupted CRC") {
    auto payload = bytes({0x10, 0x20, 0x30});
    auto frame = encode_frame(payload);
    // Flip a CRC byte.
    frame[frame.size() - 1] ^= 0xFFu;
    auto decoded = decode_frame(frame);
    CHECK(decoded.payload == payload);
    CHECK(decoded.crc_valid == false);
}

TEST_CASE("decode_frame consumes only the declared frame, leaving trailing bytes") {
    auto payload = bytes({0xAA, 0xBB});
    auto frame = encode_frame(payload);
    // Append a sentinel that should NOT be consumed.
    frame.push_back(0x77);
    frame.push_back(0x88);
    auto decoded = decode_frame(frame);
    CHECK(decoded.payload == payload);
    CHECK(decoded.bytes_consumed == 2 + payload.size() + 4);
}

TEST_CASE("decode_frame throws on too-short header") {
    std::vector<std::uint8_t> tiny{0x05};
    CHECK_THROWS_AS(decode_frame(tiny), std::length_error);
}

TEST_CASE("decode_frame throws on truncated payload") {
    // Header claims 5 bytes but only 2 follow.
    std::vector<std::uint8_t> buf{0x05, 0x00, 0xAA, 0xBB};
    CHECK_THROWS_AS(decode_frame(buf), std::length_error);
}

TEST_CASE("encode_frame round-trips with random-ish 1KB payload") {
    std::vector<std::uint8_t> payload(1024);
    for (std::size_t i = 0; i < payload.size(); ++i) {
        payload[i] = static_cast<std::uint8_t>((i * 31u + 7u) & 0xFFu);
    }
    auto frame = encode_frame(payload);
    auto decoded = decode_frame(frame);
    CHECK(decoded.payload == payload);
    CHECK(decoded.crc_valid == true);
}
