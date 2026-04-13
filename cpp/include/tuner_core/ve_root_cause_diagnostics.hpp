// SPDX-License-Identifier: MIT
//
// tuner_core::ve_root_cause_diagnostics — port of
// `VeRootCauseDiagnosticsService.diagnose`. Thirty-fourth sub-slice of
// the Phase 14 workspace-services port (Slice 4).
//
// Phase 7 Slice 7.7 — read-only inspector that scans a list of VE
// proposals for systematic patterns suggesting the *real* problem is
// something other than VE table cells. Produces advisory diagnostics;
// the operator decides what to do. Composes against the same
// `Proposal` POD as the smoothing slice (sub-slice 33).

#pragma once

#include "tuner_core/ve_proposal_smoothing.hpp"

#include <string>
#include <utility>
#include <vector>

namespace tuner_core::ve_root_cause_diagnostics {

// Reuse the proposal POD from the smoothing slice — same shape, same
// fields, no need to duplicate the type.
using Proposal = tuner_core::ve_proposal_smoothing::Proposal;

struct Diagnostic {
    std::string rule;       // stable identifier, e.g. "injector_flow_error"
    std::string severity;   // "info" | "warning"
    std::string message;    // operator-facing summary
    std::vector<std::pair<int, int>> evidence_cells;
};

struct DiagnosticReport {
    std::vector<Diagnostic> diagnostics;
    std::string summary_text;

    bool has_findings() const noexcept { return !diagnostics.empty(); }
};

// Stateless inspector. The input vector is read-only; diagnostics are
// returned as a flat report.
DiagnosticReport diagnose(const std::vector<Proposal>& proposals);

}  // namespace tuner_core::ve_root_cause_diagnostics
