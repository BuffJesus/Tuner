// SPDX-License-Identifier: MIT
//
// tuner_core::chart_axes — pure-logic axis-scaling helpers shared by
// the QPainter chart widgets in the Qt app (DynoChartWidget,
// LogTimelineWidget, etc.). Extracting these out of the widgets
// gives us doctest coverage for the math and keeps the widget classes
// focused on drawing.

#pragma once

namespace tuner_core::chart_axes {

// Round `v` up to the next "nice" axis ceiling — a 1-2-5 multiple of
// the appropriate power of ten. Example: 0.3 → 0.5, 87 → 100, 1234 →
// 2000, 4999 → 5000, 5001 → 10000.
//
// Returns 1.0 for non-positive inputs so axis divisions never go
// negative or zero. The result is strictly >= v for positive v and
// lands on the standard 1/2/5 log-grid operators expect.
double nice_ceiling(double v);

// Compute a "nice" tick step for an RPM axis given the visible span.
// The dyno chart picked 500/1000/2000 ms based on the span; this
// helper generalises that rule for any axis where the tick density
// should feel constant across different zoom levels.
//
// Returns 500 for span < 3000, 1000 for 3000..8000, 2000 otherwise.
double rpm_tick_step(double span);

}  // namespace tuner_core::chart_axes
