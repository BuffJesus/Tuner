// SPDX-License-Identifier: MIT
//
// tuner_core::operation_log — port of `OperationLogService`.
// Twenty-fourth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Session-level append-only mutation log. Tracks every staged /
// reverted / written / burned change so the operator can see what
// happened, when, and in what direction. Mirrors the Python service
// field-for-field except for the timestamp source — the C++ side
// uses `std::chrono::system_clock::now()` by default but the test
// surface lets the caller inject a fixed timestamp for parity.

#pragma once

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::operation_log {

enum class OperationKind {
    STAGED,
    REVERTED,
    WRITTEN,
    BURNED,
};

// Mirror the Python `OperationKind.value` strings.
std::string_view to_string(OperationKind kind) noexcept;

// Hours/minutes/seconds since midnight, used by `summary_line` for
// the `HH:MM:SS` prefix. Carrying the components instead of a real
// chrono timestamp keeps the C++ side parity-testable without
// depending on `std::chrono::current_zone()` (which is not available
// on all toolchains we target).
struct TimeOfDay {
    int hours = 0;
    int minutes = 0;
    int seconds = 0;
};

struct OperationEntry {
    OperationKind kind = OperationKind::STAGED;
    std::string parameter_name;
    std::string old_value;
    std::string new_value;
    TimeOfDay timestamp;
    std::string page_title;

    // Mirror `OperationEntry.summary_line`.
    std::string summary_line() const;
};

class OperationLog {
public:
    OperationLog() = default;

    // Each `record_*` method appends an entry. The `timestamp`
    // argument lets the caller inject a fixed time for parity tests;
    // production callers can pass the wall-clock equivalent.
    void record_staged(
        std::string parameter_name,
        std::string old_value,
        std::string new_value,
        TimeOfDay timestamp,
        std::string page_title = "");

    void record_reverted(
        std::string parameter_name,
        std::string old_value,
        std::string new_value,
        TimeOfDay timestamp,
        std::string page_title = "");

    void record_written(
        std::string parameter_name,
        std::string value,
        TimeOfDay timestamp,
        std::string page_title = "");

    void record_burned(
        std::string parameter_name,
        std::string value,
        TimeOfDay timestamp,
        std::string page_title = "");

    const std::vector<OperationEntry>& entries() const noexcept { return entries_; }

    // Mirror `recent(n)`: last `n` entries (or all if fewer).
    std::vector<OperationEntry> recent(std::size_t n = 50) const;

    void clear() noexcept { entries_.clear(); }

    // Mirror `summary_text(n)`: most recent first, joined with newlines.
    // Returns the documented empty-state message when there are no entries.
    std::string summary_text(std::size_t n = 50) const;

private:
    std::vector<OperationEntry> entries_;
};

}  // namespace tuner_core::operation_log
