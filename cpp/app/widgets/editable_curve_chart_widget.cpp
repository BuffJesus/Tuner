// SPDX-License-Identifier: MIT

#include "widgets/editable_curve_chart_widget.hpp"

#include <QColor>
#include <QFont>
#include <QMouseEvent>
#include <QPaintEvent>
#include <QPainter>
#include <QPen>
#include <QPolygonF>
#include <QRectF>
#include <QString>

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace tt = tuner_theme;

EditableCurveChartWidget::EditableCurveChartWidget(QWidget* parent) : QWidget(parent) {
    setMinimumSize(420, 180);
    setMouseTracking(true);
}

void EditableCurveChartWidget::set_data(const std::vector<double>& x,
                                        const std::vector<double>& y,
                                        const std::string& x_units,
                                        const std::string& y_units,
                                        double y_min, double y_max) {
    x_ = x;
    y_ = y;
    x_units_ = x_units;
    y_units_ = y_units;
    y_min_ = y_min;
    y_max_ = y_max;
    update();
}

void EditableCurveChartWidget::set_y_value(std::size_t index, double v) {
    if (index < y_.size()) {
        y_[index] = v;
        update();
    }
}

void EditableCurveChartWidget::set_accent(const char* accent_hex) {
    accent_ = accent_hex;
    update();
}

