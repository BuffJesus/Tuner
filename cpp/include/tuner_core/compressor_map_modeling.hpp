// SPDX-License-Identifier: MIT
//
// tuner_core::compressor_map_modeling — pure-logic helper that maps
// an engine operating point (RPM + MAP + IAT + VE) onto the
// compressor-map coordinate system (mass flow × pressure ratio) and
// flags surge / choke / off-map risk against a published envelope.
//
// This is Phase 15 item #10. The service is deliberately narrow:
// given engine specs and an operating point, compute where that
// point lands on a generic compressor map. A later slice can layer
// per-turbo preset envelopes on top (Garrett GT28, Precision 6266,
// etc). For now the envelope is supplied by the caller as three
// numbers (surge flow, choke flow, max PR).
//
// Temperature effects are intentionally simplified: the model assumes
// an ideal intercooler (IAT tracks ambient). An intake-air heat-soak
// correction can be added once the desktop surfaces IAT vs ambient
// deltas — that's out of scope here.

#pragma once

#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::compressor_map_modeling {

// Engine specs + map envelope used to classify operating points.
struct Context {
    double displacement_cc = 2998.0;  // total engine displacement
    int    cylinder_count  = 6;        // for future extensibility
    double baro_kpa        = 101.3;    // ambient absolute pressure
    double intake_temp_c   = 25.0;     // default ambient

    // Published compressor map envelope — all three values come from
    // the turbo vendor's datasheet. Operating points outside this
    // envelope get flagged as risky so the operator can choose a
    // different target boost or a different turbo.
    double surge_flow_lbmin = 8.0;     // mass flow at left edge (surge line)
    double choke_flow_lbmin = 55.0;    // mass flow at right edge (choke line)
    double max_pressure_ratio = 3.2;   // top of the map
    double surge_margin_pct = 10.0;    // how close to surge flow is "near_surge"
};

// Classification of one operating point against the envelope.
// Values are deliberately ordered by severity so UI can compare.
enum class RiskRegion {
    SAFE,
    NEAR_SURGE,
    NEAR_CHOKE,
    SURGE,
    CHOKE,
    OFF_MAP,
};

inline std::string_view risk_region_name(RiskRegion r) {
    switch (r) {
        case RiskRegion::SAFE:        return "safe";
        case RiskRegion::NEAR_SURGE:  return "near_surge";
        case RiskRegion::NEAR_CHOKE:  return "near_choke";
        case RiskRegion::SURGE:       return "surge";
        case RiskRegion::CHOKE:       return "choke";
        case RiskRegion::OFF_MAP:     return "off_map";
    }
    return "safe";
}

// One engine operating point projected onto compressor-map coords.
struct Point {
    // Inputs (echoed for plotting).
    double rpm = 0.0;
    double map_abs_kpa = 100.0;   // absolute manifold pressure
    double iat_c = 25.0;
    double ve_pct = 100.0;

    // Outputs.
    double mass_flow_lbmin = 0.0;  // airflow through the compressor
    double pressure_ratio  = 1.0;  // MAP_abs / baro
    RiskRegion risk = RiskRegion::SAFE;
};

// Compute one operating point. Pure function; no Qt, no I/O.
Point compute_point(double rpm, double map_abs_kpa, double iat_c,
                    double ve_pct, const Context& ctx);

// Sweep the RPM range at a fixed MAP/IAT/VE target and return the
// projected curve. Useful for plotting a "WOT line" across the map.
std::vector<Point> sweep_rpm(double rpm_min, double rpm_max, int steps,
                              double map_abs_kpa, double iat_c,
                              double ve_pct, const Context& ctx);

// Summarise a set of points for the operator-facing card: peak flow,
// peak PR, and the worst risk region encountered.
struct Summary {
    double peak_flow_lbmin = 0.0;
    double peak_pressure_ratio = 1.0;
    RiskRegion worst_risk = RiskRegion::SAFE;
    int safe_count = 0;
    int total_count = 0;
    std::string plain_language;  // one-sentence operator summary
};

Summary summarise(const std::vector<Point>& points, const Context& ctx);

}  // namespace tuner_core::compressor_map_modeling
