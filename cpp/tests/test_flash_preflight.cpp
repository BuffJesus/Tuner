// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::flash_preflight.

#include "doctest.h"

#include "tuner_core/flash_preflight.hpp"

using namespace tuner_core::flash_preflight;
using BoardFamily = tuner_core::board_detection::BoardFamily;

namespace {

bool has_substring(const std::vector<std::string>& haystack, std::string_view needle) {
    for (const auto& s : haystack) {
        if (s.find(needle) != std::string::npos) return true;
    }
    return false;
}

}  // namespace

// ---------------------------------------------------------------------------
// signature_family
// ---------------------------------------------------------------------------

TEST_CASE("signature_family: known family codes") {
    CHECK(signature_family("speeduino 202501-T41-U16P2").value() == "U16P2");
    CHECK(signature_family("speeduino 202501-T41").value() == "T41");
    CHECK(signature_family("speeduino 202501-T36").value() == "T36");
    CHECK(signature_family("speeduino 202501-T35").value() == "T35");
    CHECK(signature_family("STM32F407 build").value() == "STM32F407");
    CHECK(signature_family("F407 build").value() == "STM32F407");
    CHECK(signature_family("ATmega2560").value() == "ATMEGA2560");
    CHECK(signature_family("MEGA2560").value() == "ATMEGA2560");
}

TEST_CASE("signature_family: unknown / empty") {
    CHECK_FALSE(signature_family("").has_value());
    CHECK_FALSE(signature_family("unrelated").has_value());
}

TEST_CASE("signature_family: U16P2 wins over T41") {
    // The U16P2 substring check comes first; a T41-U16P2 string
    // should classify as U16P2, not T41.
    CHECK(signature_family("speeduino 202501-T41-U16P2").value() == "U16P2");
}

// ---------------------------------------------------------------------------
// validate
// ---------------------------------------------------------------------------

TEST_CASE("validate: empty inputs is clean") {
    PreflightInputs inputs;
    auto r = validate(inputs);
    CHECK(r.ok);
    CHECK(r.errors.empty());
    CHECK(r.warnings.empty());
}

TEST_CASE("validate: selected vs firmware-detected board is an ERROR") {
    PreflightInputs inputs;
    inputs.selected_board = BoardFamily::TEENSY36;
    inputs.firmware_entry.board_family = BoardFamily::TEENSY41;
    auto r = validate(inputs);
    CHECK_FALSE(r.ok);
    CHECK(has_substring(r.errors, "Selected board is TEENSY36"));
    CHECK(has_substring(r.errors, "looks like TEENSY41"));
}

TEST_CASE("validate: detected vs firmware board is a WARNING") {
    PreflightInputs inputs;
    inputs.detected_board = BoardFamily::TEENSY36;
    inputs.firmware_entry.board_family = BoardFamily::TEENSY41;
    auto r = validate(inputs);
    CHECK(r.ok);
    CHECK(has_substring(r.warnings, "Detected board is TEENSY36"));
}

TEST_CASE("validate: T41 signature with non-Teensy41 detected board warns") {
    PreflightInputs inputs;
    inputs.definition_signature = "speeduino 202501-T41";
    inputs.detected_board = BoardFamily::TEENSY36;
    auto r = validate(inputs);
    CHECK(has_substring(r.warnings, "signature indicates T41"));
}

TEST_CASE("validate: experimental capability vs production firmware warns") {
    PreflightInputs inputs;
    inputs.firmware_entry.is_experimental = false;
    inputs.experimental_u16p2 = true;
    auto r = validate(inputs);
    CHECK(has_substring(
        r.warnings,
        "Selected firmware is production, but the connected"));
}

TEST_CASE("validate: production capability vs experimental firmware warns") {
    PreflightInputs inputs;
    inputs.firmware_entry.is_experimental = true;
    inputs.experimental_u16p2 = false;
    auto r = validate(inputs);
    CHECK(has_substring(
        r.warnings,
        "Selected firmware is experimental (U16P2)"));
}

TEST_CASE("validate: text-heuristic experimental check when no live capability") {
    PreflightInputs inputs;
    inputs.firmware_entry.is_experimental = true;
    inputs.definition_signature = "speeduino 202501-T41";  // production text
    auto r = validate(inputs);
    CHECK(has_substring(
        r.warnings, "loaded INI/tune metadata looks production"));
}

TEST_CASE("validate: connected controller signature family mismatch warns") {
    PreflightInputs inputs;
    inputs.firmware_entry.firmware_signature = "speeduino 202501-T41";
    inputs.connected_firmware_signature = "speeduino 202501-T36";
    auto r = validate(inputs);
    CHECK(has_substring(r.warnings, "does not match the connected controller"));
}

TEST_CASE("validate: definition signature family mismatch warns") {
    PreflightInputs inputs;
    inputs.firmware_entry.firmware_signature = "speeduino 202501-T41";
    inputs.definition_signature = "speeduino 202501-T36";
    auto r = validate(inputs);
    CHECK(has_substring(r.warnings, "Loaded ECU definition signature family"));
}

TEST_CASE("validate: tune signature family mismatch warns") {
    PreflightInputs inputs;
    inputs.firmware_entry.firmware_signature = "speeduino 202501-T41";
    inputs.tune_signature = "speeduino 202501-T36";
    auto r = validate(inputs);
    CHECK(has_substring(r.warnings, "Loaded tune signature family"));
}

TEST_CASE("validate: paired tune name mismatch warns") {
    PreflightInputs inputs;
    inputs.firmware_entry.tune_path_basename = "BaseStartup.msq";
    inputs.tune_source_basename = "MyCustom.msq";
    auto r = validate(inputs);
    CHECK(has_substring(r.warnings, "paired with tune 'BaseStartup.msq'"));
    CHECK(has_substring(r.warnings, "the loaded tune is 'MyCustom.msq'"));
}

TEST_CASE("validate: paired tune name case-insensitive match → no warning") {
    PreflightInputs inputs;
    inputs.firmware_entry.tune_path_basename = "BaseStartup.msq";
    inputs.tune_source_basename = "basestartup.MSQ";
    auto r = validate(inputs);
    CHECK_FALSE(has_substring(r.warnings, "paired with tune"));
}

TEST_CASE("validate: version label not in metadata warns") {
    PreflightInputs inputs;
    inputs.firmware_entry.version_label = "v2.0.1";
    inputs.definition_signature = "speeduino 202501-T41";  // no v2.0.1
    auto r = validate(inputs);
    CHECK(has_substring(r.warnings, "v2.0.1 does not appear"));
}

TEST_CASE("validate: version label present in metadata → no warning") {
    PreflightInputs inputs;
    inputs.firmware_entry.version_label = "v2.0.1";
    inputs.tune_firmware_info = "speeduino-dropbear-v2.0.1";
    auto r = validate(inputs);
    CHECK_FALSE(has_substring(r.warnings, "does not appear"));
}
