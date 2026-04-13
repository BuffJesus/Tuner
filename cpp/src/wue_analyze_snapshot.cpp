// SPDX-License-Identifier: MIT
#include "tuner_core/wue_analyze_snapshot.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::wue_analyze_snapshot {

namespace {

std::string build_summary(int total, int accepted, int rejected,
                           int proposals, int rows_with_data) {
    if (total == 0) {
        return "WUE Analyze: no records to review.";
    }
    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "WUE Analyze reviewed %d record(s): "
        "%d accepted, %d rejected, "
        "%d row proposal(s) of %d with data.",
        total, accepted, rejected, proposals, rows_with_data);
    return buf;
}

std::vector<std::string> build_detail_lines(
    int total, int accepted, int rejected,
    const std::vector<std::pair<std::string, int>>& gate_rejections,
    const std::vector<RowCorrection>& row_corrections,
    const std::vector<RowProposal>& proposals)
{
    std::vector<std::string> lines;

    // Overview.
    char buf[256];
    std::snprintf(buf, sizeof(buf),
        "Records: %d accepted / %d rejected / %d total.",
        accepted, rejected, total);
    lines.push_back(buf);

    // Rejection breakdown.
    if (!gate_rejections.empty()) {
        std::string line = "Rejections: ";
        for (std::size_t i = 0; i < gate_rejections.size(); ++i) {
            if (i > 0) line += ", ";
            char r[128];
            std::snprintf(r, sizeof(r), "%s=%d",
                          gate_rejections[i].first.c_str(),
                          gate_rejections[i].second);
            line += r;
        }
        line += ".";
        lines.push_back(line);
    }

    // Confidence distribution.
    int dist[4] = {0, 0, 0, 0};  // insufficient, low, medium, high
    for (const auto& rc : row_corrections) {
        if (rc.confidence == "insufficient") dist[0]++;
        else if (rc.confidence == "low") dist[1]++;
        else if (rc.confidence == "medium") dist[2]++;
        else if (rc.confidence == "high") dist[3]++;
    }
    {
        std::string d;
        const char* names[] = {"insufficient", "low", "medium", "high"};
        for (int i = 0; i < 4; ++i) {
            if (dist[i] <= 0) continue;
            if (!d.empty()) d += ", ";
            char c[64];
            std::snprintf(c, sizeof(c), "%s=%d", names[i], dist[i]);
            d += c;
        }
        if (!d.empty()) {
            lines.push_back("Row confidence: " + d + ".");
        }
    }

    // Lean/rich correction previews.
    constexpr int PREVIEW = 5;
    if (!proposals.empty()) {
        std::vector<const RowProposal*> lean, rich;
        for (const auto& p : proposals) {
            if (p.correction_factor > 1.0) lean.push_back(&p);
            else if (p.correction_factor < 1.0) rich.push_back(&p);
        }
        std::sort(lean.begin(), lean.end(),
                  [](const auto* a, const auto* b) {
                      return a->correction_factor > b->correction_factor;
                  });
        std::sort(rich.begin(), rich.end(),
                  [](const auto* a, const auto* b) {
                      return a->correction_factor < b->correction_factor;
                  });

        auto format_proposals = [](const std::vector<const RowProposal*>& ps,
                                    int limit) {
            std::string text;
            int count = std::min(static_cast<int>(ps.size()), limit);
            for (int i = 0; i < count; ++i) {
                if (i > 0) text += "; ";
                char p[128];
                std::snprintf(p, sizeof(p),
                    "row %d %.1f%s%.1f %s%.4f n=%d",
                    ps[i]->row_index + 1,
                    ps[i]->current_enrichment,
                    "\xe2\x86\x92",  // →
                    ps[i]->proposed_enrichment,
                    "\xc3\x97",  // ×
                    ps[i]->correction_factor,
                    ps[i]->sample_count);
                text += p;
            }
            return text;
        };

        if (!lean.empty()) {
            std::string text = format_proposals(lean, PREVIEW);
            std::string suffix = (static_cast<int>(lean.size()) > PREVIEW)
                                     ? "\xe2\x80\xa6" : "";  // …
            lines.push_back("Largest lean corrections: " + text + suffix + ".");
        }
        if (!rich.empty()) {
            std::string text = format_proposals(rich, PREVIEW);
            std::string suffix = (static_cast<int>(rich.size()) > PREVIEW)
                                     ? "\xe2\x80\xa6" : "";
            lines.push_back("Largest rich corrections: " + text + suffix + ".");
        }
    }
    if (proposals.empty()) {
        lines.push_back("No corrections proposed yet.");
    }

    return lines;
}

}  // namespace

Snapshot build_snapshot(
    const std::vector<RowAccumulation>& row_accumulations,
    int accepted,
    int rejected,
    const std::vector<std::pair<std::string, int>>& rejection_counts,
    int min_samples,
    double wue_min,
    double wue_max)
{
    Snapshot result;
    result.accepted_records = accepted;
    result.rejected_records = rejected;
    int total = accepted + rejected;
    result.total_records = total;

    // Sort by row index to match Python's sorted() iteration.
    std::vector<const RowAccumulation*> sorted;
    sorted.reserve(row_accumulations.size());
    for (const auto& r : row_accumulations) sorted.push_back(&r);
    std::sort(sorted.begin(), sorted.end(),
              [](const auto* a, const auto* b) {
                  return a->row_index < b->row_index;
              });

    for (const auto* row : sorted) {
        int count = static_cast<int>(row->correction_factors.size());
        if (count == 0) continue;

        // Arithmetic mean.
        double sum = 0.0;
        for (double cf : row->correction_factors) sum += cf;
        double mean_cf = sum / count;

        // Round to 4dp (banker's rounding).
        double mean_cf_rounded = std::nearbyint(mean_cf * 10000.0) / 10000.0;

        bool has_current = !std::isnan(row->current_enrichment);
        double current = has_current ? row->current_enrichment : 0.0;

        double proposed = std::nan("");
        bool has_proposal = false;
        if (count >= min_samples && has_current) {
            double raw = current * mean_cf_rounded;
            proposed = std::max(wue_min, std::min(wue_max, raw));
            proposed = std::nearbyint(proposed * 100.0) / 100.0;  // round 2dp
            has_proposal = true;
        }

        if (has_proposal) {
            RowProposal p;
            p.row_index = row->row_index;
            p.current_enrichment = current;
            p.proposed_enrichment = proposed;
            p.correction_factor = mean_cf_rounded;
            p.sample_count = count;
            result.proposals.push_back(p);
        }

        RowCorrection rc;
        rc.row_index = row->row_index;
        rc.sample_count = count;
        rc.mean_correction_factor = mean_cf_rounded;
        rc.current_enrichment = has_current ? current : std::nan("");
        rc.proposed_enrichment = has_proposal ? proposed : std::nan("");
        rc.confidence = wue_analyze_helpers::confidence_label(count);
        result.row_corrections.push_back(rc);
    }

    result.rows_with_data = static_cast<int>(result.row_corrections.size());
    result.rows_with_proposals = static_cast<int>(result.proposals.size());
    result.summary_text = build_summary(total, accepted, rejected,
                                         result.rows_with_proposals,
                                         result.rows_with_data);
    result.detail_lines = build_detail_lines(
        total, accepted, rejected, rejection_counts,
        result.row_corrections, result.proposals);

    return result;
}

}  // namespace tuner_core::wue_analyze_snapshot
