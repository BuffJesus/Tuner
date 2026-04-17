// SPDX-License-Identifier: MIT
//
// tuner_core::widget_math — pure-logic helpers extracted from Qt
// widget paintEvent/mouse-handler code for unit testing. No Qt
// types in the signatures — just doubles and ints.

#pragma once

#include <utility>
#include <vector>

namespace tuner_core::widget_math {

// LogTimelineWidget zoom: maps a screen-space drag rect to a time
// range within the current view window. Used by shift-drag zoom.
struct TimeRange { double start; double end; };
TimeRange screen_drag_to_time_range(
    double drag_x0, double drag_x1,
    double margin_left, double plot_width,
    double view_start, double view_end);

// TriggerScopeWidget: builds a square-wave (stepped) polyline from
// time/value arrays. Returns (x, y) screen-coordinate pairs in
// draw order — caller feeds them into a QPainterPath or any other
// polyline renderer. For digital traces: horizontal at prev_y then
// vertical to new_y at the same x (stepped transition).
std::vector<std::pair<double, double>> build_square_wave_points(
    const std::vector<double>& times,
    const std::vector<double>& values,
    double plot_left, double plot_width,
    double time_start, double time_span,
    double track_top, double track_height,
    double val_min, double val_span);

}  // namespace tuner_core::widget_math
