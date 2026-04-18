// SPDX-License-Identifier: MIT
//
// LedGaugeWidget — round glowing indicator colored by the active zone.
// Use case: boolean / status channels (sync / learn / fuel pump / warn
// flags) where the exact numeric value isn't interesting but the
// on/off / ok/warn/danger state is. Shares the drag-swap + right-click
// config pattern with the other dashboard gauge widgets.

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

class LedGaugeWidget : public QWidget {
public:
    struct Config {
        std::string title;
        std::string units;
        double min_value = 0;
        double max_value = 1;
        struct Zone { double lo; double hi; std::string color; };
        std::vector<Zone> zones;
    };

    using ConfigCallback = std::function<void(const std::string& widget_id)>;
    using SwapCallback = std::function<void(const std::string& from, const std::string& to)>;

    explicit LedGaugeWidget(const Config& cfg, QWidget* parent = nullptr);

    void set_value(double v) { value_ = v; has_value_ = true; update(); }
    void clear_value() { has_value_ = false; update(); }
    void set_widget_id(const std::string& id) { widget_id_ = id; }
    void set_config_callback(ConfigCallback cb) { config_cb_ = std::move(cb); }
    void set_swap_callback(SwapCallback cb) { swap_cb_ = std::move(cb); }

protected:
    void mousePressEvent(QMouseEvent* ev) override;
    void mouseMoveEvent(QMouseEvent* ev) override;
    void contextMenuEvent(QContextMenuEvent* ev) override;
    void dragEnterEvent(QDragEnterEvent* ev) override;
    void dropEvent(QDropEvent* ev) override;
    void paintEvent(QPaintEvent*) override;

private:
    Config cfg_;
    double value_ = 0;
    bool has_value_ = false;
    ConfigCallback config_cb_;
    SwapCallback swap_cb_;
    std::string widget_id_;
    QPoint drag_start_;
};
