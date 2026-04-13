// SPDX-License-Identifier: MIT
//
// tuner_core::ve_analyze_review — port of `VeAnalyzeReviewService.build`.
// Thirty-sixth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Turns a VE Analyze snapshot (from sub-slice 35's accumulator) plus the
// optional smoothing layer (sub-slice 33) and diagnostics report (sub-slice
// 34) into an operator-facing review block: summary text, detail text,
// confidence distribution, largest lean/rich corrections, and Phase 7
// workspace UI surfacing lines. No tune data is modified.
//
// Composes all three preceding Phase 7 assist slices — this is the
// read-side of the assist pipeline that the workspace UI renders.

#pragma once

#include "ve_cell_hit_accumulator.hpp"
#include "ve_proposal_smoothing.hpp"
#include "ve_root_cause_diagnostics.hpp"

#include <string>
#include <vector>

namespace tuner_core::ve_analyze_review {

// Mirror of Python `VeAnalyzeReviewSnapshot`.
struct ReviewSnapshot {
    std::string summary_text;
    std::string detail_text;
    // (level, count) in order: insufficient, low, medium, high.
    std::vector<std::pair<std::string, int>> confidence_distribution;
    // Largest corrections sorted by CF (lean desc, rich asc), capped at 5.
    std::vector<ve_proposal_smoothing::Proposal> largest_lean_corrections;
    std::vector<ve_proposal_smoothing::Proposal> largest_rich_corrections;
    int cells_insufficient = 0;
    int max_preview_entries = 5;
    // Phase 7 workspace UI surfacing.
    int clamp_count = 0;
    int boost_penalty_count = 0;
    std::string smoothed_summary_text;   // empty = not supplied
    std::vector<std::string> diagnostic_lines;
};

// Build an operator-facing review snapshot.
//
// snapshot: from ve_cell_hit_accumulator::build_snapshot.
// rejection_counts: sorted (gate_name, count) pairs for the detail block.
// smoothed_layer: optional, from ve_proposal_smoothing::smooth.
// diagnostics: optional, from ve_root_cause_diagnostics::diagnose.
ReviewSnapshot build(
    const ve_cell_hit_accumulator::Snapshot& snapshot,
    const std::vector<std::pair<std::string, int>>& rejection_counts = {},
    const ve_proposal_smoothing::SmoothedProposalLayer* smoothed_layer = nullptr,
    const ve_root_cause_diagnostics::DiagnosticReport* diagnostics = nullptr);

}  // namespace tuner_core::ve_analyze_review
