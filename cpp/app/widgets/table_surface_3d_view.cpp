// SPDX-License-Identifier: MIT

#include "widgets/table_surface_3d_view.hpp"

#include "tuner_core/table_surface_3d.hpp"

#include <QColor>
#include <QFont>
#include <QMouseEvent>
#include <QPaintEvent>
#include <QPainter>
#include <QPen>
#include <QPointF>
#include <QRect>
#include <QString>

#include <algorithm>
#include <cstddef>
#include <cstdio>

TableSurface3DView::TableSurface3DView(QWidget* parent) : QWidget(parent) {
    setMinimumSize(240, 180);
    setAttribute(Qt::WA_OpaquePaintEvent, true);
    setCursor(Qt::OpenHandCursor);
}

void TableSurface3DView::set_table(const std::vector<double>& values, int rows, int cols) {
    values_ = values;
    rows_ = rows;
    cols_ = cols;
    update();
}

void TableSurface3DView::set_operating_point(double row_frac, double col_frac) {
    op_row_ = row_frac;
    op_col_ = col_frac;
    update();
}

void TableSurface3DView::clear_operating_point() {
    op_row_ = -1.0;
    op_col_ = -1.0;
    update();
}

void TableSurface3DView::set_azimuth(double deg) {
    while (deg < 0) deg += 360;
    while (deg >= 360) deg -= 360;
    azimuth_ = deg;
    update();
}

void TableSurface3DView::set_elevation(double deg) {
    if (deg < 15) deg = 15;
    if (deg > 85) deg = 85;
    elevation_ = deg;
    update();
}

void TableSurface3DView::mousePressEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        dragging_ = true;
        drag_last_ = e->pos();
        setCursor(Qt::ClosedHandCursor);
    }
}

void TableSurface3DView::mouseMoveEvent(QMouseEvent* e) {
    if (!dragging_) return;
    QPoint d = e->pos() - drag_last_;
    drag_last_ = e->pos();
    set_azimuth(azimuth_ + d.x() * 0.6);
    set_elevation(elevation_ - d.y() * 0.4);
}

void TableSurface3DView::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        dragging_ = false;
        setCursor(Qt::OpenHandCursor);
    }
}

void TableSurface3DView::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    p.fillRect(rect(), QColor(26, 29, 36));

    const double w = width(), h = height();

    if (rows_ <= 0 || cols_ <= 0 || values_.empty()) {
        p.setPen(QColor(138, 147, 166));
        QFont f = p.font(); f.setPointSize(9); p.setFont(f);
        p.drawText(rect(), Qt::AlignCenter, QString::fromUtf8("No table data"));
        return;
    }

    namespace ts3d = tuner_core::table_surface_3d;
    auto surface = ts3d::project(values_, rows_, cols_,
                                 azimuth_, elevation_, w, h);
    if (surface.points.empty()) return;

    const double range = std::max(1.0, surface.max_value - surface.min_value);

    // Col-parallel edges (walk cols within each row).
    for (int r = 0; r < surface.rows; ++r) {
        for (int c = 0; c + 1 < surface.cols; ++c) {
            const auto& a = surface.points[r][c];
            const auto& b = surface.points[r][c + 1];
            double va = (surface.values[r][c] - surface.min_value) / range;
            double vb = (surface.values[r][c + 1] - surface.min_value) / range;
            QColor col = heat_color((va + vb) * 0.5);
            col.setAlphaF(0.9);
            p.setPen(QPen(col, 1.4));
            p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y));
        }
    }
    // Row-parallel edges (walk rows within each col).
    for (int c = 0; c < surface.cols; ++c) {
        for (int r = 0; r + 1 < surface.rows; ++r) {
            const auto& a = surface.points[r][c];
            const auto& b = surface.points[r + 1][c];
            double va = (surface.values[r][c] - surface.min_value) / range;
            double vb = (surface.values[r + 1][c] - surface.min_value) / range;
            QColor col = heat_color((va + vb) * 0.5);
            col.setAlphaF(0.9);
            p.setPen(QPen(col, 1.4));
            p.drawLine(QPointF(a.x, a.y), QPointF(b.x, b.y));
        }
    }

    // Value dots at each vertex.
    for (int r = 0; r < surface.rows; ++r) {
        for (int c = 0; c < surface.cols; ++c) {
            double v = (surface.values[r][c] - surface.min_value) / range;
            QColor col = heat_color(v);
            p.setPen(Qt::NoPen);
            p.setBrush(col);
            p.drawEllipse(QPointF(surface.points[r][c].x,
                                  surface.points[r][c].y),
                          2.4, 2.4);
        }
    }

    // Crosshair at the live operating point.
    if (op_row_ >= 0.0 && op_col_ >= 0.0) {
        auto pt = ts3d::interpolate_screen_point(surface, op_row_, op_col_);
        if (pt) {
            p.setPen(QPen(QColor(255, 255, 255), 2.0));
            p.setBrush(QColor(255, 68, 68));
            p.drawEllipse(QPointF(pt->x, pt->y), 5.0, 5.0);
            p.setPen(QPen(QColor(255, 68, 68, 200), 1.0, Qt::DashLine));
            p.drawLine(QPointF(pt->x - 14, pt->y), QPointF(pt->x + 14, pt->y));
            p.drawLine(QPointF(pt->x, pt->y - 14), QPointF(pt->x, pt->y + 14));
        }
    }

    // Corner labels.
    char buf[160];
    std::snprintf(buf, sizeof(buf),
        "min %.1f  \xc2\xb7  max %.1f  \xc2\xb7  az %.0f\xc2\xb0  el %.0f\xc2\xb0",
        surface.min_value, surface.max_value, azimuth_, elevation_);
    QFont lf = p.font(); lf.setPixelSize(10); p.setFont(lf);
    p.setPen(QColor(138, 147, 166));
    p.drawText(QRect(6, 4, static_cast<int>(w) - 12, 14),
               Qt::AlignLeft | Qt::AlignTop,
               QString::fromUtf8(buf));
    p.setPen(QColor(106, 112, 128));
    p.drawText(QRect(6, static_cast<int>(h) - 16, static_cast<int>(w) - 12, 14),
               Qt::AlignRight | Qt::AlignBottom,
               QString::fromUtf8("drag to rotate"));
}

QColor TableSurface3DView::heat_color(double t) {
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    struct Stop { double t; int r, g, b; };
    static const Stop stops[] = {
        {0.00,  50,  90, 180},
        {0.25,  40, 170, 200},
        {0.50,  90, 200, 110},
        {0.75, 230, 200,  80},
        {1.00, 220,  80,  60},
    };
    for (std::size_t i = 0; i + 1 < sizeof(stops) / sizeof(stops[0]); ++i) {
        if (t <= stops[i + 1].t) {
            double span = stops[i + 1].t - stops[i].t;
            double u = span > 0 ? (t - stops[i].t) / span : 0.0;
            int r = static_cast<int>(stops[i].r + (stops[i + 1].r - stops[i].r) * u);
            int g = static_cast<int>(stops[i].g + (stops[i + 1].g - stops[i].g) * u);
            int b = static_cast<int>(stops[i].b + (stops[i + 1].b - stops[i].b) * u);
            return QColor(r, g, b);
        }
    }
    return QColor(stops[4].r, stops[4].g, stops[4].b);
}
