// SPDX-License-Identifier: MIT
//
// tuner_core::table_replay_context implementation. Pure logic.

#include "tuner_core/table_replay_context.hpp"

#include "tuner_core/wue_analyze_helpers.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <string>

namespace tuner_core::table_replay_context {

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

// Mirror Python `_AXIS_CHANNEL_HINTS`. Each entry maps a substring
// found in the axis parameter name to one or more candidate channel
// name substrings. Walked in declaration order; multiple matching
// hints accumulate (without duplicates).
struct AxisHint {
    const char* axis_token;
    std::array<const char*, 3> channel_names;  // null-terminated
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

std::optional<double> axis_value(
    const std::optional<std::string>& axis_name,
    const std::vector<RuntimeChannel>& channels) {
    if (!axis_name.has_value() || axis_name->empty()) return std::nullopt;
    std::string normalized = lowercase(*axis_name);

    // Build the candidate list per Python: walk hints in order,
    // accumulate matched channels (no duplicates). Empty list →
    // fall back to the normalized axis name itself.
    std::vector<std::string> candidates;
    for (const auto& hint : kAxisHints) {
        if (contains(normalized, hint.axis_token)) {
            for (const auto* ch : hint.channel_names) {
                if (ch == nullptr) break;
                std::string s(ch);
                if (std::find(candidates.begin(), candidates.end(), s) ==
                    candidates.end()) {
                    candidates.push_back(std::move(s));
                }
            }
        }
    }
    if (candidates.empty()) candidates.push_back(normalized);

    // Walk runtime channels in input order; first one whose lowered
    // name contains any candidate substring wins.
    for (const auto& channel : channels) {
        std::string lower_name = lowercase(channel.name);
        for (const auto& candidate : candidates) {
            if (contains(lower_name, candidate)) {
                return channel.value;
            }
        }
    }
    return std::nullopt;
}

std::string fmt_1f(double v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.1f", v);
    return std::string(buf);
}

}  // namespace

std::optional<Snapshot> build(
    const TablePageSnapshot& table_snapshot,
    const std::vector<RuntimeChannel>& runtime_channels) {
    if (table_snapshot.cells.empty()) return std::nullopt;

    auto x_value = axis_value(table_snapshot.x_parameter_name, runtime_channels);
    auto y_value = axis_value(table_snapshot.y_parameter_name, runtime_channels);
    if (!x_value.has_value() || !y_value.has_value()) return std::nullopt;

    auto x_axis = wah::numeric_axis(
        std::span<const std::string>(table_snapshot.x_labels.data(),
                                      table_snapshot.x_labels.size()));
    auto y_axis = wah::numeric_axis(
        std::span<const std::string>(table_snapshot.y_labels.data(),
                                      table_snapshot.y_labels.size()));
    if (x_axis.empty() || y_axis.empty()) return std::nullopt;

    std::size_t column_index = wah::nearest_index(
        std::span<const double>(x_axis.data(), x_axis.size()), *x_value);
    std::size_t row_index = wah::nearest_index(
        std::span<const double>(y_axis.data(), y_axis.size()), *y_value);

    std::optional<std::string> cell_value;
    if (row_index < table_snapshot.cells.size()) {
        const auto& row = table_snapshot.cells[row_index];
        if (column_index < row.size()) {
            cell_value = row[column_index];
        }
    }

    Snapshot snap;
    snap.row_index = row_index;
    snap.column_index = column_index;
    snap.x_value = *x_value;
    snap.y_value = *y_value;
    snap.cell_value_text = cell_value;

    snap.summary_text =
        "Replay position is nearest row " + std::to_string(row_index + 1) +
        ", column " + std::to_string(column_index + 1) + " for this table.";
    snap.detail_text =
        snap.summary_text + "\n" +
        "Axis match: X=" + fmt_1f(*x_value) +
        " near " + fmt_1f(x_axis[column_index]) +
        ", Y=" + fmt_1f(*y_value) +
        " near " + fmt_1f(y_axis[row_index]) + ".";
    if (cell_value.has_value() && !cell_value->empty()) {
        snap.detail_text += " Table cell value: " + *cell_value + ".";
    }
    return snap;
}

}  // namespace tuner_core::table_replay_context
