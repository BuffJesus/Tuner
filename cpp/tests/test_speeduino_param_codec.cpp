// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::speeduino_param_codec.

#include "doctest.h"

#include "tuner_core/speeduino_param_codec.hpp"

#include <stdexcept>
#include <vector>

using namespace tuner_core::speeduino_param_codec;
using DT = tuner_core::speeduino_value_codec::DataType;

TEST_CASE("encode_scalar U08 with scale=0.1 round-trips through decode") {
    ScalarLayout layout;
    layout.offset = 5;
    layout.data_type = DT::U08;
    layout.scale = 0.1;
    layout.translate = 0.0;
    std::vector<std::uint8_t> page(16, 0);
    auto bytes = encode_scalar(layout, 12.5, page);  // raw = 125
    REQUIRE(bytes.size() == 1);
    CHECK(bytes[0] == 125);
    page[5] = bytes[0];
    auto v = decode_scalar(layout, page);
    CHECK(v == doctest::Approx(12.5));
}

TEST_CASE("encode_scalar respects translate") {
    ScalarLayout layout;
    layout.offset = 0;
    layout.data_type = DT::S08;
    layout.scale = 1.0;
    layout.translate = -40.0;
    std::vector<std::uint8_t> page(2, 0);
    // physical 25 → raw = (25 - (-40)) / 1.0 = 65
    auto bytes = encode_scalar(layout, 25.0, page);
    CHECK(bytes[0] == 65);
    page[0] = 65;
    CHECK(decode_scalar(layout, page) == doctest::Approx(25.0));
}

TEST_CASE("encode_scalar treats scale=0 as missing on encode") {
    ScalarLayout layout;
    layout.offset = 0;
    layout.data_type = DT::U08;
    layout.scale = 0.0;
    layout.translate = 0.0;
    std::vector<std::uint8_t> page(1, 0);
    // scale==0 ⇒ encode falls back to 1.0; raw value = round(7.0)
    auto bytes = encode_scalar(layout, 7.0, page);
    CHECK(bytes[0] == 7);
}

TEST_CASE("encode_scalar bit-field merges into existing page byte") {
    ScalarLayout layout;
    layout.offset = 3;
    layout.data_type = DT::U08;
    layout.bit_offset = 2;
    layout.bit_length = 1;
    std::vector<std::uint8_t> page(8, 0);
    page[3] = 0b1100'0001;  // bit 2 currently 0
    auto bytes = encode_scalar(layout, 1, page);
    REQUIRE(bytes.size() == 1);
    // Expected: clear bit 2, then OR in 1<<2 = 0b0000'0100 → 0b1100'0101
    CHECK(bytes[0] == 0b1100'0101);
}

TEST_CASE("encode_scalar bit-field clears the field when value is 0") {
    ScalarLayout layout;
    layout.offset = 0;
    layout.data_type = DT::U08;
    layout.bit_offset = 4;
    layout.bit_length = 2;
    std::vector<std::uint8_t> page(1, 0);
    page[0] = 0b1111'1111;
    auto bytes = encode_scalar(layout, 0, page);
    // Bits 4-5 cleared: 0b1100'1111
    CHECK(bytes[0] == 0b1100'1111);
}

TEST_CASE("decode_scalar bit-field returns the masked integer") {
    ScalarLayout layout;
    layout.offset = 0;
    layout.data_type = DT::U08;
    layout.bit_offset = 3;
    layout.bit_length = 2;
    std::vector<std::uint8_t> page{0b0001'1000};  // bits 3-4 == 0b11 == 3
    CHECK(decode_scalar(layout, page) == doctest::Approx(3.0));
}

TEST_CASE("encode_table builds N raw items concatenated") {
    TableLayout layout;
    layout.offset = 0;
    layout.data_type = DT::U16;
    layout.scale = 1.0;
    layout.translate = 0.0;
    layout.rows = 2;
    layout.columns = 2;
    std::vector<double> values{1.0, 2.0, 3.0, 4.0};
    auto bytes = encode_table(layout, values);
    REQUIRE(bytes.size() == 4 * 2);
    CHECK(bytes[0] == 0x01);
    CHECK(bytes[1] == 0x00);
    CHECK(bytes[2] == 0x02);
    CHECK(bytes[3] == 0x00);
}

TEST_CASE("decode_table returns physical values via scale and translate") {
    TableLayout layout;
    layout.offset = 4;
    layout.data_type = DT::U08;
    layout.scale = 0.5;
    layout.translate = -10.0;
    layout.rows = 1;
    layout.columns = 3;
    // physical = raw * 0.5 - 10
    std::vector<std::uint8_t> page(8, 0);
    page[4] = 100;  // → 40.0
    page[5] = 50;   // → 15.0
    page[6] = 0;    // → -10.0
    auto values = decode_table(layout, page);
    REQUIRE(values.size() == 3);
    CHECK(values[0] == doctest::Approx(40.0));
    CHECK(values[1] == doctest::Approx(15.0));
    CHECK(values[2] == doctest::Approx(-10.0));
}

TEST_CASE("encode_table → decode_table round-trip") {
    TableLayout layout;
    layout.offset = 0;
    layout.data_type = DT::U08;
    layout.scale = 0.1;
    layout.translate = 0.0;
    layout.rows = 4;
    layout.columns = 1;
    std::vector<double> values{0.0, 5.5, 12.3, 25.5};
    auto bytes = encode_table(layout, values);
    auto round_tripped = decode_table(layout, bytes);
    REQUIRE(round_tripped.size() == values.size());
    for (std::size_t i = 0; i < values.size(); ++i) {
        CHECK(round_tripped[i] == doctest::Approx(values[i]).epsilon(0.05));
    }
}

TEST_CASE("decode_scalar throws on undersized page") {
    ScalarLayout layout;
    layout.offset = 10;
    layout.data_type = DT::U16;
    std::vector<std::uint8_t> page(4, 0);
    CHECK_THROWS_AS(decode_scalar(layout, page), std::runtime_error);
}
