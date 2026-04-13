// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_param_codec — scale/translate/bit-field layer
// over the raw value codec. Direct port of
// `SpeeduinoControllerClient._encode_scalar`, `_decode_scalar`,
// `_encode_table`, `_decode_table`. Fourth sub-slice of the Phase 14
// comms-layer port (Slice 3).
//
// This layer takes a *layout* (offset + data type + scale/translate
// metadata, plus optional bit-field positioning) and translates
// physical values to/from raw page bytes. The layout structs are
// minimal PODs that capture only the fields the codec actually needs
// — they're not the full Python `ScalarParameterDefinition` /
// `TableDefinition` (those will land alongside the workspace services
// in Slice 4).
//
// Quirks-of-the-Python-implementation preserved (and pinned by the
// parity test) so the C++ side stays drop-in compatible:
//   - encode treats `scale == 0` the same as `scale == None` and
//     falls back to 1.0; decode only treats `None` as missing and
//     would honor `scale == 0` literally
//   - bit-field encode reads the existing value from the page,
//     masks out the field, ORs in the new bits, and re-encodes the
//     full integer
//   - bit-field decode shifts and masks the integer view of the
//     decoded raw value and returns the resulting integer as the
//     scaled `double` (mirroring Python's `int → return value`)

#pragma once

#include "tuner_core/speeduino_value_codec.hpp"

#include <cstddef>
#include <optional>
#include <span>
#include <vector>

namespace tuner_core::speeduino_param_codec {

using DataType = speeduino_value_codec::DataType;

struct ScalarLayout {
    std::size_t offset = 0;
    DataType data_type = DataType::U08;
    // Both scale fields use `std::optional` so the caller can
    // distinguish "missing" from "0.0", matching the Python `None`-vs-
    // numeric handling exactly.
    std::optional<double> scale;
    std::optional<double> translate;
    // -1 ⇒ no bit-field positioning. Both must be set together; the
    // codec checks both to decide whether to take the bit-field branch.
    int bit_offset = -1;
    int bit_length = -1;
};

struct TableLayout {
    std::size_t offset = 0;
    DataType data_type = DataType::U08;
    std::optional<double> scale;
    std::optional<double> translate;
    std::size_t rows = 0;
    std::size_t columns = 0;
};

// Encode `value` against `layout` and return the resulting size-byte
// slice (one element wide for the data type). For bit-field layouts,
// the existing value is read from `page[offset : offset + size]`,
// the field bits are replaced, and the full integer is re-encoded.
//
// `value` is `double` so callers can pass either an integer or a
// float; the codec routes through `int(value)` for integer types
// the same way Python `_encode_scalar` does.
std::vector<std::uint8_t> encode_scalar(
    const ScalarLayout& layout,
    double value,
    std::span<const std::uint8_t> page);

// Decode `page[layout.offset : layout.offset + size]` against
// `layout`. Returns the scaled physical value (or, for bit-field
// layouts, the masked integer cast to `double`).
double decode_scalar(
    const ScalarLayout& layout,
    std::span<const std::uint8_t> page);

// Encode a list of physical values into `rows * columns` little-
// endian raw values. Caller is responsible for placing the result at
// `layout.offset` in the destination page; this helper does not
// touch surrounding bytes (mirrors `_encode_table`'s return shape).
std::vector<std::uint8_t> encode_table(
    const TableLayout& layout,
    std::span<const double> values);

// Decode `page[layout.offset : layout.offset + rows*columns*item_size]`
// into a `vector<double>` of physical values.
std::vector<double> decode_table(
    const TableLayout& layout,
    std::span<const std::uint8_t> page);

}  // namespace tuner_core::speeduino_param_codec
