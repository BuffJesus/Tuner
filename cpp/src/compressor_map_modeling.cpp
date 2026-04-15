// SPDX-License-Identifier: MIT
#include "tuner_core/compressor_map_modeling.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace tuner_core::compressor_map_modeling {

namespace {

// Ideal-gas mass-air-flow calculation in lb/min. Pure textbook formula:
//   mass_flow_kg_s = (VE * Vd * N * P) / (R * T * rev_per_intake * 60)
// where
//   Vd     = displacement in m^3
//   N      = engine speed rev/min
//   P      = absolute manifold pressure in Pa
//   R      = specific gas constant for dry air, 287.05 J/(kg·K)
//   T      = intake air temperature in Kelvin
//   rev_per_intake = 2 for a 4-stroke engine
//   (the second /60 converts rpm → rps)
// Then convert kg/s → lb/min for compressor-map axes:
//   lb/min = kg/s * (1 / 0.45359237) * 60
constexpr double R_AIR = 287.05;
constexpr double KG_S_TO_LB_MIN = 132.27735;

double mass_flow_lbmin(double displacement_cc, double rpm,
                       double map_abs_kpa, double iat_c, double ve_pct) {
    if (displacement_cc <= 0 || rpm <= 0 || map_abs_kpa <= 0 || ve_pct <= 0)
        return 0.0;
    const double Vd_m3 = displacement_cc * 1e-6;
    const double P_pa = map_abs_kpa * 1000.0;
    const double T_k = iat_c + 273.15;
    const double ve = ve_pct / 100.0;
    // Flow at full charge: double-check the /2 for 4-stroke (each
    // cylinder fires every other revolution).
    const double mass_flow_kg_s = (ve * Vd_m3 * (rpm / 60.0) * P_pa) /
                                   (R_AIR * T_k * 2.0);
    return mass_flow_kg_s * KG_S_TO_LB_MIN;
}

RiskRegion classify(double flow_lbmin, double pressure_ratio,
                    const Context& ctx) {
    if (pressure_ratio > ctx.max_pressure_ratio) return RiskRegion::OFF_MAP;
    if (flow_lbmin > ctx.choke_flow_lbmin)        return RiskRegion::CHOKE;
    if (flow_lbmin < ctx.surge_flow_lbmin)        return RiskRegion::SURGE;
    // Margin bands — "near_" regions give the operator early warning
    // without escalating to a red state.
    const double surge_margin = ctx.surge_flow_lbmin *
        (1.0 + ctx.surge_margin_pct / 100.0);
    if (flow_lbmin < surge_margin) return RiskRegion::NEAR_SURGE;
    const double choke_margin = ctx.choke_flow_lbmin *
        (1.0 - ctx.surge_margin_pct / 100.0);
    if (flow_lbmin > choke_margin) return RiskRegion::NEAR_CHOKE;
    return RiskRegion::SAFE;
}

}  // namespace

Point compute_point(double rpm, double map_abs_kpa, double iat_c,
                    double ve_pct, const Context& ctx) {
    Point p;
    p.rpm = rpm;
    p.map_abs_kpa = map_abs_kpa;
    p.iat_c = iat_c;
    p.ve_pct = ve_pct;
    p.mass_flow_lbmin = mass_flow_lbmin(
        ctx.displacement_cc, rpm, map_abs_kpa, iat_c, ve_pct);
    p.pressure_ratio = (ctx.baro_kpa > 0.0)
        ? (map_abs_kpa / ctx.baro_kpa) : 1.0;
    p.risk = classify(p.mass_flow_lbmin, p.pressure_ratio, ctx);
    return p;
}

std::vector<Point> sweep_rpm(double rpm_min, double rpm_max, int steps,
                              double map_abs_kpa, double iat_c,
                              double ve_pct, const Context& ctx) {
    std::vector<Point> pts;
    if (steps < 2) steps = 2;
    if (rpm_max <= rpm_min) rpm_max = rpm_min + 1.0;
    pts.reserve(static_cast<std::size_t>(steps));
    const double step = (rpm_max - rpm_min) /
                        static_cast<double>(steps - 1);
    for (int i = 0; i < steps; ++i) {
        double rpm = rpm_min + step * static_cast<double>(i);
        pts.push_back(compute_point(rpm, map_abs_kpa, iat_c, ve_pct, ctx));
    }
    return pts;
}

Summary summarise(const std::vector<Point>& points, const Context& ctx) {
    Summary s;
    s.total_count = static_cast<int>(points.size());
    if (points.empty()) {
        s.plain_language = "No operating points to analyse.";
        return s;
    }
    for (const auto& p : points) {
        if (p.mass_flow_lbmin > s.peak_flow_lbmin)
            s.peak_flow_lbmin = p.mass_flow_lbmin;
        if (p.pressure_ratio > s.peak_pressure_ratio)
            s.peak_pressure_ratio = p.pressure_ratio;
        if (p.risk == RiskRegion::SAFE) s.safe_count++;
        if (static_cast<int>(p.risk) > static_cast<int>(s.worst_risk))
            s.worst_risk = p.risk;
    }

    char buf[512];
    const char* shape;
    switch (s.worst_risk) {
        case RiskRegion::SAFE:
            shape = "The projected flow stays inside the published envelope.";
            break;
        case RiskRegion::NEAR_SURGE:
            shape = "Low-RPM flow is close to the surge line. "
                    "Consider a smaller turbo or a higher boost threshold "
                    "to keep operation clear of surge.";
            break;
        case RiskRegion::NEAR_CHOKE:
            shape = "High-RPM flow is close to the choke line. "
                    "Efficiency drops past this point \xe2\x80\x94 a "
                    "larger turbo would be worth evaluating.";
            break;
        case RiskRegion::SURGE:
            shape = "Operation crosses the surge line. "
                    "This turbo is too large for the requested boost "
                    "at low RPM \xe2\x80\x94 expect stalling flow and "
                    "compressor damage.";
            break;
        case RiskRegion::CHOKE:
            shape = "Operation crosses the choke line. "
                    "The turbo is too small at high RPM \xe2\x80\x94 "
                    "flow plateaus and IAT climbs regardless of wastegate.";
            break;
        case RiskRegion::OFF_MAP:
            shape = "Pressure ratio exceeds the published map. "
                    "The turbo is not specified for this boost target \xe2\x80\x94 "
                    "reduce target or pick a different wheel.";
            break;
    }
    std::snprintf(buf, sizeof(buf),
        "Peak flow %.1f lb/min at PR %.2f across %d sample points "
        "(%d in safe zone). %s",
        s.peak_flow_lbmin, s.peak_pressure_ratio,
        s.total_count, s.safe_count, shape);
    (void)ctx;
    s.plain_language = buf;
    return s;
}

}  // namespace tuner_core::compressor_map_modeling
