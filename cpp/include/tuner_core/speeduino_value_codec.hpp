// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_value_codec — pure-logic encode/decode of the
// Speeduino raw scalar/table data types (U08, S08, U16, S16, U32,
// S32, F32). Direct port of `SpeeduinoControllerClient._data_size`,
// `_encode_raw_value`, and `_decode_raw_value`. Third sub-slice of
// the Phase 14 comms-layer port (Slice 3).
//
// All encodings are little-endian (the Speeduino raw protocol is
// little-endian on every supported board family — see CLAUDE.md
// "Endianness field consumer added but byte paths unchanged"). The
// `RawValue` variant carries either an integer or a float so the
// caller doesn't need to know the type ahead of time when decoding.
//
// No domain dependency on `ScalarParameterDefinition` / `TableDefinition` —
// the higher-level scale/translate/bit-field handling lives one layer
// up and will be ported alongside the workspace services in Slice 4.

#pragma once

#include <cstdint>
#include <span>
#include <string_view>
#include <variant>
#include <vector>

namespace tuner_core::speeduino_value_codec {

// Mirrors the type tags used in INI `[Constants]` and the Python raw
// codec. Unknown / unsupported types raise at runtime — see
// `data_size_bytes` and `encode_raw_value` / `decode_raw_value`.
enum class DataType {
    U08,
    S08,
    U16,
    S16,
    U32,
    S32,
    F32,
};

// A decoded raw value. Integer types decode into the `int64_t` arm,
// `F32` decodes into `double`. Mirrors the `int | float` return type
// on `_decode_raw_value`.
using RawValue = std::variant<std::int64_t, double>;

// Parse a Python-style data-type tag (case-insensitive). Throws
// `std::runtime_error` for unknown tags so the C++ side surfaces the
// same failure shape as the Python `_data_size` / `_encode_raw_value`
// fallthrough cases.
DataType parse_data_type(std::string_view tag);

// Byte size of one value of `type`. Mirrors `_data_size`:
// {U08,S08}=1, {U16,S16}=2, {U32,S32,F32}=4.
std::size_t data_size_bytes(DataType type) noexcept;

// Convenience overload that accepts the textual tag.
std::size_t data_size_bytes(std::string_view tag);

// Encode `value` as the little-endian byte representation of `type`.
// Float types accept the value as the `double` arm of `RawValue` (or
// any integer that exactly fits); integer types accept either arm and
// truncate floats via `static_cast<int64_t>` to mirror Python's
// `int(value)` behaviour.
std::vector<std::uint8_t> encode_raw_value(RawValue value, DataType type);

// Convenience overload that accepts the textual tag.
std::vector<std::uint8_t> encode_raw_value(RawValue value, std::string_view tag);

// Decode `raw` as `type`. Caller must pass at least
// `data_size_bytes(type)` bytes; the high-byte slice is consumed
// little-endian. Mirrors `_decode_raw_value`.
RawValue decode_raw_value(std::span<const std::uint8_t> raw, DataType type);

// Convenience overload that accepts the textual tag.
RawValue decode_raw_value(std::span<const std::uint8_t> raw, std::string_view tag);

}  // namespace tuner_core::speeduino_value_codec
