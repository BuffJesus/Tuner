// SPDX-License-Identifier: MIT
#include "tuner_core/widget_math.hpp"

#include <algorithm>
#include <cmath>

namespace tuner_core::widget_math {

TimeRange screen_drag_to_time_range(
    double drag_x0, double drag_x1,
    double margin_left, double plot_width,
    double view_start, double view_end)
{
    if (plot_width <= 0.0) return {view_start, view_end};

    // Normalize drag coordinates to [0, 1] fraction of the plot area.
    double f0 = (std::min(drag_x0, drag_x1) - margin_left) / plot_width;
    double f1 = (std::max(drag_x0, drag_x1) - margin_left) / plot_width;
    f0 = std::clamp(f0, 0.0, 1.0);
    f1 = std::clamp(f1, 0.0, 1.0);

    // Map fractions to the current view's time range.
    double span = view_end - view_start;
    double new_start = view_start + f0 * span;
    double new_end   = view_start + f1 * span;

    // Reject degenerate drags (< 1% of the view).
    if ((new_end - new_start) < span * 0.01)
        return {view_start, view_end};

    return {new_start, new_end};
}

std::vector<std::pair<double, double>> build_square_wave_points(
    const std::vector<double>& times,
    const std::vector<double>& values,
    double plot_left, double plot_width,
    double time_start, double time_span,
    double track_top, double track_height,
    double val_min, double val_span)
{
    std::vector<std::pair<double, double>> pts;
    if (times.empty() || values.empty() || time_span <= 0.0)
        return pts;

    std::size_t n = std::min(times.size(), values.size());
    pts.reserve(n * 2);

    auto x_at = [&](double t) {
        return plot_left + ((t - time_start) / time_span) * plot_width;
    };
    auto y_at = [&](double v) {
        double frac = (val_span > 0.0) ? (v - val_min) / val_span : 0.5;
        frac = std::clamp(frac, 0.0, 1.0);
        return track_top + track_height * (1.0 - frac);
    };

    double prev_y = y_at(values[0]);
    pts.push_back({x_at(times[0]), prev_y});

    for (std::size_t i = 1; i < n; ++i) {
        double x = x_at(times[i]);
        double y = y_at(values[i]);
        // Square-wave step: horizontal at prev_y, then vertical to y.
        pts.push_back({x, prev_y});
        pts.push_back({x, y});
        prev_y = y;
    }
    return pts;
}

}  // namespace tuner_core::widget_math
