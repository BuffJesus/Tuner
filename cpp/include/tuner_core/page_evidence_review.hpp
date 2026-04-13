// SPDX-License-Identifier: MIT
//
// tuner_core::page_evidence_review — port of PageEvidenceReviewService.
// Sub-slice 59 of Phase 14 Slice 4.
//
// Selects relevant runtime channels for a given workspace page based on
// keyword matching across page title, parameter names, group/family IDs,
// and evidence hints.  Pure logic, no Qt.

#pragma once

#include "evidence_replay.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::page_evidence_review {

struct ReviewSnapshot {
    std::string summary_text;
    std::string detail_text;
    std::vector<evidence_replay::Channel> relevant_channels;
};

struct PageContext {
    std::string page_title;
    std::vector<std::string> parameter_names;
    std::string page_id;
    std::string group_id;
    std::string page_family_id;
    std::vector<std::string> evidence_hints;
};

/// Build a page evidence review snapshot.  Returns nullopt if the
/// evidence snapshot pointer is null.
std::optional<ReviewSnapshot> build(
    const PageContext& ctx,
    const evidence_replay::Snapshot* evidence);

}  // namespace tuner_core::page_evidence_review
