// SPDX-License-Identifier: MIT
//
// tuner_core::required_fuel_calculator implementation. Pure logic,
// direct port of `RequiredFuelCalculatorService.calculate`.

#include "tuner_core/required_fuel_calculator.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace tuner_core::required_fuel_calculator {

namespace {

// Constants pulled from the Python module — kept verbatim so any
// future operator-visible drift between the two implementations is a
// single literal change in both places.
constexpr double kReqFuelK = 3.6e7 * 4.27793e-5;  // ≈ 1540.0548
constexpr double kCcPerCid = 16.38706;
constexpr double kCcMinPerLbHr = 10.5;
constexpr double kStoredScale = 0.1;

// Mirrors Python's `round(...)` (banker's, half-to-even). Critical
// for the rare exact-half cases where a half-away-from-zero round
// would diverge from Python's stored value by 1.
int banker_round_int(double x) noexcept {
    return static_cast<int>(std::nearbyint(x));
}

std::string format_summary(
    double displacement_cc,
    int cylinder_count,
    double injector_flow_ccmin,
    double target_afr) {
    char buf[128];
    // Match Python's `f"{displacement_cc:.0f} cc, {cylinder_count} cyl, "
    //                  f"{injector_flow_ccmin:.0f} cc/min, AFR {target_afr:.1f}"`
    std::snprintf(
        buf, sizeof(buf),
        "%.0f cc, %d cyl, %.0f cc/min, AFR %.1f",
        displacement_cc, cylinder_count, injector_flow_ccmin, target_afr);
    return std::string(buf);
}

}  // namespace

Result calculate(
    double displacement_cc,
    int cylinder_count,
    double injector_flow_ccmin,
    double target_afr) {
    Result r;
    r.displacement_cc = displacement_cc;
    r.cylinder_count = cylinder_count;
    r.injector_flow_ccmin = injector_flow_ccmin;
    r.target_afr = target_afr;

    const bool is_valid =
        displacement_cc > 0.0 &&
        cylinder_count > 0 &&
        injector_flow_ccmin > 0.0 &&
        target_afr > 0.0;

    if (!is_valid) {
        r.req_fuel_ms = 0.0;
        r.req_fuel_stored = 0;
        r.inputs_summary = "Invalid inputs — all values must be positive.";
        r.is_valid = false;
        return r;
    }

    const double displacement_cid = displacement_cc / kCcPerCid;
    const double injflow_lbhr = injector_flow_ccmin / kCcMinPerLbHr;
    const double numerator = kReqFuelK * displacement_cid;
    const double denominator =
        static_cast<double>(cylinder_count) * target_afr * injflow_lbhr;
    const double req_fuel_ms = numerator / denominator / 10.0;

    int stored_raw = banker_round_int(req_fuel_ms / kStoredScale);
    int stored = std::clamp(stored_raw, 0, 255);

    r.req_fuel_ms = req_fuel_ms;
    r.req_fuel_stored = stored;
    r.inputs_summary = format_summary(
        displacement_cc, cylinder_count, injector_flow_ccmin, target_afr);
    r.is_valid = true;
    return r;
}

}  // namespace tuner_core::required_fuel_calculator
