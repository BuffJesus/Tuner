// SPDX-License-Identifier: MIT
//
// tuner_core::firmware_catalog — port of FirmwareCatalogService scoring
// and board detection.  Sub-slice 66 of Phase 14 Slice 4.
//
// The scan_release filesystem walk stays in the caller (Python or Qt).
// This slice ports the pure-logic parts: board detection from filename,
// entry scoring for firmware suggestion, and version label extraction.

#pragma once

#include <optional>
#include <string>

namespace tuner_core::firmware_catalog {

enum class BoardFamily {
    ATMEGA2560, TEENSY35, TEENSY36, TEENSY41, STM32F407_DFU, UNKNOWN,
};

enum class ArtifactKind { STANDARD, DIAGNOSTIC };

struct CatalogEntry {
    std::string filename;
    BoardFamily board_family = BoardFamily::UNKNOWN;
    std::string version_label;
    bool is_experimental = false;
    ArtifactKind artifact_kind = ArtifactKind::STANDARD;
    bool preferred = false;
    std::string firmware_signature;
};

struct ScoringContext {
    BoardFamily preferred_board = BoardFamily::UNKNOWN;
    std::string definition_signature;
    std::string definition_name;
    std::string tune_signature;
    std::string tune_firmware_info;
    std::string tune_filename;
    bool include_diagnostic = false;
};

/// Detect board family from a lowercased firmware filename.
BoardFamily board_from_filename(const std::string& name);

/// Extract version label (e.g. "v2.0.1") from a filename.
std::optional<std::string> version_from_filename(const std::string& name);

/// Score a catalog entry for firmware suggestion.
/// Returns 0 if the entry should be excluded, >0 otherwise (higher = better).
int score_entry(const CatalogEntry& entry, const ScoringContext& ctx);

}  // namespace tuner_core::firmware_catalog
