// SPDX-License-Identifier: MIT
//
// tuner_core::hardware_presets — curated hardware preset catalog.
// Fifty-second sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Ignition coil presets with sourced dwell values. Pure static data.

#pragma once

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::hardware_presets {

struct IgnitionPreset {
    std::string key;
    std::string label;
    std::string description;
    double running_dwell_ms = 0;
    double cranking_dwell_ms = 0;
    std::string source_note;
    std::string source_url;  // empty = no URL
};

const std::vector<IgnitionPreset>& ignition_presets();
const IgnitionPreset* ignition_preset_by_key(const std::string& key);
std::string source_confidence_label(const std::string& source_note,
                                     const std::string& source_url);

}  // namespace tuner_core::hardware_presets
