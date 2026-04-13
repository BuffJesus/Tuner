// SPDX-License-Identifier: MIT
//
// tuner_core::evidence_replay_formatter — port of
// EvidenceReplayFormatterService.  Sub-slice 60 of Phase 14 Slice 4.
//
// Formats an EvidenceReplaySnapshot to multi-line text or JSON.

#pragma once

#include "evidence_replay.hpp"

#include <string>

namespace tuner_core::evidence_replay_formatter {

std::string to_text(const evidence_replay::Snapshot& snap);
std::string to_json(const evidence_replay::Snapshot& snap);

}  // namespace tuner_core::evidence_replay_formatter
