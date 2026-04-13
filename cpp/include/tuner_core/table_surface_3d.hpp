// SPDX-License-Identifier: MIT
//
// tuner_core::table_surface_3d — 3D surface projection for table values.
// Sub-slice 82 of Phase 14 Slice 4.
//
// Projects a 2D table (rows × cols of values) into 3D wireframe
// vertices for QPainter rendering.  Pure math, no Qt dependency.

#pragma once

#include <cmath>
#include <optional>
#include <vector>

namespace tuner_core::table_surface_3d {

struct Point2D { double x = 0, y = 0; };

struct ProjectedSurface {
    int rows = 0, cols = 0;
    std::vector<std::vector<Point2D>> points;  // [row][col] → screen coords
    std::vector<std::vector<double>> values;   // [row][col] → original values
    double min_value = 0, max_value = 1;
};

/// Project a flat table into 3D screen coordinates.
/// azimuth: rotation around vertical axis (degrees, 0-360)
/// elevation: tilt angle (degrees, 15-90)
/// width/height: output screen size
///
/// Default azimuth is 45° — front-right camera — which puts col 0 on
/// the viewer's left and row 0 at the front of the mesh. Combined with
/// model-order input (`values[r*cols+c]` with row 0 = lowest load in
/// Speeduino's VE/AFR/spark tables), this gives the familiar
/// "low-low at front, high-high at back" 3D surface orientation where
/// RPM increases to the right and load increases away from the viewer.
///
/// Historical note: sub-slice 82 originally shipped with the default
/// at 225° (back-left camera), which rendered as a mirror-image of the
/// 2D heatmap — easy to spot when both views are side-by-side.
/// Sub-slice 83 flipped the default when wiring up the widget.
ProjectedSurface project(
    const std::vector<double>& values,
    int rows, int cols,
    double azimuth_deg = 45.0,
    double elevation_deg = 30.0,
    double width = 400.0,
    double height = 300.0);

/// Bilinear interpolation of the projected screen coordinate for a
/// fractional grid position. `row_frac` and `col_frac` are given in
/// display space, i.e. `row_frac == 0` picks row 0, `row_frac == rows-1`
/// picks the last row. Returns `nullopt` if the surface is empty or the
/// fractional coordinates fall outside the grid.
///
/// Used by the 3D table surface widget to place the live operating-point
/// crosshair on the projected mesh. Pure logic so it can be unit-tested
/// without Qt.
std::optional<Point2D> interpolate_screen_point(
    const ProjectedSurface& surface,
    double row_frac,
    double col_frac);

}  // namespace tuner_core::table_surface_3d