void EditableCurveChartWidget::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    p.fillRect(rect(), QColor(QString::fromUtf8(tt::bg_elevated)));

    if (x_.empty() || y_.empty()) return;

    const int left_pad = 44;
    const int right_pad = 12;
    const int top_pad = 10;
    const int bot_pad = 26;
    QRectF plot(left_pad, top_pad,
                width() - left_pad - right_pad,
                height() - top_pad - bot_pad);
    if (plot.width() <= 0 || plot.height() <= 0) return;

    const std::size_t n = std::min(x_.size(), y_.size());
    double y_lo = y_min_;
    double y_hi = y_max_;
    if (y_hi <= y_lo) {
        double mn = *std::min_element(y_.begin(), y_.begin() + n);
        double mx = *std::max_element(y_.begin(), y_.begin() + n);
        double span = std::max(1.0, mx - mn);
        y_lo = mn - span * 0.10;
        y_hi = mx + span * 0.10;
    }
    double y_span = std::max(1e-9, y_hi - y_lo);

    p.setPen(QPen(QColor(QString::fromUtf8(tt::border)), 1, Qt::DotLine));
    for (int i = 0; i <= 4; ++i) {
        double y = plot.top() + plot.height() * i / 4.0;
        p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y));
        double v = y_hi - y_span * i / 4.0;
        char yl[32];
        std::snprintf(yl, sizeof(yl), "%.1f", v);
        p.setPen(QColor(QString::fromUtf8(tt::text_muted)));
        QFont af = p.font(); af.setPixelSize(tt::font_micro); p.setFont(af);
        p.drawText(QRectF(0, y - 8, left_pad - 4, 16),
                   Qt::AlignRight | Qt::AlignVCenter,
                   QString::fromUtf8(yl));
        p.setPen(QPen(QColor(QString::fromUtf8(tt::border)), 1, Qt::DotLine));
    }

    points_.clear();
    points_.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        double xf = (n == 1) ? 0.5
            : static_cast<double>(i) / static_cast<double>(n - 1);
        double yf = (y_[i] - y_lo) / y_span;
        QPointF pt(plot.left() + xf * plot.width(),
                   plot.bottom() - yf * plot.height());
        points_.push_back(pt);
    }

    QColor accent(QString::fromUtf8(accent_));
    QColor accent_soft = accent; accent_soft.setAlpha(60);

    QPolygonF fill;
    fill.append(QPointF(points_.front().x(), plot.bottom()));
    for (const auto& pt : points_) fill.append(pt);
    fill.append(QPointF(points_.back().x(), plot.bottom()));
    p.setPen(Qt::NoPen);
    p.setBrush(accent_soft);
    p.drawPolygon(fill);

    p.setPen(QPen(accent, 2.0, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    p.setBrush(Qt::NoBrush);
    for (std::size_t i = 1; i < points_.size(); ++i)
        p.drawLine(points_[i - 1], points_[i]);

    for (std::size_t i = 0; i < points_.size(); ++i) {
        double r = (editing_ && i == drag_index_) ? 5.5 : 3.5;
        p.setPen(QPen(QColor(QString::fromUtf8(tt::bg_base)), 1.5));
        p.setBrush(accent);
        p.drawEllipse(points_[i], r, r);
    }

    p.setPen(QColor(QString::fromUtf8(tt::text_muted)));
    QFont af = p.font(); af.setPixelSize(tt::font_micro); p.setFont(af);
    auto draw_x_label = [&](std::size_t i) {
        if (i >= x_.size()) return;
        char xl[40];
        std::snprintf(xl, sizeof(xl), "%g", x_[i]);
        p.drawText(
            QRectF(points_[i].x() - 32, plot.bottom() + 4, 64, 14),
            Qt::AlignCenter, QString::fromUtf8(xl));
    };
    draw_x_label(0);
    if (n >= 3) draw_x_label(n / 2);
    if (n >= 2) draw_x_label(n - 1);

    if (!x_units_.empty() || !y_units_.empty()) {
        char ulbl[64];
        std::snprintf(ulbl, sizeof(ulbl), "Y %s  \xc2\xb7  X %s",
            y_units_.c_str(), x_units_.c_str());
        p.setPen(QColor(QString::fromUtf8(tt::text_dim)));
        p.drawText(
            QRectF(plot.left(), plot.bottom() + 14, plot.width(), 12),
            Qt::AlignRight | Qt::AlignVCenter,
            QString::fromUtf8(ulbl));
    }
}

void EditableCurveChartWidget::mousePressEvent(QMouseEvent* ev) {
    if (!on_value_changed) return;
    if (ev->button() != Qt::LeftButton) return;
    int idx = nearest_vertex(ev->position());
    if (idx < 0) return;
    editing_ = true;
    drag_index_ = static_cast<std::size_t>(idx);
    apply_drag(ev->position());
}

void EditableCurveChartWidget::mouseMoveEvent(QMouseEvent* ev) {
    if (!editing_) return;
    apply_drag(ev->position());
}

void EditableCurveChartWidget::mouseReleaseEvent(QMouseEvent*) {
    editing_ = false;
    update();
}

int EditableCurveChartWidget::nearest_vertex(QPointF pos) const {
    int best = -1;
    double best_d = 20.0;
    for (std::size_t i = 0; i < points_.size(); ++i) {
        double dx = points_[i].x() - pos.x();
        double dy = points_[i].y() - pos.y();
        double d = std::sqrt(dx * dx + dy * dy);
        if (d < best_d) { best_d = d; best = static_cast<int>(i); }
    }
    return best;
}

void EditableCurveChartWidget::apply_drag(QPointF pos) {
    if (drag_index_ >= y_.size()) return;
    const int top_pad = 10;
    const int bot_pad = 26;
    double plot_top = top_pad;
    double plot_bot = height() - bot_pad;
    double plot_h = plot_bot - plot_top;
    if (plot_h <= 0) return;

    double y_lo = y_min_, y_hi = y_max_;
    if (y_hi <= y_lo) {
        double mn = *std::min_element(y_.begin(), y_.end());
        double mx = *std::max_element(y_.begin(), y_.end());
        double span = std::max(1.0, mx - mn);
        y_lo = mn - span * 0.10;
        y_hi = mx + span * 0.10;
    }
    double yf = (plot_bot - pos.y()) / plot_h;
    if (yf < 0.0) yf = 0.0;
    if (yf > 1.0) yf = 1.0;
    double new_v = y_lo + yf * (y_hi - y_lo);
    y_[drag_index_] = new_v;
    update();
    if (on_value_changed) on_value_changed(drag_index_, new_v);
}
