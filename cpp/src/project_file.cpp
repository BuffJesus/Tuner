// SPDX-License-Identifier: MIT
#include "tuner_core/project_file.hpp"

#include <nlohmann/json.hpp>
#include <stdexcept>
#include <cctype>

namespace tuner_core::project_file {

std::string_view firmware_family_to_string(FirmwareFamily family) noexcept {
    switch (family) {
        case FirmwareFamily::SPEEDUINO: return "speeduino";
        case FirmwareFamily::RUSEFI:    return "rusefi";
    }
    return "speeduino";
}

FirmwareFamily firmware_family_from_string(std::string_view s) noexcept {
    // Case-insensitive compare. "speeduino" / "rusefi" are the
    // canonical wire forms; anything else falls back to SPEEDUINO
    // so legacy projects (no field) and typos load safely.
    std::string lower;
    lower.reserve(s.size());
    for (char c : s) lower.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    if (lower == "rusefi")    return FirmwareFamily::RUSEFI;
    if (lower == "speeduino") return FirmwareFamily::SPEEDUINO;
    return FirmwareFamily::SPEEDUINO;
}

std::string export_json(const Project& p) {
    nlohmann::ordered_json j;
    j["format"] = p.format;
    j["name"] = p.name;
    // firmware_family is always emitted — the project's tilt is
    // load-bearing for protocol selection and shouldn't be
    // implicit. Phase 18 schema addition.
    j["firmware_family"] = std::string(firmware_family_to_string(p.firmware_family));
    if (!p.definition_path.empty()) j["definition_path"] = p.definition_path;
    if (!p.tune_path.empty()) j["tune_path"] = p.tune_path;
    if (!p.active_settings.empty()) {
        auto arr = nlohmann::ordered_json::array();
        for (const auto& s : p.active_settings) arr.push_back(s);
        j["active_settings"] = arr;
    }
    j["dashboard_layout"] = p.dashboard_layout;
    if (!p.logging_profiles.empty()) {
        auto arr = nlohmann::ordered_json::array();
        for (const auto& s : p.logging_profiles) arr.push_back(s);
        j["logging_profiles"] = arr;
    }
    if (!p.last_connected.empty()) j["last_connected"] = p.last_connected;
    if (!p.calibration_intent.empty()) j["calibration_intent"] = p.calibration_intent;
    if (!p.last_opened_iso.empty()) j["last_opened"] = p.last_opened_iso;
    if (!p.firmware_signature.empty()) j["firmware_signature"] = p.firmware_signature;
    return j.dump(2);
}

Project import_json(const std::string& json_text) {
    nlohmann::json j;
    try { j = nlohmann::json::parse(json_text); }
    catch (...) { throw std::invalid_argument("Invalid .tunerproj JSON"); }
    if (!j.is_object()) throw std::invalid_argument("Root must be an object");

    Project p;
    p.format = j.value("format", "tuner-project-v1");
    p.name = j.value("name", "");
    // Forward-compatible: missing field → SPEEDUINO default.
    p.firmware_family = firmware_family_from_string(
        j.value("firmware_family", std::string("speeduino")));
    p.definition_path = j.value("definition_path", j.value("definition_file", ""));
    p.tune_path = j.value("tune_path", j.value("tune_file", ""));
    if (j.contains("active_settings") && j["active_settings"].is_array())
        for (const auto& s : j["active_settings"]) p.active_settings.push_back(s.get<std::string>());
    p.dashboard_layout = j.value("dashboard_layout", "default");
    if (j.contains("logging_profiles") && j["logging_profiles"].is_array())
        for (const auto& s : j["logging_profiles"]) p.logging_profiles.push_back(s.get<std::string>());
    p.last_connected = j.value("last_connected", "");
    p.calibration_intent = j.value("calibration_intent", "");
    p.last_opened_iso = j.value("last_opened", "");
    p.firmware_signature = j.value("firmware_signature", "");
    return p;
}

}  // namespace tuner_core::project_file
