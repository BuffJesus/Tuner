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
#include <string_view>
#include <vector>

namespace tuner_core::project_file {

// Primary firmware family the project targets. Added Phase 18 to
// route protocol selection, INI signature sniffing, and operator
// workflow defaults. Default `SPEEDUINO` matches existing
// projects on load (when the JSON field is absent).
enum class FirmwareFamily {
    SPEEDUINO = 0,
    RUSEFI    = 1,
};

// JSON-string form. Lowercase wire form for portability; the
// enum name stays uppercase by C++ convention.
std::string_view firmware_family_to_string(FirmwareFamily family) noexcept;

// Parse the wire form (case-insensitive). Returns SPEEDUINO for
// any unrecognised value so legacy / mistyped files load safely.
FirmwareFamily firmware_family_from_string(std::string_view s) noexcept;

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
    FirmwareFamily firmware_family = FirmwareFamily::SPEEDUINO;
};

/// Export a Project to JSON string.
std::string export_json(const Project& project);

/// Import a Project from JSON string.
Project import_json(const std::string& json_text);

}  // namespace tuner_core::project_file
