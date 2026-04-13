// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_param_codec implementation. Pure-logic.

#include "tuner_core/speeduino_param_codec.hpp"

#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <variant>

namespace tuner_core::speeduino_param_codec {

namespace {

namespace vc = speeduino_value_codec;

// Mirror Python: `scale if scale not in {None, 0} else 1.0`.
double encode_scale_or_one(const std::optional<double>& scale) noexcept {
    if (!scale.has_value()) return 1.0;
    if (*scale == 0.0) return 1.0;
    return *scale;
}

// Mirror Python decode: `scale if scale is not None else 1.0`.
// Note: 0 is preserved literally on decode (the Python quirk).
double decode_scale_or_one(const std::optional<double>& scale) noexcept {
    return scale.value_or(1.0);
}

double translate_or_zero(const std::optional<double>& translate) noexcept {
    return translate.value_or(0.0);
}

// Read an integer at `page[offset : offset + size]` for the given
// data type. Used by both the bit-field encode (to merge into the
// existing value) and the bit-field decode path.
std::int64_t read_int(
    std::span<const std::uint8_t> page,
    std::size_t offset,
    DataType type) {
    auto size = vc::data_size_bytes(type);
    if (page.size() < offset + size) {
        throw std::runtime_error(
            "speeduino_param_codec: page slice too short for layout");
    }
    auto raw = page.subspan(offset, size);
    auto v = vc::decode_raw_value(raw, type);
    if (std::holds_alternative<std::int64_t>(v)) {
        return std::get<std::int64_t>(v);
    }
    return static_cast<std::int64_t>(std::get<double>(v));
}

// Mirror Python `round(...)` (banker's rounding to nearest even on
// .5 ties): the Speeduino client uses Python's built-in `round`,
// which is banker's. C++ `std::lround` rounds half-away-from-zero,
// which would diverge on exact halves. We use the same banker's
// rounding policy here.
std::int64_t banker_round(double x) noexcept {
    double r = std::nearbyint(x);  // honors current rounding mode (default round-to-nearest-even)
    return static_cast<std::int64_t>(r);
}

}  // namespace

std::vector<std::uint8_t> encode_scalar(
    const ScalarLayout& layout,
    double value,
    std::span<const std::uint8_t> page) {
    const auto size = vc::data_size_bytes(layout.data_type);

    // Bit-field branch: read the existing value, replace the masked
    // bits, re-encode the full integer.
    if (layout.bit_offset >= 0 && layout.bit_length >= 0) {
        std::int64_t current = read_int(page, layout.offset, layout.data_type);
        const std::int64_t mask =
            ((std::int64_t{1} << layout.bit_length) - 1) << layout.bit_offset;
        const std::int64_t new_field = (static_cast<std::int64_t>(value)
                                        << layout.bit_offset) & mask;
        const std::int64_t merged = (current & ~mask) | new_field;
        return vc::encode_raw_value(vc::RawValue{merged}, layout.data_type);
    }

    const double scale = encode_scale_or_one(layout.scale);
    const double translate = translate_or_zero(layout.translate);
    const double scaled = (value - translate) / scale;
    const std::int64_t raw_int = banker_round(scaled);
    // For F32 the int round-trip would lose precision; the Python
    // codec also uses int(round(...)) regardless of underlying type
    // when there's no bit-field, so we mirror that exactly.
    if (layout.data_type == DataType::F32) {
        return vc::encode_raw_value(vc::RawValue{static_cast<double>(raw_int)},
                                    layout.data_type);
    }
    return vc::encode_raw_value(vc::RawValue{raw_int}, layout.data_type);
    (void)size;
}

double decode_scalar(
    const ScalarLayout& layout,
    std::span<const std::uint8_t> page) {
    const auto size = vc::data_size_bytes(layout.data_type);
    if (page.size() < layout.offset + size) {
        throw std::runtime_error(
            "speeduino_param_codec::decode_scalar: page slice too short");
    }
    auto raw = page.subspan(layout.offset, size);
    auto value = vc::decode_raw_value(raw, layout.data_type);

    if (layout.bit_offset >= 0 && layout.bit_length >= 0) {
        std::int64_t int_val = std::holds_alternative<std::int64_t>(value)
                                   ? std::get<std::int64_t>(value)
                                   : static_cast<std::int64_t>(std::get<double>(value));
        const std::int64_t mask = (std::int64_t{1} << layout.bit_length) - 1;
        const std::int64_t masked = (int_val >> layout.bit_offset) & mask;
        return static_cast<double>(masked);
    }

    double v = std::holds_alternative<double>(value)
                   ? std::get<double>(value)
                   : static_cast<double>(std::get<std::int64_t>(value));
    return (v * decode_scale_or_one(layout.scale)) + translate_or_zero(layout.translate);
}

std::vector<std::uint8_t> encode_table(
    const TableLayout& layout,
    std::span<const double> values) {
    const auto item_size = vc::data_size_bytes(layout.data_type);
    const double scale = encode_scale_or_one(layout.scale);
    const double translate = translate_or_zero(layout.translate);

    std::vector<std::uint8_t> out;
    out.reserve(values.size() * item_size);
    for (double v : values) {
        const double scaled = (v - translate) / scale;
        const std::int64_t raw_int = banker_round(scaled);
        std::vector<std::uint8_t> bytes;
        if (layout.data_type == DataType::F32) {
            bytes = vc::encode_raw_value(
                vc::RawValue{static_cast<double>(raw_int)}, layout.data_type);
        } else {
            bytes = vc::encode_raw_value(vc::RawValue{raw_int}, layout.data_type);
        }
        out.insert(out.end(), bytes.begin(), bytes.end());
    }
    return out;
}

std::vector<double> decode_table(
    const TableLayout& layout,
    std::span<const std::uint8_t> page) {
    const auto item_size = vc::data_size_bytes(layout.data_type);
    const std::size_t total = layout.rows * layout.columns;
    const double scale = decode_scale_or_one(layout.scale);
    const double translate = translate_or_zero(layout.translate);
    if (page.size() < layout.offset + total * item_size) {
        throw std::runtime_error(
            "speeduino_param_codec::decode_table: page slice too short");
    }

    std::vector<double> out;
    out.reserve(total);
    for (std::size_t i = 0; i < total; ++i) {
        auto raw = page.subspan(layout.offset + i * item_size, item_size);
        auto v = vc::decode_raw_value(raw, layout.data_type);
        double dv = std::holds_alternative<double>(v)
                        ? std::get<double>(v)
                        : static_cast<double>(std::get<std::int64_t>(v));
        out.push_back((dv * scale) + translate);
    }
    return out;
}

}  // namespace tuner_core::speeduino_param_codec
