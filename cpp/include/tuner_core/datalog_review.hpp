// SPDX-License-Identifier: MIT
//
// tuner_core::datalog_review — port of the Python
// `DatalogReviewService`. Thirty-first sub-slice of the Phase 14
// workspace-services port (Slice 4).
//
// Builds the per-record trace summary that backs the Logging tab's
// review chart: takes a datalog (already parsed into a flat record
// vector), an optional channel-selection profile, and the operator's
// currently-selected row, and produces up to three named traces +
// the marker position for the selected row + a summary text line.
//
// Pure logic, no Qt and no datalog domain types — the caller is
// responsible for flattening `DataLog` / `DatalogProfile` into the
// PODs below. The C++ side carries seconds-from-base timestamps as
// `double` rather than `datetime`, mirroring how the Python service
// already collapses timestamps to deltas in `(t - base_time).total_seconds()`.

#pragma once

#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace tuner_core::datalog_review {

// Single datalog record. `values` is order-preserving (Python dict
// iteration order matches insertion order, and the channel selector
// walks records in that order to discover available channels).
struct Record {
    double timestamp_seconds = 0.0;  // monotonically increasing; base subtracted by build()
    std::vector<std::pair<std::string, double>> values;
};

// Optional profile shell. Only the ordered list of enabled channel
// names is load-bearing for review trace selection.
struct Profile {
    std::vector<std::string> enabled_channels;
};

struct TraceSnapshot {
    std::string name;
    std::vector<double> x_values;  // seconds since first record
    std::vector<double> y_values;
};

struct Snapshot {
    std::string summary_text;
    std::size_t selected_index = 0;
    double marker_x = 0.0;
    std::vector<TraceSnapshot> traces;
};

// Mirrors `DatalogReviewService.build`. Throws `std::invalid_argument`
// when `records` is empty (Python raises `ValueError`).
//
// `profile` may be `nullptr` to fall through to the priority-channel
// heuristic. When supplied, the first up-to-three matching channels
// from `profile->enabled_channels` are used; if none match, the
// heuristic still runs.
Snapshot build(
    const std::vector<Record>& records,
    std::size_t selected_index,
    const Profile* profile = nullptr);

}  // namespace tuner_core::datalog_review
