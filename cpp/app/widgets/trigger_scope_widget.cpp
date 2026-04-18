// SPDX-License-Identifier: MIT

#include "widgets/trigger_scope_widget.hpp"

#include "theme.hpp"

#include <QColor>
#include <QFont>
#include <QPaintEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QPointF>
#include <QRectF>
#include <QString>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>

namespace tt = tuner_theme;

TriggerScopeWidget::TriggerScopeWidget(QWidget* parent) : QWidget(parent) {
    setMinimumSize(560, 240);
}

void TriggerScopeWidget::set_snapshot(
    const tuner_core::trigger_log_visualization::Snapshot& s) {
    snap_ = s;
    update();
}

void TriggerScopeWidget::clear_snapshot() {
    snap_ = {};
    update();
}

void TriggerScopeWidget::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    const double w = width(), h = height();

    p.fillRect(rect(), QColor(tt::bg_deep));
    p.setPen(QPen(QColor(tt::border), 1));
    p.drawRect(0, 0, static_cast<int>(w) - 1, static_cast<int>(h) - 1);

    if (snap_.traces.empty()) {
        p.setPen(QColor(tt::text_muted));
        QFont f; f.setPixelSize(tt::font_small); p.setFont(f);
        p.drawText(rect(), Qt::AlignCenter, QString::fromUtf8(
            "Capture a trigger log to see the oscilloscope view"));
        return;
    }

    const int ml = 76, mr = 16, mt = 20, mb = 22;
    const double pw = w - ml - mr;
    const double ph = h - mt - mb;
    if (pw <= 0 || ph <= 0) return;

    double t_min = std::numeric_limits<double>::infinity();
    double t_max = -std::numeric_limits<double>::infinity();
    for (const auto& tr : snap_.traces) {
        for (double x : tr.x_values) {
            if (x < t_min) t_min = x;
            if (x > t_max) t_max = x;
        }
    }
    if (!std::isfinite(t_min)) { t_min = 0; t_max = 1; }
    if (t_max <= t_min) t_max = t_min + 1;
    double t_span = t_max - t_min;

    int n_tr = static_cast<int>(snap_.traces.size());
    double track_h = ph / n_tr;

    const char* colors[] = {
        tt::accent_primary, tt::accent_warning, tt::accent_ok,
        tt::accent_special, tt::accent_danger, tt::text_secondary
    };

    for (int ti = 0; ti < n_tr; ++ti) {
        const auto& tr = snap_.traces[ti];
        double ty0 = mt + ti * track_h;
        double ty1 = ty0 + track_h;
        const char* color = colors[ti % 6];

        p.setPen(QColor(color));
        QFont lf; lf.setPixelSize(tt::font_small); lf.setBold(true); p.setFont(lf);
        p.drawText(QRectF(0, ty0, ml - 6, track_h),
            Qt::AlignRight | Qt::AlignVCenter,
            QString::fromUtf8(tr.name.c_str()));

        if (ti > 0) {
            p.setPen(QPen(QColor(tt::border_soft), 1));
            p.drawLine(QPointF(ml, ty0), QPointF(ml + pw, ty0));
        }

        double y_min = tr.y_values.empty() ? 0
            : *std::min_element(tr.y_values.begin(), tr.y_values.end());
        double y_max = tr.y_values.empty() ? 1
            : *std::max_element(tr.y_values.begin(), tr.y_values.end());
        if (y_max <= y_min) y_max = y_min + 1;
        double y_span = y_max - y_min;

        p.save();
        p.setClipRect(QRectF(ml, ty0 + 2, pw, track_h - 4));
        p.setPen(QPen(QColor(color), 1.4));
        int N = static_cast<int>(std::min(tr.x_values.size(),
                                          tr.y_values.size()));
        if (N >= 2) {
            QPainterPath path;
            bool started = false;
            double prev_y = 0;
            for (int i = 0; i < N; ++i) {
                double x = ml + ((tr.x_values[i] - t_min) / t_span) * pw;
                double v = tr.y_values[i];
                double y = ty1 - 2
                    - ((v - y_min) / y_span) * (track_h - 4);
                if (!started) {
                    path.moveTo(x, y);
                    started = true;
                } else if (tr.is_digital) {
                    // Square-wave: horizontal segment at prev_y,
                    // then vertical to new y.
                    path.lineTo(x, prev_y);
                    path.lineTo(x, y);
                } else {
                    path.lineTo(x, y);
                }
                prev_y = y;
            }
            p.drawPath(path);
        }
        p.restore();
    }

    // Annotations — vertical marks across all tracks.
    for (const auto& ann : snap_.annotations) {
        if (ann.time_ms < t_min || ann.time_ms > t_max) continue;
        double x = ml + ((ann.time_ms - t_min) / t_span) * pw;
        bool warn = (ann.severity == "warning");
        QColor col(warn ? tt::accent_warning : tt::text_dim);
        col.setAlpha(warn ? 180 : 90);
        p.setPen(QPen(col, warn ? 1.5 : 1.0, Qt::DashLine));
        p.drawLine(QPointF(x, mt), QPointF(x, mt + ph));
    }

    // Time axis.
    QFont af; af.setPixelSize(tt::font_micro); p.setFont(af);
    p.setPen(QColor(tt::text_muted));
    for (int i = 0; i <= 4; ++i) {
        double t = t_min + t_span * i / 4.0;
        double x = ml + pw * i / 4.0;
        char buf[24];
        std::snprintf(buf, sizeof(buf), "%.1f ms", t);
        p.drawText(QRectF(x - 36, mt + ph + 2, 72, 16),
            Qt::AlignCenter, QString::fromUtf8(buf));
    }

    // Header.
    QFont hf; hf.setPixelSize(tt::font_label); hf.setBold(true); p.setFont(hf);
    p.setPen(QColor(tt::text_primary));
    p.drawText(QPointF(ml, mt - 6),
        QString::fromUtf8("Trigger Scope"));
}
