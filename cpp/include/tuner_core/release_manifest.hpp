// SPDX-License-Identifier: MIT
//
// tuner_core::release_manifest — port of `ReleaseManifestService`.
// Tenth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Parses the `release_manifest.json` document that ships alongside
// each Speeduino firmware release. Each `firmware` entry describes a
// single .hex/.bin/.srec artifact plus its companion definition and
// tune files. The desktop uses this to populate the Flash tab's
// firmware picker without re-scanning the release directory.

#pragma once

#include "tuner_core/board_detection.hpp"

#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::release_manifest {

enum class ArtifactKind {
    STANDARD,
    DIAGNOSTIC,
};

// Stringify an `ArtifactKind` to the same identifier the Python
// `FirmwareArtifactKind` StrEnum produces (`"standard"` /
// `"diagnostic"`).
std::string_view to_string(ArtifactKind kind) noexcept;

struct FirmwareEntry {
    std::string file_name;
    std::optional<board_detection::BoardFamily> board_family;
    std::optional<std::string> version_label;
    bool is_experimental = false;
    ArtifactKind artifact_kind = ArtifactKind::STANDARD;
    bool preferred = false;
    std::optional<std::string> definition_file_name;
    std::optional<std::string> tune_file_name;
    std::optional<std::string> firmware_signature;
};

struct Manifest {
    std::vector<FirmwareEntry> firmware;
};

// Parse a `release_manifest.json` payload from in-memory text. Throws
// `std::runtime_error` for malformed JSON, missing/empty `file`
// fields, or unknown `board_family` / `artifact_kind` enum values.
Manifest parse_manifest_text(std::string_view text);

// Convenience: read `<release_root>/release_manifest.json` from disk
// and parse it. Returns nullopt when the file does not exist.
std::optional<Manifest> load_manifest(const std::filesystem::path& release_root);

// File name the loader looks for inside the release directory.
inline constexpr std::string_view kManifestFileName = "release_manifest.json";

}  // namespace tuner_core::release_manifest
