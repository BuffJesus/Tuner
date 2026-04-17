// SPDX-License-Identifier: MIT
//
// DynoChartWidget — torque + HP curves over RPM.
// Dual-axis: left axis is torque (Nm) in accent_primary, right axis is
// horsepower in accent_warning. Peak markers annotate both curves with
// bold labels. Same QPainter + token grammar as HistogramWidget.
//
// Extracted from cpp/app/main.cpp. Header-only; no Q_OBJECT.

#pragma once

#include "../theme.hpp"

#include "tuner_core/chart_axes.hpp"
#include "tuner_core/virtual_dyno.hpp"

#include <QBrush>
#include <QColor>
#include <QFont>
#include <QPaintEvent>
#include <QPainter>
#include <QPen>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QWidget>
#include <Qt>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdio>

namespace tuner_app {

class DynoChartWidget : public QWidget {
public:
    explicit DynoChartWidget(QWidget* parent = nullptr) : QWidget(parent) {
        setMinimumSize(420, 240);
    }

    void set_result(const tuner_core::virtual_dyno::DynoResult& r) {
        result_ = r;
        update();
    }

    void clear_result() {
        result_ = {};
        update();
    }

    // Overlay / "before" comparison track (G8). Rendered as dashed
    // torque + HP lines underneath the primary curves so the operator
    // can eyeball the delta between two WOT pulls without exporting to
    // a spreadsheet. The overlay shares the same axis ranges as the
    // primary so the comparison is visually honest.
    void set_overlay(const tuner_core::virtual_dyno::DynoResult& r) {
        overlay_ = r;
        has_overlay_ = true;
        update();
    }

    void clear_overlay() {
        overlay_ = {};
        has_overlay_ = false;
        update();
    }

