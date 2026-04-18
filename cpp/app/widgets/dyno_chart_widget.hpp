// SPDX-License-Identifier: MIT
//
// DynoChartWidget — torque + HP curves over RPM.
// Dual-axis: left axis is torque (Nm) in accent_primary, right axis is
// horsepower in accent_warning. Peak markers annotate both curves with
// bold labels. Optional dashed overlay underneath the primary curves
// for two-pull comparison (G8). Same QPainter + token grammar as
// HistogramWidget.

#pragma once

#include <QWidget>

#include "tuner_core/virtual_dyno.hpp"

class QPaintEvent;

class DynoChartWidget : public QWidget {
public:
    explicit DynoChartWidget(QWidget* parent = nullptr);

    void set_result(const tuner_core::virtual_dyno::DynoResult& r);
    void clear_result();

    // Overlay / "before" comparison track (G8). Rendered as dashed
    // torque + HP lines underneath the primary curves so the operator
    // can eyeball the delta between two WOT pulls without exporting to
    // a spreadsheet. The overlay shares the same axis ranges as the
    // primary so the comparison is visually honest.
    void set_overlay(const tuner_core::virtual_dyno::DynoResult& r);
    void clear_overlay();

    bool has_overlay() const { return has_overlay_; }

protected:
    void paintEvent(QPaintEvent*) override;

private:
    tuner_core::virtual_dyno::DynoResult result_;
    tuner_core::virtual_dyno::DynoResult overlay_;
    bool has_overlay_ = false;
};
