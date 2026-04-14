// SPDX-License-Identifier: MIT
//
// doctest cases for `teensy_hex_image.hpp`.

#include "doctest.h"

#include "tuner_core/teensy_hex_image.hpp"

#include <cstdint>
#include <stdexcept>
#include <string>

using namespace tuner_core::teensy_hex_image;

namespace {

McuSpec teensy35() { return McuSpec{"TEENSY35", 524288, 1024}; }
McuSpec teensy41() { return McuSpec{"TEENSY41", 8126464, 1024}; }

// Build one Intel HEX data record for testing.
std::string hex_data(int addr, std::vector<std::uint8_t> data) {
    char buf[16];
    std::string line = ":";
    std::snprintf(buf, sizeof(buf), "%02X", static_cast<int>(data.size()));
    line += buf;
    std::snprintf(buf, sizeof(buf), "%04X", addr);
    line += buf;
    line += "00";
    int sum = static_cast<int>(data.size()) + ((addr >> 8) & 0xFF) + (addr & 0xFF);
    for (auto b : data) {
        std::snprintf(buf, sizeof(buf), "%02X", b);
        line += buf;
        sum += b;
    }
    std::snprintf(buf, sizeof(buf), "%02X", (-sum) & 0xFF);
    line += buf;
    return line;
}

std::string hex_linear_addr(int upper) {
    char buf[16];
    std::string line = ":02000004";
    std::snprintf(buf, sizeof(buf), "%04X", upper);
    line += buf;
    int sum = 2 + 0 + 0 + 4 + ((upper >> 8) & 0xFF) + (upper & 0xFF);
    std::snprintf(buf, sizeof(buf), "%02X", (-sum) & 0xFF);
    line += buf;
    return line;
}

constexpr const char* kEof = ":00000001FF";

}  // namespace

TEST_CASE("read_hex parses simple data record") {
    auto spec = teensy35();
    std::string text = hex_data(0x0000, {0xAA, 0xBB, 0xCC, 0xDD}) + "\n" + kEof + "\n";
    auto image = read_hex(text, spec);
    CHECK(image.byte_count == 4);
    CHECK(image.bytes_by_address.at(0) == 0xAA);
    CHECK(image.bytes_by_address.at(1) == 0xBB);
    CHECK(image.bytes_by_address.at(2) == 0xCC);
    CHECK(image.bytes_by_address.at(3) == 0xDD);
}

TEST_CASE("read_hex stops at EOF record") {
    auto spec = teensy35();
    std::string text = hex_data(0x0000, {0x11}) + "\n" + kEof + "\n" +
                       hex_data(0x0010, {0x22}) + "\n";
    auto image = read_hex(text, spec);
    CHECK(image.byte_count == 1);
    CHECK(image.bytes_by_address.count(0x10) == 0);
}

TEST_CASE("read_hex honors linear address records") {
    auto spec = teensy35();
    std::string text = hex_linear_addr(0x0001) + "\n" +
                       hex_data(0x0000, {0x99}) + "\n" +
                       kEof + "\n";
    auto image = read_hex(text, spec);
    CHECK(image.byte_count == 1);
    CHECK(image.bytes_by_address.at(0x10000) == 0x99);
}

TEST_CASE("read_hex rebases Teensy 4.x 0x60000000 flash origin") {
    auto spec = teensy41();
    std::string text = hex_linear_addr(0x6000) + "\n" +
                       hex_data(0x0000, {0x42}) + "\n" +
                       kEof + "\n";
    auto image = read_hex(text, spec);
    CHECK(image.bytes_by_address.at(0) == 0x42);
    CHECK(image.bytes_by_address.count(0x60000000) == 0);
}

TEST_CASE("read_hex throws on bad checksum") {
    auto spec = teensy35();
    std::string text = ":010000000000\n";  // checksum should be FF, we put 00
    CHECK_THROWS_AS(read_hex(text, spec), std::runtime_error);
}

TEST_CASE("read_hex throws on malformed line") {
    auto spec = teensy35();
    CHECK_THROWS_AS(read_hex("garbage\n", spec), std::runtime_error);
    CHECK_THROWS_AS(read_hex(":ZZ\n", spec), std::runtime_error);
}

