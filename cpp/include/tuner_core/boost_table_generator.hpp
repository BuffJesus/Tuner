// SPDX-License-Identifier: MIT
//
// tuner_core::boost_table_generator — generates starter boost target
// and duty cycle tables for forced-induction builds.

#pragma once

#include <vector>

namespace tuner_core::boost_table_generator {

struct BoostGeneratorContext {
    double target_boost_kpa = 200.0;  // absolute kPa at peak
    bool intercooled = false;
    int rows = 8;    // RPM bins (typically 8)
    int columns = 8; // TPS bins (typically 8)
};

struct BoostGeneratorResult {
    std::vector<double> target_values;  // boost target (kPa), row-major
    std::vector<double> duty_values;    // boost duty (%), row-major
};

// Generate a conservative boost target + duty table.
// Target ramps linearly from atmospheric at low RPM/TPS to
// full target at high RPM/WOT. Duty cycle mirrors at ~50-85%.
BoostGeneratorResult generate(const BoostGeneratorContext& ctx);

}  // namespace tuner_core::boost_table_generator
