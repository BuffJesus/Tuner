// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::live_data_map_parser.

#include "doctest.h"

#include "tuner_core/live_data_map_parser.hpp"

#include <string>

using namespace tuner_core::live_data_map_parser;

// ---------------------------------------------------------------------------
// ChannelEncoding helpers
// ---------------------------------------------------------------------------

TEST_CASE("parse_encoding handles all known encodings") {
    CHECK(parse_encoding("U08") == ChannelEncoding::U08);
    CHECK(parse_encoding("U08 bits") == ChannelEncoding::U08_BITS);
    CHECK(parse_encoding("U16 LE") == ChannelEncoding::U16_LE);
    CHECK(parse_encoding("S16 LE") == ChannelEncoding::S16_LE);
    CHECK(parse_encoding("U32 LE") == ChannelEncoding::U32_LE);
}

TEST_CASE("parse_encoding is case-insensitive") {
    CHECK(parse_encoding("u08") == ChannelEncoding::U08);
    CHECK(parse_encoding("u16 le") == ChannelEncoding::U16_LE);
}

TEST_CASE("parse_encoding falls through to UNKNOWN") {
    CHECK(parse_encoding("garbage") == ChannelEncoding::UNKNOWN);
    CHECK(parse_encoding("") == ChannelEncoding::UNKNOWN);
}

TEST_CASE("byte_width matches the documented widths") {
    CHECK(byte_width(ChannelEncoding::U08) == 1);
    CHECK(byte_width(ChannelEncoding::U08_BITS) == 1);
    CHECK(byte_width(ChannelEncoding::U16_LE) == 2);
    CHECK(byte_width(ChannelEncoding::S16_LE) == 2);
    CHECK(byte_width(ChannelEncoding::U32_LE) == 4);
    CHECK(byte_width(ChannelEncoding::UNKNOWN) == 0);
}

// ---------------------------------------------------------------------------
// parse_text — full header parse
// ---------------------------------------------------------------------------

const char* SAMPLE_HEADER = R"(
/*
 * byte    ridx  field                          encoding       notes
 * 4-5      4    MAP                            U16 LE         map (kPa)
 * 14-15    13   RPM                            U16 LE         rpm
 * 84       57   status3                        U08 bits       status3 [LOCKED]
 * 100      -    AEamount >> 1                  U08            AEamount [low]
 */

#define LIVE_DATA_MAP_SIZE  148U

static constexpr uint16_t OCH_OFFSET_RUNTIME_STATUS_A    = 147U;
static constexpr uint16_t OCH_OFFSET_BOARD_CAPABILITY_FLAGS = 130U;
static constexpr uint16_t OCH_OFFSET_FLASH_HEALTH_STATUS = 131U;
)";

TEST_CASE("parse_text extracts log_entry_size") {
    auto c = parse_text(SAMPLE_HEADER);
    CHECK(c.log_entry_size == 148);
}

TEST_CASE("parse_text extracts the OCH_OFFSET constants") {
    auto c = parse_text(SAMPLE_HEADER);
    REQUIRE(c.runtime_status_a_offset.has_value());
    CHECK(*c.runtime_status_a_offset == 147);
    REQUIRE(c.board_capability_flags_offset.has_value());
    CHECK(*c.board_capability_flags_offset == 130);
    REQUIRE(c.flash_health_status_offset.has_value());
    CHECK(*c.flash_health_status_offset == 131);
}

TEST_CASE("parse_text extracts entries from the doxygen table") {
    auto c = parse_text(SAMPLE_HEADER);
    REQUIRE(c.entries.size() == 4);

    // MAP
    CHECK(c.entries[0].name == "map");  // notes-derived name
    CHECK(c.entries[0].byte_start == 4);
    CHECK(c.entries[0].byte_end == 5);
    CHECK(c.entries[0].readable_index.value() == 4);
    CHECK(c.entries[0].encoding == ChannelEncoding::U16_LE);
    CHECK(c.entries[0].field == "MAP");
    CHECK(c.entries[0].width() == 2);
    CHECK_FALSE(c.entries[0].locked);

    // RPM
    CHECK(c.entries[1].name == "rpm");
    CHECK(c.entries[1].byte_start == 14);
    CHECK(c.entries[1].byte_end == 15);

    // status3 [LOCKED]
    CHECK(c.entries[2].name == "status3");
    CHECK(c.entries[2].locked);
    CHECK(c.entries[2].notes == "status3");  // [LOCKED] stripped
    CHECK(c.entries[2].encoding == ChannelEncoding::U08_BITS);

    // single-byte row with '-' readable_index
    CHECK(c.entries[3].byte_start == 100);
    CHECK(c.entries[3].byte_end == 100);
    CHECK_FALSE(c.entries[3].readable_index.has_value());
    CHECK(c.entries[3].encoding == ChannelEncoding::U08);
}

TEST_CASE("parse_text accepts a firmware_signature pass-through") {
    auto c = parse_text(SAMPLE_HEADER, std::string("speeduino 202501-T41"));
    REQUIRE(c.firmware_signature.has_value());
    CHECK(*c.firmware_signature == "speeduino 202501-T41");
}

TEST_CASE("parse_text empty input yields empty contract") {
    auto c = parse_text("");
    CHECK(c.entries.empty());
    CHECK(c.log_entry_size == 0);
    CHECK_FALSE(c.runtime_status_a_offset.has_value());
}

TEST_CASE("parse_text skips DEPRECATED notes and uses field as name") {
    const char* header =
        " * 200      -    legacyVar                      U08            DEPRECATED: use newVar\n";
    auto c = parse_text(header);
    REQUIRE(c.entries.size() == 1);
    // Notes start with "DEPRECATED:" → name falls back to the field text.
    CHECK(c.entries[0].name == "legacyVar");
}
