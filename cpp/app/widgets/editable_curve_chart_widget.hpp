// SPDX-License-Identifier: MIT
//
// EditableCurveChartWidget — live line-chart editor for 1D curves.
// Paints bins on the X axis and values on the Y axis with a connected
// polyline + filled area + draggable vertex dots. Click a vertex and
// drag vertically to change that bin's Y value; `on_value_changed`
// fires with (index, new_value) so the caller can stage the edit +
// sync a companion QTableWidget. Read-only when on_value_changed is
// left null. No Q_OBJECT — uses std::function callbacks.

#pragma once

#include <QPointF>
#include <QWidget>

#include <cstddef>
#include <functional>
#include <string>
#include <vector>

#include "theme.hpp"

class QMouseEvent;
class QPaintEvent;

class EditableCurveChartWidget : public QWidget {
public:
    explicit EditableCurveChartWidget(QWidget* parent = nullptr);

    void set_data(const std::vector<double>& x,
                  const std::vector<double>& y,
                  const std::string& x_units,
                  const std::string& y_units,
                  double y_min, double y_max);

    void set_y_value(std::size_t index, double v);
    void set_accent(const char* accent_hex);

    std::function<void(std::size_t, double)> on_value_changed;

protected:
    void paintEvent(QPaintEvent*) override;
    void mousePressEvent(QMouseEvent* ev) override;
    void mouseMoveEvent(QMouseEvent* ev) override;
    void mouseReleaseEvent(QMouseEvent*) override;

private:
    int nearest_vertex(QPointF pos) const;
    void apply_drag(QPointF pos);

    std::vector<double> x_;
    std::vector<double> y_;
    std::string x_units_;
    std::string y_units_;
    double y_min_ = 0.0;
    double y_max_ = 0.0;
    const char* accent_ = tuner_theme::accent_primary;
    mutable std::vector<QPointF> points_;
    bool editing_ = false;
    std::size_t drag_index_ = 0;
};
