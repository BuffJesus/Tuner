// SPDX-License-Identifier: MIT
//
// tuner_core::ve_proposal_smoothing — port of `VeProposalSmoothingService.smooth`.
// Thirty-third sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Phase 7 Slice 7.5 — VE proposal smoothing as a strictly additive
// review layer. Reads a list of raw `VeAnalysisProposal` records and
// returns a separate `SmoothedProposalLayer`; the input proposals are
// never mutated. The operator chooses raw, smoothed, or neither.
//
// Hard rules preserved from the Python service:
//   - Smoothing only operates on cells that already have a raw proposal
//     (never invents VE values for unvisited cells).
//   - Edge cells use only existing neighbors — the kernel shrinks at
//     the grid boundary.
//   - Sample-count-weighted average prevents a low-confidence neighbor
//     from pulling a high-confidence anchor.
//   - `min_neighbors` lets the operator require N neighbors before
//     smoothing fires.
//   - `preserve_edge_magnitude` keeps the strongest correction in the
//     kernel intact so a real boost-spool transition is not averaged
//     away.
//   - `kernel_radius == 0` is the documented identity transform.

#pragma once

#include <string>
#include <vector>

namespace tuner_core::ve_proposal_smoothing {

// Mirror of Python `VeAnalysisProposal` — only the fields the smoothing
// service reads or copies into the smoothed layer.
struct Proposal {
    int row_index = 0;
    int col_index = 0;
    double current_ve = 0.0;
    double proposed_ve = 0.0;
    double correction_factor = 1.0;
    int sample_count = 0;
    // Raw correction factor preserved from the upstream Phase 7.2
    // weighted-correction layer; copied through unchanged.
    double raw_correction_factor = 1.0;
    bool clamp_applied = false;
};

struct SmoothingConfig {
    int kernel_radius = 1;
    int min_neighbors = 1;
    bool preserve_edge_magnitude = false;
};

struct SmoothedProposalLayer {
    std::vector<Proposal> smoothed_proposals;
    int unchanged_count = 0;
    int smoothed_count = 0;
    std::string summary_text;
};

// Mirror `VeProposalSmoothingService.smooth`. Stateless — the input
// vector is read-only and a new layer is returned.
SmoothedProposalLayer smooth(
    const std::vector<Proposal>& proposals,
    const SmoothingConfig& config = {});

}  // namespace tuner_core::ve_proposal_smoothing
