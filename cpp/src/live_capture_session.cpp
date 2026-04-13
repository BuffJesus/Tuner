// SPDX-License-Identifier: MIT
//
// Implementation of `live_capture_session.hpp`. Direct port of the
// pure-logic helpers in `LiveCaptureSessionService`.

#include "tuner_core/live_capture_session.hpp"

#include "tuner_core/tune_value_preview.hpp"

#include <cmath>
#include <cstdio>
#include <unordered_set>

namespace tuner_core::live_capture_session {

std::string status_text(bool recording, std::size_t row_count,
                        double elapsed_seconds) {
    char buf[96];
    if (recording) {
        std::snprintf(buf, sizeof(buf),
                      "Recording: %zu rows (%.1fs)",
                      row_count, elapsed_seconds);
        return buf;
    }
    if (row_count > 0) {
        // Em dash U+2014 == 0xE2 0x80 0x94 in UTF-8.
        std::snprintf(buf, sizeof(buf),
                      "Stopped \xe2\x80\x94 %zu rows captured (%.1fs)",
                      row_count, elapsed_seconds);
        return buf;
    }
    return "Ready";
}

std::vector<std::string> ordered_column_names(
    const std::vector<std::string>& profile_channel_names,
    const std::vector<CapturedRecord>& records) {
    std::vector<std::string> ordered;
    std::unordered_set<std::string> seen;
    if (!profile_channel_names.empty()) {
        for (const auto& name : profile_channel_names) {
            if (seen.insert(name).second) ordered.push_back(name);
        }
    }
    for (const auto& rec : records) {
        for (const auto& key : rec.keys) {
            if (seen.insert(key).second) ordered.push_back(key);
        }
    }
    return ordered;
}

std::string format_value(double value, int digits) {
    if (digits >= 0) {
        char buf[64];
        std::snprintf(buf, sizeof(buf), "%.*f", digits, value);
        return buf;
    }
    return tune_value_preview::format_scalar_python_repr(value);
}

namespace {

const double* find_value(const CapturedRecord& rec,
                         const std::string& key) {
    for (std::size_t i = 0; i < rec.keys.size(); ++i) {
        if (rec.keys[i] == key) return &rec.values[i];
    }
    return nullptr;
}

int digits_for(const std::unordered_map<std::string, int>& format_digits,
               const std::string& column) {
    auto it = format_digits.find(column);
    if (it == format_digits.end()) return -1;
    return it->second;
}

}  // namespace

std::string format_csv(
    const std::vector<CapturedRecord>& records,
    const std::vector<std::string>& columns,
    const std::unordered_map<std::string, int>& format_digits) {
    if (records.empty()) return "";

    std::string out;
    out.reserve(64 + records.size() * (16 + columns.size() * 8));

    // Header row.
    out += "Time_ms";
    for (const auto& col : columns) {
        out += ',';
        out += col;
    }
    out += "\r\n";

    for (const auto& rec : records) {
        // Time_ms — rounded to integer to mirror Python's `f"{ms:.0f}"`.
        // Python uses banker-friendly fixed-format rounding here; the
        // values are millisecond-scale floats so a plain printf "%.0f"
        // matches in every observed case.
        char tbuf[32];
        std::snprintf(tbuf, sizeof(tbuf), "%.0f", rec.elapsed_ms);
        out += tbuf;

        for (const auto& col : columns) {
            out += ',';
            const double* v = find_value(rec, col);
            if (v == nullptr) continue;  // missing -> empty cell
            out += format_value(*v, digits_for(format_digits, col));
        }
        out += "\r\n";
    }

    return out;
}

}  // namespace tuner_core::live_capture_session