TEST_CASE("read_hex rejects data outside code_size") {
    McuSpec tiny{"TINY", 16, 16};
    std::string text = hex_data(0x0020, {0x01}) + "\n" + kEof + "\n";
    CHECK_THROWS_AS(read_hex(text, tiny), std::runtime_error);
}

TEST_CASE("block_is_blank treats missing bytes as 0xFF") {
    auto spec = teensy35();
    HexImage image;
    CHECK(block_is_blank(image, 0, spec.block_size) == true);
    image.bytes_by_address[10] = 0xFF;
    CHECK(block_is_blank(image, 0, spec.block_size) == true);
    image.bytes_by_address[20] = 0x00;
    CHECK(block_is_blank(image, 0, spec.block_size) == false);
}

TEST_CASE("block_addresses always emits block 0") {
    auto spec = teensy35();
    HexImage image;
    auto addrs = block_addresses(image, spec);
    REQUIRE(addrs.size() >= 1);
    CHECK(addrs[0] == 0);
}

TEST_CASE("block_addresses skips blank trailing blocks") {
    auto spec = teensy35();
    HexImage image;
    image.bytes_by_address[0] = 0x42;
    image.bytes_by_address[2048] = 0x43;
    auto addrs = block_addresses(image, spec);
    REQUIRE(addrs.size() == 2);
    CHECK(addrs[0] == 0);
    CHECK(addrs[1] == 2048);
}

TEST_CASE("block_addresses skips blocks of only 0xFF after first") {
    auto spec = teensy35();
    HexImage image;
    image.bytes_by_address[0] = 0x01;
    for (int i = 0; i < 1024; ++i) image.bytes_by_address[1024 + i] = 0xFF;
    image.bytes_by_address[2048] = 0x02;
    auto addrs = block_addresses(image, spec);
    REQUIRE(addrs.size() == 2);
    CHECK(addrs[0] == 0);
    CHECK(addrs[1] == 2048);
}

TEST_CASE("build_write_payload 1024-byte block shape") {
    auto spec = teensy35();
    HexImage image;
    image.bytes_by_address[0x123456] = 0xAB;
    auto payload = build_write_payload(image, spec, 0x123400);
    REQUIRE(payload.size() == 1024 + 64);
    CHECK(payload[0] == 0x00);
    CHECK(payload[1] == 0x34);
    CHECK(payload[2] == 0x12);
    CHECK(payload[64 + 0x56] == 0xAB);
    CHECK(payload[64 + 0x55] == 0xFF);  // unset -> 0xFF
}

TEST_CASE("build_write_payload small-MCU (<64KiB) shape") {
    McuSpec small{"SMALL", 32768, 256};
    HexImage image;
    image.bytes_by_address[0x1234] = 0xCD;
    auto payload = build_write_payload(image, small, 0x1200);
    REQUIRE(payload.size() == 256 + 2);
    CHECK(payload[0] == 0x00);
    CHECK(payload[1] == 0x12);
    CHECK(payload[2 + 0x34] == 0xCD);
}

TEST_CASE("build_write_payload medium-MCU (>=64KiB, non-1024 block) shape") {
    McuSpec medium{"MED", 131072, 256};
    HexImage image;
    image.bytes_by_address[0x012345] = 0xEF;
    auto payload = build_write_payload(image, medium, 0x012300);
    REQUIRE(payload.size() == 256 + 2);
    CHECK(payload[0] == 0x23);
    CHECK(payload[1] == 0x01);
    CHECK(payload[2 + 0x45] == 0xEF);
}

TEST_CASE("build_boot_payload starts with 0xFF 0xFF 0xFF") {
    auto spec = teensy35();
    auto payload = build_boot_payload(spec);
    REQUIRE(payload.size() == 1024 + 64);
    CHECK(payload[0] == 0xFF);
    CHECK(payload[1] == 0xFF);
    CHECK(payload[2] == 0xFF);
    CHECK(payload[3] == 0x00);
}

TEST_CASE("build_boot_payload non-1024 block sizing") {
    McuSpec small{"SMALL", 32768, 256};
    auto payload = build_boot_payload(small);
    REQUIRE(payload.size() == 256 + 2);
    CHECK(payload[0] == 0xFF);
}
