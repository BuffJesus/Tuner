// SPDX-License-Identifier: MIT
//
// tuner_core::datalog_review implementation. Pure logic.

#include "tuner_core/datalog_review.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <stdexcept>
#include <unordered_set>

namespace tuner_core::datalog_review {

namespace {

// Mirror of Python `_PRIORITY_CHANNELS`.
const std::vector<std::string>& priority_channels() {
    static const std::vector<std::string> table = {
        "rpm", "map", "tps", "afr", "lambda", "advance", "pw", "ego",
    };
    return table;
}

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

bool record_has(const Record& rec, const std::string& name) {
    for (const auto& [k, _] : rec.values) {
        if (k == name) return true;
    }
    return false;
}

double record_get(const Record& rec, const std::string& name) {
    for (const auto& [k, v] : rec.values) {
        if (k == name) return v;
    }
    return 0.0;  // unreachable in build() — guarded by record_has
}

std::vector<std::string> select_channels(
    const std::vector<Record>& records,
    const Profile* profile)
{
    // Collect all channel names in insertion order across the log.
    std::vector<std::string> available;
    std::unordered_set<std::string> seen;
    for (const auto& rec : records) {
        for (const auto& [name, _] : rec.values) {
            if (seen.insert(name).second) {
                available.push_back(name);
            }
        }
    }

    // Profile path: prefer enabled channels in their declared order.
    if (profile != nullptr) {
        std::vector<std::string> selected;
        for (const auto& name : profile->enabled_channels) {
            if (seen.find(name) != seen.end()) {
                // Skip duplicates (the Python set membership check
                // also dedupes implicitly via list iteration).
                bool already = false;
                for (const auto& s : selected) {
                    if (s == name) { already = true; break; }
                }
                if (!already) selected.push_back(name);
            }
            if (selected.size() >= 3) return selected;
        }
        if (!selected.empty()) return selected;
        // Fall through to the heuristic.
    }

    // Heuristic: pick by priority then fill from available order.
    std::vector<std::string> selected;
    // Build a lowercased→canonical map (insertion order doesn't
    // matter here — only the lookup result matters).
    std::vector<std::pair<std::string, std::string>> lowered;
    lowered.reserve(available.size());
    for (const auto& name : available) {
        lowered.emplace_back(lowercase(name), name);
    }
    auto find_actual = [&](const std::string& key) -> const std::string* {
        for (const auto& [low, actual] : lowered) {
            if (low == key) return &actual;
        }
        return nullptr;
    };

    for (const auto& key : priority_channels()) {
        const std::string* actual = find_actual(key);
        if (actual != nullptr) {
            bool already = false;
            for (const auto& s : selected) {
                if (s == *actual) { already = true; break; }
            }
            if (!already) selected.push_back(*actual);
        }
        if (selected.size() >= 3) return selected;
    }
    for (const auto& name : available) {
        bool already = false;
        for (const auto& s : selected) {
            if (s == name) { already = true; break; }
        }
        if (!already) selected.push_back(name);
        if (selected.size() >= 3) break;
    }
    return selected;
}

std::string format_summary(std::size_t trace_count, std::size_t row_count,
                           std::size_t selected_index, double marker_x) {
    char buf[160];
    std::snprintf(buf, sizeof(buf),
        "Datalog review shows %zu trace(s) across %zu row(s). "
        "Selected replay row %zu is at +%.3fs.",
        trace_count, row_count, selected_index + 1, marker_x);
    return buf;
}

}  // namespace

Snapshot build(
    const std::vector<Record>& records,
    std::size_t selected_index,
    const Profile* profile)
{
    if (records.empty()) {
        throw std::invalid_argument("Datalog is empty.");
    }
    std::size_t bounded_index = selected_index;
    if (bounded_index >= records.size()) {
        bounded_index = records.size() - 1;
    }

    const double base_time = records.front().timestamp_seconds;
    const auto channel_names = select_channels(records, profile);

    std::vector<TraceSnapshot> traces;
    traces.reserve(channel_names.size());
    for (const auto& channel_name : channel_names) {
        TraceSnapshot trace;
        trace.name = channel_name;
        for (const auto& rec : records) {
            if (!record_has(rec, channel_name)) continue;
            trace.x_values.push_back(rec.timestamp_seconds - base_time);
            trace.y_values.push_back(record_get(rec, channel_name));
        }
        if (!trace.x_values.empty()) {
            traces.push_back(std::move(trace));
        }
    }

    const double marker_x = records[bounded_index].timestamp_seconds - base_time;

    Snapshot out;
    out.summary_text = format_summary(traces.size(), records.size(), bounded_index, marker_x);
    out.selected_index = bounded_index;
    out.marker_x = marker_x;
    out.traces = std::move(traces);
    return out;
}

}  // namespace tuner_core::datalog_review
