// SPDX-License-Identifier: MIT
//
// tuner_core::native_definition_writer — .tunerdef JSON definition export.
// Sub-slice 79 of Phase 14 Slice 4.
//
// Exports the compiled NativeEcuDefinition to the .tunerdef JSON format.
// This is step 3 (final) of the native format migration path.
// No page/offset, no lastOffset, no #if/#else — just semantic parameters.

#pragma once

#include "ecu_definition_compiler.hpp"

#include <string>

namespace tuner_core::native_definition_writer {

/// Export a compiled EcuDefinition to .tunerdef JSON.
std::string export_json(const NativeEcuDefinition& definition,
                         const std::string& firmware_name = "speeduino",
                         const std::string& version = "");

/// Validate that a .tunerdef JSON string parses successfully.
/// Returns empty string on success, error message on failure.
std::string validate_json(const std::string& json_text);

}  // namespace tuner_core::native_definition_writer
