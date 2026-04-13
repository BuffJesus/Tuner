// SPDX-License-Identifier: MIT
#include "tuner_core/table_surface_3d.hpp"

#include <algorithm>
#include <cmath>

namespace tuner_core::table_surface_3d {

ProjectedSurface project(
    const std::vector<double>& flat_values,
    int rows, int cols,
    double azimuth_deg,
    double elevation_deg,
    double width,
    double height)
{
    ProjectedSurface result;
    result.rows = rows;
    result.cols = cols;

    if (rows <= 0 || cols <= 0 || flat_values.empty()) return result;

    // Build 2D value grid.
    result.values.resize(rows);
    double min_v = flat_values[0], max_v = flat_values[0];
    for (int r = 0; r < rows; ++r) {
        result.values[r].resize(cols, 0);
        for (int c = 0; c < cols; ++c) {
            int idx = r * cols + c;
            double v = (idx < static_cast<int>(flat_values.size())) ? flat_values[idx] : 0;
            result.values[r][c] = v;
            min_v = std::min(min_v, v);
            max_v = std::max(max_v, v);
        }
    }
    result.min_value = min_v;
    result.max_value = max_v;
    double range = std::max(1.0, max_v - min_v);

    // Rotation angles.
    constexpr double PI = 3.14159265358979323846;
    double az = azimuth_deg * PI / 180.0;
    double el = elevation_deg * PI / 180.0;
    double cos_az = std::cos(az), sin_az = std::sin(az);
    double cos_el = std::cos(el), sin_el = std::sin(el);

    // Project each grid point.
    // 3D coords: x = col fraction [0,1], y = row fraction [0,1], z = value fraction [0,1]
    // Camera: simple rotation then orthographic projection.
    result.points.resize(rows);
    double min_sx = 1e9, max_sx = -1e9, min_sy = 1e9, max_sy = -1e9;

    for (int r = 0; r < rows; ++r) {
        result.points[r].resize(cols);
        for (int c = 0; c < cols; ++c) {
            double x3 = static_cast<double>(c) / std::max(1, cols - 1) - 0.5;
            double y3 = static_cast<double>(r) / std::max(1, rows - 1) - 0.5;
            double z3 = (result.values[r][c] - min_v) / range * 0.6;

            // Rotate around Y (azimuth).
            double rx = x3 * cos_az - y3 * sin_az;
            double ry = x3 * sin_az + y3 * cos_az;

            // Rotate around X (elevation).
            double ry2 = ry * cos_el - z3 * sin_el;
            double rz2 = ry * sin_el + z3 * cos_el;

            // Orthographic projection.
            double sx = rx;
            double sy = -rz2;  // flip Y so Z-up renders as screen-up

            min_sx = std::min(min_sx, sx); max_sx = std::max(max_sx, sx);
            min_sy = std::min(min_sy, sy); max_sy = std::max(max_sy, sy);
            result.points[r][c] = {sx, sy};
        }
    }

    // Scale to fit output dimensions with margin.
    double sx_range = max_sx - min_sx;
    double sy_range = max_sy - min_sy;
    if (sx_range <= 0) sx_range = 1;
    if (sy_range <= 0) sy_range = 1;
    double scale = std::min((width - 40) / sx_range, (height - 40) / sy_range);
    double cx = width / 2.0, cy = height / 2.0;
    double ox = (min_sx + max_sx) / 2.0;
    double oy = (min_sy + max_sy) / 2.0;

    for (int r = 0; r < rows; ++r)
        for (int c = 0; c < cols; ++c) {
            result.points[r][c].x = cx + (result.points[r][c].x - ox) * scale;
            result.points[r][c].y = cy + (result.points[r][c].y - oy) * scale;
        }

    return result;
}

std::optional<Point2D> interpolate_screen_point(
    const ProjectedSurface& surface,
    double row_frac,
    double col_frac)
{
    if (surface.rows <= 0 || surface.cols <= 0 || surface.points.empty())
        return std::nullopt;
    if (row_frac < 0.0 || col_frac < 0.0)
        return std::nullopt;
    const double max_r = static_cast<double>(surface.rows - 1);
    const double max_c = static_cast<double>(surface.cols - 1);
    if (row_frac > max_r || col_frac > max_c)
        return std::nullopt;

    // Single row or single column: clamp to nearest vertex and return.
    if (surface.rows == 1 && surface.cols == 1)
        return surface.points[0][0];
    if (surface.rows == 1) {
        int c0 = static_cast<int>(std::floor(col_frac));
        int c1 = std::min(c0 + 1, surface.cols - 1);
        double tc = col_frac - c0;
        const auto& p0 = surface.points[0][c0];
        const auto& p1 = surface.points[0][c1];
        return Point2D{ p0.x + (p1.x - p0.x) * tc,
                        p0.y + (p1.y - p0.y) * tc };
    }
    if (surface.cols == 1) {
        int r0 = static_cast<int>(std::floor(row_frac));
        int r1 = std::min(r0 + 1, surface.rows - 1);
        double tr = row_frac - r0;
        const auto& p0 = surface.points[r0][0];
        const auto& p1 = surface.points[r1][0];
        return Point2D{ p0.x + (p1.x - p0.x) * tr,
                        p0.y + (p1.y - p0.y) * tr };
    }

    // Bilinear between the four corners of the containing cell.
    int r0 = static_cast<int>(std::floor(row_frac));
    int c0 = static_cast<int>(std::floor(col_frac));
    int r1 = std::min(r0 + 1, surface.rows - 1);
    int c1 = std::min(c0 + 1, surface.cols - 1);
    double tr = row_frac - r0;
    double tc = col_frac - c0;

    const auto& p00 = surface.points[r0][c0];
    const auto& p01 = surface.points[r0][c1];
    const auto& p10 = surface.points[r1][c0];
    const auto& p11 = surface.points[r1][c1];

    double x0 = p00.x + (p01.x - p00.x) * tc;
    double y0 = p00.y + (p01.y - p00.y) * tc;
    double x1 = p10.x + (p11.x - p10.x) * tc;
    double y1 = p10.y + (p11.y - p10.y) * tc;
    return Point2D{ x0 + (x1 - x0) * tr,
                    y0 + (y1 - y0) * tr };
}

}  // namespace tuner_core::table_surface_3d
