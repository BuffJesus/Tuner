// SPDX-License-Identifier: MIT
//
// tuner_core::thermistor_calibration — port of ThermistorCalibrationService.
// Thirty-ninth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Generates Speeduino-format 32-point ADC → temperature lookup tables for
// CLT/IAT sensors using the Steinhart-Hart equation. Includes the full
// built-in preset catalog (15 presets from the Speeduino/legacy INI).
//
// Pure math — no Qt, no IO, no transport.

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::thermistor_calibration {

// -----------------------------------------------------------------------
// Constants
// -----------------------------------------------------------------------

constexpr int ADC_COUNT = 32;
constexpr double SUPPLY_V = 5.0;
constexpr double KELVIN_OFFSET = 273.15;
constexpr int ADC_MAX = 1023;
constexpr double TEMP_MIN_C = -40.0;
constexpr double TEMP_MAX_C = 350.0;

enum class Sensor : int { CLT = 0, IAT = 1 };

// -----------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------

struct Point {
    double temp_c = 0.0;
    double resistance_ohms = 0.0;
};

struct Preset {
    std::string name;
    double pullup_ohms = 0.0;
    Point point1;
    Point point2;
    Point point3;
    std::string source_note;
    std::string source_url;  // empty = no URL
    bool applicable_clt = true;
    bool applicable_iat = true;
};

struct CalibrationResult {
    Sensor sensor = Sensor::CLT;
    std::string preset_name;
    std::vector<double> temperatures_c;  // 32 values

    // Encode as 64 bytes: 32 × big-endian int16 temperatures in °F × 10.
    std::vector<uint8_t> encode_payload() const;

    // Preview (adc, temp_c) pairs at representative indices.
    std::vector<std::pair<int, double>> preview_points() const;
};

// Steinhart-Hart coefficients (A, B, C).
struct SHCoefficients {
    double A = 0.0;
    double B = 0.0;
    double C = 0.0;
};

// -----------------------------------------------------------------------
// Pure functions
// -----------------------------------------------------------------------

// Get the full built-in preset catalog (15 presets).
const std::vector<Preset>& presets();

// Get presets applicable to a specific sensor.
std::vector<Preset> presets_for_sensor(Sensor sensor);

// Find a preset by name. Returns nullptr if not found.
const Preset* preset_by_name(const std::string& name);

// Source confidence label for a preset.
std::string source_confidence_label(const Preset& preset);

// Solve Steinhart-Hart coefficients from three (T, R) points.
SHCoefficients steinhart_hart_coefficients(
    const Point& p1, const Point& p2, const Point& p3);

// Temperature in °C for a given ADC reading.
double temp_at_adc(int adc, double pullup_ohms, const SHCoefficients& sh);

// Generate a 32-point calibration table.
CalibrationResult generate(const Preset& preset, Sensor sensor);

}  // namespace tuner_core::thermistor_calibration
