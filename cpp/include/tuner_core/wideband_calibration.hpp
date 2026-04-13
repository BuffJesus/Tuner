// SPDX-License-Identifier: MIT
//
// tuner_core::wideband_calibration — port of WidebandCalibrationService.
// Fiftieth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Generates 32-point ADC → AFR lookup tables for Speeduino wideband O2
// sensor calibration (page 2). Includes a 5-preset catalog of popular
// aftermarket wideband controllers. Pure math, no IO.

#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace tuner_core::wideband_calibration {

constexpr int ADC_COUNT = 32;
constexpr int ADC_MAX = 1023;
constexpr double SUPPLY_V = 5.0;
constexpr double AFR_MIN = 5.0;
constexpr double AFR_MAX = 30.0;

struct Preset {
    std::string name;
    double voltage_low = 0.0;
    double afr_at_voltage_low = 0.0;
    double voltage_high = 5.0;
    double afr_at_voltage_high = 0.0;
    std::string notes;
};

struct CalibrationResult {
    std::string preset_name;
    std::vector<double> afrs;  // 32 values

    std::vector<uint8_t> encode_payload() const;
    double afr_at_voltage(double voltage) const;
};

const std::vector<Preset>& presets();
const Preset* preset_by_name(const std::string& name);
CalibrationResult generate(const Preset& preset);

}  // namespace tuner_core::wideband_calibration
