// SPDX-License-Identifier: MIT
//
// tuner_core::wue_analyze_snapshot — port of WueAnalyzeAccumulator.snapshot
// and WUE summary text builders.
// Thirty-seventh sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// WUE Analyze is the warmup-enrichment counterpart of VE Analyze. Key
// differences from VE:
//   - 1-D lookup: only the CLT axis is used (row-keyed, not 2D cell-keyed)
//   - No Phase 7 weighting/decay/clamp/boost — simple arithmetic mean
//   - Default gates exclude minCltFilter (WUE wants cold-running samples)
//   - Enrichment range defaults to [100, 250] instead of [0, 100]
//
// Composes against wue_analyze_helpers (sub-slice 6) for confidence
// labels, nearest_index, numeric_axis, and CLT detection.

#pragma once

#include "wue_analyze_helpers.hpp"

#include <string>
#include <vector>

namespace tuner_core::wue_analyze_snapshot {

// -----------------------------------------------------------------------
// Input types — flat representation of accumulated row data
// -----------------------------------------------------------------------

struct RowAccumulation {
    int row_index = 0;
    std::vector<double> correction_factors;
    double current_enrichment = 0.0;  // NaN if unknown
};

// -----------------------------------------------------------------------
// Output types
// -----------------------------------------------------------------------

struct RowCorrection {
    int row_index = 0;
    int sample_count = 0;
    double mean_correction_factor = 1.0;
    double current_enrichment = 0.0;  // NaN if unknown
    double proposed_enrichment = 0.0; // NaN if below threshold or no current
    std::string confidence;           // "insufficient" | "low" | "medium" | "high"
};

struct RowProposal {
    int row_index = 0;
    double current_enrichment = 0.0;
    double proposed_enrichment = 0.0;
    double correction_factor = 1.0;
    int sample_count = 0;
};

struct Snapshot {
    int total_records = 0;
    int accepted_records = 0;
    int rejected_records = 0;
    int rows_with_data = 0;
    int rows_with_proposals = 0;
    std::vector<RowCorrection> row_corrections;
    std::vector<RowProposal> proposals;
    std::string summary_text;
    std::vector<std::string> detail_lines;
};

// -----------------------------------------------------------------------
// Pure functions
// -----------------------------------------------------------------------

// Build a WUE Analyze snapshot from accumulated row data.
Snapshot build_snapshot(
    const std::vector<RowAccumulation>& row_accumulations,
    int accepted,
    int rejected,
    const std::vector<std::pair<std::string, int>>& rejection_counts = {},
    int min_samples = wue_analyze_helpers::kConfidenceLow,
    double wue_min = 100.0,
    double wue_max = 250.0);

}  // namespace tuner_core::wue_analyze_snapshot
