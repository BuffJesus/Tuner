// SPDX-License-Identifier: MIT
//
// DialGaugeWidget — analog dial gauge with sweep arc, zone coloring,
// tapered needle, and value/units/title readout. Supports drag-swap with
// other dashboard widgets via the `application/x-gauge-widget-id` MIME
// type and right-click "Configure Gauge..." via a config callback.

#pragma once

#include <QPoint>
#include <QWidget>

#include <functional>
#include <string>
#include <vector>

class QContextMenuEvent;
class QDragEnterEvent;
class QDropEvent;
class QMouseEvent;
class QPaintEvent;

class DialGaugeWidget : public QWidget {
public:
    struct Config {
        std::string title;
        std::string units;
        double min_value = 0;
        double max_value = 100;
        struct Zone { double lo; double hi; std::string color; };
        std::vector<Zone> zones;
    };

    using ClickCallback = std::function<void(const std::string& title)>;
    using ConfigCallback = std::function<void(const std::string& widget_id)>;
    using SwapCallback = std::function<void(const std::string& from, const std::string& to)>;

    explicit DialGaugeWidget(const Config& cfg, QWidget* parent = nullptr);

    void set_value(double v) { value_ = v; has_value_ = true; update(); }
    void clear_value() { has_value_ = false; update(); }
    void set_click_callback(ClickCallback cb) { click_cb_ = std::move(cb); }
    void set_config_callback(ConfigCallback cb) { config_cb_ = std::move(cb); }
    void set_swap_callback(SwapCallback cb) { swap_cb_ = std::move(cb); }
    void set_widget_id(const std::string& id) { widget_id_ = id; }

protected:
    void mousePressEvent(QMouseEvent* ev) override;
    void contextMenuEvent(QContextMenuEvent* ev) override;
    void mouseMoveEvent(QMouseEvent* ev) override;
    void mouseReleaseEvent(QMouseEvent* ev) override;
    void dragEnterEvent(QDragEnterEvent* ev) override;
    void dropEvent(QDropEvent* ev) override;
    void paintEvent(QPaintEvent*) override;

private:
    Config cfg_;
    double value_ = 0;
    bool has_value_ = false;
    ClickCallback click_cb_;
    ConfigCallback config_cb_;
    SwapCallback swap_cb_;
    std::string widget_id_;
    QPoint drag_start_;
    bool click_armed_ = false;
    bool dragged_ = false;
};
