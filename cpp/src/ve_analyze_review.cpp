// SPDX-License-Identifier: MIT
#include "tuner_core/ve_analyze_review.hpp"

#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::ve_analyze_review {

namespace {

// Format the one-line summary — matches Python _build_summary exactly.
std::string build_summary(const ve_cell_hit_accumulator::Snapshot& snap) {
    int total = snap.accepted_records + snap.rejected_records;
    if (total == 0) {
        return "VE Analyze: no records to review.";
    }
    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "VE Analyze reviewed %d record(s): %d accepted, %d rejected, "
        "%d cell proposal(s) of %d with data.",
        total, snap.accepted_records, snap.rejected_records,
        snap.cells_with_proposals, snap.cells_with_data);
    return buf;
}

// Format the multi-line detail block — matches Python _build_detail exactly.
std::string build_detail(
    const ve_cell_hit_accumulator::Snapshot& snap,
    const std::vector<std::pair<std::string, int>>& rejection_counts,
    const std::vector<std::pair<std::string, int>>& confidence_distribution,
    const std::vector<ve_proposal_smoothing::Proposal>& largest_lean,
    const std::vector<ve_proposal_smoothing::Proposal>& largest_rich,
    int cells_insufficient,
    int clamp_count,
    int boost_penalty_count,
    const std::string& smoothed_summary_text,
    const std::vector<std::string>& diagnostic_lines)
{
    std::string out;
    int total = snap.accepted_records + snap.rejected_records;

    // Overview line.
    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "Records: %d accepted / %d rejected / %d total.",
        snap.accepted_records, snap.rejected_records, total);
    out += buf;

    // Rejection breakdown.
    if (!rejection_counts.empty()) {
        out += "\nRejections: ";
        for (std::size_t i = 0; i < rejection_counts.size(); ++i) {
            if (i > 0) out += ", ";
            char r[128];
            std::snprintf(r, sizeof(r), "%s=%d",
                          rejection_counts[i].first.c_str(),
                          rejection_counts[i].second);
            out += r;
        }
        out += ".";
    }

    // Confidence distribution (non-zero only).
    {
        std::string dist;
        for (const auto& [lvl, cnt] : confidence_distribution) {
            if (cnt <= 0) continue;
            if (!dist.empty()) dist += ", ";
            char d[64];
            std::snprintf(d, sizeof(d), "%s=%d", lvl.c_str(), cnt);
            dist += d;
        }
        if (!dist.empty()) {
            out += "\nCell confidence: ";
            out += dist;
            out += ".";
        }
    }

    if (cells_insufficient > 0) {
        char c[128];
        std::snprintf(c, sizeof(c),
            "\nCells skipped (insufficient samples): %d.", cells_insufficient);
        out += c;
    }

    // Coverage line.
    if (snap.coverage.total_count > 0) {
        double ratio = snap.coverage.coverage_ratio() * 100.0;
        char c[128];
        std::snprintf(c, sizeof(c),
            "\nCoverage: %d/%d cells (%.0f%%) visited.",
            snap.coverage.visited_count, snap.coverage.total_count, ratio);
        out += c;
    }

    // Lean corrections preview.
    auto format_proposal = [](const ve_proposal_smoothing::Proposal& p, char* b, int sz) {
        std::snprintf(b, sz,
            "(%d,%d) %.1f%s%.1f %s%.4f n=%d",
            p.row_index + 1, p.col_index + 1,
            p.current_ve,
            "\xe2\x86\x92",  // UTF-8 for →
            p.proposed_ve,
            "\xc3\x97",  // UTF-8 for ×
            p.correction_factor, p.sample_count);
    };

    if (!largest_lean.empty()) {
        out += "\nLargest lean corrections: ";
        for (std::size_t i = 0; i < largest_lean.size(); ++i) {
            if (i > 0) out += "; ";
            char p[128];
            format_proposal(largest_lean[i], p, sizeof(p));
            out += p;
        }
        if (largest_lean.size() == 5 && snap.cells_with_proposals > 5) {
            out += "\xe2\x80\xa6";  // UTF-8 for …
        }
        out += ".";
    }

    if (!largest_rich.empty()) {
        out += "\nLargest rich corrections: ";
        for (std::size_t i = 0; i < largest_rich.size(); ++i) {
            if (i > 0) out += "; ";
            char p[128];
            format_proposal(largest_rich[i], p, sizeof(p));
            out += p;
        }
        if (largest_rich.size() == 5 && snap.cells_with_proposals > 5) {
            out += "\xe2\x80\xa6";  // UTF-8 for …
        }
        out += ".";
    }

    if (largest_lean.empty() && largest_rich.empty() && snap.cells_with_proposals == 0) {
        out += "\nNo corrections proposed yet.";
    }

    // Phase 7 workspace UI surfacing lines.
    if (clamp_count > 0) {
        char c[256];
        std::snprintf(c, sizeof(c),
            "\nClamp transparency: %d proposal(s) hit the per-cell "
            "max-correction clamp \xe2\x80\x94 review raw_correction_factor before staging.",
            clamp_count);
        out += c;
    }
    if (boost_penalty_count > 0) {
        char c[256];
        std::snprintf(c, sizeof(c),
            "\nBoost penalty: %d cell(s) downweighted by the "
            "spool/MAT confidence model.",
            boost_penalty_count);
        out += c;
    }
    if (!smoothed_summary_text.empty()) {
        out += "\nSmoothed layer: ";
        out += smoothed_summary_text;
    }
    if (!diagnostic_lines.empty()) {
        out += "\nRoot-cause diagnostics:";
        for (const auto& line : diagnostic_lines) {
            out += "\n  ";
            out += line;
        }
    }

    return out;
}

}  // namespace

