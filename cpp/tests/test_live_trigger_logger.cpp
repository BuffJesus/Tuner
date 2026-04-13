// SPDX-License-Identifier: MIT
//
// doctest cases for `live_trigger_logger.hpp` — port of
// `LiveTriggerLoggerService.decode` and `_extract_field`.

#include "doctest.h"

#include "tuner_core/live_trigger_logger.hpp"

#include <cstdint>
#include <vector>

using namespace tuner_core;
using namespace tuner_core::live_trigger_logger;

namespace {

IniLoggerRecordField make_field(const std::string& header,
                                int start_bit, int bit_count, double scale) {
    IniLoggerRecordField f;
    f.name = header;
    f.header = header;
    f.start_bit = start_bit;
    f.bit_count = bit_count;
    f.scale = scale;
    return f;
}

IniLoggerDefinition make_tooth_logger(int record_count) {
    IniLoggerDefinition l;
    l.name = "ToothLog";
    l.display_name = "Tooth Log";
    l.kind = "tooth";
    l.record_header_len = 0;
    l.record_len = 4;
    l.record_count = record_count;
    l.record_fields.push_back(make_field("ToothTime", 0, 32, 1.0));
    return l;
}

IniLoggerDefinition make_composite_logger(int record_count) {
    IniLoggerDefinition l;
    l.name = "CompositeLog";
    l.display_name = "Composite Log";
    l.kind = "composite";
    l.record_header_len = 0;
    l.record_len = 5;
    l.record_count = record_count;
    // Bit flags packed in byte 0.
    l.record_fields.push_back(make_field("PriLevel",   0, 1, 1.0));
    l.record_fields.push_back(make_field("SecLevel",   1, 1, 1.0));
    l.record_fields.push_back(make_field("ThirdLevel", 2, 1, 1.0));
    l.record_fields.push_back(make_field("Trigger",    3, 1, 1.0));
    l.record_fields.push_back(make_field("Sync",       4, 1, 1.0));
    l.record_fields.push_back(make_field("Cycle",      5, 1, 1.0));
    // refTime u32 LE at byte 1 = bit 8.
    l.record_fields.push_back(make_field("RefTime",    8, 32, 0.001));
    return l;
}

}  // namespace

TEST_CASE("live_trigger_logger: empty raw -> empty rows") {
    auto logger = make_tooth_logger(/*record_count=*/0);
    std::vector<std::uint8_t> raw;
    auto cap = decode(logger, raw);
    CHECK(cap.logger_name == "ToothLog");
    CHECK(cap.display_name == "Tooth Log");
    CHECK(cap.kind == "tooth");
    CHECK(cap.columns.size() == 1);
    CHECK(cap.columns[0] == "ToothTime");
    CHECK(cap.rows.empty());
    CHECK(cap.record_count() == 0);
}

TEST_CASE("live_trigger_logger: tooth records decoded as u32 LE microseconds") {
    auto logger = make_tooth_logger(3);
    // Three records: 1000us, 1500us, 1234567us.
    std::vector<std::uint8_t> raw = {
        0xE8, 0x03, 0x00, 0x00,  // 1000
        0xDC, 0x05, 0x00, 0x00,  // 1500
        0x87, 0xD6, 0x12, 0x00,  // 1234567
    };
    auto cap = decode(logger, raw);
    REQUIRE(cap.rows.size() == 3);
    CHECK(cap.rows[0].values.at("ToothTime") == doctest::Approx(1000.0));
    CHECK(cap.rows[1].values.at("ToothTime") == doctest::Approx(1500.0));
    CHECK(cap.rows[2].values.at("ToothTime") == doctest::Approx(1234567.0));
}

TEST_CASE("live_trigger_logger: composite record decodes bit flags + refTime ms") {
    auto logger = make_composite_logger(1);
    // Byte 0: bits 0,1,3 set => priLevel=1 secLevel=1 trigger=1
    //         => 0b0000_1011 = 0x0B
    // Bytes 1..4: refTime = 5000 (us) -> 5.000 ms after scale.
    std::vector<std::uint8_t> raw = {
        0x0B,
        0x88, 0x13, 0x00, 0x00,  // 5000
    };
    auto cap = decode(logger, raw);
    REQUIRE(cap.rows.size() == 1);
    const auto& row = cap.rows[0].values;
    CHECK(row.at("PriLevel") == doctest::Approx(1.0));
    CHECK(row.at("SecLevel") == doctest::Approx(1.0));
    CHECK(row.at("ThirdLevel") == doctest::Approx(0.0));
    CHECK(row.at("Trigger") == doctest::Approx(1.0));
    CHECK(row.at("Sync") == doctest::Approx(0.0));
    CHECK(row.at("Cycle") == doctest::Approx(0.0));
    CHECK(row.at("RefTime") == doctest::Approx(5.0));
}

TEST_CASE("live_trigger_logger: rec_len == 0 yields empty rows but full metadata") {
    IniLoggerDefinition logger;
    logger.name = "Empty";
    logger.display_name = "Empty Log";
    logger.kind = "tooth";
    logger.record_len = 0;
    logger.record_count = 5;
    logger.record_fields.push_back(make_field("X", 0, 8, 1.0));
    std::vector<std::uint8_t> raw{1, 2, 3, 4, 5};
    auto cap = decode(logger, raw);
    CHECK(cap.logger_name == "Empty");
    CHECK(cap.columns == std::vector<std::string>{"X"});
    CHECK(cap.rows.empty());
}

