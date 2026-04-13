// SPDX-License-Identifier: MIT
//
// tuner_core::ve_analyze_accumulator — port of VeAnalyzeCellHitAccumulator.
// Sub-slice 72 of Phase 14 Slice 4.
//
// Stateful accumulator for VE analyze. Accepts records one at a time,
// maps each to a table cell via RPM/load axis lookup, extracts lambda,
// resolves the target, computes correction factors, and produces
// snapshots via the already-ported ve_cell_hit_accumulator::build_snapshot.

#pragma once

#include "ve_cell_hit_accumulator.hpp"
#include "table_replay_context.hpp"

#include <map>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::ve_analyze_accumulator {

using ve_cell_hit_accumulator::CellAccumulation;
using ve_cell_hit_accumulator::CorrectionSample;
using ve_cell_hit_accumulator::Snapshot;

// -----------------------------------------------------------------------
// Table snapshot (minimal: axis labels + cells + param names)
// -----------------------------------------------------------------------

struct TableSnapshot {
    std::string x_param_name;    // e.g. "rpmBins"
    std::string y_param_name;    // e.g. "mapBins"
    std::vector<std::string> x_labels;
    std::vector<std::string> y_labels;
    std::vector<std::vector<std::string>> cells;  // row-major
};

// -----------------------------------------------------------------------
// Record
// -----------------------------------------------------------------------

struct Record {
    std::map<std::string, double> values;
    double timestamp_seconds = 0;
};

// -----------------------------------------------------------------------
// Accumulator
// -----------------------------------------------------------------------

class Accumulator {
public:
    /// Feed one record. Returns true if accepted into a cell.
    bool add_record(
        const Record& record,
        const TableSnapshot& ve_table,
        double lambda_target = 1.0);

    /// Build a snapshot without clearing state.
    Snapshot snapshot(
        const TableSnapshot& ve_table,
        int min_samples = 3,
        double ve_min = 0.0,
        double ve_max = 100.0) const;

    void reset();

    int accepted_count() const { return accepted_; }
    int rejected_count() const { return rejected_; }

private:
    // (row, col) → list of correction samples
    std::map<std::pair<int,int>, std::vector<CorrectionSample>> cell_corrections_;
    int accepted_ = 0;
    int rejected_ = 0;
    std::map<std::string, int> gate_rejections_;
};

}  // namespace tuner_core::ve_analyze_accumulator
