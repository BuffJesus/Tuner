// SPDX-License-Identifier: MIT
//
// tuner_core::datalog_profile — port of DatalogProfileService.
// Sub-slice 65 of Phase 14 Slice 4.
//
// Manages datalog profiles: default creation from output channel
// definitions, priority-based channel ordering, and JSON
// serialization for the multi-profile sidecar format.  Pure logic.

#pragma once

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::datalog_profile {

struct ChannelEntry {
    std::string name;
    std::string label;
    std::string units;
    bool enabled = true;
    std::optional<int> format_digits;
};

struct Profile {
    std::string name = "Default";
    std::vector<ChannelEntry> channels;

    std::vector<ChannelEntry> enabled_channels() const {
        std::vector<ChannelEntry> out;
        for (const auto& ch : channels) if (ch.enabled) out.push_back(ch);
        return out;
    }
};

// Channel definition input for building a default profile.
struct ChannelDef {
    std::string name;
    std::string label;
    std::string units;
    std::optional<int> digits;
};

/// Build a default profile ordered by priority from channel definitions.
Profile default_profile(const std::vector<ChannelDef>& defs);

/// Return the priority rank for a channel name (lower = higher priority).
int priority_rank(const std::string& name);

/// Serialize a profile to JSON string.
std::string serialize_profile(const Profile& profile);

/// Deserialize a profile from JSON string.
Profile deserialize_profile(const std::string& json_text, const std::string& fallback_name = "Default");

/// Serialize a profile collection (multi-profile sidecar format).
std::string serialize_collection(const std::vector<Profile>& profiles, const std::string& active_name);

/// Deserialize a profile collection. Returns (profiles, active_name).
std::pair<std::vector<Profile>, std::string> deserialize_collection(const std::string& json_text);

/// Return names of enabled channels not in the available set.
std::vector<std::string> unavailable_channels(
    const Profile& profile,
    const std::vector<std::string>& available_names);

}  // namespace tuner_core::datalog_profile
