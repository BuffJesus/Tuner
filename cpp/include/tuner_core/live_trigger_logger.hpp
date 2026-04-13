// SPDX-License-Identifier: MIT
//
// tuner_core::live_trigger_logger — port of the pure-logic decode path
// of `LiveTriggerLoggerService` (Python). Decodes raw binary buffers
// returned by the live tooth/composite trigger loggers into named-
// column rows compatible with the existing trigger-log analysis
// pipeline.
//
// Drives the bit-level field extraction off the same
// `IniLoggerDefinition` parsed by `ini_logger_definition_parser.hpp`,
// so the decode shape is INI-driven (no hard-coded byte layouts).
//
// Tooth records: 4-byte u32 LE inter-tooth time in microseconds.
//   Column: ToothTime
//
// Composite records: 5 bytes:
//   Byte 0 bits: priLevel(0), secLevel(1), ThirdLevel(2),
//                trigger(3), sync(4), cycle(5)
//   Bytes 1-4:   refTime (u32 LE), scale 0.001 -> milliseconds
//   Columns: PriLevel, SecLevel, ThirdLevel, Trigger, Sync, Cycle, RefTime
//
// I/O — tempfile-write of the captured rows to CSV — stays in Python.
// This module owns only the byte -> typed-row decoder.

#pragma once

#include "tuner_core/ini_logger_definition_parser.hpp"

#include <cstdint>
#include <span>
#include <string>
#include <unordered_map>
#include <vector>

namespace tuner_core::live_trigger_logger {

// One decoded record. `values` is keyed by the `header` column name from
// the matching `IniLoggerRecordField` (matches the Python service's
// `dict[str, float]` row shape exactly).
struct TriggerLogRow {
    std::unordered_map<std::string, double> values;
};

struct TriggerLogCapture {
    std::string logger_name;
    std::string display_name;
    std::string kind;  // "tooth" / "composite" / etc.
    std::vector<std::string> columns;  // header names, in record-field order
    std::vector<TriggerLogRow> rows;

    std::size_t record_count() const noexcept { return rows.size(); }
};

// Extract a single field value from a record byte slice. Mirrors the
// Python `_extract_field` helper:
//   - bit_count == 1: single-bit flag at start_bit
//   - bit_count == 32: u32 LE at byte (start_bit / 8)
//   - else: generic bit-window extraction across bytes
// Out-of-range reads return 0.0 (matches the Python defensive default).
double extract_field(std::span<const std::uint8_t> record,
                     const IniLoggerRecordField& field_def);

// Decode a raw logger buffer according to *logger*'s record fields.
// Iterates `logger.record_count` records of length `logger.record_len`
// bytes (after `logger.record_header_len` bytes of leading header).
// Stops short if the buffer truncates mid-record. `record_len == 0`
// returns an empty capture.
TriggerLogCapture decode(const IniLoggerDefinition& logger,
                         std::span<const std::uint8_t> raw);

}  // namespace tuner_core::live_trigger_logger
