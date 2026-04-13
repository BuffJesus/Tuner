// SPDX-License-Identifier: MIT
//
// Implementation notes:
//   - Python `round(x, n)` uses banker's rounding (round-half-to-even),
//     which matches the IEEE-754 default `FE_TONEAREST` mode used by
//     `std::nearbyint`. We round via `std::nearbyint(x * 10^n) / 10^n`
//     so ties land identically to the Python service. `std::round`
//     (round-half-away-from-zero) would diverge on exact halves and is
//     deliberately avoided — same call documented in the
//     `table_rendering` slice notes.
//   - Neighbor lookup is a flat scan over the proposal vector. The
//     workspace presenter never produces more than a few hundred
//     proposals per pass and the kernel is at most 5×5, so the linear
//     scan stays trivially fast and avoids pulling in std::unordered_map
//     just for one slice.

#include "tuner_core/ve_proposal_smoothing.hpp"

#include <cmath>
#include <cstdio>

namespace tuner_core::ve_proposal_smoothing {

namespace {

double round_to(double value, int decimals) {
    double scale = 1.0;
    for (int i = 0; i < decimals; ++i) {
        scale *= 10.0;
    }
    return std::nearbyint(value * scale) / scale;
}

const Proposal* find_at(
    const std::vector<Proposal>& proposals, int row, int col) {
    for (const auto& p : proposals) {
        if (p.row_index == row && p.col_index == col) {
            return &p;
        }
    }
    return nullptr;
}

std::string format_summary(int modified, int unchanged, const SmoothingConfig& cfg) {
    char buffer[160];
    std::snprintf(
        buffer, sizeof(buffer),
        "Smoothed %d proposal(s); %d preserved unchanged "
        "(kernel radius %d, min_neighbors %d).",
        modified, unchanged, cfg.kernel_radius, cfg.min_neighbors);
    return std::string(buffer);
}

std::string format_identity_summary(int kernel_radius) {
    char buffer[80];
    std::snprintf(
        buffer, sizeof(buffer),
        "Kernel radius %d \xe2\x86\x92 identity transform.",
        kernel_radius);
    return std::string(buffer);
}

}  // namespace

SmoothedProposalLayer smooth(
    const std::vector<Proposal>& proposals,
    const SmoothingConfig& config) {
    SmoothedProposalLayer layer;

    if (proposals.empty()) {
        layer.summary_text = "No proposals to smooth.";
        return layer;
    }

    if (config.kernel_radius < 1) {
        // Identity transform — pass the raw proposals through so the
        // caller can treat the layer as "smoothing disabled" without a
        // special-case branch.
        layer.smoothed_proposals = proposals;
        layer.unchanged_count = static_cast<int>(proposals.size());
        layer.smoothed_count = 0;
        layer.summary_text = format_identity_summary(config.kernel_radius);
        return layer;
    }

    layer.smoothed_proposals.reserve(proposals.size());
    const int radius = config.kernel_radius;

    for (const auto& proposal : proposals) {
        std::vector<const Proposal*> neighbors;
        for (int dr = -radius; dr <= radius; ++dr) {
            for (int dc = -radius; dc <= radius; ++dc) {
                if (dr == 0 && dc == 0) {
                    continue;
                }
                const Proposal* n = find_at(
                    proposals,
                    proposal.row_index + dr,
                    proposal.col_index + dc);
                if (n != nullptr) {
                    neighbors.push_back(n);
                }
            }
        }

        if (static_cast<int>(neighbors.size()) < config.min_neighbors) {
            // Insufficient neighbours — preserve the raw proposal.
            layer.smoothed_proposals.push_back(proposal);
            layer.unchanged_count += 1;
            continue;
        }

        // Build the smoothing window: the cell itself plus its
        // neighbors. Mirrors the Python `[proposal, *neighbors]`.
        std::vector<const Proposal*> window;
        window.reserve(neighbors.size() + 1);
        window.push_back(&proposal);
        for (const auto* n : neighbors) {
            window.push_back(n);
        }

        if (config.preserve_edge_magnitude) {
            // Find the strongest deviation from 1.0 in the window.
            // If the current cell IS that strongest deviation, leave
            // it alone so a real edge is not averaged away by softer
            // neighbors. Mirrors `max(window, key=lambda p: abs(p.cf - 1.0))`.
            const Proposal* strongest = window.front();
            double strongest_dev = std::fabs(strongest->correction_factor - 1.0);
            for (size_t i = 1; i < window.size(); ++i) {
                double dev = std::fabs(window[i]->correction_factor - 1.0);
                if (dev > strongest_dev) {
                    strongest = window[i];
                    strongest_dev = dev;
                }
            }
            if (strongest == &proposal) {
                layer.smoothed_proposals.push_back(proposal);
                layer.unchanged_count += 1;
                continue;
            }
        }

        // Sample-count-weighted average of the correction factors.
        // Falls back to a uniform mean when the total weight is zero
        // (defensive — sample_count is always >= 1 in practice).
        long long total_weight = 0;
        double weighted_sum = 0.0;
        double uniform_sum = 0.0;
        for (const auto* p : window) {
            total_weight += p->sample_count;
            weighted_sum += p->correction_factor * static_cast<double>(p->sample_count);
            uniform_sum += p->correction_factor;
        }
        double avg_cf;
        if (total_weight <= 0) {
            avg_cf = uniform_sum / static_cast<double>(window.size());
        } else {
            avg_cf = weighted_sum / static_cast<double>(total_weight);
        }

        double new_proposed = round_to(proposal.current_ve * avg_cf, 2);
        if (std::fabs(new_proposed - proposal.proposed_ve) < 0.01) {
            // The smoothing pass would not move this cell — preserve
            // the raw proposal so the diff stays minimal and obvious.
            layer.smoothed_proposals.push_back(proposal);
            layer.unchanged_count += 1;
            continue;
        }

        Proposal updated = proposal;
        updated.proposed_ve = new_proposed;
        updated.correction_factor = round_to(avg_cf, 4);
        // Preserve the raw correction factor from the upstream Phase 7.2
        // layer — the smoothed cell carries forward the *original* raw
        // correction factor for review transparency, NOT the pre-smoothing
        // cf. Mirrors the Python `raw_correction_factor=proposal.correction_factor`.
        updated.raw_correction_factor = proposal.correction_factor;
        updated.clamp_applied = proposal.clamp_applied;
        layer.smoothed_proposals.push_back(updated);
        layer.smoothed_count += 1;
    }

    layer.summary_text = format_summary(layer.smoothed_count, layer.unchanged_count, config);
    return layer;
}

}  // namespace tuner_core::ve_proposal_smoothing
