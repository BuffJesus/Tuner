// SPDX-License-Identifier: MIT
//
// TableSurface3DView — wireframe 3D surface render of a 2D table value
// grid. Sub-slice 83 of Phase 14 Slice 4. Consumes the pure-logic
// projection math from `tuner_core::table_surface_3d` and paints the
// resulting mesh with QPainter. Supports mouse-drag rotation (azimuth
// on X, elevation on Y) and overlays the live operating-point crosshair
// via `interpolate_screen_point`.
//
// No Q_OBJECT — no signals/slots needed, so MOC stays out of the
// picture.

#pragma once

#include <QColor>
#include <QPoint>
#include <QSize>
#include <QWidget>

#include <vector>

class QMouseEvent;
class QPaintEvent;

class TableSurface3DView : public QWidget {
public:
    explicit TableSurface3DView(QWidget* parent = nullptr);

    void set_table(const std::vector<double>& values, int rows, int cols);
    void set_operating_point(double row_frac, double col_frac);
    void clear_operating_point();
    void set_azimuth(double deg);
    void set_elevation(double deg);

    double azimuth() const { return azimuth_; }
    double elevation() const { return elevation_; }

protected:
    QSize sizeHint() const override { return QSize(360, 260); }

    void mousePressEvent(QMouseEvent* e) override;
    void mouseMoveEvent(QMouseEvent* e) override;
    void mouseReleaseEvent(QMouseEvent* e) override;
    void paintEvent(QPaintEvent*) override;

private:
    static QColor heat_color(double t);

    std::vector<double> values_;
    int rows_ = 0, cols_ = 0;
    double azimuth_ = 45.0;
    double elevation_ = 30.0;
    double op_row_ = -1.0;
    double op_col_ = -1.0;
    QPoint drag_last_;
    bool dragging_ = false;
};
