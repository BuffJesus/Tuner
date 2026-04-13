// SPDX-License-Identifier: MIT
//
// tuner_core::table_replay_hit implementation. Pure logic.

#include "tuner_core/table_replay_hit.hpp"

#include "tuner_core/wue_analyze_helpers.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <span>
#include <string>

namespace tuner_core::table_replay_hit {

namespace {

namespace wah = tuner_core::wue_analyze_helpers;

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

bool contains(std::string_view haystack, std::string_view needle) noexcept {
    return haystack.find(needle) != std::string_view::npos;
}

// Same hint table as `table_replay_context` — kept inline so this
// slice is independent of the context service header.
struct AxisHint {
    const char* axis_token;
    std::array<const char*, 3> channel_names;
};

constexpr std::array<AxisHint, 10> kAxisHints{{
    {"rpm",      {"rpm", nullptr, nullptr}},
    {"map",      {"map", nullptr, nullptr}},
    {"load",     {"map", "tps", nullptr}},
    {"kpa",      {"map", nullptr, nullptr}},
    {"tps",      {"tps", nullptr, nullptr}},
    {"throttle", {"tps", nullptr, nullptr}},
    {"afr",      {"afr", "lambda", nullptr}},
    {"lambda",   {"lambda", "afr", nullptr}},
    {"spark",    {"advance", nullptr, nullptr}},
    {"advance",  {"advance", nullptr, nullptr}},
}};

std::vector<std::string> axis_candidates(
    const std::optional<std::string>& axis_name) {
    if (!axis_name.has_value() || axis_name->empty()) return {};
    std::string normalized = lowercase(*axis_name);
    std::vector<std::string> out;
    for (const auto& hint : kAxisHints) {
        if (contains(normalized, hint.axis_token)) {
            for (const auto* ch : hint.channel_names) {
                if (ch == nullptr) break;
                std::string s(ch);
                if (std::find(out.begin(), out.end(), s) == out.end()) {
                    out.push_back(std::move(s));
                }
            }
        }
    }
    if (out.empty()) out.push_back(normalized);
    return out;
}

std::optional<double> lookup_channel(
    const std::vector<std::pair<std::string, double>>& values,
    const std::vector<std::string>& candidates) {
    for (const auto& candidate : candidates) {
        for (const auto& [name, value] : values) {
            if (contains(lowercase(name), candidate)) return value;
        }
    }
    return std::nullopt;
}

std::optional<double> afr_value(
    const std::vector<std::pair<std::string, double>>& values) {
    for (const auto& [name, value] : values) {
        auto lower = lowercase(name);
        if (contains(lower, "afr")) return value;
        if (contains(lower, "lambda")) return value * 14.7;
    }
    return std::nullopt;
}

std::string fmt_2f(double v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.2f", v);
    return std::string(buf);
}

}  // namespace

std::optional<HitSummarySnapshot> build(
    const TablePageSnapshot& table_snapshot,
    const std::vector<Record>& records,
    const PreRejected& pre_rejected,
    std::size_t max_records) {
    if (records.empty() || table_snapshot.cells.empty()) return std::nullopt;

    auto x_axis = wah::numeric_axis(
        std::span<const std::string>(table_snapshot.x_labels.data(),
                                      table_snapshot.x_labels.size()));
    auto y_axis = wah::numeric_axis(
        std::span<const std::string>(table_snapshot.y_labels.data(),
                                      table_snapshot.y_labels.size()));
    if (x_axis.empty() || y_axis.empty()) return std::nullopt;

    auto x_candidates = axis_candidates(table_snapshot.x_parameter_name);
    auto y_candidates = axis_candidates(table_snapshot.y_parameter_name);

    // Aggregation state — keyed by (row, column) packed into a single
    // 64-bit int for cheap map lookup.
    std::map<std::pair<std::size_t, std::size_t>, std::size_t> counts;
    std::map<std::pair<std::size_t, std::size_t>, double> afr_sums;
    std::map<std::pair<std::size_t, std::size_t>, std::size_t> afr_counts;

    std::size_t rejected_rows = pre_rejected.count;
    std::map<std::string, std::size_t> rejected_reason_counts(pre_rejected.reasons);

    const std::size_t limit = std::min(records.size(), max_records);
    for (std::size_t i = 0; i < limit; ++i) {
        const auto& record = records[i];
        auto x_value = lookup_channel(record.values, x_candidates);
        auto y_value = lookup_channel(record.values, y_candidates);
        if (!x_value.has_value() || !y_value.has_value()) {
            ++rejected_rows;
            ++rejected_reason_counts["unmappable_axes"];
            continue;
        }
        std::size_t col = wah::nearest_index(
            std::span<const double>(x_axis.data(), x_axis.size()), *x_value);
        std::size_t row = wah::nearest_index(
            std::span<const double>(y_axis.data(), y_axis.size()), *y_value);
        auto key = std::make_pair(row, col);
        ++counts[key];
        auto afr = afr_value(record.values);
        if (afr.has_value()) {
            afr_sums[key] += *afr;
            ++afr_counts[key];
        }
    }

    if (counts.empty()) return std::nullopt;

    // Sort cells by hit count descending; keep top 3.
    std::vector<std::pair<std::pair<std::size_t, std::size_t>, std::size_t>> ordered(
        counts.begin(), counts.end());
    std::sort(ordered.begin(), ordered.end(),
              [](const auto& a, const auto& b) { return a.second > b.second; });
    if (ordered.size() > 3) ordered.resize(3);

    HitSummarySnapshot snap;
    for (const auto& [key, hit_count] : ordered) {
        HitCellSnapshot cell;
        cell.row_index = key.first;
        cell.column_index = key.second;
        cell.hit_count = hit_count;
        auto sum_it = afr_sums.find(key);
        auto count_it = afr_counts.find(key);
        if (sum_it != afr_sums.end() && count_it != afr_counts.end() &&
            count_it->second > 0) {
            cell.mean_afr = sum_it->second / static_cast<double>(count_it->second);
        }
        snap.hot_cells.push_back(std::move(cell));
    }

    std::size_t accepted_rows = 0;
    for (const auto& [_, count] : counts) accepted_rows += count;
    snap.accepted_row_count = accepted_rows;
    snap.rejected_row_count = rejected_rows;

    snap.summary_text =
        "Replay hit summary found " + std::to_string(accepted_rows) +
        " mappable row(s) across " + std::to_string(counts.size()) +
        " table cell(s); " + std::to_string(rejected_rows) +
        " row(s) could not be mapped.";

    snap.detail_text = snap.summary_text;
    for (const auto& cell : snap.hot_cells) {
        snap.detail_text += " Hot cell row " + std::to_string(cell.row_index + 1) +
                            ", column " + std::to_string(cell.column_index + 1) +
                            ": " + std::to_string(cell.hit_count) + " hit(s)";
        if (cell.mean_afr.has_value()) {
            snap.detail_text += ", mean AFR " + fmt_2f(*cell.mean_afr) + ".";
        } else {
            snap.detail_text += ".";
        }
    }
    if (!rejected_reason_counts.empty()) {
        snap.detail_text += " Rejections: ";
        bool first = true;
        // std::map already iterates in sorted key order — same as Python's
        // `sorted(rejected_reason_counts.items())`.
        for (const auto& [reason, count] : rejected_reason_counts) {
            if (!first) snap.detail_text += ", ";
            snap.detail_text += reason + "=" + std::to_string(count);
            first = false;
        }
        snap.detail_text += ".";
    }

    snap.rejected_reason_counts.assign(
        rejected_reason_counts.begin(), rejected_reason_counts.end());
    return snap;
}

}  // namespace tuner_core::table_replay_hit
