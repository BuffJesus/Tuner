// SPDX-License-Identifier: MIT
//
// tuner_core::flash_preflight — port of `FlashPreflightService.validate`
// (warning rules) and `_signature_family`. Twentieth sub-slice of the
// Phase 14 workspace-services port (Slice 4).
//
// The Python service combines two concerns: (1) filesystem checks
// (does the firmware file exist?) and (2) consistency rules between
// the selected firmware, the loaded definition, the loaded tune, and
// the live controller capabilities. This C++ slice ports concern (2)
// — the warning logic — and leaves the filesystem checks to the
// caller. The caller passes a `PreflightInputs` shell carrying every
// field the rules read, and gets back the same errors / warnings the
// Python service emits.

#pragma once

#include "tuner_core/board_detection.hpp"

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::flash_preflight {

using BoardFamily = board_detection::BoardFamily;

struct FirmwareEntryInputs {
    std::optional<BoardFamily> board_family;
    std::optional<std::string> firmware_signature;
    std::optional<std::string> version_label;
    // Basename of the paired tune file (e.g. `"BaseStartup.msq"`),
    // not the full path. The Python service uses
    // `entry.tune_path.name` for the comparison.
    std::optional<std::string> tune_path_basename;
    bool is_experimental = false;
};

struct PreflightInputs {
    // Board selection / detection
    std::optional<BoardFamily> selected_board;
    std::optional<BoardFamily> detected_board;
    // Firmware catalog entry for the selected file
    FirmwareEntryInputs firmware_entry;
    // Loaded ECU definition
    std::optional<std::string> definition_signature;
    // Loaded tune file
    std::optional<std::string> tune_signature;
    std::optional<std::string> tune_firmware_info;
    std::optional<std::string> tune_source_basename;
    // Live firmware capability fact (nullopt when no live session)
    std::optional<bool> experimental_u16p2;
    // Connected controller's firmware signature
    std::optional<std::string> connected_firmware_signature;
};

struct Report {
    bool ok = true;
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
};

// Mirror `_signature_family`. Returns the family code for a known
// signature, or nullopt for unknown / empty input.
std::optional<std::string> signature_family(std::string_view value);

// Run the warning-rule pass. Mirrors the *post-filesystem* portion of
// `FlashPreflightService.validate`: caller has already verified the
// firmware file exists (errors for missing files are the caller's job).
Report validate(const PreflightInputs& inputs);

}  // namespace tuner_core::flash_preflight
