// SPDX-License-Identifier: MIT
//
// tuner_core::table_replay_context — port of `TableReplayContextService.build`.
// Twenty-seventh sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// The live operating-point crosshair locator. Given a table page
// snapshot (axis labels + cell grid + axis parameter names) and a
// runtime channel snapshot, finds the nearest cell to the live
// operating point and produces a `Snapshot` with row/column index,
// matched axis values, and a human-readable summary.
//
// This is the load-bearing logic for the redesigned Tune tab's
// live crosshair overlay called out in the UI/UX modernization plan.
// Reuses `wue_analyze_helpers::nearest_index` and `numeric_axis` so
// the C++ side has one canonical axis-snap implementation.

#pragma once

#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace tuner_core::table_replay_context {

// Minimal table page snapshot — only the fields the locator reads.
struct TablePageSnapshot {
    std::optional<std::string> x_parameter_name;
    std::optional<std::string> y_parameter_name;
    std::vector<std::string> x_labels;   // string axis labels (parsed to float)
    std::vector<std::string> y_labels;
    // Row-major cell grid; cells are pre-formatted strings.
    std::vector<std::vector<std::string>> cells;
};

// One runtime channel from the evidence snapshot.
struct RuntimeChannel {
    std::string name;
    double value = 0.0;
};

struct Snapshot {
    std::string summary_text;
    std::string detail_text;
    std::size_t row_index = 0;
    std::size_t column_index = 0;
    double x_value = 0.0;
    double y_value = 0.0;
    std::optional<std::string> cell_value_text;
};

// Mirror `TableReplayContextService.build`. Returns nullopt when:
//   - the table snapshot has no cells
//   - either axis parameter is missing or has no matching channel
//   - either axis label list isn't fully numeric
std::optional<Snapshot> build(
    const TablePageSnapshot& table_snapshot,
    const std::vector<RuntimeChannel>& runtime_channels);

}  // namespace tuner_core::table_replay_context
