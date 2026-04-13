// SPDX-License-Identifier: MIT
//
// Implementation of `live_trigger_logger.hpp`. Direct port of
// `LiveTriggerLoggerService.decode` and `_extract_field` from
// `src/tuner/services/live_trigger_logger_service.py`.

#include "tuner_core/live_trigger_logger.hpp"

#include <cstddef>
#include <cstdint>

namespace tuner_core::live_trigger_logger {

double extract_field(std::span<const std::uint8_t> record,
                     const IniLoggerRecordField& field_def) {
    const int start_bit = field_def.start_bit;
    const int bit_count = field_def.bit_count;
    const double scale = field_def.scale;

    // Special case: single-bit flag at start_bit.
    if (bit_count == 1) {
        const std::size_t byte_index = static_cast<std::size_t>(start_bit / 8);
        const int bit_index = start_bit % 8;
        if (byte_index >= record.size()) return 0.0;
        const unsigned raw_bit = (record[byte_index] >> bit_index) & 0x01u;
        return static_cast<double>(raw_bit) * scale;
    }

    // Special case: u32 LE at byte (start_bit / 8).
    if (bit_count == 32) {
        const std::size_t byte_index = static_cast<std::size_t>(start_bit / 8);
        if (byte_index + 4 > record.size()) return 0.0;
        const std::uint32_t raw_u32 =
            static_cast<std::uint32_t>(record[byte_index]) |
            (static_cast<std::uint32_t>(record[byte_index + 1]) << 8) |
            (static_cast<std::uint32_t>(record[byte_index + 2]) << 16) |
            (static_cast<std::uint32_t>(record[byte_index + 3]) << 24);
        return static_cast<double>(raw_u32) * scale;
    }

    // Generic: extract `bit_count` bits starting at `start_bit`,
    // crossing byte boundaries. Mirrors the Python loop.
    const std::size_t byte_index = static_cast<std::size_t>(start_bit / 8);
    const int bit_offset = start_bit % 8;
    const int needed_bytes = (bit_offset + bit_count + 7) / 8;
    if (byte_index + static_cast<std::size_t>(needed_bytes) > record.size())
        return 0.0;

    // Accumulate up to needed_bytes (cap at 8 bytes = 64 bits, which
    // covers everything sane for a logger field).
    std::uint64_t accumulated = 0;
    for (int j = 0; j < needed_bytes && j < 8; ++j) {
        accumulated |= static_cast<std::uint64_t>(record[byte_index + j])
                       << (8 * j);
    }
    const std::uint64_t mask =
        bit_count >= 64 ? ~static_cast<std::uint64_t>(0)
                        : ((static_cast<std::uint64_t>(1) << bit_count) - 1);
    const std::uint64_t raw_val =
        (accumulated >> bit_offset) & mask;
    return static_cast<double>(raw_val) * scale;
}

TriggerLogCapture decode(const IniLoggerDefinition& logger,
                         std::span<const std::uint8_t> raw) {
    TriggerLogCapture capture;
    capture.logger_name = logger.name;
    capture.display_name = logger.display_name;
    capture.kind = logger.kind;
    capture.columns.reserve(logger.record_fields.size());
    for (const auto& f : logger.record_fields)
        capture.columns.push_back(f.header);

    const int rec_len = logger.record_len;
    if (rec_len == 0) return capture;

    const std::size_t header_len =
        static_cast<std::size_t>(logger.record_header_len);
    const int count = logger.record_count;
    capture.rows.reserve(count > 0 ? static_cast<std::size_t>(count) : 0);

    for (int i = 0; i < count; ++i) {
        const std::size_t start =
            header_len + static_cast<std::size_t>(i) *
                             static_cast<std::size_t>(rec_len);
        const std::size_t end = start + static_cast<std::size_t>(rec_len);
        if (end > raw.size()) break;  // truncated buffer
        std::span<const std::uint8_t> record_bytes(raw.data() + start,
                                                   static_cast<std::size_t>(rec_len));
        TriggerLogRow row;
        for (const auto& field_def : logger.record_fields) {
            row.values[field_def.header] =
                extract_field(record_bytes, field_def);
        }
        capture.rows.push_back(std::move(row));
    }

    return capture;
}

}  // namespace tuner_core::live_trigger_logger
