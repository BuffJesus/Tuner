// SPDX-License-Identifier: MIT
//
// tuner_core::wue_analyze_accumulator — port of WueAnalyzeAccumulator.
// Sub-slice 71 of Phase 14 Slice 4.
//
// Stateful accumulator for WUE (warmup enrichment) analyze. Accepts
// records one at a time (for both live polling and batch replay),
// maps each to a CLT-axis row, computes per-row correction factors,
// and produces WueAnalysisSummary snapshots. Pure logic, no Qt.

#pragma once

#include "wue_analyze_snapshot.hpp"

#include <map>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::wue_analyze_accumulator {

using wue_analyze_snapshot::RowAccumulation;
using wue_analyze_snapshot::Snapshot;

// -----------------------------------------------------------------------
// CLT axis orientation detection
// -----------------------------------------------------------------------

struct TableAxis {
    std::vector<double> bins;
    bool along_y = true;  // true = N×1 (CLT along rows), false = 1×N (CLT along cols)
};

/// Detect CLT axis from a table page snapshot shape.
/// Returns nullopt if neither axis looks like CLT.
std::optional<TableAxis> detect_clt_axis(
    const std::string& x_param_name,
    const std::string& y_param_name,
    const std::vector<std::string>& x_labels,
    const std::vector<std::string>& y_labels);

// -----------------------------------------------------------------------
// Record for feeding into the accumulator
// -----------------------------------------------------------------------

struct Record {
    std::map<std::string, double> values;
};

// -----------------------------------------------------------------------
// Gating config (simplified — mirrors the Python SampleGatingConfig)
// -----------------------------------------------------------------------

struct GatingConfig {
    double afr_min = 10.0;
    double afr_max = 20.0;
    bool require_lambda = true;
};

// -----------------------------------------------------------------------
// Accumulator
// -----------------------------------------------------------------------

class Accumulator {
public:
    /// Feed one record. Returns true if accepted into a CLT row.
    bool add_record(
        const Record& record,
        const TableAxis& axis,
        const std::vector<std::string>& cell_texts,  // current WUE values
        double lambda_target = 1.0,
        const GatingConfig& gating = {});

    /// Build a snapshot without clearing state.
    Snapshot snapshot(
        const std::vector<std::string>& cell_texts,
        int min_samples = 3,
        double wue_min = 100.0,
        double wue_max = 250.0) const;

    void reset();

    int accepted_count() const { return accepted_; }
    int rejected_count() const { return rejected_; }

private:
    // row_index → list of correction factors
    std::map<int, std::vector<double>> row_corrections_;
    int accepted_ = 0;
    int rejected_ = 0;
    std::map<std::string, int> gate_rejections_;
};

}  // namespace tuner_core::wue_analyze_accumulator
