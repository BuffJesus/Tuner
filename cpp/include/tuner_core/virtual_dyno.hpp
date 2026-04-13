// SPDX-License-Identifier: MIT
//
// tuner_core::virtual_dyno — estimates torque and horsepower from
// ECU sensor data during a WOT pull. No physical dyno required.
//
// Uses the ideal gas law to estimate mass air flow from VE, MAP,
// IAT, and displacement, then derives indicated torque from fuel
// energy and assumed thermal/mechanical efficiency.

#pragma once

#include <string>
#include <vector>

namespace tuner_core::virtual_dyno {

struct DataPoint {
    double rpm = 0;
    double map_kpa = 0;
    double iat_celsius = 0;
    double afr = 14.7;
    double ve_percent = 100.0;  // optional — defaults to 100 if unknown
};

struct DynoPoint {
    double rpm = 0;
    double torque_nm = 0;
    double horsepower = 0;
};

struct EngineSpec {
    double displacement_cc = 2000.0;
    int cylinders = 4;
    bool four_stroke = true;
    double mechanical_efficiency = 0.85;  // brake / indicated
    double thermal_efficiency = 0.33;     // typical gasoline SI
};

struct DynoResult {
    std::vector<DynoPoint> points;
    double peak_torque_nm = 0;
    double peak_torque_rpm = 0;
    double peak_hp = 0;
    double peak_hp_rpm = 0;
    std::string summary_text;
};

// Calculate dyno curve from a WOT pull dataset.
// Points should be sorted by RPM ascending. Duplicate RPMs are
// averaged. Returns empty result if fewer than 3 data points.
DynoResult calculate(
    const std::vector<DataPoint>& data,
    const EngineSpec& spec);

}  // namespace tuner_core::virtual_dyno
