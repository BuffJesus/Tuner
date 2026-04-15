// SPDX-License-Identifier: MIT
//
// tuner_core::native_tune_writer — export/import .tuner JSON files.
// Sub-slice 77 of Phase 14 Slice 4.
//
// The .tuner format is the owned tune file: JSON with typed values,
// no page/offset concerns, no XML namespace.  This is step 1 of the
// native format migration path from docs/ux-design.md.

#pragma once

#include "local_tune_edit.hpp"
#include "operator_engine_context.hpp"

#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace tuner_core::native_tune_writer {

using local_tune_edit::Value;

struct TunerTune {
    std::string format = "tuner-tune-v1";
    std::string definition_signature;
    std::string created_iso;
    std::string modified_iso;
    // Flat name → value map.
    std::vector<std::pair<std::string, Value>> values;
    // Optional operator context.
    std::optional<operator_engine_context::OperatorEngineContext> operator_context;
    // Multi-tune slot metadata (mirrors NativeTune v1.1). Emitted only
    // when set; readers that don't understand the keys fall back to
    // slot 0 implicitly.
    std::optional<int> slot_index;
    std::optional<std::string> slot_name;
};

/// Export a TunerTune to JSON string.
std::string export_json(const TunerTune& tune);

/// Import a TunerTune from JSON string.
/// Throws std::invalid_argument on malformed input.
TunerTune import_json(const std::string& json_text);

/// Build a TunerTune from the current edit service state.
TunerTune from_edit_service(
    const local_tune_edit::EditService& edit,
    const std::string& definition_signature = "",
    const operator_engine_context::OperatorEngineContext* ctx = nullptr);

}  // namespace tuner_core::native_tune_writer
