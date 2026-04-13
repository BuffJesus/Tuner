// SPDX-License-Identifier: MIT
#include "tuner_core/ve_cell_hit_accumulator.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <string>
#include <vector>

namespace tuner_core::ve_cell_hit_accumulator {

// -----------------------------------------------------------------------
// confidence_label
// -----------------------------------------------------------------------

std::string confidence_label(int sample_count) {
    if (sample_count < CONFIDENCE_LOW) return "insufficient";
    if (sample_count < CONFIDENCE_MEDIUM) return "low";
    if (sample_count < CONFIDENCE_HIGH) return "medium";
    return "high";
}

// -----------------------------------------------------------------------
// confidence_score
// -----------------------------------------------------------------------

double confidence_score(int sample_count) {
    if (sample_count <= 0) return 0.0;
    double raw = 1.0 - std::exp(-static_cast<double>(sample_count) / CONFIDENCE_SCORE_K);
    // Round to 4 decimal places using banker's rounding (std::nearbyint).
    return std::nearbyint(raw * 10000.0) / 10000.0;
}

// -----------------------------------------------------------------------
// build_snapshot
// -----------------------------------------------------------------------

Snapshot build_snapshot(
    const std::vector<CellAccumulation>& cell_accumulations,
    int grid_rows,
    int grid_cols,
    int accepted,
    int rejected,
    int min_samples,
    double ve_min,
    double ve_max,
    const WeightedCorrectionConfig* config)
{
    Snapshot result;
    result.accepted_records = accepted;
    result.rejected_records = rejected;

    // Find the latest timestamp across all samples for age decay.
    double latest_ts = 0.0;
    bool has_latest = false;
    if (config != nullptr && config->sample_age_decay_per_second >= 0.0) {
        for (const auto& cell : cell_accumulations) {
            for (const auto& s : cell.samples) {
                if (!has_latest || s.timestamp_seconds > latest_ts) {
                    latest_ts = s.timestamp_seconds;
                    has_latest = true;
                }
            }
        }
    }

    double decay = (config != nullptr && config->sample_age_decay_per_second >= 0.0)
                       ? config->sample_age_decay_per_second
                       : -1.0;
    double clamp_limit = (config != nullptr && config->max_correction_per_cell >= 0.0)
                             ? config->max_correction_per_cell
                             : -1.0;

    // Build a cell-key map for coverage lookup later.
    std::map<std::pair<int, int>, int> cell_sample_counts;

    // Process each cell's accumulated data.
    // Sort by (row, col) to match Python's sorted() iteration.
    std::vector<const CellAccumulation*> sorted_cells;
    sorted_cells.reserve(cell_accumulations.size());
    for (const auto& c : cell_accumulations) sorted_cells.push_back(&c);
    std::sort(sorted_cells.begin(), sorted_cells.end(),
              [](const CellAccumulation* a, const CellAccumulation* b) {
                  if (a->row_index != b->row_index) return a->row_index < b->row_index;
                  return a->col_index < b->col_index;
              });

    for (const auto* cell : sorted_cells) {
        int count = static_cast<int>(cell->samples.size());
        auto key = std::make_pair(cell->row_index, cell->col_index);
        cell_sample_counts[key] = count;

        // Compute weighted mean correction factor.
        double total_weight = 0.0;
        double total_weighted = 0.0;
        for (const auto& s : cell->samples) {
            double effective_w = s.weight;
            if (decay >= 0.0 && has_latest) {
                double age = latest_ts - s.timestamp_seconds;
                if (age > 0.0) {
                    effective_w *= std::exp(-age * decay);
                }
            }
            total_weight += effective_w;
            total_weighted += s.correction_factor * effective_w;
        }
        double raw_mean_cf = (total_weight > 0.0)
                                 ? (total_weighted / total_weight)
                                 : 1.0;

        // Apply per-cell clamp.
        double mean_cf = raw_mean_cf;
        bool clamp_applied = false;
        if (clamp_limit >= 0.0) {
            double lower = 1.0 - clamp_limit;
            double upper = 1.0 + clamp_limit;
            double clamped = std::max(lower, std::min(upper, raw_mean_cf));
            if (clamped != raw_mean_cf) {
                clamp_applied = true;
            }
            mean_cf = clamped;
        }

        // Round mean_cf and raw_mean_cf to 4 decimal places (banker's).
        double mean_cf_rounded = std::nearbyint(mean_cf * 10000.0) / 10000.0;
        double raw_mean_cf_rounded = std::nearbyint(raw_mean_cf * 10000.0) / 10000.0;

        // Current VE — NaN means unknown.
        bool has_current = !std::isnan(cell->current_ve);
        double current_ve = has_current ? cell->current_ve : 0.0;

        // Proposed VE — only if min_samples met and current value known.
        double proposed_ve = std::nan("");
        bool has_proposal = false;
        if (count >= min_samples && has_current) {
            double raw_proposed = current_ve * mean_cf_rounded;
            proposed_ve = std::max(ve_min, std::min(ve_max, raw_proposed));
            proposed_ve = std::nearbyint(proposed_ve * 100.0) / 100.0;  // round to 2dp
            has_proposal = true;
        }

        if (has_proposal) {
            ve_proposal_smoothing::Proposal p;
            p.row_index = cell->row_index;
            p.col_index = cell->col_index;
            p.current_ve = current_ve;
            p.proposed_ve = proposed_ve;
            p.correction_factor = mean_cf_rounded;
            p.sample_count = count;
            p.raw_correction_factor = clamp_applied ? raw_mean_cf_rounded : mean_cf_rounded;
            p.clamp_applied = clamp_applied;
            result.proposals.push_back(p);
        }

        CellCorrection cc;
        cc.row_index = cell->row_index;
        cc.col_index = cell->col_index;
        cc.sample_count = count;
        cc.mean_correction_factor = mean_cf_rounded;
        cc.current_ve = has_current ? current_ve : std::nan("");
        cc.proposed_ve = has_proposal ? proposed_ve : std::nan("");
        cc.confidence = confidence_label(count);
        cc.raw_correction_factor = clamp_applied ? raw_mean_cf_rounded : mean_cf_rounded;
        cc.clamp_applied = clamp_applied;
        cc.confidence_score = confidence_score(count);
        cc.boost_penalty_applied = std::nearbyint(cell->boost_penalty_applied * 10000.0) / 10000.0;
        result.cell_corrections.push_back(cc);
    }

    result.cells_with_data = static_cast<int>(cell_accumulations.size());
    result.cells_with_proposals = static_cast<int>(result.proposals.size());

    // Build coverage map.
    Coverage cov;
    cov.rows = grid_rows;
    cov.columns = grid_cols;
    cov.total_count = grid_rows * grid_cols;
    cov.visited_count = 0;
    cov.cells.resize(grid_rows);
    for (int r = 0; r < grid_rows; ++r) {
        cov.cells[r].resize(grid_cols);
        for (int c = 0; c < grid_cols; ++c) {
            auto it = cell_sample_counts.find({r, c});
            int samples = (it != cell_sample_counts.end()) ? it->second : 0;
            CoverageCell& cc = cov.cells[r][c];
            cc.row_index = r;
            cc.col_index = c;
            cc.sample_count = samples;
            cc.confidence_score = confidence_score(samples);
            cc.status = (samples > 0) ? "visited" : "unvisited";
            if (samples > 0) cov.visited_count++;
        }
    }
    result.coverage = cov;

    // Summary text — matches Python format exactly.
    int total = accepted + rejected;
    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "VE Analyze: %d accepted samples across %d cell(s); "
        "%d rejected; %d cell(s) have correction proposals.",
        accepted, result.cells_with_data,
        rejected, result.cells_with_proposals);
    result.summary_text = buf;

    return result;
}

}  // namespace tuner_core::ve_cell_hit_accumulator
