// SPDX-License-Identifier: MIT
//
// tuner_core::wue_analyze_review — port of `WueAnalyzeReviewService.build`.
// Thirty-eighth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Mirrors ve_analyze_review but for 1-D WUE table corrections. Simpler
// than its VE counterpart — no Phase 7 clamp/boost/smoothing/diagnostics
// lines, just confidence distribution, lean/rich previews, and detail text.

#pragma once

#include "wue_analyze_snapshot.hpp"

#include <string>
#include <vector>

namespace tuner_core::wue_analyze_review {

struct ReviewSnapshot {
    std::string summary_text;
    std::string detail_text;
    std::vector<std::pair<std::string, int>> confidence_distribution;
    std::vector<wue_analyze_snapshot::RowProposal> largest_lean_corrections;
    std::vector<wue_analyze_snapshot::RowProposal> largest_rich_corrections;
    int rows_insufficient = 0;
    int max_preview_entries = 5;
};

// Build an operator-facing review snapshot from a WUE Analyze snapshot.
ReviewSnapshot build(
    const wue_analyze_snapshot::Snapshot& snapshot);

}  // namespace tuner_core::wue_analyze_review
