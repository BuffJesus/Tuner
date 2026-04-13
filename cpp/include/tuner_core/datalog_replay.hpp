// SPDX-License-Identifier: MIT
//
// tuner_core::datalog_replay — port of DatalogReplayService.select_row.
// Sub-slice 67 of Phase 14 Slice 4.
//
// Selects a single datalog row and builds a replay selection snapshot
// with summary text, channel preview, and evidence context.  Pure logic.

#pragma once

#include <string>
#include <vector>

namespace tuner_core::datalog_replay {

struct Record {
    std::string timestamp_iso;
    std::vector<std::pair<std::string, double>> values;
};

struct SelectionSnapshot {
    int selected_index = 0;
    int total_rows = 0;
    int channel_count = 0;
    std::string summary_text;
    std::string preview_text;
};

/// Select a row from a datalog and build a replay snapshot.
/// Throws std::invalid_argument if records is empty.
SelectionSnapshot select_row(
    const std::vector<Record>& records,
    int index);

}  // namespace tuner_core::datalog_replay
