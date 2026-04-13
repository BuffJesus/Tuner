// SPDX-License-Identifier: MIT
//
// tuner_core::legacy_project_file — pure-logic port of the legacy
// `.project` text file format parser/writer used before the JSON
// `.tunerproj` native format. Mirrors:
//
//   - `tuner.parsers.common.parse_key_value_lines`
//   - `tuner.parsers.project_parser.ProjectParser._parse_default_connection_profile`
//   - `tuner.services.project_service.ProjectService._sanitize_name`
//   - the line builder body of `ProjectService.save_project`
//
// I/O — Path resolution, mkdir, file read/write, the
// `_resolve_optional_path` arithmetic that needs the project file's
// parent directory — stays Python where the orchestration loop lives.
// This module owns the byte-on-disk shape of the legacy format and
// the deterministic helpers behind it.

#pragma once

#include <map>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::legacy_project_file {

// Mirrors the Python `ConnectionProfile` dataclass. Optional ints
// stay `std::optional<int>`; optional strings stay `std::optional<string>`
// because the empty-string-vs-missing distinction matters for the
// per-profile field skip rules in the writer.
struct ConnectionProfile {
    std::string name;
    std::string transport;
    std::optional<std::string> protocol;
    std::optional<std::string> host;
    std::optional<int> port;
    std::optional<std::string> serial_port;
    std::optional<int> baud_rate;
};

// Mirrors the subset of `Project` that the legacy text format
// actually serializes. Path values are passed in as already-resolved
// strings — the C++ side doesn't touch the filesystem.
struct LegacyProjectModel {
    std::string name;
    std::optional<std::string> ecu_definition_path;
    std::optional<std::string> tune_file_path;
    std::vector<std::string> dashboards;
    std::vector<std::string> active_settings;
    std::vector<ConnectionProfile> connection_profiles;
    // Free-form key=value pairs the parser preserved from the
    // original file. The writer round-trips these (sorted) after
    // skipping any keys that the structured fields above already
    // own (`projectName`, `ecuDefinition`, `tuneFile`, `dashboards`,
    // `activeSettings`, and any `connection.default.*` key).
    std::map<std::string, std::string> metadata;
};

// `parse_key_value_lines` parity. Strips leading/trailing whitespace
// from each line, drops empty lines and lines starting with `#`,
// `;`, or `//`. Splits on the first `=`; falls back to `:` if no
// `=` exists. Trims keys and values. Returns the resulting
// dictionary in insertion order via `std::map` for deterministic
// iteration (Python's dict preserves insertion order, but the
// downstream `save_project` already sorts metadata before writing
// so insertion-vs-sorted-order doesn't matter for round-trip).
std::map<std::string, std::string> parse_key_value_lines(
    const std::vector<std::string>& lines);

// `ProjectParser._parse_default_connection_profile` parity.
// Returns nullopt when no `connection.default.*` keys exist.
// Otherwise builds a profile from the keys, parsing `port` and
// `baudRate` as ints. On parse failure (non-numeric value), the
// corresponding optional stays unset (matches Python's `try/except
// ValueError: port = None`).
std::optional<ConnectionProfile> parse_default_connection_profile(
    const std::map<std::string, std::string>& metadata);

// `ProjectService._sanitize_name` parity. Each character that is
// not alphanumeric, `-`, or `_` becomes `_`. After substitution,
// trim leading and trailing `_` characters. Empty result allowed —
// the caller decides the fallback (`"project"` in the Python code).
std::string sanitize_project_name(std::string_view name);

// `ProjectService.save_project` line builder body, isolated from
// the file write. Produces the full text contents (lines joined
// with `\n` plus a trailing `\n`) of a legacy `.project` file.
// Path values inside `model` should already be resolved relative
// to the project file's parent directory — `_relative_path` is the
// caller's job since it depends on the actual filesystem layout.
std::string format_legacy_project_file(const LegacyProjectModel& model);

}  // namespace tuner_core::legacy_project_file
