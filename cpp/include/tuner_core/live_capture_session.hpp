// SPDX-License-Identifier: MIT
//
// tuner_core::live_capture_session — pure-logic port of the
// formatting / status / column-ordering surface of
// `LiveCaptureSessionService` (`src/tuner/services/live_capture_session_service.py`).
//
// The Python service is half pure-logic (status text, ordered column
// names, CSV emission, format-digits lookup) and half I/O (file open /
// stream-write / close lifecycle). This module owns only the pure
// half — the I/O lifecycle stays in Python where Qt timers and the
// `QFileDialog`-driven output path live.
//
// Functions in this module:
//   - `status_text`              : compose the human-readable session status
//   - `ordered_column_names`     : profile-first then record-insertion fallback
//   - `format_value`             : per-cell value formatter (digits or repr)
//   - `format_csv`               : full captured-rows -> CSV string
// All four are pure functions; no globals, no mutable state.

#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace tuner_core::live_capture_session {

// One captured record as the C++ side sees it. Mirrors the Python
// `DataLogRecord` shape (timestamp + values dict) but with the
// timestamp pre-resolved to milliseconds-from-session-start so the
// pure formatter does not need a clock dependency.
struct CapturedRecord {
    double elapsed_ms = 0.0;
    // Insertion-ordered keys + parallel values, mirroring Python
    // dict's preserved insertion order. Used for both CSV emission
    // and `ordered_column_names` fallback.
    std::vector<std::string> keys;
    std::vector<double> values;
};

// Compose the status string the workspace shows beside the live
// capture controls. Mirrors `CaptureSessionStatus.status_text`:
//   recording               -> "Recording: N rows (E.Es)"
//   not recording, rows > 0 -> "Stopped — N rows captured (E.Es)"  (em dash)
//   else                    -> "Ready"
std::string status_text(bool recording, std::size_t row_count,
                        double elapsed_seconds);

// Build the ordered column-name list. If `profile_channel_names` is
// non-empty, those names lead and any extra names seen in the records
// are appended in record-insertion order. If empty, the result is
// just the union of record keys in insertion order.
std::vector<std::string> ordered_column_names(
    const std::vector<std::string>& profile_channel_names,
    const std::vector<CapturedRecord>& records);

// Format a single value the way the Python service does:
//   digits >= 0 -> Python's `f"{value:.{digits}f}"`
//   digits <  0 -> Python's `str(value)` (shortest round-trip repr)
std::string format_value(double value, int digits);

// Render the captured rows as a CSV string. Header row is
// `Time_ms,col1,col2,...`. Each data row is the elapsed-ms (rounded
// to integer) plus per-column values formatted via `format_value`.
// Missing values render as the empty string. Line terminator is
// `\r\n` to match Python's `csv` module default. Returns the empty
// string when `records` is empty (mirrors the Python early-return).
//
// `format_digits` maps column name -> digits. A column missing from
// the map (or mapped to a negative value) means "use repr".
std::string format_csv(
    const std::vector<CapturedRecord>& records,
    const std::vector<std::string>& columns,
    const std::unordered_map<std::string, int>& format_digits);

}  // namespace tuner_core::live_capture_session
