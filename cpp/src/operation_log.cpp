// SPDX-License-Identifier: MIT
//
// tuner_core::operation_log implementation. Pure logic — direct port
// of `OperationLogService`.

#include "tuner_core/operation_log.hpp"

#include <algorithm>
#include <cstdio>

namespace tuner_core::operation_log {

namespace {

// UTF-8 byte sequences for the arrow characters the Python service
// uses in its summary line. Preserving these byte-for-byte means the
// rendered output is identical between Python and C++.
constexpr const char* kRightArrow = "\xe2\x86\x92";  // U+2192 →
constexpr const char* kLeftArrow  = "\xe2\x86\x90";  // U+2190 ←

std::string format_time(const TimeOfDay& t) {
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%02d:%02d:%02d",
                  t.hours, t.minutes, t.seconds);
    return std::string(buf);
}

}  // namespace

std::string_view to_string(OperationKind kind) noexcept {
    switch (kind) {
        case OperationKind::STAGED:   return "staged";
        case OperationKind::REVERTED: return "reverted";
        case OperationKind::WRITTEN:  return "written";
        case OperationKind::BURNED:   return "burned";
    }
    return "";
}

std::string OperationEntry::summary_line() const {
    std::string ts = format_time(timestamp);
    switch (kind) {
        case OperationKind::STAGED:
            return ts + "  staged   " + parameter_name + ": " +
                   old_value + " " + kRightArrow + " " + new_value;
        case OperationKind::REVERTED:
            return ts + "  reverted " + parameter_name + ": " +
                   new_value + " " + kLeftArrow + " " + old_value;
        case OperationKind::WRITTEN:
            return ts + "  written  " + parameter_name + " = " + new_value;
        case OperationKind::BURNED:
            return ts + "  burned   " + parameter_name + " = " + new_value;
    }
    return ts + "  " + std::string(to_string(kind)) + " " + parameter_name;
}

void OperationLog::record_staged(
    std::string parameter_name,
    std::string old_value,
    std::string new_value,
    TimeOfDay timestamp,
    std::string page_title) {
    OperationEntry e;
    e.kind = OperationKind::STAGED;
    e.parameter_name = std::move(parameter_name);
    e.old_value = std::move(old_value);
    e.new_value = std::move(new_value);
    e.timestamp = timestamp;
    e.page_title = std::move(page_title);
    entries_.push_back(std::move(e));
}

void OperationLog::record_reverted(
    std::string parameter_name,
    std::string old_value,
    std::string new_value,
    TimeOfDay timestamp,
    std::string page_title) {
    OperationEntry e;
    e.kind = OperationKind::REVERTED;
    e.parameter_name = std::move(parameter_name);
    e.old_value = std::move(old_value);
    e.new_value = std::move(new_value);
    e.timestamp = timestamp;
    e.page_title = std::move(page_title);
    entries_.push_back(std::move(e));
}

void OperationLog::record_written(
    std::string parameter_name,
    std::string value,
    TimeOfDay timestamp,
    std::string page_title) {
    OperationEntry e;
    e.kind = OperationKind::WRITTEN;
    e.parameter_name = std::move(parameter_name);
    // Mirror Python: written entries store the same value in old_value
    // and new_value so the summary line can read either.
    e.old_value = value;
    e.new_value = std::move(value);
    e.timestamp = timestamp;
    e.page_title = std::move(page_title);
    entries_.push_back(std::move(e));
}

void OperationLog::record_burned(
    std::string parameter_name,
    std::string value,
    TimeOfDay timestamp,
    std::string page_title) {
    OperationEntry e;
    e.kind = OperationKind::BURNED;
    e.parameter_name = std::move(parameter_name);
    e.old_value = value;
    e.new_value = std::move(value);
    e.timestamp = timestamp;
    e.page_title = std::move(page_title);
    entries_.push_back(std::move(e));
}

std::vector<OperationEntry> OperationLog::recent(std::size_t n) const {
    if (n >= entries_.size()) return entries_;
    return std::vector<OperationEntry>(entries_.end() - n, entries_.end());
}

std::string OperationLog::summary_text(std::size_t n) const {
    auto recent_entries = recent(n);
    if (recent_entries.empty()) {
        return "No operations recorded this session.";
    }
    // Mirror Python `reversed(recent)` — most recent first.
    std::string out;
    for (auto it = recent_entries.rbegin(); it != recent_entries.rend(); ++it) {
        if (!out.empty()) out += "\n";
        out += it->summary_line();
    }
    return out;
}

}  // namespace tuner_core::operation_log
