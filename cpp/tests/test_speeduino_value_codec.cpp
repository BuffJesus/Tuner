// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::speeduino_value_codec.

#include "doctest.h"

#include "tuner_core/speeduino_value_codec.hpp"

#include <cstdint>
#include <stdexcept>
#include <vector>

using namespace tuner_core::speeduino_value_codec;

TEST_CASE("data_size_bytes covers every supported tag") {
    CHECK(data_size_bytes("U08") == 1);
    CHECK(data_size_bytes("S08") == 1);
    CHECK(data_size_bytes("U16") == 2);
    CHECK(data_size_bytes("S16") == 2);
    CHECK(data_size_bytes("U32") == 4);
    CHECK(data_size_bytes("S32") == 4);
    CHECK(data_size_bytes("F32") == 4);
}

TEST_CASE("parse_data_type is case-insensitive") {
    CHECK(parse_data_type("u08") == DataType::U08);
    CHECK(parse_data_type("U16") == DataType::U16);
    CHECK(parse_data_type("f32") == DataType::F32);
}

TEST_CASE("parse_data_type throws on unknown tag") {
    CHECK_THROWS_AS(parse_data_type("Q42"), std::runtime_error);
}

TEST_CASE("U08 encode/decode round-trip") {
    auto bytes = encode_raw_value(std::int64_t{200}, DataType::U08);
    REQUIRE(bytes.size() == 1);
    CHECK(bytes[0] == 200);
    auto v = decode_raw_value(bytes, DataType::U08);
    CHECK(std::get<std::int64_t>(v) == 200);
}

TEST_CASE("S08 sign-extends on decode") {
    auto bytes = encode_raw_value(std::int64_t{-1}, DataType::S08);
    REQUIRE(bytes.size() == 1);
    CHECK(bytes[0] == 0xFF);
    auto v = decode_raw_value(bytes, DataType::S08);
    CHECK(std::get<std::int64_t>(v) == -1);
}

TEST_CASE("U16 little-endian round-trip") {
    auto bytes = encode_raw_value(std::int64_t{0xBEEF}, DataType::U16);
    REQUIRE(bytes.size() == 2);
    CHECK(bytes[0] == 0xEF);
    CHECK(bytes[1] == 0xBE);
    auto v = decode_raw_value(bytes, DataType::U16);
    CHECK(std::get<std::int64_t>(v) == 0xBEEF);
}

TEST_CASE("S16 negative round-trip") {
    auto bytes = encode_raw_value(std::int64_t{-1234}, DataType::S16);
    auto v = decode_raw_value(bytes, DataType::S16);
    CHECK(std::get<std::int64_t>(v) == -1234);
}

TEST_CASE("U32 round-trip preserves the full 32-bit range") {
    auto bytes = encode_raw_value(std::int64_t{0xDEADBEEF}, DataType::U32);
    REQUIRE(bytes.size() == 4);
    CHECK(bytes[0] == 0xEF);
    CHECK(bytes[1] == 0xBE);
    CHECK(bytes[2] == 0xAD);
    CHECK(bytes[3] == 0xDE);
    auto v = decode_raw_value(bytes, DataType::U32);
    CHECK(std::get<std::int64_t>(v) == static_cast<std::int64_t>(0xDEADBEEF));
}

TEST_CASE("S32 negative round-trip sign-extends") {
    auto bytes = encode_raw_value(std::int64_t{-100000}, DataType::S32);
    auto v = decode_raw_value(bytes, DataType::S32);
    CHECK(std::get<std::int64_t>(v) == -100000);
}

TEST_CASE("F32 round-trip preserves the float value") {
    auto bytes = encode_raw_value(double{3.14159}, DataType::F32);
    REQUIRE(bytes.size() == 4);
    auto v = decode_raw_value(bytes, DataType::F32);
    REQUIRE(std::holds_alternative<double>(v));
    CHECK(std::get<double>(v) == doctest::Approx(3.14159).epsilon(1e-5));
}

TEST_CASE("F32 accepts an integer-valued RawValue input") {
    auto bytes = encode_raw_value(std::int64_t{42}, DataType::F32);
    auto v = decode_raw_value(bytes, DataType::F32);
    CHECK(std::get<double>(v) == doctest::Approx(42.0));
}

TEST_CASE("decode_raw_value throws on undersized buffer") {
    std::vector<std::uint8_t> short_buf{0x01};
    CHECK_THROWS_AS(decode_raw_value(short_buf, DataType::U16), std::runtime_error);
}

TEST_CASE("encode_raw_value via textual tag matches enum overload") {
    auto a = encode_raw_value(std::int64_t{1234}, DataType::U16);
    auto b = encode_raw_value(std::int64_t{1234}, "U16");
    CHECK(a == b);
}
