// SPDX-License-Identifier: MIT
//
// tuner_core::gauge_color_zones implementation. Pure logic — direct
// port of `DashboardLayoutService._zones_from_gauge_config`.

#include "tuner_core/gauge_color_zones.hpp"

namespace tuner_core::gauge_color_zones {

std::vector<Zone> derive_zones(double lo, double hi, const Thresholds& t) {
    std::vector<Zone> zones;

    // Low danger: [lo, lo_danger) when lo_danger > lo
    if (t.lo_danger.has_value() && *t.lo_danger > lo) {
        zones.push_back({lo, *t.lo_danger, "danger"});
    }
    // Low warning: [warn_start, lo_warn) where warn_start =
    // lo_danger when present, else lo
    if (t.lo_warn.has_value()) {
        double warn_start = t.lo_danger.has_value() ? *t.lo_danger : lo;
        if (warn_start < *t.lo_warn) {
            zones.push_back({warn_start, *t.lo_warn, "warning"});
        }
    }
    // OK band: only when at least one warn threshold is defined.
    if (t.lo_warn.has_value() || t.hi_warn.has_value()) {
        double ok_lo = t.lo_warn.has_value() ? *t.lo_warn : lo;
        double ok_hi = t.hi_warn.has_value() ? *t.hi_warn : hi;
        if (ok_lo < ok_hi) {
            zones.push_back({ok_lo, ok_hi, "ok"});
        }
    }
    // High warning: [hi_warn, warn_end) where warn_end =
    // hi_danger when present, else hi
    if (t.hi_warn.has_value()) {
        double warn_end = t.hi_danger.has_value() ? *t.hi_danger : hi;
        if (*t.hi_warn < warn_end) {
            zones.push_back({*t.hi_warn, warn_end, "warning"});
        }
    }
    // High danger: [hi_danger, hi) when hi_danger < hi
    if (t.hi_danger.has_value() && *t.hi_danger < hi) {
        zones.push_back({*t.hi_danger, hi, "danger"});
    }
    return zones;
}

}  // namespace tuner_core::gauge_color_zones
