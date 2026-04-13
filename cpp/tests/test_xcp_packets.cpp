// SPDX-License-Identifier: MIT
//
// doctest cases for `xcp_packets.hpp` — port of
// `tests/unit/test_xcp_packets.py`.

#include "doctest.h"

#include "tuner_core/xcp_packets.hpp"

#include <cstdint>
#include <stdexcept>
#include <vector>

using namespace tuner_core::xcp_packets;

namespace {

std::span<const std::uint8_t> as_span(const std::vector<std::uint8_t>& v) {
    return std::span<const std::uint8_t>(v.data(), v.size());
}

}  // namespace

// ---------------------------------------------------------------------
// Builders
// ---------------------------------------------------------------------

TEST_CASE("build_connect_command default mode") {
    auto cmd = build_connect_command();
    CHECK(cmd == std::vector<std::uint8_t>{0xFF, 0x00});
}

TEST_CASE("build_connect_command custom mode") {
    auto cmd = build_connect_command(0x01);
    CHECK(cmd == std::vector<std::uint8_t>{0xFF, 0x01});
}

TEST_CASE("build_get_status_command") {
    auto cmd = build_get_status_command();
    CHECK(cmd == std::vector<std::uint8_t>{0xFD});
}

TEST_CASE("build_get_id_command default identifier type") {
    auto cmd = build_get_id_command();
    CHECK(cmd == std::vector<std::uint8_t>{0xFA, 0x00});
}

TEST_CASE("build_get_id_command custom identifier type") {
    auto cmd = build_get_id_command(0x05);
    CHECK(cmd == std::vector<std::uint8_t>{0xFA, 0x05});
}

TEST_CASE("build_set_mta_command packs the address big-endian in bytes 4..8") {
    auto cmd = build_set_mta_command(0x12345678);
    CHECK(cmd == std::vector<std::uint8_t>{
        0xF6, 0x00, 0x00, 0x00, 0x12, 0x34, 0x56, 0x78});
}

TEST_CASE("build_set_mta_command address_extension lands at byte 3") {
    auto cmd = build_set_mta_command(0xDEADBEEF, 0x42);
    CHECK(cmd == std::vector<std::uint8_t>{
        0xF6, 0x00, 0x00, 0x42, 0xDE, 0xAD, 0xBE, 0xEF});
}

TEST_CASE("build_upload_command happy path") {
    auto cmd = build_upload_command(4);
    CHECK(cmd == std::vector<std::uint8_t>{0xF5, 0x04});
}

TEST_CASE("build_upload_command rejects out-of-range size") {
    CHECK_THROWS_AS(build_upload_command(0),   std::runtime_error);
    CHECK_THROWS_AS(build_upload_command(-1),  std::runtime_error);
    CHECK_THROWS_AS(build_upload_command(256), std::runtime_error);
}

TEST_CASE("build_upload_command boundary values") {
    auto lo = build_upload_command(1);
    auto hi = build_upload_command(255);
    CHECK(lo == std::vector<std::uint8_t>{0xF5, 0x01});
    CHECK(hi == std::vector<std::uint8_t>{0xF5, 0xFF});
}

// ---------------------------------------------------------------------
// Parsers
// ---------------------------------------------------------------------

TEST_CASE("parse_connect_response decodes the full 8-byte shape") {
    std::vector<std::uint8_t> packet = {0xFF, 0x01, 0x02, 0x08, 0x01, 0x00, 0x01, 0x01};
    auto r = parse_connect_response(as_span(packet));
    CHECK(r.resource == 0x01);
    CHECK(r.comm_mode_basic == 0x02);
    CHECK(r.max_cto == 0x08);
    CHECK(r.max_dto == 0x0100);
    CHECK(r.protocol_layer_version == 0x01);
    CHECK(r.transport_layer_version == 0x01);
}

TEST_CASE("parse_connect_response throws on wrong length") {
    std::vector<std::uint8_t> short_pkt = {0xFF, 0x01, 0x02, 0x08, 0x01, 0x00, 0x01};
    CHECK_THROWS_AS(parse_connect_response(as_span(short_pkt)), std::runtime_error);
}

TEST_CASE("parse_connect_response throws when first byte is not 0xFF") {
    std::vector<std::uint8_t> packet = {0xFE, 0x01, 0x02, 0x08, 0x01, 0x00, 0x01, 0x01};
    CHECK_THROWS_AS(parse_connect_response(as_span(packet)), std::runtime_error);
}

