// SPDX-License-Identifier: MIT
#include "tuner_core/datalog_profile.hpp"

#include <nlohmann/json.hpp>
#include <algorithm>
#include <cctype>
#include <set>
#include <string>

namespace tuner_core::datalog_profile {

namespace {

const std::vector<std::string> PRIORITY_PREFIXES = {
    "rpm", "map", "tps", "afr", "lambda", "coolant", "iat",
    "battery", "advance", "ve", "dwell", "pulsewidth", "pw",
    "ego", "o2", "fuel",
};

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

}  // namespace

int priority_rank(const std::string& name) {
    std::string lower = to_lower(name);
    for (size_t i = 0; i < PRIORITY_PREFIXES.size(); ++i) {
        if (lower.rfind(PRIORITY_PREFIXES[i], 0) == 0) return static_cast<int>(i);
    }
    return static_cast<int>(PRIORITY_PREFIXES.size());
}

Profile default_profile(const std::vector<ChannelDef>& defs) {
    if (defs.empty()) return {"Default", {}};
    std::vector<ChannelEntry> entries;
    for (const auto& d : defs) {
        ChannelEntry e;
        e.name = d.name;
        e.label = d.label.empty() ? d.name : d.label;
        e.units = d.units;
        e.enabled = true;
        e.format_digits = d.digits;
        entries.push_back(std::move(e));
    }
    std::stable_sort(entries.begin(), entries.end(),
        [](const ChannelEntry& a, const ChannelEntry& b) {
            return priority_rank(a.name) < priority_rank(b.name);
        });
    return {"Default", std::move(entries)};
}

std::string serialize_profile(const Profile& profile) {
    nlohmann::ordered_json j;
    j["name"] = profile.name;
    nlohmann::ordered_json channels = nlohmann::ordered_json::array();
    for (const auto& ch : profile.channels) {
        nlohmann::ordered_json c;
        c["name"] = ch.name;
        if (!ch.label.empty()) c["label"] = ch.label;
        if (!ch.units.empty()) c["units"] = ch.units;
        c["enabled"] = ch.enabled;
        if (ch.format_digits) c["format_digits"] = *ch.format_digits;
        channels.push_back(c);
    }
    j["channels"] = channels;
    return j.dump(2);
}

Profile deserialize_profile(const std::string& json_text, const std::string& fallback_name) {
    nlohmann::json j;
    try { j = nlohmann::json::parse(json_text); } catch (...) { return {fallback_name, {}}; }
    if (!j.is_object()) return {fallback_name, {}};

    Profile p;
    p.name = j.value("name", fallback_name);
    if (j.contains("channels") && j["channels"].is_array()) {
        for (const auto& ch : j["channels"]) {
            ChannelEntry e;
            e.name = ch.value("name", "");
            e.label = ch.value("label", "");
            e.units = ch.value("units", "");
            e.enabled = ch.value("enabled", true);
            if (ch.contains("format_digits") && !ch["format_digits"].is_null())
                e.format_digits = ch["format_digits"].get<int>();
            p.channels.push_back(std::move(e));
        }
    }
    return p;
}

std::string serialize_collection(const std::vector<Profile>& profiles, const std::string& active_name) {
    nlohmann::ordered_json j;
    j["version"] = 1;
    j["active"] = active_name;
    nlohmann::ordered_json arr = nlohmann::ordered_json::array();
    for (const auto& p : profiles) {
        arr.push_back(nlohmann::ordered_json::parse(serialize_profile(p)));
    }
    j["profiles"] = arr;
    return j.dump(2);
}

std::pair<std::vector<Profile>, std::string> deserialize_collection(const std::string& json_text) {
    nlohmann::json j;
    try { j = nlohmann::json::parse(json_text); } catch (...) { return {{{"Default", {}}}, "Default"}; }
    if (!j.is_object()) return {{{"Default", {}}}, "Default"};

    if (j.contains("profiles") && j["profiles"].is_array()) {
        std::vector<Profile> profiles;
        for (const auto& p : j["profiles"]) {
            profiles.push_back(deserialize_profile(p.dump()));
        }
        if (profiles.empty()) profiles.push_back({"Default", {}});
        std::string active = j.value("active", profiles[0].name);
        return {std::move(profiles), active};
    }
    // Old single-profile format.
    auto p = deserialize_profile(json_text);
    return {{p}, p.name};
}

std::vector<std::string> unavailable_channels(
    const Profile& profile,
    const std::vector<std::string>& available_names)
{
    std::set<std::string> avail(available_names.begin(), available_names.end());
    std::vector<std::string> missing;
    for (const auto& ch : profile.channels) {
        if (ch.enabled && avail.find(ch.name) == avail.end())
            missing.push_back(ch.name);
    }
    return missing;
}

}  // namespace tuner_core::datalog_profile