    bool has_overlay() const { return has_overlay_; }

protected:
    void paintEvent(QPaintEvent*) override {
        namespace tt = tuner_theme;
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        const double w = width(), h = height();

        p.fillRect(rect(), QColor(tt::bg_deep));
        p.setPen(QPen(QColor(tt::border), 1));
        p.drawRect(0, 0, static_cast<int>(w) - 1, static_cast<int>(h) - 1);

        const int ml = 52, mr = 52, mt = 32, mb = 26;
        const double pw = w - ml - mr;
        const double ph = h - mt - mb;

        if (result_.points.size() < 2 || pw <= 0 || ph <= 0) {
            p.setPen(QColor(tt::text_muted));
            QFont f; f.setPixelSize(tt::font_small); p.setFont(f);
            p.drawText(rect(), Qt::AlignCenter,
                QString::fromUtf8("Import a WOT pull CSV to see the dyno curve"));
            return;
        }

        double rpm_min = result_.points.front().rpm;
        double rpm_max = result_.points.back().rpm;
        double tq_max = 0, hp_max = 0;
        for (const auto& pt : result_.points) {
            tq_max = std::max(tq_max, pt.torque_nm);
            hp_max = std::max(hp_max, pt.horsepower);
        }
        // Fold the overlay into the range calculation so both curves
        // stay on the same axis scale — otherwise two pulls with
        // different peaks would render against different Y grids and
        // the visual comparison would be a lie.
        if (has_overlay_ && !overlay_.points.empty()) {
            rpm_min = std::min(rpm_min, overlay_.points.front().rpm);
            rpm_max = std::max(rpm_max, overlay_.points.back().rpm);
            for (const auto& pt : overlay_.points) {
                tq_max = std::max(tq_max, pt.torque_nm);
                hp_max = std::max(hp_max, pt.horsepower);
            }
        }
        tq_max = tuner_core::chart_axes::nice_ceiling(tq_max * 1.1);
        hp_max = tuner_core::chart_axes::nice_ceiling(hp_max * 1.1);
        double rpm_span = std::max(1.0, rpm_max - rpm_min);

        auto x_at = [&](double rpm) {
            return ml + ((rpm - rpm_min) / rpm_span) * pw;
        };
        auto y_tq = [&](double v) { return mt + ph - (v / tq_max) * ph; };
        auto y_hp = [&](double v) { return mt + ph - (v / hp_max) * ph; };

        p.setPen(QPen(QColor(tt::fill_primary_soft), 1, Qt::DotLine));
        for (int i = 1; i < 4; ++i) {
            double y = mt + ph * i / 4.0;
            p.drawLine(QPointF(ml, y), QPointF(ml + pw, y));
        }
        double step = tuner_core::chart_axes::rpm_tick_step(rpm_span);
        for (double rpm = std::ceil(rpm_min / step) * step;
             rpm <= rpm_max; rpm += step) {
            double x = x_at(rpm);
            p.drawLine(QPointF(x, mt), QPointF(x, mt + ph));
        }

        // Overlay curves (dashed, muted) under the primary curves so
        // the comparison reads as "this was the baseline, here's the
        // current pull on top". Only drawn when has_overlay_.
        if (has_overlay_ && overlay_.points.size() >= 2) {
            QColor tq_overlay(tt::accent_primary);
            tq_overlay.setAlpha(140);
            p.setPen(QPen(tq_overlay, 1.5, Qt::DashLine));
            for (size_t i = 1; i < overlay_.points.size(); ++i) {
                p.drawLine(QPointF(x_at(overlay_.points[i - 1].rpm),
                                   y_tq(overlay_.points[i - 1].torque_nm)),
                           QPointF(x_at(overlay_.points[i].rpm),
                                   y_tq(overlay_.points[i].torque_nm)));
            }
            QColor hp_overlay(tt::accent_warning);
            hp_overlay.setAlpha(140);
            p.setPen(QPen(hp_overlay, 1.5, Qt::DashLine));
            for (size_t i = 1; i < overlay_.points.size(); ++i) {
                p.drawLine(QPointF(x_at(overlay_.points[i - 1].rpm),
                                   y_hp(overlay_.points[i - 1].horsepower)),
                           QPointF(x_at(overlay_.points[i].rpm),
                                   y_hp(overlay_.points[i].horsepower)));
            }
        }

        p.setPen(QPen(QColor(tt::accent_primary), 2));
        for (size_t i = 1; i < result_.points.size(); ++i) {
            p.drawLine(QPointF(x_at(result_.points[i - 1].rpm),
                               y_tq(result_.points[i - 1].torque_nm)),
                       QPointF(x_at(result_.points[i].rpm),
                               y_tq(result_.points[i].torque_nm)));
        }

        p.setPen(QPen(QColor(tt::accent_warning), 2));
        for (size_t i = 1; i < result_.points.size(); ++i) {
            p.drawLine(QPointF(x_at(result_.points[i - 1].rpm),
                               y_hp(result_.points[i - 1].horsepower)),
                       QPointF(x_at(result_.points[i].rpm),
                               y_hp(result_.points[i].horsepower)));
        }

        auto draw_peak = [&](double x, double y, const char* label,
                             const QColor& color) {
            p.setPen(QPen(color, 2));
            p.setBrush(color);
            p.drawEllipse(QPointF(x, y), 4, 4);
            p.setBrush(Qt::NoBrush);
            p.setPen(QColor(tt::text_primary));
            QFont f; f.setPixelSize(tt::font_small); f.setBold(true); p.setFont(f);
            p.drawText(QPointF(x + 7, y - 6), QString::fromUtf8(label));
        };
        char tq_lbl[48], hp_lbl[48];
        std::snprintf(tq_lbl, sizeof(tq_lbl), "%.0f Nm @ %.0f",
            result_.peak_torque_nm, result_.peak_torque_rpm);
        std::snprintf(hp_lbl, sizeof(hp_lbl), "%.0f hp @ %.0f",
            result_.peak_hp, result_.peak_hp_rpm);
        draw_peak(x_at(result_.peak_torque_rpm),
                  y_tq(result_.peak_torque_nm),
                  tq_lbl, QColor(tt::accent_primary));
        draw_peak(x_at(result_.peak_hp_rpm),
                  y_hp(result_.peak_hp),
                  hp_lbl, QColor(tt::accent_warning));

        QFont af; af.setPixelSize(tt::font_small); p.setFont(af);

        p.setPen(QColor(tt::accent_primary));
        for (int i = 0; i <= 4; ++i) {
            double v = tq_max * i / 4.0;
            double y = mt + ph - (v / tq_max) * ph;
            char buf[16]; std::snprintf(buf, sizeof(buf), "%.0f", v);
            p.drawText(QRectF(0, y - 8, ml - 4, 16),
                       Qt::AlignRight | Qt::AlignVCenter,
                       QString::fromUtf8(buf));
        }

        p.setPen(QColor(tt::accent_warning));
        for (int i = 0; i <= 4; ++i) {
            double v = hp_max * i / 4.0;
            double y = mt + ph - (v / hp_max) * ph;
            char buf[16]; std::snprintf(buf, sizeof(buf), "%.0f", v);
            p.drawText(QRectF(ml + pw + 4, y - 8, mr - 8, 16),
                       Qt::AlignLeft | Qt::AlignVCenter,
                       QString::fromUtf8(buf));
        }

        p.setPen(QColor(tt::text_muted));
        for (double rpm = std::ceil(rpm_min / step) * step;
             rpm <= rpm_max; rpm += step) {
            double x = x_at(rpm);
            char buf[16]; std::snprintf(buf, sizeof(buf), "%.0f", rpm);
            p.drawText(QRectF(x - 28, mt + ph + 4, 56, 16),
                       Qt::AlignCenter, QString::fromUtf8(buf));
        }

        p.setPen(QColor(tt::text_primary));
        QFont hf; hf.setPixelSize(tt::font_label); hf.setBold(true); p.setFont(hf);
        p.drawText(QPointF(ml, mt - 12), QString::fromUtf8("Dyno Curve"));

        QFont lf; lf.setPixelSize(tt::font_small); p.setFont(lf);
        double lx = ml + pw - 150;
        p.setPen(QPen(QColor(tt::accent_primary), 2));
        p.drawLine(QPointF(lx, mt - 14), QPointF(lx + 14, mt - 14));
        p.setPen(QColor(tt::text_secondary));
        p.drawText(QPointF(lx + 18, mt - 10), QString::fromUtf8("Torque (Nm)"));

        p.setPen(QPen(QColor(tt::accent_warning), 2));
        p.drawLine(QPointF(lx + 90, mt - 14), QPointF(lx + 104, mt - 14));
        p.setPen(QColor(tt::text_secondary));
        p.drawText(QPointF(lx + 108, mt - 10), QString::fromUtf8("HP"));
    }

private:
    tuner_core::virtual_dyno::DynoResult result_;
    tuner_core::virtual_dyno::DynoResult overlay_;
    bool has_overlay_ = false;
};

}  // namespace tuner_app
