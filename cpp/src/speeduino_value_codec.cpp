// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_value_codec implementation. Pure-logic, no I/O.

#include "tuner_core/speeduino_value_codec.hpp"

#include <cctype>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>

namespace tuner_core::speeduino_value_codec {

namespace {

std::string upper(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
    }
    return out;
}

[[noreturn]] void unsupported(std::string_view tag) {
    throw std::runtime_error(
        std::string("Unsupported Speeduino data type: ") + std::string(tag));
}

// Extract `width` bytes little-endian into the appropriate signed/
// unsigned integer of that width.
template <typename T>
T read_le(std::span<const std::uint8_t> raw) noexcept {
    T value = 0;
    for (std::size_t i = 0; i < sizeof(T); ++i) {
        value |= static_cast<T>(static_cast<std::uint64_t>(raw[i]) << (8 * i));
    }
    return value;
}

template <typename T>
void append_le(std::vector<std::uint8_t>& out, T value) {
    auto bits = static_cast<std::uint64_t>(value);
    for (std::size_t i = 0; i < sizeof(T); ++i) {
        out.push_back(static_cast<std::uint8_t>((bits >> (8 * i)) & 0xFFu));
    }
}

std::int64_t to_int(RawValue value) noexcept {
    if (std::holds_alternative<std::int64_t>(value)) {
        return std::get<std::int64_t>(value);
    }
    // Mirror Python's `int(value)` truncation toward zero.
    return static_cast<std::int64_t>(std::get<double>(value));
}

double to_double(RawValue value) noexcept {
    if (std::holds_alternative<double>(value)) {
        return std::get<double>(value);
    }
    return static_cast<double>(std::get<std::int64_t>(value));
}

}  // namespace

DataType parse_data_type(std::string_view tag) {
    auto u = upper(tag);
    if (u == "U08") return DataType::U08;
    if (u == "S08") return DataType::S08;
    if (u == "U16") return DataType::U16;
    if (u == "S16") return DataType::S16;
    if (u == "U32") return DataType::U32;
    if (u == "S32") return DataType::S32;
    if (u == "F32") return DataType::F32;
    unsupported(tag);
}

std::size_t data_size_bytes(DataType type) noexcept {
    switch (type) {
        case DataType::U08:
        case DataType::S08:
            return 1;
        case DataType::U16:
        case DataType::S16:
            return 2;
        case DataType::U32:
        case DataType::S32:
        case DataType::F32:
            return 4;
    }
    return 0;  // unreachable
}

std::size_t data_size_bytes(std::string_view tag) {
    return data_size_bytes(parse_data_type(tag));
}

std::vector<std::uint8_t> encode_raw_value(RawValue value, DataType type) {
    std::vector<std::uint8_t> out;
    out.reserve(data_size_bytes(type));
    switch (type) {
        case DataType::U08:
            append_le<std::uint8_t>(out, static_cast<std::uint8_t>(to_int(value)));
            return out;
        case DataType::S08:
            append_le<std::uint8_t>(out, static_cast<std::uint8_t>(
                static_cast<std::int8_t>(to_int(value))));
            return out;
        case DataType::U16:
            append_le<std::uint16_t>(out, static_cast<std::uint16_t>(to_int(value)));
            return out;
        case DataType::S16:
            append_le<std::uint16_t>(out, static_cast<std::uint16_t>(
                static_cast<std::int16_t>(to_int(value))));
            return out;
        case DataType::U32:
            append_le<std::uint32_t>(out, static_cast<std::uint32_t>(to_int(value)));
            return out;
        case DataType::S32:
            append_le<std::uint32_t>(out, static_cast<std::uint32_t>(
                static_cast<std::int32_t>(to_int(value))));
            return out;
        case DataType::F32: {
            float f = static_cast<float>(to_double(value));
            std::uint32_t bits;
            std::memcpy(&bits, &f, sizeof(bits));
            append_le<std::uint32_t>(out, bits);
            return out;
        }
    }
    return out;  // unreachable
}

std::vector<std::uint8_t> encode_raw_value(RawValue value, std::string_view tag) {
    return encode_raw_value(value, parse_data_type(tag));
}

RawValue decode_raw_value(std::span<const std::uint8_t> raw, DataType type) {
    const std::size_t needed = data_size_bytes(type);
    if (raw.size() < needed) {
        throw std::runtime_error(
            "speeduino_value_codec::decode_raw_value: buffer too small for type");
    }
    switch (type) {
        case DataType::U08:
            return static_cast<std::int64_t>(raw[0]);
        case DataType::S08:
            return static_cast<std::int64_t>(static_cast<std::int8_t>(raw[0]));
        case DataType::U16:
            return static_cast<std::int64_t>(read_le<std::uint16_t>(raw));
        case DataType::S16:
            return static_cast<std::int64_t>(
                static_cast<std::int16_t>(read_le<std::uint16_t>(raw)));
        case DataType::U32:
            return static_cast<std::int64_t>(read_le<std::uint32_t>(raw));
        case DataType::S32:
            return static_cast<std::int64_t>(
                static_cast<std::int32_t>(read_le<std::uint32_t>(raw)));
        case DataType::F32: {
            std::uint32_t bits = read_le<std::uint32_t>(raw);
            float f;
            std::memcpy(&f, &bits, sizeof(f));
            return static_cast<double>(f);
        }
    }
    return std::int64_t{0};  // unreachable
}

RawValue decode_raw_value(std::span<const std::uint8_t> raw, std::string_view tag) {
    return decode_raw_value(raw, parse_data_type(tag));
}

}  // namespace tuner_core::speeduino_value_codec
