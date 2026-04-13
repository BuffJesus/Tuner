// SPDX-License-Identifier: MIT
//
// tuner_core::pressure_sensor_calibration — port of
// `PressureSensorCalibrationService` plus the
// `source_confidence_label` helper from `HardwarePresetService`.
// Ninth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Pure-logic preset matching and assessment for MAP / baro pressure
// sensor calibration values. The C++ side mirrors the operator-facing
// guidance / warning strings byte-for-byte so a future C++ Hardware
// Setup Wizard can render the same advice the Python wizard does.

#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::pressure_sensor_calibration {

// Mirror of `services.hardware_preset_service.PressureSensorPreset`.
struct Preset {
    std::string key;
    std::string label;
    std::string description;
    double minimum_value = 0.0;
    double maximum_value = 0.0;
    std::string units;
    std::string source_note;
    std::optional<std::string> source_url;
};

// Mirror of `PressureCalibrationAssessment`.
struct Assessment {
    std::optional<double> minimum_value;
    std::optional<double> maximum_value;
    std::optional<Preset> matching_preset;
    std::string guidance;
    std::optional<std::string> warning;
};

enum class SensorKind {
    MAP,
    BARO,
};

// Match input range against the preset list with a ±0.5 kPa tolerance
// on each endpoint, mirroring `find_matching_preset`. Returns the
// first matching preset in input order.
std::optional<Preset> find_matching_preset(
    double minimum_value,
    double maximum_value,
    const std::vector<Preset>& presets);

// Build the full assessment, mirroring `assess`. Handles the
// "no calibration available yet" branch, the baro-overrange warning,
// the matched-preset guidance string (with confidence label), and the
// unmatched-range guidance string.
Assessment assess(
    std::optional<double> minimum_value,
    std::optional<double> maximum_value,
    const std::vector<Preset>& presets,
    SensorKind sensor_kind);

// Mirror `HardwarePresetService.source_confidence_label`. Returns
// "Starter" / "Official" / "Trusted Secondary" / "Sourced" based on
// the source note (case-insensitive substring "inferred") and the
// source URL's netloc (matched against fixed allowlists).
std::string source_confidence_label(
    std::string_view source_note,
    const std::optional<std::string>& source_url);

}  // namespace tuner_core::pressure_sensor_calibration
