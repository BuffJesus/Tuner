// SPDX-License-Identifier: MIT
#include "tuner_core/project_file.hpp"

#include <nlohmann/json.hpp>
#include <stdexcept>

namespace tuner_core::project_file {

std::string export_json(const Project& p) {
    nlohmann::ordered_json j;
    j["format"] = p.format;
    j["name"] = p.name;
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
