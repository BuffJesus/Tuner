// SPDX-License-Identifier: MIT
//
// HistogramWidget — scrolling sparkline chart (Phase D).
//
// Extracted from cpp/app/main.cpp. Header-only; no Q_OBJECT.

#pragma once

#include "../theme.hpp"

#include <QColor>
#include <QFont>
#include <QPaintEvent>
#include <QPainter>
#include <QPen>
#include <QPointF>
#include <QString>
#include <QWidget>
#include <Qt>

#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_app {

class HistogramWidget : public QWidget {
public:
    struct Config {
        std::string title;
        std::string units;
        double min_value = 0;
        double max_value = 100;
        int max_samples = 60;  // ~12 seconds at 5Hz
        std::string line_color = tuner_theme::accent_primary;
    };

    explicit HistogramWidget(const Config& cfg, QWidget* parent = nullptr)
        : QWidget(parent), cfg_(cfg) {
        setMinimumSize(200, 80);
        samples_.reserve(cfg.max_samples);
    }

    void push_value(double v) {
        samples_.push_back(v);
        if (static_cast<int>(samples_.size()) > cfg_.max_samples)
            samples_.erase(samples_.begin());
        update();
    }

protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        const double w = width(), h = height();

        // Background.
        p.fillRect(rect(), QColor(26, 29, 36));

        // Border.
        p.setPen(QPen(QColor(47, 52, 61), 1));
        p.drawRect(0, 0, static_cast<int>(w) - 1, static_cast<int>(h) - 1);

        if (samples_.size() < 2) {
            p.setPen(QColor(100, 106, 120));
            QFont f; f.setPixelSize(10); p.setFont(f);
            p.drawText(rect(), Qt::AlignCenter, QString::fromUtf8("Waiting for data..."));
            return;
        }

        double range = cfg_.max_value - cfg_.min_value;
        if (range <= 0) range = 1;

        // Draw gridlines.
        p.setPen(QPen(QColor(35, 39, 48), 1));
        for (int i = 1; i < 4; ++i) {
            double y = h * i / 4.0;
            p.drawLine(QPointF(0, y), QPointF(w, y));
        }

        // Draw line.
        QColor lineColor(cfg_.line_color.c_str());
        p.setPen(QPen(lineColor, 1.5));
        int n = static_cast<int>(samples_.size());
        double step = w / std::max(1, cfg_.max_samples - 1);
        double x_offset = (cfg_.max_samples - n) * step;
        for (int i = 1; i < n; ++i) {
            double x0 = x_offset + (i - 1) * step;
            double x1 = x_offset + i * step;
            double y0 = h - ((samples_[i - 1] - cfg_.min_value) / range) * h;
            double y1 = h - ((samples_[i] - cfg_.min_value) / range) * h;
            y0 = std::clamp(y0, 0.0, h);
            y1 = std::clamp(y1, 0.0, h);
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1));
        }

        // Title + latest value.
        p.setPen(QColor(138, 147, 166));
        QFont tf; tf.setPixelSize(9); p.setFont(tf);
        char label[64];
        std::snprintf(label, sizeof(label), "%s: %.1f %s",
            cfg_.title.c_str(), samples_.back(), cfg_.units.c_str());
        p.drawText(4, 12, QString::fromUtf8(label));

        // Min/max labels.
        char min_label[16], max_label[16];
        std::snprintf(min_label, sizeof(min_label), "%.0f", cfg_.min_value);
        std::snprintf(max_label, sizeof(max_label), "%.0f", cfg_.max_value);
        p.drawText(4, static_cast<int>(h) - 3, QString::fromUtf8(min_label));
        p.drawText(4, 22, QString::fromUtf8(max_label));
    }

private:
    Config cfg_;
    std::vector<double> samples_;
};

}  // namespace tuner_app
