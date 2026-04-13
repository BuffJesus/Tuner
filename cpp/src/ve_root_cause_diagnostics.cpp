// SPDX-License-Identifier: MIT

#include "tuner_core/ve_root_cause_diagnostics.hpp"

#include <cmath>
#include <cstdio>

namespace tuner_core::ve_root_cause_diagnostics {

namespace {

// Conservative thresholds — preserved verbatim from the Python service.
constexpr int    MIN_PROPOSALS              = 6;
constexpr double UNIFORM_BIAS_THRESHOLD     = 0.05;
constexpr double UNIFORM_BIAS_VARIANCE_MAX  = 0.0025;
constexpr double DEADTIME_REGION_BIAS       = 0.08;
constexpr double OPPOSITE_REGION_BIAS       = 0.05;
constexpr double LOAD_CORRELATION_THRESHOLD = 0.7;

std::vector<std::pair<int, int>> evidence_for(const std::vector<Proposal>& ps) {
    std::vector<std::pair<int, int>> out;
    out.reserve(ps.size());
    for (const auto& p : ps) {
        out.emplace_back(p.row_index, p.col_index);
    }
    return out;
}

// ---- Rule 1: uniform global bias ----
bool check_uniform_global_bias(
    const std::vector<Proposal>& proposals, Diagnostic& out) {
    double sum_cf = 0.0;
    for (const auto& p : proposals) sum_cf += p.correction_factor;
    double mean_cf = sum_cf / static_cast<double>(proposals.size());
    double bias = mean_cf - 1.0;
    if (std::fabs(bias) < UNIFORM_BIAS_THRESHOLD) return false;

    double var = 0.0;
    for (const auto& p : proposals) {
        double d = p.correction_factor - mean_cf;
        var += d * d;
    }
    var /= static_cast<double>(proposals.size());
    if (var > UNIFORM_BIAS_VARIANCE_MAX) return false;

    const char* direction = (bias > 0) ? "lean" : "rich";
    char buf[256];
    std::snprintf(buf, sizeof(buf),
        "All cells biased %s by ~%+.0f%% with low variance "
        "\xe2\x80\x94 re-check injector flow rating and deadtime curve "
        "before staging VE corrections.",
        direction, bias * 100.0);

    out.rule = "injector_flow_error";
    out.severity = "warning";
    out.message = buf;
    out.evidence_cells = evidence_for(proposals);
    return true;
}

// ---- Rule 2: deadtime / low-load bias ----
bool check_deadtime_low_load_bias(
    const std::vector<Proposal>& proposals, Diagnostic& out) {
    if (proposals.empty()) return false;
    int max_row = proposals.front().row_index;
    int max_col = proposals.front().col_index;
    for (const auto& p : proposals) {
        if (p.row_index > max_row) max_row = p.row_index;
        if (p.col_index > max_col) max_col = p.col_index;
    }
    if (max_row < 2 || max_col < 2) return false;
    int row_split = max_row / 2;
    int col_split = max_col / 2;

    std::vector<Proposal> low_region;
    std::vector<Proposal> rest;
    for (const auto& p : proposals) {
        if (p.row_index <= row_split && p.col_index <= col_split) {
            low_region.push_back(p);
        } else {
            rest.push_back(p);
        }
    }
    if (low_region.size() < 2 || rest.size() < 2) return false;

    auto mean_cf = [](const std::vector<Proposal>& v) {
        double s = 0.0;
        for (const auto& p : v) s += p.correction_factor;
        return s / static_cast<double>(v.size());
    };
    double low_bias = mean_cf(low_region) - 1.0;
    double rest_bias = mean_cf(rest) - 1.0;
    if (std::fabs(low_bias) < DEADTIME_REGION_BIAS) return false;
    if (std::fabs(low_bias) - std::fabs(rest_bias) < DEADTIME_REGION_BIAS) {
        return false;
    }

    const char* direction = (low_bias > 0) ? "lean" : "rich";
    char buf[384];
    std::snprintf(buf, sizeof(buf),
        "Low-load / low-rpm cells biased %s by ~%+.0f%% (vs %+.0f%% elsewhere) "
        "\xe2\x80\x94 deadtime characterization is the most likely cause; "
        "re-check the injector deadtime curve before VE edits.",
        direction, low_bias * 100.0, rest_bias * 100.0);

    out.rule = "deadtime_error";
    out.severity = "warning";
    out.message = buf;
    out.evidence_cells = evidence_for(low_region);
    return true;
}

// ---- Rule 3: opposite high vs low load ----
bool check_opposite_high_low_load_bias(
    const std::vector<Proposal>& proposals, Diagnostic& out) {
    if (proposals.empty()) return false;
    int max_row = proposals.front().row_index;
    for (const auto& p : proposals) {
        if (p.row_index > max_row) max_row = p.row_index;
    }
    if (max_row < 2) return false;
    int row_split = max_row / 2;

    std::vector<Proposal> low;
    std::vector<Proposal> high;
    for (const auto& p : proposals) {
        if (p.row_index <= row_split) low.push_back(p);
        else                          high.push_back(p);
    }
    if (low.size() < 2 || high.size() < 2) return false;

    auto mean_cf = [](const std::vector<Proposal>& v) {
        double s = 0.0;
        for (const auto& p : v) s += p.correction_factor;
        return s / static_cast<double>(v.size());
    };
    double low_bias = mean_cf(low) - 1.0;
    double high_bias = mean_cf(high) - 1.0;
    if (std::fabs(low_bias) < OPPOSITE_REGION_BIAS ||
        std::fabs(high_bias) < OPPOSITE_REGION_BIAS) {
        return false;
    }
    if ((low_bias > 0) == (high_bias > 0)) return false;

    char buf[384];
    std::snprintf(buf, sizeof(buf),
        "Low-load region biased %+.0f%% while high-load region biased %+.0f%% "
        "\xe2\x80\x94 opposite directions across the load axis suggest an "
        "AFR/lambda target table problem, not a VE problem.",
        low_bias * 100.0, high_bias * 100.0);

    out.rule = "target_table_error";
    out.severity = "info";
    out.message = buf;
    std::vector<Proposal> combined = low;
    combined.insert(combined.end(), high.begin(), high.end());
    out.evidence_cells = evidence_for(combined);
    return true;
}

// ---- Rule 4: load-axis correlation (Pearson r) ----
bool check_load_axis_correlation(
    const std::vector<Proposal>& proposals, Diagnostic& out) {
    if (proposals.size() < static_cast<size_t>(MIN_PROPOSALS)) return false;
    double n = static_cast<double>(proposals.size());
    double sum_x = 0.0, sum_y = 0.0;
    for (const auto& p : proposals) {
        sum_x += static_cast<double>(p.row_index);
        sum_y += p.correction_factor;
    }
    double mean_x = sum_x / n;
    double mean_y = sum_y / n;

    double cov = 0.0, var_x = 0.0, var_y = 0.0;
    for (const auto& p : proposals) {
        double dx = static_cast<double>(p.row_index) - mean_x;
        double dy = p.correction_factor - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    if (var_x == 0.0 || var_y == 0.0) return false;
    double r = cov / (std::sqrt(var_x) * std::sqrt(var_y));
    if (std::fabs(r) < LOAD_CORRELATION_THRESHOLD) return false;

    char buf[320];
    std::snprintf(buf, sizeof(buf),
        "Correction factor correlates with load axis (Pearson r=%+.2f) "
        "\xe2\x80\x94 MAP/IAT/baro calibration is a more likely explanation "
        "than VE table error; verify sensor scaling before staging VE edits.",
        r);

    out.rule = "sensor_calibration_error";
    out.severity = "info";
    out.message = buf;
    out.evidence_cells = evidence_for(proposals);
    return true;
}

}  // namespace

DiagnosticReport diagnose(const std::vector<Proposal>& proposals) {
    DiagnosticReport report;
    if (static_cast<int>(proposals.size()) < MIN_PROPOSALS) {
        char buf[160];
        std::snprintf(buf, sizeof(buf),
            "Root-cause diagnostics: only %zu proposal(s) "
            "\xe2\x80\x94 need \xe2\x89\xa5%d before patterns are reliable.",
            proposals.size(), MIN_PROPOSALS);
        report.summary_text = buf;
        return report;
    }

    Diagnostic d;
    if (check_uniform_global_bias(proposals, d))      { report.diagnostics.push_back(d); d = {}; }
    if (check_deadtime_low_load_bias(proposals, d))   { report.diagnostics.push_back(d); d = {}; }
    if (check_opposite_high_low_load_bias(proposals, d)) { report.diagnostics.push_back(d); d = {}; }
    if (check_load_axis_correlation(proposals, d))    { report.diagnostics.push_back(d); d = {}; }

    if (!report.diagnostics.empty()) {
        std::string rules;
        for (size_t i = 0; i < report.diagnostics.size(); ++i) {
            if (i > 0) rules += ", ";
            rules += report.diagnostics[i].rule;
        }
        char buf[256];
        std::snprintf(buf, sizeof(buf),
            "Root-cause diagnostics: %zu pattern(s) found (%s).",
            report.diagnostics.size(), rules.c_str());
        report.summary_text = buf;
    } else {
        char buf[200];
        std::snprintf(buf, sizeof(buf),
            "Root-cause diagnostics: no systemic patterns found across "
            "%zu proposal(s).",
            proposals.size());
        report.summary_text = buf;
    }
    return report;
}

}  // namespace tuner_core::ve_root_cause_diagnostics
