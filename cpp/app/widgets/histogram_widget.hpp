// SPDX-License-Identifier: MIT
//
// HistogramWidget — scrolling sparkline chart for a single channel with
// a rolling window, gridlines, title + latest-value overlay, and
// min/max labels. Used on the LIVE tab for AFR/RPM/MAP trends.

#pragma once

#include <QWidget>

#include <string>
#include <vector>

#include "theme.hpp"

class QPaintEvent;

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

    explicit HistogramWidget(const Config& cfg, QWidget* parent = nullptr);

    void push_value(double v);

protected:
    void paintEvent(QPaintEvent*) override;

private:
    Config cfg_;
    std::vector<double> samples_;
};
