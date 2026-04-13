// SPDX-License-Identifier: MIT
//
// tuner_core::NativeFormat — C++ port of the v1 owned tune/definition
// contract (Future Phase 12). Mirrors the Python dataclasses in
// `src/tuner/domain/native_format.py` and the serialization service
// in `src/tuner/services/native_format_service.py`.
//
// Python is the oracle: every parser and serializer here must produce
// JSON byte-identical to the Python `NativeFormatService.dump_*`
// output on the same input, and parse anything that Python emits.
//
// Schema version: "1.0" — must equal NATIVE_SCHEMA_VERSION on the
// Python side. Loaders refuse files whose major version is higher
// than the bundled value; minor bumps are forward-compatible.

#pragma once

#include <filesystem>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace tuner_core {

inline constexpr const char* kNativeSchemaVersion = "1.0";

// Mirrors the Python `NativeParameter` dataclass.
struct NativeParameter {
    std::string semantic_id;
    std::string legacy_name;
    std::optional<std::string> label;
    std::optional<std::string> units;
    std::string kind = "scalar";    // "scalar" | "enum" | "bits"
    std::optional<double> min_value;
    std::optional<double> max_value;
    // Default value is intentionally untyped — the Python contract
    // permits int, float, or string. We model it as an optional
    // string and let callers parse it; v1 doesn't carry defaults
    // through any actual code path so this is structural only.
    std::optional<std::string> default_value;
};

struct NativeAxis {
    std::string semantic_id;
    std::string legacy_name;
    int length = 0;
    std::optional<std::string> units;
};

struct NativeTable {
    std::string semantic_id;
    std::string legacy_name;
    int rows = 0;
    int columns = 0;
    std::optional<std::string> label;
    std::optional<std::string> units;
    std::optional<std::string> x_axis_id;
    std::optional<std::string> y_axis_id;
};

struct NativeCurve {
    std::string semantic_id;
    std::string legacy_name;
    int point_count = 0;
    std::optional<std::string> label;
    std::optional<std::string> units;
    std::optional<std::string> x_axis_id;
};

struct NativeDefinition {
    std::string schema_version = kNativeSchemaVersion;
    std::string name;
    std::optional<std::string> firmware_signature;
    std::vector<NativeParameter> parameters;
    std::vector<NativeAxis> axes;
    std::vector<NativeTable> tables;
    std::vector<NativeCurve> curves;
};

// One value in a NativeTune. The Python contract permits scalar
// (number or string) or list-of-floats. The Python implementation
// preserves Python int vs float distinction; the C++ port stores
// integers as `double` since JSON has only one numeric type — the
// parity harness verifies the on-disk JSON matches Python output.
using NativeTuneValue = std::variant<double, std::string, std::vector<double>>;

struct NativeTune {
    std::string schema_version = kNativeSchemaVersion;
    std::optional<std::string> definition_signature;
    std::map<std::string, NativeTuneValue> values;  // ordered for stable JSON output
};

// Thrown when a native file's schema_version is missing, malformed,
// or newer than the bundled major version.
class NativeFormatVersionError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// ---------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------

// JSON dump matching Python `NativeFormatService.dump_definition()`
// with the default `indent=2` and `sort_keys=False`.
std::string dump_definition(const NativeDefinition& definition, int indent = 2);
std::string dump_tune(const NativeTune& tune, int indent = 2);

// JSON load with the same schema-version gating as the Python loader.
NativeDefinition load_definition(std::string_view text);
NativeTune load_tune(std::string_view text);

NativeDefinition load_definition_file(const std::filesystem::path& path);
NativeTune load_tune_file(const std::filesystem::path& path);

// ---------------------------------------------------------------------
// v2 full-definition format — serializes NativeEcuDefinition directly
// so the app can load from .tunerdef without parsing INI.
// Schema version: "2.0". Accepts JSON5 on input (via strip_json5).
// ---------------------------------------------------------------------

}  // namespace tuner_core

// Forward-declare the compiler header types for v2 serialization.
// Consumers that call these must include ecu_definition_compiler.hpp.
#include "tuner_core/ecu_definition_compiler.hpp"

namespace tuner_core {

// Serialize a full NativeEcuDefinition to JSON (schema 2.0).
// Output is strict JSON with indent; input accepts JSON5 comments.
std::string dump_definition_v2(const NativeEcuDefinition& def, int indent = 2);

// Load a NativeEcuDefinition from JSON5 text (schema 2.0).
// Falls through to v1 loader if schema_version is "1.0".
NativeEcuDefinition load_definition_v2(std::string_view text);
NativeEcuDefinition load_definition_v2_file(const std::filesystem::path& path);

}  // namespace tuner_core
