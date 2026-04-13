// SPDX-License-Identifier: MIT
//
// tuner_core::surface_evidence — port of `SurfaceEvidenceService`.
// Twenty-ninth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Builds the strip-of-pills evidence summary the workspace shell shows
// at the top of every page (Connection / Source / Sync / Changes / Ops
// / Runtime). Pure logic — the input is a flat POD so the C++ side
// doesn't have to model the SessionInfo / SyncState / OperationLog /
// WorkspaceReview / OutputChannelSnapshot graph just to render text.

#pragma once

#include <cstddef>
#include <optional>
#include <string>

namespace tuner_core::surface_evidence {

struct Inputs {
    bool connected = false;
    std::string connection_state_text;  // session_info.state.value
    bool sync_state_present = false;
    bool sync_has_ecu_ram = false;
    std::size_t mismatch_count = 0;
    std::size_t staged_count = 0;
    std::size_t log_count = 0;
    bool has_unwritten = false;
    std::string operation_log_summary_text;  // multi-line; first non-empty line surfaces

    bool runtime_present = false;          // runtime_snapshot != None and has values
    std::size_t runtime_value_count = 0;
    // Age of the latest runtime sample in seconds; nullopt if unknown
    // (no timestamp), or if no runtime snapshot at all.
    std::optional<double> runtime_age_seconds;
};

struct Snapshot {
    std::string connection_text;
    std::string connection_severity;
    std::string source_text;
    std::string source_severity;
    std::string sync_text;
    std::string sync_severity;
    std::string changes_text;
    std::string changes_severity;
    std::string log_text;
    std::string log_severity;
    std::string runtime_text;
    std::string runtime_severity;
    std::string summary_text;
};

Snapshot build(const Inputs& in);

// Exposed for parity testing.
std::string format_age(double age_seconds);

}  // namespace tuner_core::surface_evidence
