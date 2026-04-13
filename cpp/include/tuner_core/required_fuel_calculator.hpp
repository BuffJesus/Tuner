// SPDX-License-Identifier: MIT
//
// tuner_core::required_fuel_calculator — port of the Python
// `RequiredFuelCalculatorService`. Implements the exact formula used
// in the TunerStudio Required Fuel Calculator dialog (an.java) so the
// C++ Hardware Setup Wizard can compute the staged `reqFuel` value
// without round-tripping through Python. Second sub-slice of the
// Phase 14 workspace-services port (Slice 4).
//
// Formula::
//
//     reqFuel_ms = (displacement_CID × 36,000,000 × 4.27793e-5)
//                  ÷ (cylinder_count × AFR × injFlow_lbhr)
//                  ÷ 10.0
//
// where:
//     displacement_CID = displacement_cc ÷ 16.38706
//     injFlow_lbhr     = injector_flow_ccmin ÷ 10.5
//
// Speeduino stores reqFuel as tenths of milliseconds (U08, scale 0.1),
// so the stored integer is round(reqFuel_ms × 10), clipped to 0..255.

#pragma once

#include <string>

namespace tuner_core::required_fuel_calculator {

struct Result {
    double req_fuel_ms = 0.0;
    int req_fuel_stored = 0;
    double displacement_cc = 0.0;
    int cylinder_count = 0;
    double injector_flow_ccmin = 0.0;
    double target_afr = 0.0;
    std::string inputs_summary;
    bool is_valid = false;
};

Result calculate(
    double displacement_cc,
    int cylinder_count,
    double injector_flow_ccmin,
    double target_afr);

}  // namespace tuner_core::required_fuel_calculator
