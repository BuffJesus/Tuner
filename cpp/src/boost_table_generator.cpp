// SPDX-License-Identifier: MIT

#include "tuner_core/boost_table_generator.hpp"

#include <algorithm>
#include <cmath>

namespace tuner_core::boost_table_generator {

BoostGeneratorResult generate(const BoostGeneratorContext& ctx) {
    BoostGeneratorResult result;
    int total = ctx.rows * ctx.columns;
    result.target_values.resize(total);
    result.duty_values.resize(total);

    constexpr double ATMO = 101.3;  // kPa atmospheric

    for (int r = 0; r < ctx.rows; ++r) {
        // RPM fraction: 0 = low RPM, 1 = redline.
        double rpm_frac = static_cast<double>(r) / std::max(1, ctx.rows - 1);

        for (int c = 0; c < ctx.columns; ++c) {
            // TPS fraction: 0 = closed, 1 = WOT.
            double tps_frac = static_cast<double>(c) / std::max(1, ctx.columns - 1);

            // Boost target ramps with both RPM and TPS.
            // At low RPM or closed throttle → atmospheric.
            // At high RPM + WOT → full target.
            double ramp = rpm_frac * tps_frac;
            // Smooth the ramp slightly (square root curve = faster onset).
            ramp = std::sqrt(ramp);

            double target = ATMO + (ctx.target_boost_kpa - ATMO) * ramp;
            target = std::clamp(target, ATMO, ctx.target_boost_kpa);

            // Duty cycle: 0% at atmospheric, ramps to 50-85%.
            // Intercooled builds can run slightly more aggressive duty
            // because charge temps are lower.
            double max_duty = ctx.intercooled ? 85.0 : 75.0;
            double duty = ramp * max_duty;
            duty = std::clamp(duty, 0.0, max_duty);

            int flat = r * ctx.columns + c;
            result.target_values[flat] = std::round(target);
            result.duty_values[flat] = std::round(duty);
        }
    }

    return result;
}

}  // namespace tuner_core::boost_table_generator
