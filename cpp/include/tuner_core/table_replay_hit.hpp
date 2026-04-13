// SPDX-License-Identifier: MIT
//
// tuner_core::table_replay_hit — port of `TableReplayHitService.build`.
// Twenty-eighth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Aggregates a datalog into table-cell hit counts with optional AFR
// averaging per cell. The result drives the workspace presenter's
// "where has the engine actually been?" overlay — operators use it
// to spot-check whether their VE table edits are landing on cells
// that ever see real load.
//
// **Gating decoupled from aggregation:** the Python service composes
// `ReplaySampleGateService` for sample rejection. The C++ port
// pushes that responsibility back to the caller — pass the records
// pre-filtered, plus an optional pre-rejected count and per-reason
// rejection map. The aggregator merges those into the final summary
// alongside its own `unmappable_axes` rejections.

#pragma once

#include "tuner_core/table_replay_context.hpp"

#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace tuner_core::table_replay_hit {

using table_replay_context::TablePageSnapshot;

struct Record {
    // Same insertion-order map shape used elsewhere in the workspace
    // layer (datalog records preserve channel ordering across the FFI).
    std::vector<std::pair<std::string, double>> values;
};

struct HitCellSnapshot {
    std::size_t row_index = 0;
    std::size_t column_index = 0;
    std::size_t hit_count = 0;
    std::optional<double> mean_afr;
};

struct HitSummarySnapshot {
    std::string summary_text;
    std::string detail_text;
    std::vector<HitCellSnapshot> hot_cells;
    std::size_t accepted_row_count = 0;
    std::size_t rejected_row_count = 0;
    // Sorted by reason name for deterministic output, mirroring
    // Python `sorted(rejected_reason_counts.items())`.
    std::vector<std::pair<std::string, std::size_t>> rejected_reason_counts;
};

// Caller-supplied accumulators for gating that happens upstream.
// `count` is the number of records the caller already rejected;
// `reasons` is a per-reason rejection histogram. Both are merged
// into the final summary.
struct PreRejected {
    std::size_t count = 0;
    std::map<std::string, std::size_t> reasons;
};

// Mirror `TableReplayHitService.build`. Returns nullopt for empty
// inputs / non-numeric axes / no surviving accepted records.
std::optional<HitSummarySnapshot> build(
    const TablePageSnapshot& table_snapshot,
    const std::vector<Record>& records,
    const PreRejected& pre_rejected = {},
    std::size_t max_records = 50'000);

}  // namespace tuner_core::table_replay_hit