ReviewSnapshot build(
    const ve_cell_hit_accumulator::Snapshot& snapshot,
    const std::vector<std::pair<std::string, int>>& rejection_counts,
    const ve_proposal_smoothing::SmoothedProposalLayer* smoothed_layer,
    const ve_root_cause_diagnostics::DiagnosticReport* diagnostics)
{
    ReviewSnapshot result;

    // Confidence distribution across all cells that received data.
    int dist_insufficient = 0, dist_low = 0, dist_medium = 0, dist_high = 0;
    int cells_insufficient = 0;
    int clamp_count = 0;
    int boost_penalty_count = 0;

    for (const auto& cc : snapshot.cell_corrections) {
        if (cc.confidence == "insufficient") dist_insufficient++;
        else if (cc.confidence == "low") dist_low++;
        else if (cc.confidence == "medium") dist_medium++;
        else if (cc.confidence == "high") dist_high++;

        // Cell has data but no proposal and has a current_ve.
        if (std::isnan(cc.proposed_ve) && !std::isnan(cc.current_ve)) {
            cells_insufficient++;
        }
        if (cc.clamp_applied) clamp_count++;
        if (cc.boost_penalty_applied > 0.0) boost_penalty_count++;
    }

    result.confidence_distribution = {
        {"insufficient", dist_insufficient},
        {"low", dist_low},
        {"medium", dist_medium},
        {"high", dist_high},
    };
    result.cells_insufficient = cells_insufficient;
    result.clamp_count = clamp_count;
    result.boost_penalty_count = boost_penalty_count;

    // Largest lean corrections (CF > 1.0, sorted descending).
    std::vector<ve_proposal_smoothing::Proposal> lean;
    std::vector<ve_proposal_smoothing::Proposal> rich;
    for (const auto& p : snapshot.proposals) {
        if (p.correction_factor > 1.0) lean.push_back(p);
        else if (p.correction_factor < 1.0) rich.push_back(p);
    }
    std::sort(lean.begin(), lean.end(),
              [](const auto& a, const auto& b) {
                  return a.correction_factor > b.correction_factor;
              });
    std::sort(rich.begin(), rich.end(),
              [](const auto& a, const auto& b) {
                  return a.correction_factor < b.correction_factor;
              });
    if (lean.size() > 5) lean.resize(5);
    if (rich.size() > 5) rich.resize(5);
    result.largest_lean_corrections = lean;
    result.largest_rich_corrections = rich;

    // Smoothed layer and diagnostics.
    if (smoothed_layer != nullptr) {
        result.smoothed_summary_text = smoothed_layer->summary_text;
    }
    if (diagnostics != nullptr && diagnostics->has_findings()) {
        for (const auto& d : diagnostics->diagnostics) {
            char line[512];
            std::snprintf(line, sizeof(line), "[%s] %s: %s",
                          d.severity.c_str(), d.rule.c_str(), d.message.c_str());
            result.diagnostic_lines.push_back(line);
        }
    }

    // Build text.
    result.summary_text = build_summary(snapshot);
    result.detail_text = build_detail(
        snapshot, rejection_counts, result.confidence_distribution,
        lean, rich, cells_insufficient,
        clamp_count, boost_penalty_count,
        result.smoothed_summary_text, result.diagnostic_lines);

    return result;
}

}  // namespace tuner_core::ve_analyze_review
