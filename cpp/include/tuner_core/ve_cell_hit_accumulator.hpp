// SPDX-License-Identifier: MIT
//
// tuner_core::ve_cell_hit_accumulator — port of the snapshot/proposal layer
// from `VeAnalyzeCellHitAccumulator.snapshot`.
// Thirty-fifth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Phase 7 Slice 7.2 weighted-correction logic: takes accumulated per-cell
// correction samples and produces `Proposal` objects (the same POD shape
// from sub-slice 33 that the smoothing and diagnostics services consume).
//
// This is the *producer* of the Proposal shape — sub-slices 33 and 34 are
// its consumers. Porting it now closes the Phase 7 assist pipeline on the
// C++ side: cell hits → proposals → smoothing → diagnostics.
//
// Ported logic:
//   - Per-cell weighted mean of correction factors (dwell + age decay)
//   - Per-cell max correction clamp with raw_correction_factor transparency
//   - Confidence scoring (categorical + continuous)
//   - Full-grid coverage map
//   - Summary text
//
// Not ported in this slice (requires unported dependencies):
//   - The stateful accumulator's add_record() path (needs DataLogRecord,
//     ReplaySampleGateService, TableReplayContextService)
//   - Boost confidence penalty accumulation (BoostConfidenceConfig)
//   - Steady-state / EGO transport-delay compensation

#pragma once

#include "ve_proposal_smoothing.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace tuner_core::ve_cell_hit_accumulator {

// -----------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------

struct WeightedCorrectionConfig {
    // Max signed deviation from 1.0 per cell. -1.0 = disabled.
    double max_correction_per_cell = -1.0;
    bool dwell_weight_enabled = false;
    double dwell_weight_cap_seconds = 2.0;
    // Exponential decay per second for older samples. < 0 = disabled.
    double sample_age_decay_per_second = -1.0;
};

// -----------------------------------------------------------------------
// Input types — flat representation of accumulated cell data
// -----------------------------------------------------------------------

// One correction sample accumulated for a cell.
struct CorrectionSample {
    double correction_factor = 1.0;
    double weight = 1.0;
    double timestamp_seconds = 0.0;  // epoch seconds, for age decay
};

// All accumulated data for one cell.
struct CellAccumulation {
    int row_index = 0;
    int col_index = 0;
    std::vector<CorrectionSample> samples;
    double current_ve = 0.0;        // NaN if unknown
    double boost_penalty_applied = 0.0;
};

// -----------------------------------------------------------------------
// Output types
// -----------------------------------------------------------------------

// Confidence for one cell (categorical + continuous).
struct CellCorrection {
    int row_index = 0;
    int col_index = 0;
    int sample_count = 0;
    double mean_correction_factor = 1.0;
    double current_ve = 0.0;        // NaN if unknown
    double proposed_ve = 0.0;       // NaN if below threshold or no current
    std::string confidence;         // "insufficient" | "low" | "medium" | "high"
    double raw_correction_factor = 1.0;
    bool clamp_applied = false;
    double confidence_score = 0.0;
    double boost_penalty_applied = 0.0;
};

// Coverage status for one cell.
struct CoverageCell {
    int row_index = 0;
    int col_index = 0;
    int sample_count = 0;
    double confidence_score = 0.0;
    std::string status;  // "unvisited" | "visited"
};

// Full-grid coverage map.
struct Coverage {
    int rows = 0;
    int columns = 0;
    std::vector<std::vector<CoverageCell>> cells;
    int visited_count = 0;
    int total_count = 0;

    double coverage_ratio() const {
        if (total_count == 0) return 0.0;
        return static_cast<double>(visited_count) / total_count;
    }
};

// Complete snapshot result.
struct Snapshot {
    int accepted_records = 0;
    int rejected_records = 0;
    int cells_with_data = 0;
    int cells_with_proposals = 0;
    std::vector<CellCorrection> cell_corrections;
    std::vector<ve_proposal_smoothing::Proposal> proposals;
    std::string summary_text;
    Coverage coverage;
};

// -----------------------------------------------------------------------
// Constants (exposed for testing)
// -----------------------------------------------------------------------

constexpr int CONFIDENCE_LOW = 3;
constexpr int CONFIDENCE_MEDIUM = 10;
constexpr int CONFIDENCE_HIGH = 30;
constexpr double CONFIDENCE_SCORE_K = 10.0;

// -----------------------------------------------------------------------
// Pure functions
// -----------------------------------------------------------------------

// Categorical confidence from sample count.
std::string confidence_label(int sample_count);

// Continuous confidence score in [0.0, 1.0].
// Uses 1 - exp(-n / K), rounded to 4 decimal places.
double confidence_score(int sample_count);

// Build a snapshot from accumulated cell data.
//
// cell_accumulations: per-cell correction data (one entry per visited cell).
// grid_rows / grid_cols: full table dimensions (for coverage map).
// accepted / rejected: record counts for the summary.
// min_samples: minimum samples per cell before a proposal is generated.
// ve_min / ve_max: clamp bounds for proposed VE values.
// config: weighted correction configuration (nullptr = Phase 6 baseline).
Snapshot build_snapshot(
    const std::vector<CellAccumulation>& cell_accumulations,
    int grid_rows,
    int grid_cols,
    int accepted,
    int rejected,
    int min_samples = CONFIDENCE_LOW,
    double ve_min = 0.0,
    double ve_max = 100.0,
    const WeightedCorrectionConfig* config = nullptr);

}  // namespace tuner_core::ve_cell_hit_accumulator
