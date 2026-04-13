// SPDX-License-Identifier: MIT
//
// tuner_core::trigger_log_visualization — port of
// TriggerLogVisualizationService.  Sub-slice 61 of Phase 14 Slice 4.
//
// Builds visualization traces and edge/gap annotations from trigger
// log data (rows of named columns).  Pure logic, no file I/O.

#pragma once

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::trigger_log_visualization {

struct Trace {
    std::string name;
    std::vector<double> x_values;
    std::vector<double> y_values;
    double offset = 0;
    bool is_digital = false;
};

struct Annotation {
    double time_ms = 0;
    std::string label;
    std::string severity;
};

struct Snapshot {
    int trace_count = 0;
    int point_count = 0;
    std::string summary_text;
    std::vector<Trace> traces;
    std::vector<Annotation> annotations;
};

// Row: vector of (column_name, value_string) pairs — preserves column order.
struct Row {
    std::vector<std::pair<std::string, std::string>> fields;
    std::string get(const std::string& col) const {
        for (const auto& [k, v] : fields) if (k == col) return v;
        return {};
    }
};

/// Build visualization from pre-parsed rows and column names.
Snapshot build_from_rows(
    const std::vector<Row>& rows,
    const std::vector<std::string>& columns);

}  // namespace tuner_core::trigger_log_visualization
