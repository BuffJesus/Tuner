// SPDX-License-Identifier: MIT
//
// Implementation of `legacy_project_file.hpp`.

#include "tuner_core/legacy_project_file.hpp"

#include <algorithm>
#include <cctype>
#include <set>
#include <stdexcept>
#include <string>

namespace tuner_core::legacy_project_file {

namespace {

std::string strip(std::string_view s) {
    std::size_t start = 0;
    while (start < s.size() && std::isspace(static_cast<unsigned char>(s[start]))) ++start;
    std::size_t end = s.size();
    while (end > start && std::isspace(static_cast<unsigned char>(s[end - 1]))) --end;
    return std::string(s.substr(start, end - start));
}

bool starts_with(std::string_view s, std::string_view prefix) {
    return s.size() >= prefix.size() && s.substr(0, prefix.size()) == prefix;
}

bool is_comment(const std::string& line) {
    return starts_with(line, "#") || starts_with(line, ";") || starts_with(line, "//");
}

std::optional<int> parse_int_or_null(const std::string& raw) {
    // Mirrors Python's `int(...)` strictly: leading/trailing whitespace
    // is OK, the body must be all digits (with an optional leading sign).
    std::string s = strip(raw);
    if (s.empty()) return std::nullopt;
    std::size_t i = 0;
    if (s[0] == '+' || s[0] == '-') {
        if (s.size() == 1) return std::nullopt;
        ++i;
    }
    for (; i < s.size(); ++i) {
        if (!std::isdigit(static_cast<unsigned char>(s[i]))) return std::nullopt;
    }
    try {
        return std::stoi(s);
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<std::string> get_optional(
    const std::map<std::string, std::string>& m, const std::string& key) {
    auto it = m.find(key);
    if (it == m.end()) return std::nullopt;
    return it->second;
}

}  // namespace

std::map<std::string, std::string> parse_key_value_lines(
    const std::vector<std::string>& lines) {
    std::map<std::string, std::string> data;
    for (const auto& raw_line : lines) {
        std::string line = strip(raw_line);
        if (line.empty() || is_comment(line)) continue;
        std::size_t sep = line.find('=');
        if (sep == std::string::npos) sep = line.find(':');
        if (sep == std::string::npos) continue;
        std::string key = strip(line.substr(0, sep));
        std::string value = strip(line.substr(sep + 1));
        data[key] = value;
    }
    return data;
}

std::optional<ConnectionProfile> parse_default_connection_profile(
    const std::map<std::string, std::string>& metadata) {
    static const std::string prefix = "connection.default.";
    std::map<std::string, std::string> relevant;
    for (const auto& [k, v] : metadata) {
        if (starts_with(k, prefix)) {
            relevant[k.substr(prefix.size())] = v;
        }
    }
    if (relevant.empty()) return std::nullopt;

    ConnectionProfile profile;
    profile.name = relevant.count("name") ? relevant["name"] : "Default";
    profile.transport = relevant.count("transport") ? relevant["transport"] : "mock";
    if (auto v = get_optional(relevant, "protocol"))   profile.protocol = *v;
    if (auto v = get_optional(relevant, "host"))       profile.host = *v;
    if (auto v = get_optional(relevant, "serialPort")) profile.serial_port = *v;
    if (auto v = get_optional(relevant, "port"))       profile.port = parse_int_or_null(*v);
    if (auto v = get_optional(relevant, "baudRate"))   profile.baud_rate = parse_int_or_null(*v);
    return profile;
}

std::string sanitize_project_name(std::string_view name) {
    // Strip leading/trailing whitespace before substitution (Python
    // calls `name.strip()` first).
    std::string s = strip(name);
    std::string result;
    result.reserve(s.size());
    for (char c : s) {
        const unsigned char uc = static_cast<unsigned char>(c);
        if (std::isalnum(uc) || c == '-' || c == '_') {
            result.push_back(c);
        } else {
            result.push_back('_');
        }
    }
    // Trim leading and trailing underscores from the substituted form.
    std::size_t start = 0;
    while (start < result.size() && result[start] == '_') ++start;
    std::size_t end = result.size();
    while (end > start && result[end - 1] == '_') --end;
    return result.substr(start, end - start);
}

std::string format_legacy_project_file(const LegacyProjectModel& model) {
    std::vector<std::string> lines;
    lines.reserve(16 + model.metadata.size());
    lines.push_back("projectName=" + model.name);
    if (model.ecu_definition_path)
        lines.push_back("ecuDefinition=" + *model.ecu_definition_path);
    if (model.tune_file_path)
        lines.push_back("tuneFile=" + *model.tune_file_path);
    if (!model.dashboards.empty()) {
        std::string joined;
        for (std::size_t i = 0; i < model.dashboards.size(); ++i) {
            if (i > 0) joined.push_back(',');
            joined += model.dashboards[i];
        }
        lines.push_back("dashboards=" + joined);
    }
    if (!model.active_settings.empty()) {
        // Python: `','.join(sorted(project.active_settings))` —
        // active_settings is a frozenset so iteration order is
        // arbitrary; the writer sorts before joining.
        std::vector<std::string> sorted = model.active_settings;
        std::sort(sorted.begin(), sorted.end());
        std::string joined;
        for (std::size_t i = 0; i < sorted.size(); ++i) {
            if (i > 0) joined.push_back(',');
            joined += sorted[i];
        }
        lines.push_back("activeSettings=" + joined);
    }
    if (!model.connection_profiles.empty()) {
        // Python only writes the first profile (`profile = project.connection_profiles[0]`).
        const auto& p = model.connection_profiles[0];
        lines.push_back("connection.default.name=" + p.name);
        lines.push_back("connection.default.transport=" + p.transport);
        if (p.protocol)    lines.push_back("connection.default.protocol=" + *p.protocol);
        if (p.host)        lines.push_back("connection.default.host=" + *p.host);
        if (p.port)        lines.push_back("connection.default.port=" + std::to_string(*p.port));
        if (p.serial_port) lines.push_back("connection.default.serialPort=" + *p.serial_port);
        if (p.baud_rate)   lines.push_back("connection.default.baudRate=" + std::to_string(*p.baud_rate));
    }
    // Spill remaining metadata in sorted order, skipping the keys
    // owned by structured fields above.
    static const std::set<std::string> reserved = {
        "projectName", "ecuDefinition", "tuneFile", "dashboards", "activeSettings",
    };
    for (const auto& [key, value] : model.metadata) {
        if (reserved.count(key)) continue;
        if (starts_with(key, "connection.default.")) continue;
        lines.push_back(key + "=" + value);
    }
    std::string out;
    for (std::size_t i = 0; i < lines.size(); ++i) {
        if (i > 0) out.push_back('\n');
        out += lines[i];
    }
    out.push_back('\n');
    return out;
}

}  // namespace tuner_core::legacy_project_file
