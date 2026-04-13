// SPDX-License-Identifier: MIT
//
// tuner_core::dashboard_layout — dashboard widget model + default layout.
// Fifty-first sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Domain types for the dashboard gauge cluster plus the default Speeduino
// 11-gauge layout. Pure logic, no file I/O (JSON load/save deferred to
// a later slice).

#pragma once

#include <string>
#include <vector>

namespace tuner_core::dashboard_layout {

struct ColorZone {
    double lo = 0.0;
    double hi = 0.0;
    std::string color;  // "ok" | "warning" | "danger"
};

struct Widget {
    std::string widget_id;
    std::string kind;       // "number" | "bar" | "dial" | "led" | "label"
    std::string title;
    std::string source;     // output channel name (empty = none)
    std::string units;
    double x = 0.0;
    double y = 0.0;
    double width = 1.0;
    double height = 1.0;
    double min_value = 0.0;
    double max_value = 100.0;
    std::vector<ColorZone> color_zones;
    std::string tune_page;  // page_id for navigation (empty = none)
    std::string text;       // static text for "label" kind (empty = use title)
};

struct Layout {
    std::string name;
    std::vector<Widget> widgets;
};

// Return the default 11-gauge Speeduino dashboard layout.
Layout default_layout();

}  // namespace tuner_core::dashboard_layout
