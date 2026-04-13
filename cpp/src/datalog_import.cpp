// SPDX-License-Identifier: MIT
#include "tuner_core/datalog_import.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>

namespace tuner_core::datalog_import {

namespace {

const std::set<std::string> TIME_MS = {"timems", "time_ms", "timestampms", "timestamp_ms"};
const std::set<std::string> TIME_S = {"time", "time_s", "times", "sec", "secs", "second", "seconds", "timestamp"};

std::string normalize(const std::string& s) {
    std::string r;
    for (char c : s) {
        if (c == ' ' || c == '-') r += '_';
        else r += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return r;
}

std::optional<double> parse_float(const std::string& s) {
    if (s.empty()) return std::nullopt;
    try {
        size_t pos;
        double v = std::stod(s, &pos);
        // Accept partial parses too (e.g. trailing whitespace).
        return v;
    } catch (...) { return std::nullopt; }
}

std::string detect_time_field(const std::vector<std::string>& headers) {
    for (const auto& h : headers) {
        std::string norm = normalize(h);
        if (TIME_MS.count(norm) || TIME_S.count(norm)) return h;
    }
    return {};
}

bool is_time_ms(const std::string& field) {
    return TIME_MS.count(normalize(field)) > 0;
}

std::string get_value(const CsvRow& row, const std::string& col) {
    for (const auto& [k, v] : row) if (k == col) return v;
    return {};
}

}  // namespace

ImportSnapshot import_rows(
    const std::vector<std::string>& headers,
    const std::vector<CsvRow>& rows,
    const std::string& source_name)
{
    std::string time_field = detect_time_field(headers);
    bool time_is_ms = !time_field.empty() && is_time_ms(time_field);

    std::vector<Record> records;
    std::vector<std::string> channel_names;
    std::set<std::string> seen_channels;

    for (size_t row_idx = 0; row_idx < rows.size(); ++row_idx) {
        const auto& row = rows[row_idx];
        double timestamp = static_cast<double>(row_idx);  // fallback: row index

        if (!time_field.empty()) {
            auto raw = get_value(row, time_field);
            auto parsed = parse_float(raw);
            if (parsed) {
                timestamp = time_is_ms ? (*parsed / 1000.0) : *parsed;
            }
        }

        Record rec;
        rec.timestamp_seconds = timestamp;
        for (const auto& h : headers) {
            if (h == time_field) continue;
            auto raw = get_value(row, h);
            auto val = parse_float(raw);
            if (!val) continue;
            rec.values[h] = *val;
            if (!seen_channels.count(h)) {
                seen_channels.insert(h);
                channel_names.push_back(h);
            }
        }
        if (!rec.values.empty())
            records.push_back(std::move(rec));
    }

    if (records.empty())
        throw std::invalid_argument("CSV did not contain any numeric replay rows.");

    // Summary.
    char summary[512];
    std::string ch_list;
    int lim = std::min(static_cast<int>(channel_names.size()), 8);
    for (int i = 0; i < lim; ++i) {
        if (i > 0) ch_list += ", ";
        ch_list += channel_names[i];
    }
    if (channel_names.size() > 8) ch_list += "...";
    std::snprintf(summary, sizeof(summary),
        "Imported %d datalog row(s) from %s. Channels: %s.",
        static_cast<int>(records.size()), source_name.c_str(), ch_list.c_str());

    // Preview.
    std::string preview = summary;
    int preview_lim = std::min(static_cast<int>(records.size()), 3);
    for (int i = 0; i < preview_lim; ++i) {
        preview += "\n";
        char row_buf[256];
        std::string sample;
        int ch_lim = std::min(static_cast<int>(records[i].values.size()), 6);
        int j = 0;
        for (const auto& [name, val] : records[i].values) {
            if (j >= ch_lim) break;
            if (j > 0) sample += ", ";
            char vb[32]; std::snprintf(vb, sizeof(vb), "%s=%g", name.c_str(), val);
            sample += vb;
            ++j;
        }
        std::snprintf(row_buf, sizeof(row_buf), "Row %d: %s", i + 1, sample.c_str());
        preview += row_buf;
    }

    return {static_cast<int>(records.size()), channel_names, std::move(records), summary, preview};
}

}  // namespace tuner_core::datalog_import
