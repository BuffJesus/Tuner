// SPDX-License-Identifier: MIT
//
// tuner_core::operation_evidence — port of `OperationEvidenceService`.
// Twenty-fifth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Composes the just-ported `operation_log` entries into a session-
// aware evidence snapshot the workspace presenter renders for the
// "what's happened so far" surface. Sessions are split on every
// `BURNED` entry — anything before a burn is one session, anything
// after the latest burn is the active session.

#pragma once

#include "tuner_core/operation_log.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::operation_evidence {

using operation_log::OperationEntry;
using operation_log::OperationKind;

struct Session {
    int sequence = 0;
    std::size_t entry_count = 0;
    bool has_burn = false;
    bool has_write = false;
    bool has_unwritten_stage = false;
    std::optional<OperationEntry> latest_entry;
};

struct Snapshot {
    std::string summary_text;
    std::size_t session_count = 0;
    std::optional<OperationEntry> latest_write_entry;
    std::optional<OperationEntry> latest_burn_entry;
    std::optional<Session> active_session;
};

// Mirror `OperationEvidenceService.build`. The `entries` argument is
// the full append-only log; `has_unwritten` is the workspace
// presenter's "are there staged edits not yet sent to RAM?" flag.
Snapshot build(
    const std::vector<OperationEntry>& entries,
    bool has_unwritten,
    std::size_t limit = 12);

}  // namespace tuner_core::operation_evidence
