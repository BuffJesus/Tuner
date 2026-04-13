// SPDX-License-Identifier: MIT
//
// tuner_core::release_manifest implementation. Uses the vendored
// nlohmann/json header for parsing.

#include "tuner_core/release_manifest.hpp"

#include "nlohmann/json.hpp"

#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace tuner_core::release_manifest {

namespace {

using json = nlohmann::json;
namespace bd = board_detection;

std::string_view trim_view(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
        s.remove_prefix(1);
    }
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
        s.remove_suffix(1);
    }
    return s;
}

// Mirror Python `_optional_string`: returns nullopt for null inputs,
// trimmed-non-empty strings otherwise. Throws on non-string inputs
// (mirroring Python's `ValueError`).
std::optional<std::string> optional_string(const json& value) {
    if (value.is_null()) return std::nullopt;
    if (!value.is_string()) {
        throw std::runtime_error(
            "release_manifest.json string fields must contain strings.");
    }
    auto trimmed = trim_view(value.get<std::string>());
    if (trimmed.empty()) return std::nullopt;
    return std::string(trimmed);
}

std::optional<bd::BoardFamily> parse_board_family(const json& value) {
    auto name = optional_string(value);
    if (!name.has_value()) return std::nullopt;
    if (*name == "ATMEGA2560")    return bd::BoardFamily::ATMEGA2560;
    if (*name == "TEENSY35")      return bd::BoardFamily::TEENSY35;
    if (*name == "TEENSY36")      return bd::BoardFamily::TEENSY36;
    if (*name == "TEENSY41")      return bd::BoardFamily::TEENSY41;
    if (*name == "STM32F407_DFU") return bd::BoardFamily::STM32F407_DFU;
    throw std::runtime_error(
        "Unknown board_family in release_manifest.json: " + *name);
}

ArtifactKind parse_artifact_kind(const json& value) {
    auto name = optional_string(value);
    if (!name.has_value()) return ArtifactKind::STANDARD;
    if (*name == "standard")   return ArtifactKind::STANDARD;
    if (*name == "diagnostic") return ArtifactKind::DIAGNOSTIC;
    throw std::runtime_error(
        "Unknown artifact_kind in release_manifest.json: " + *name);
}

FirmwareEntry parse_firmware_entry(const json& payload) {
    if (!payload.is_object()) {
        throw std::runtime_error(
            "release_manifest.json firmware entries must be objects.");
    }
    FirmwareEntry e;

    auto file_field = payload.value("file", json{});
    if (!file_field.is_string()) {
        throw std::runtime_error(
            "release_manifest.json firmware entries require a non-empty 'file' value.");
    }
    auto file_str = file_field.get<std::string>();
    auto file_trimmed = trim_view(file_str);
    if (file_trimmed.empty()) {
        throw std::runtime_error(
            "release_manifest.json firmware entries require a non-empty 'file' value.");
    }
    e.file_name = std::string(file_trimmed);

    e.board_family = parse_board_family(payload.value("board_family", json{}));
    e.version_label = optional_string(payload.value("version", json{}));

    auto exp = payload.value("is_experimental", json{false});
    e.is_experimental = exp.is_boolean() ? exp.get<bool>() : false;

    e.artifact_kind = parse_artifact_kind(payload.value("artifact_kind", json{}));

    auto pref = payload.value("preferred", json{false});
    e.preferred = pref.is_boolean() ? pref.get<bool>() : false;

    e.definition_file_name = optional_string(payload.value("definition_file", json{}));
    e.tune_file_name = optional_string(payload.value("tune_file", json{}));
    e.firmware_signature = optional_string(payload.value("firmware_signature", json{}));

    return e;
}

}  // namespace

std::string_view to_string(ArtifactKind kind) noexcept {
    return kind == ArtifactKind::DIAGNOSTIC ? "diagnostic" : "standard";
}

Manifest parse_manifest_text(std::string_view text) {
    json payload;
    try {
        payload = json::parse(text);
    } catch (const json::parse_error& e) {
        throw std::runtime_error(
            std::string("release_manifest.json parse error: ") + e.what());
    }

    Manifest m;
    auto firmware_field = payload.value("firmware", json::array());
    if (!firmware_field.is_array()) {
        throw std::runtime_error(
            "release_manifest.json field 'firmware' must be a list.");
    }
    for (const auto& item : firmware_field) {
        m.firmware.push_back(parse_firmware_entry(item));
    }
    return m;
}

std::optional<Manifest> load_manifest(const std::filesystem::path& release_root) {
    auto manifest_path = std::filesystem::weakly_canonical(
        release_root / std::string(kManifestFileName));
    if (!std::filesystem::is_regular_file(manifest_path)) return std::nullopt;
    std::ifstream stream(manifest_path, std::ios::binary);
    if (!stream) return std::nullopt;
    std::ostringstream buffer;
    buffer << stream.rdbuf();
    return parse_manifest_text(buffer.str());
}

}  // namespace tuner_core::release_manifest
