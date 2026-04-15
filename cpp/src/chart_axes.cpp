// SPDX-License-Identifier: MIT
#include "tuner_core/chart_axes.hpp"

#include <cmath>

namespace tuner_core::chart_axes {

double nice_ceiling(double v) {
    if (v <= 0) return 1.0;
    double mag = std::pow(10.0, std::floor(std::log10(v)));
    double norm = v / mag;
    double c = (norm <= 1.0) ? 1.0
             : (norm <= 2.0) ? 2.0
             : (norm <= 5.0) ? 5.0 : 10.0;
    return c * mag;
}

double rpm_tick_step(double span) {
    if (span > 8000.0) return 2000.0;
    if (span < 3000.0) return 500.0;
    return 1000.0;
}

}  // namespace tuner_core::chart_axes
