// SPDX-License-Identifier: MIT
#include "tuner_core/wue_analyze_review.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::wue_analyze_review {

namespace {

std::string build_detail(
    const wue_analyze_snapshot::Snapshot& snap,
    const std::vector<std::pair<std::string, int>>& confidence_distribution,
    const std::vector<wue_analyze_snapshot::RowProposal>& largest_lean,
    const std::vector<wue_analyze_snapshot::RowProposal>& largest_rich,
    int rows_insufficient)
{
    std::string out;

    // Overview.
    char buf[256];
    std::snprintf(buf, sizeof(buf),
        "Records: %d accepted / %d rejected / %d total.",
        snap.accepted_records, snap.rejected_records, snap.total_records);
    out += buf;

    // Rejection breakdown — from the snapshot's detail_lines we can't
    // easily extract just the rejection line, so we re-derive from
    // the detail_lines by looking for "Rejections:". But simpler to
    // just check the snapshot's detail_lines. Actually the Python
    // service reads rejection_counts_by_gate from the summary. Since
    // we don't carry that separately in our snapshot, scan detail_lines.
    for (const auto& line : snap.detail_lines) {
        if (line.find("Rejections:") != std::string::npos) {
            out += "\n";
            out += line;
            break;
        }
    }

    // Confidence distribution.
    {
        std::string d;
        for (const auto& [lvl, cnt] : confidence_distribution) {
            if (cnt <= 0) continue;
            if (!d.empty()) d += ", ";
            char c[64];
            std::snprintf(c, sizeof(c), "%s=%d", lvl.c_str(), cnt);
            d += c;
        }
        if (!d.empty()) {
            out += "\nRow confidence: ";
            out += d;
            out += ".";
        }
    }

    if (rows_insufficient > 0) {
        char c[128];
        std::snprintf(c, sizeof(c),
            "\nRows skipped (insufficient samples): %d.", rows_insufficient);
        out += c;
    }

    // Lean corrections preview.
    auto format_proposal = [](const wue_analyze_snapshot::RowProposal& p,
                               char* b, int sz) {
        std::snprintf(b, sz,
            "row %d %.1f%s%.1f %s%.4f n=%d",
            p.row_index + 1,
            p.current_enrichment,
            "\xe2\x86\x92",  // →
            p.proposed_enrichment,
            "\xc3\x97",  // ×
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
        if (largest_lean.size() == 5 && snap.rows_with_proposals > 5) {
            out += "\xe2\x80\xa6";  // …
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
        if (largest_rich.size() == 5 && snap.rows_with_proposals > 5) {
            out += "\xe2\x80\xa6";
        }
        out += ".";
    }

    if (largest_lean.empty() && largest_rich.empty() && snap.rows_with_proposals == 0) {
        out += "\nNo corrections proposed yet.";
    }

    return out;
}

}  // namespace

ReviewSnapshot build(const wue_analyze_snapshot::Snapshot& snapshot) {
    ReviewSnapshot result;

    // Confidence distribution.
    int dist[4] = {0, 0, 0, 0};
    int rows_insufficient = 0;
    for (const auto& rc : snapshot.row_corrections) {
        if (rc.confidence == "insufficient") dist[0]++;
        else if (rc.confidence == "low") dist[1]++;
        else if (rc.confidence == "medium") dist[2]++;
        else if (rc.confidence == "high") dist[3]++;

        if (std::isnan(rc.proposed_enrichment) && !std::isnan(rc.current_enrichment)) {
            rows_insufficient++;
        }
    }
    result.confidence_distribution = {
        {"insufficient", dist[0]},
        {"low", dist[1]},
        {"medium", dist[2]},
        {"high", dist[3]},
    };
    result.rows_insufficient = rows_insufficient;

    // Largest lean/rich sorted.
    std::vector<wue_analyze_snapshot::RowProposal> lean, rich;
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

    result.summary_text = snapshot.summary_text;
    result.detail_text = build_detail(
        snapshot, result.confidence_distribution,
        lean, rich, rows_insufficient);

    return result;
}

}  // namespace tuner_core::wue_analyze_review
