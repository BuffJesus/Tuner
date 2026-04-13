// SPDX-License-Identifier: MIT
//
// tuner_core::trigger_log_analysis — port of TriggerLogAnalysisService.
// Sub-slice 62 of Phase 14 Slice 4.
//
// Analyzes trigger log CSV data: detects log kind, builds decoder
// context from tune parameters, validates timing, checks missing-tooth
// gaps, and produces operator-facing findings.  Pure logic, no file I/O.

#pragma once

#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::trigger_log_analysis {

struct DecoderContext {
    std::string decoder_name;
    std::string wheel_summary;
    bool sequential_requested = false;
    std::string cam_mode;  // "cam_present", "cam_optional", "crank_only", "unknown"
    std::optional<bool> full_sync;
    std::optional<double> tooth_count;
    std::optional<double> missing_teeth;
};

struct AnalysisSummary {
    std::string log_kind;       // "tooth", "composite", "trigger", "unknown"
    std::string severity;       // "info", "warning"
    int sample_count = 0;
    int channel_count = 0;
    std::optional<double> time_span_ms;
    std::vector<std::string> columns;
    std::string capture_summary_text;
    std::string decoder_summary_text;
    std::string operator_summary_text;
    std::vector<std::string> findings;
    std::string preview_text;
};

// Row: column_name → value_string.
struct Row {
    std::vector<std::pair<std::string, std::string>> fields;
    std::string get(const std::string& col) const {
        for (const auto& [k, v] : fields) if (k == col) return v;
        return {};
    }
};

/// Value getter for tune parameters — returns numeric value by name.
using TuneValueGetter = std::function<std::optional<double>(const std::string&)>;

/// Build a decoder context from tune/definition/runtime state.
DecoderContext build_decoder_context(
    TuneValueGetter get_value,
    std::optional<double> runtime_status_a = std::nullopt,
    std::optional<double> rsa_full_sync = std::nullopt);

/// Analyze trigger log rows.
AnalysisSummary analyze_rows(
    const std::vector<Row>& rows,
    const std::vector<std::string>& columns,
    const DecoderContext& decoder);

}  // namespace tuner_core::trigger_log_analysis
