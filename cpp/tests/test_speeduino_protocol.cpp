// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::speeduino_protocol.

#include "doctest.h"

#include "tuner_core/speeduino_protocol.hpp"

#include <vector>

using namespace tuner_core::speeduino_protocol;

TEST_CASE("page_request lays out the documented 7-byte header") {
    auto req = page_request('p', 4, 0x0102, 0x0304);
    REQUIRE(req.size() == 7);
    CHECK(req[0] == 'p');
    CHECK(req[1] == 0x00);
    CHECK(req[2] == 4);
    CHECK(req[3] == 0x02);  // offset lo
    CHECK(req[4] == 0x01);  // offset hi
    CHECK(req[5] == 0x04);  // length lo
    CHECK(req[6] == 0x03);  // length hi
}

TEST_CASE("page_read_request defaults to the 'p' command") {
    auto req = page_read_request(2, 0, 256);
    REQUIRE(req.size() == 7);
    CHECK(req[0] == 'p');
    CHECK(req[2] == 2);
    CHECK(req[5] == 0x00);
    CHECK(req[6] == 0x01);
}

TEST_CASE("page_write_request appends the payload after the header") {
    std::vector<std::uint8_t> payload{0xAA, 0xBB, 0xCC};
    auto req = page_write_request(1, 16, payload);
    REQUIRE(req.size() == 7 + 3);
    CHECK(req[0] == 'M');
    CHECK(req[2] == 1);
    CHECK(req[3] == 16);  // offset lo
    CHECK(req[5] == 3);   // length lo (length comes from payload size)
    CHECK(req[7] == 0xAA);
    CHECK(req[8] == 0xBB);
    CHECK(req[9] == 0xCC);
}

TEST_CASE("page_write_request honors a custom command character") {
    std::vector<std::uint8_t> payload{0xDE, 0xAD};
    auto req = page_write_request(0, 0, payload, 'W');
    CHECK(req[0] == 'W');
}

TEST_CASE("runtime_request matches the SEND_OUTPUT_CHANNELS shape") {
    auto req = runtime_request(0x0008, 0x0080);
    REQUIRE(req.size() == 7);
    CHECK(req[0] == 'r');
    CHECK(req[1] == 0x00);
    CHECK(req[2] == 0x30);
    CHECK(req[3] == 0x08);
    CHECK(req[4] == 0x00);
    CHECK(req[5] == 0x80);
    CHECK(req[6] == 0x00);
}

TEST_CASE("burn_request is a 3-byte sequence with the burn command char") {
    auto req = burn_request(7);
    REQUIRE(req.size() == 3);
    CHECK(req[0] == 'b');
    CHECK(req[1] == 0x00);
    CHECK(req[2] == 7);
}

TEST_CASE("burn_request honors a custom command character") {
    auto req = burn_request(2, 'B');
    CHECK(req[0] == 'B');
}

TEST_CASE("select_command_char returns the first character of a non-empty string") {
    CHECK(select_command_char("M%2i%2o%2c%v", 'M') == 'M');
    CHECK(select_command_char("Z", 'M') == 'Z');
}

TEST_CASE("select_command_char falls back when raw is null or empty") {
    CHECK(select_command_char(nullptr, 'p') == 'p');
    CHECK(select_command_char("", 'p') == 'p');
}

TEST_CASE("page_request encodes 16-bit offsets and lengths little-endian") {
    auto req = page_request('p', 0, 0xFEDC, 0xBA98);
    CHECK(req[3] == 0xDC);
    CHECK(req[4] == 0xFE);
    CHECK(req[5] == 0x98);
    CHECK(req[6] == 0xBA);
}

TEST_CASE("TN-005: page_crc_request is 3 bytes [d, 0, page]") {
    auto req = page_crc_request(7);
    REQUIRE(req.size() == 3);
    CHECK(req[0] == 'd');
    CHECK(req[1] == 0x00);
    CHECK(req[2] == 7);
}

TEST_CASE("TN-005: page_crc_request honors a custom command char") {
    auto req = page_crc_request(0, 'D');
    CHECK(req[0] == 'D');
}

TEST_CASE("TN-005: parse_page_crc_response decodes big-endian u32") {
    std::uint8_t buf[] = {0xDE, 0xAD, 0xBE, 0xEF};
    auto crc = parse_page_crc_response(std::span{buf});
    CHECK(crc == 0xDEADBEEFu);
}

TEST_CASE("TN-005: parse_page_crc_response zero") {
    std::uint8_t buf[] = {0x00, 0x00, 0x00, 0x00};
    CHECK(parse_page_crc_response(std::span{buf}) == 0u);
}

TEST_CASE("TN-005: parse_page_crc_response throws on short input") {
    std::uint8_t buf[] = {0x01, 0x02, 0x03};
    CHECK_THROWS(parse_page_crc_response(std::span{buf}));
}
