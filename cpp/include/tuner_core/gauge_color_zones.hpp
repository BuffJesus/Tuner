// SPDX-License-Identifier: MIT
//
// tuner_core::gauge_color_zones — port of
// `DashboardLayoutService._zones_from_gauge_config`. Sixteenth
// sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Derives the (ok / warning / danger) color zones a dashboard gauge
// renders, given the gauge's display range plus the INI-supplied
// `lo_danger`, `lo_warn`, `hi_warn`, `hi_danger` thresholds. Each
// threshold is independently optional. Pure logic — no domain types,
// no I/O.

#pragma once

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::gauge_color_zones {

struct Zone {
    double lo = 0.0;
    double hi = 0.0;
    std::string color;  // "ok" / "warning" / "danger"
};

// The thresholds the Python service reads from `GaugeConfiguration`.
// Each is optional and may be set independently.
struct Thresholds {
    std::optional<double> lo_danger;
    std::optional<double> lo_warn;
    std::optional<double> hi_warn;
    std::optional<double> hi_danger;
};

// Mirror Python `_zones_from_gauge_config`. The display range
// (`lo`, `hi`) bounds the result; thresholds inside the range carve
// out warning / ok / warning / danger bands.
std::vector<Zone> derive_zones(double lo, double hi, const Thresholds& thresholds);

}  // namespace tuner_core::gauge_color_zones
