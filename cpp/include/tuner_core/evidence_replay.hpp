// SPDX-License-Identifier: MIT
//
// tuner_core::evidence_replay — port of EvidenceReplayService.build.
// Sub-slice 58 of Phase 14 Slice 4.
//
// Composes SurfaceEvidenceService (already ported) with workspace and
// runtime state to produce an EvidenceReplaySnapshot.  Pure logic.

#pragma once

#include "surface_evidence.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::evidence_replay {

struct Channel {
    std::string name;
    double value = 0;
    std::string units;
};

struct Snapshot {
    std::string captured_at_iso;
    std::string session_state;
    std::string connection_text;
    std::string source_text;
    std::string sync_summary_text;
    std::vector<std::string> sync_mismatch_details;
    std::string staged_summary_text;
    std::string operation_summary_text;
    int operation_session_count = 0;
    std::string latest_write_text;
    std::string latest_burn_text;
    std::string runtime_summary_text;
    int runtime_channel_count = 0;
    std::optional<double> runtime_age_seconds;
    std::vector<Channel> runtime_channels;
    std::string evidence_summary_text;
};

// -----------------------------------------------------------------------
// Flat inputs — caller flattens workspace/session state into these.
// -----------------------------------------------------------------------

struct Inputs {
    // From the surface evidence service.
    surface_evidence::Inputs surface_inputs;

    // Workspace state (flattened).
    std::string session_state;       // e.g. "disconnected", "connected"
    std::vector<std::string> sync_mismatch_details;
    std::string staged_summary_text;
    std::string operation_summary_text;
    int operation_session_count = 0;
    std::string latest_write_text;
    std::string latest_burn_text;

    // Runtime channels (flattened).
    std::vector<Channel> runtime_channels;
    std::optional<double> runtime_age_seconds;

    // Timestamp (ISO 8601 string, caller-provided).
    std::string captured_at_iso;
};

Snapshot build(const Inputs& inputs);

}  // namespace tuner_core::evidence_replay
