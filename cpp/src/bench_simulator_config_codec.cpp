// SPDX-License-Identifier: MIT
//
// Implementation of the bench-simulator config codec.

#include "tuner_core/bench_simulator_config_codec.hpp"

namespace tuner_core::bench_simulator {

namespace {

// Pack a little-endian u16 into the buffer at `pos`, advance `pos`.
void put_u16_le(std::vector<std::uint8_t>& out, std::uint16_t v) {
    out.push_back(static_cast<std::uint8_t>(v & 0xFF));
    out.push_back(static_cast<std::uint8_t>((v >> 8) & 0xFF));
}

// Read a little-endian u16 from the buffer at `pos`.
std::uint16_t get_u16_le(std::span<const std::uint8_t> bytes, std::size_t pos) noexcept {
    return static_cast<std::uint16_t>(bytes[pos]) |
           (static_cast<std::uint16_t>(bytes[pos + 1]) << 8);
}

}  // namespace

bool is_compression_type_firmware_supported(CompressionType type) noexcept {
    // Firmware comments at globals.h::COMPRESSION_TYPE_1CYL_4STROKE
    // and COMPRESSION_TYPE_3CYL_4STROKE declare these
    // "Not initially supported". Every other entry is live.
    switch (type) {
        case CompressionType::CYL2_4STROKE:
        case CompressionType::CYL4_4STROKE:
        case CompressionType::CYL6_4STROKE:
        case CompressionType::CYL8_4STROKE:
            return true;
        case CompressionType::CYL1_4STROKE:
        case CompressionType::CYL3_4STROKE:
            return false;
    }
    return false;
}

std::optional<CompressionType> compression_type_from_cylinders(std::uint8_t cyl) noexcept {
    switch (cyl) {
        case 2: return CompressionType::CYL2_4STROKE;
        case 4: return CompressionType::CYL4_4STROKE;
        case 6: return CompressionType::CYL6_4STROKE;
        case 8: return CompressionType::CYL8_4STROKE;
        default: return std::nullopt;
    }
}

std::vector<std::uint8_t> encode_v2(const BenchSimulatorConfig& config) {
    std::vector<std::uint8_t> out;
    out.reserve(kV2ByteSize);
    out.push_back(kSchemaVersionV2);
    out.push_back(config.wheel);
    out.push_back(static_cast<std::uint8_t>(config.mode));
    put_u16_le(out, config.fixed_rpm);
    put_u16_le(out, config.sweep_low_rpm);
    put_u16_le(out, config.sweep_high_rpm);
    put_u16_le(out, config.sweep_interval);
    out.push_back(config.use_compression ? std::uint8_t{1} : std::uint8_t{0});
    out.push_back(static_cast<std::uint8_t>(config.compression_type));
    put_u16_le(out, config.compression_rpm);
    put_u16_le(out, config.compression_offset);
    out.push_back(config.compression_dynamic ? std::uint8_t{1} : std::uint8_t{0});
    return out;
}

std::vector<std::uint8_t> encode_v1(const BenchSimulatorConfig& config) {
    std::vector<std::uint8_t> out;
    out.reserve(kV1ByteSize);
    out.push_back(kSchemaVersionV1);
    out.push_back(config.wheel);
    out.push_back(static_cast<std::uint8_t>(config.mode));
    put_u16_le(out, config.fixed_rpm);
    put_u16_le(out, config.sweep_low_rpm);
    put_u16_le(out, config.sweep_high_rpm);
    put_u16_le(out, config.sweep_interval);
    return out;
}

std::optional<BenchSimulatorConfig> decode_v2(std::span<const std::uint8_t> bytes) {
    if (bytes.size() != kV2ByteSize) return std::nullopt;
    if (bytes[0] != kSchemaVersionV2) return std::nullopt;

    BenchSimulatorConfig c;
    c.version            = bytes[0];
    c.wheel              = bytes[1];
    c.mode               = static_cast<RpmMode>(bytes[2]);
    c.fixed_rpm          = get_u16_le(bytes, 3);
    c.sweep_low_rpm      = get_u16_le(bytes, 5);
    c.sweep_high_rpm     = get_u16_le(bytes, 7);
    c.sweep_interval     = get_u16_le(bytes, 9);
    c.use_compression    = bytes[11] != 0;
    c.compression_type   = static_cast<CompressionType>(bytes[12]);
    c.compression_rpm    = get_u16_le(bytes, 13);
    c.compression_offset = get_u16_le(bytes, 15);
    c.compression_dynamic = bytes[17] != 0;
    return c;
}

std::optional<BenchSimulatorConfig> decode_v1(std::span<const std::uint8_t> bytes) {
    if (bytes.size() != kV1ByteSize) return std::nullopt;
    if (bytes[0] != kSchemaVersionV1) return std::nullopt;

    BenchSimulatorConfig c;
    c.version        = bytes[0];
    c.wheel          = bytes[1];
    c.mode           = static_cast<RpmMode>(bytes[2]);
    c.fixed_rpm      = get_u16_le(bytes, 3);
    c.sweep_low_rpm  = get_u16_le(bytes, 5);
    c.sweep_high_rpm = get_u16_le(bytes, 7);
    c.sweep_interval = get_u16_le(bytes, 9);
    // Compression fields stay at the struct defaults.
    return c;
}

std::optional<BenchSimulatorConfig> decode_auto(std::span<const std::uint8_t> bytes) {
    if (bytes.size() == kV1ByteSize) return decode_v1(bytes);
    if (bytes.size() == kV2ByteSize) return decode_v2(bytes);
    return std::nullopt;
}

}  // namespace tuner_core::bench_simulator