TEST_CASE("parse_status_response decodes the 6-byte shape") {
    std::vector<std::uint8_t> packet = {0xFF, 0x05, 0x00, 0x00, 0x01, 0x00};
    auto r = parse_status_response(as_span(packet));
    CHECK(r.session_status == 0x05);
    CHECK(r.protection_status == 0x00);
    // Big-endian u16 at packet[3..5) -> 0x00 << 8 | 0x01 = 1.
    CHECK(r.configuration_status == 0x0001);
}

TEST_CASE("parse_status_response throws on wrong length / PID") {
    std::vector<std::uint8_t> too_short = {0xFF, 0x05, 0x00, 0x00, 0x01};
    std::vector<std::uint8_t> bad_pid   = {0xFE, 0x05, 0x00, 0x00, 0x01, 0x00};
    CHECK_THROWS_AS(parse_status_response(as_span(too_short)), std::runtime_error);
    CHECK_THROWS_AS(parse_status_response(as_span(bad_pid)),   std::runtime_error);
}

TEST_CASE("parse_get_id_response decodes mode + length + identifier bytes") {
    // Mode 1, identifier length 5, identifier "HELLO".
    std::vector<std::uint8_t> packet = {
        0xFF,                          // PID
        0x01,                          // mode
        0x00, 0x00,                    // padding
        0x00, 0x00, 0x00, 0x05,        // identifier_length big-endian u32
        'H', 'E', 'L', 'L', 'O',
    };
    auto r = parse_get_id_response(as_span(packet));
    CHECK(r.mode == 1);
    CHECK(r.identifier_length == 5);
    CHECK(r.identifier == std::vector<std::uint8_t>{'H','E','L','L','O'});
    CHECK(r.identifier_text() == "HELLO");
}

TEST_CASE("parse_get_id_response identifier_text replaces non-ASCII bytes") {
    std::vector<std::uint8_t> packet = {
        0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03,
        'A', 0xFF, 'Z',
    };
    auto r = parse_get_id_response(as_span(packet));
    // U+FFFD == EF BF BD in UTF-8.
    CHECK(r.identifier_text() == std::string("A") + "\xEF\xBF\xBD" + "Z");
}

TEST_CASE("parse_get_id_response throws on truncated identifier payload") {
    // Length says 5, but only 3 bytes of identifier present.
    std::vector<std::uint8_t> packet = {
        0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05,
        'A', 'B', 'C',
    };
    CHECK_THROWS_AS(parse_get_id_response(as_span(packet)), std::runtime_error);
}

TEST_CASE("parse_get_id_response throws on zero length and unsupported mode") {
    std::vector<std::uint8_t> zero_len = {
        0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    };
    std::vector<std::uint8_t> bad_mode = {
        0xFF, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05, 'A','B','C','D','E',
    };
    CHECK_THROWS_AS(parse_get_id_response(as_span(zero_len)), std::runtime_error);
    CHECK_THROWS_AS(parse_get_id_response(as_span(bad_mode)), std::runtime_error);
}

TEST_CASE("parse_command_ack accepts the single 0xFF byte") {
    std::vector<std::uint8_t> ack = {0xFF};
    CHECK_NOTHROW(parse_command_ack(as_span(ack)));
}

TEST_CASE("parse_command_ack throws on every other shape") {
    std::vector<std::uint8_t> empty;
    std::vector<std::uint8_t> wrong_byte = {0xFE};
    std::vector<std::uint8_t> too_long   = {0xFF, 0x00};
    CHECK_THROWS_AS(parse_command_ack(as_span(empty)),      std::runtime_error);
    CHECK_THROWS_AS(parse_command_ack(as_span(wrong_byte)), std::runtime_error);
    CHECK_THROWS_AS(parse_command_ack(as_span(too_long)),   std::runtime_error);
}

TEST_CASE("parse_upload_response strips PID and returns payload bytes") {
    std::vector<std::uint8_t> packet = {0xFF, 0xDE, 0xAD, 0xBE, 0xEF};
    auto payload = parse_upload_response(as_span(packet), 4);
    CHECK(payload == std::vector<std::uint8_t>{0xDE, 0xAD, 0xBE, 0xEF});
}

TEST_CASE("parse_upload_response throws on length / PID mismatch") {
    std::vector<std::uint8_t> wrong_len = {0xFF, 0xAA, 0xBB};
    std::vector<std::uint8_t> bad_pid   = {0xFE, 0xAA, 0xBB, 0xCC, 0xDD};
    CHECK_THROWS_AS(parse_upload_response(as_span(wrong_len), 4), std::runtime_error);
    CHECK_THROWS_AS(parse_upload_response(as_span(bad_pid),   4), std::runtime_error);
}
