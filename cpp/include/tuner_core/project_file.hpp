// SPDX-License-Identifier: MIT
//
// tuner_core::project_file — .tunerproj JSON project metadata.
// Sub-slice 78 of Phase 14 Slice 4.
//
// The project file ties a definition + tune + settings together.
// This is step 2 of the native format migration path.

#pragma once

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::project_file {

struct Project {
    std::string format = "tuner-project-v1";
    std::string name;
    std::string definition_path;
    std::string tune_path;
    std::vector<std::string> active_settings;
    std::string dashboard_layout = "default";
    std::vector<std::string> logging_profiles;
    std::string last_connected;           // e.g. "COM3:115200:SPEEDUINO"
    std::string calibration_intent;       // e.g. "drivable_base"
    std::string last_opened_iso;
    std::string firmware_signature;
};

/// Export a Project to JSON string.
std::string export_json(const Project& project);

/// Import a Project from JSON string.
Project import_json(const std::string& json_text);

}  // namespace tuner_core::project_file
