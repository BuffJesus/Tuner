// SPDX-License-Identifier: MIT
//
// tuner_core::evidence_replay_comparison — port of the channel-diff
// logic in `EvidenceReplayComparisonService.build`. Fifteenth
// sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// The Python service has two early-out branches: snapshots-are-None
// and snapshots-are-equal. Both are the caller's responsibility on
// the C++ side — `compare_runtime_channels` only models the channel
// diff itself, which is the load-bearing logic. The full snapshot
// shape (16 fields incl. timestamps and assorted text blobs) does
// not need to land in C++ for this slice.

#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::evidence_replay_comparison {

// Mirror of `EvidenceReplayChannel` but without the Python-specific
// fields. Names compare case-insensitively (Python lowercases both
// sides for the lookup).
struct Channel {
    std::string name;
    double value = 0.0;
    std::optional<std::string> units;
};

struct Delta {
    std::string name;
    double previous_value = 0.0;
    double current_value = 0.0;
    double delta_value = 0.0;
    std::optional<std::string> units;
};

struct Comparison {
    std::string summary_text;
    std::string detail_text;
    // Top 4 channel deltas, sorted by `abs(delta_value)` descending.
    std::vector<Delta> changed_channels;
};

// Mirror `EvidenceReplayComparisonService.build`'s channel diff:
//   - lookup table on lowercased names
//   - if `relevant_channel_names` is empty, use every current channel
//   - skip channels missing from either side
//   - skip deltas with `|delta| < 1e-9`
//   - return nullopt when no surviving deltas remain
//   - keep the top 4 by absolute delta and format the summary/detail
//
// The full-snapshot equality early-out is the caller's responsibility.
std::optional<Comparison> compare_runtime_channels(
    const std::vector<Channel>& baseline_channels,
    const std::vector<Channel>& current_channels,
    const std::vector<std::string>& relevant_channel_names);

}  // namespace tuner_core::evidence_replay_comparison