TEST_CASE("live_trigger_logger: truncated raw stops at last full record") {
    auto logger = make_tooth_logger(3);
    // Only enough bytes for 2 full records (8 of the 12 needed).
    std::vector<std::uint8_t> raw = {
        0x01, 0x00, 0x00, 0x00,  // 1
        0x02, 0x00, 0x00, 0x00,  // 2
        0x03, 0x00,              // truncated
    };
    auto cap = decode(logger, raw);
    REQUIRE(cap.rows.size() == 2);
    CHECK(cap.rows[0].values.at("ToothTime") == doctest::Approx(1.0));
    CHECK(cap.rows[1].values.at("ToothTime") == doctest::Approx(2.0));
}

TEST_CASE("live_trigger_logger: record_header_len skip is honored") {
    auto logger = make_tooth_logger(2);
    logger.record_header_len = 3;  // skip 3 leading header bytes
    std::vector<std::uint8_t> raw = {
        0xAA, 0xBB, 0xCC,        // header to skip
        0x05, 0x00, 0x00, 0x00,  // 5
        0x06, 0x00, 0x00, 0x00,  // 6
    };
    auto cap = decode(logger, raw);
    REQUIRE(cap.rows.size() == 2);
    CHECK(cap.rows[0].values.at("ToothTime") == doctest::Approx(5.0));
    CHECK(cap.rows[1].values.at("ToothTime") == doctest::Approx(6.0));
}

TEST_CASE("live_trigger_logger: extract_field bit flag at varied byte positions") {
    // Byte 0 = 0xA5 = 1010_0101.  Byte 1 = 0x10 = 0001_0000 (bit 4 of byte 1 = bit 12).
    std::vector<std::uint8_t> rec = {0xA5, 0x10};
    auto bit0  = make_field("b0",  0, 1, 1.0);
    auto bit1  = make_field("b1",  1, 1, 1.0);
    auto bit2  = make_field("b2",  2, 1, 1.0);
    auto bit5  = make_field("b5",  5, 1, 1.0);
    auto bit12 = make_field("b12", 12, 1, 1.0);
    auto bit13 = make_field("b13", 13, 1, 1.0);
    CHECK(extract_field(rec, bit0)  == doctest::Approx(1.0));
    CHECK(extract_field(rec, bit1)  == doctest::Approx(0.0));
    CHECK(extract_field(rec, bit2)  == doctest::Approx(1.0));
    CHECK(extract_field(rec, bit5)  == doctest::Approx(1.0));
    CHECK(extract_field(rec, bit12) == doctest::Approx(1.0));
    CHECK(extract_field(rec, bit13) == doctest::Approx(0.0));
}

TEST_CASE("live_trigger_logger: extract_field generic bit window across bytes") {
    // 12-bit field starting at bit 4: spans 2 bytes.
    // Bytes: 0x34 0x12 -> u16 LE 0x1234. bits[4..16) = 0x123 = 291.
    std::vector<std::uint8_t> rec = {0x34, 0x12};
    auto field = make_field("twelve", 4, 12, 1.0);
    CHECK(extract_field(rec, field) == doctest::Approx(291.0));
}

TEST_CASE("live_trigger_logger: extract_field out-of-range returns 0") {
    std::vector<std::uint8_t> rec = {0xFF};
    auto bit_oob = make_field("oob", 16, 1, 1.0);
    auto u32_oob = make_field("u32_oob", 0, 32, 1.0);
    auto generic_oob = make_field("gen_oob", 0, 16, 1.0);
    CHECK(extract_field(rec, bit_oob) == doctest::Approx(0.0));
    CHECK(extract_field(rec, u32_oob) == doctest::Approx(0.0));
    CHECK(extract_field(rec, generic_oob) == doctest::Approx(0.0));
}

TEST_CASE("live_trigger_logger: scale is applied to all extraction modes") {
    std::vector<std::uint8_t> rec = {0x01, 0x88, 0x13, 0x00, 0x00};
    auto bit_field = make_field("flag", 0, 1, 2.5);              // raw 1 * 2.5
    auto u32_field = make_field("count", 8, 32, 0.5);            // 5000 * 0.5
    auto generic_field = make_field("nibble", 0, 4, 10.0);       // 0x1 * 10
    CHECK(extract_field(rec, bit_field) == doctest::Approx(2.5));
    CHECK(extract_field(rec, u32_field) == doctest::Approx(2500.0));
    CHECK(extract_field(rec, generic_field) == doctest::Approx(10.0));
}

TEST_CASE("live_trigger_logger: capture columns preserve record-field order") {
    auto logger = make_composite_logger(0);
    auto cap = decode(logger, std::span<const std::uint8_t>{});
    REQUIRE(cap.columns.size() == 7);
    CHECK(cap.columns[0] == "PriLevel");
    CHECK(cap.columns[1] == "SecLevel");
    CHECK(cap.columns[2] == "ThirdLevel");
    CHECK(cap.columns[3] == "Trigger");
    CHECK(cap.columns[4] == "Sync");
    CHECK(cap.columns[5] == "Cycle");
    CHECK(cap.columns[6] == "RefTime");
}
