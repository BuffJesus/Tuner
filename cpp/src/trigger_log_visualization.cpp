// SPDX-License-Identifier: MIT
#include "tuner_core/trigger_log_visualization.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <set>
#include <string>

namespace tuner_core::trigger_log_visualization {

namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

std::string strip(const std::string& s) {
    auto a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return {};
    auto b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

std::string find_time_column(const std::vector<std::string>& columns) {
    for (const auto& col : columns) {
        std::string low = to_lower(strip(col));
        if (low == "time" || low == "timems" || low == "timestamp" ||
            low == "time_ms" || low == "time (ms)" || low.find("time") != std::string::npos)
            return strip(col);
    }
    return {};
}

std::vector<double> time_values(const std::vector<Row>& rows, const std::string& col) {
    std::vector<double> vals;
    for (const auto& row : rows) {
        std::string raw = strip(row.get(col));
        if (raw.empty()) return {};
        try {
            size_t pos = 0;
            double v = std::stod(raw, &pos);
            if (pos != raw.size()) return {};
            vals.push_back(v);
        } catch (...) { return {}; }
    }
    return vals;
}

std::vector<double> numeric_values(const std::vector<Row>& rows, const std::string& col) {
    std::vector<double> vals;
    for (const auto& row : rows) {
        std::string raw = strip(row.get(col));
        if (raw.empty()) return {};
        try {
            size_t pos = 0;
            double v = std::stod(raw, &pos);
            if (pos != raw.size()) return {};
            vals.push_back(v);
        } catch (...) { return {}; }
    }
    return vals;
}

bool is_digital(const std::vector<double>& values) {
    for (double v : values) {
        double r = std::round(v * 1e6) / 1e6;
        if (r != 0.0 && r != 1.0) return false;
    }
    return true;
}

std::vector<Annotation> trace_annotations(
    const std::string& name,
    const std::vector<double>& x,
    const std::vector<double>& y)
{
    if (!is_digital(y)) return {};
    std::string low = to_lower(name);
    bool relevant = false;
    for (const char* tok : {"crank", "cam", "trigger", "sync", "tooth", "composite"}) {
        if (low.find(tok) != std::string::npos) { relevant = true; break; }
    }
    if (!relevant) return {};

    std::vector<Annotation> out;
    int edge_count = 0;
    for (size_t i = 1; i < y.size(); ++i) {
        if (y[i - 1] == y[i]) continue;
        if (++edge_count > 6) break;
        const char* dir = (y[i] > y[i - 1]) ? "rising" : "falling";
        char label[128];
        std::snprintf(label, sizeof(label), "%s %s", name.c_str(), dir);
        out.push_back({x[i], label, "info"});
    }
    return out;
}

std::optional<Annotation> gap_annotation(const std::vector<double>& x) {
    if (x.size() < 6) return std::nullopt;
    std::vector<double> deltas;
    for (size_t i = 1; i < x.size(); ++i) {
        if (x[i] > x[i - 1]) deltas.push_back(x[i] - x[i - 1]);
    }
    if (deltas.size() < 4) return std::nullopt;
    auto sorted = deltas;
    std::sort(sorted.begin(), sorted.end());
    double median = sorted[sorted.size() / 2];
    if (median <= 0.0) return std::nullopt;
    double max_gap = *std::max_element(deltas.begin(), deltas.end());
    if (max_gap < median * 1.6) return std::nullopt;
    // Find position of max gap.
    size_t gap_idx = 0;
    for (size_t i = 0; i < deltas.size(); ++i) {
        if (deltas[i] == max_gap) { gap_idx = i + 1; break; }
    }
    return Annotation{x[gap_idx], "Possible missing-tooth gap", "warning"};
}

}  // namespace

// -----------------------------------------------------------------------
// build_from_rows()
// -----------------------------------------------------------------------

Snapshot build_from_rows(
    const std::vector<Row>& rows,
    const std::vector<std::string>& columns)
{
    std::vector<std::string> normalized;
    for (const auto& col : columns) {
        std::string s = strip(col);
        if (!s.empty()) normalized.push_back(s);
    }

    std::string time_col = find_time_column(normalized);
    if (time_col.empty() || rows.empty()) {
        return {0, 0,
            "Visualization unavailable: the CSV needs a time column and at least one row.",
            {}, {}};
    }

    auto x = time_values(rows, time_col);
    if (x.empty()) {
        return {0, 0,
            "Visualization unavailable: the time column could not be parsed.",
            {}, {}};
    }

    std::vector<Trace> traces;
    std::vector<Annotation> annotations;
    double offset = 0.0;

    for (const auto& col : normalized) {
        if (col == time_col) continue;
        auto y = numeric_values(rows, col);
        if (y.size() != x.size() || y.empty()) continue;

        bool dig = is_digital(y);
        double min_val = *std::min_element(y.begin(), y.end());
        double max_val = *std::max_element(y.begin(), y.end());
        std::vector<double> norm_y(y.size());
        for (size_t i = 0; i < y.size(); ++i) norm_y[i] = (y[i] - min_val) + offset;

        traces.push_back({col, x, norm_y, offset, dig});

        auto ta = trace_annotations(col, x, y);
        annotations.insert(annotations.end(), ta.begin(), ta.end());

        offset += std::max(1.0, (max_val - min_val) + 0.75);
    }

    auto ga = gap_annotation(x);
    if (ga) annotations.push_back(*ga);

    if (traces.empty()) {
        return {0, static_cast<int>(x.size()),
            "Visualization unavailable: no numeric signal columns were found beside the time axis.",
            {}, {}};
    }

    char summary[256];
    if (annotations.empty()) {
        std::snprintf(summary, sizeof(summary),
            "Visualization: %d numeric trace(s) across %d sample(s), no decoder-aware annotations.",
            static_cast<int>(traces.size()), static_cast<int>(x.size()));
    } else {
        std::snprintf(summary, sizeof(summary),
            "Visualization: %d numeric trace(s) across %d sample(s), %d annotation(s).",
            static_cast<int>(traces.size()), static_cast<int>(x.size()),
            static_cast<int>(annotations.size()));
    }
    return {static_cast<int>(traces.size()), static_cast<int>(x.size()),
            summary, std::move(traces), std::move(annotations)};
}

}  // namespace tuner_core::trigger_log_visualization
