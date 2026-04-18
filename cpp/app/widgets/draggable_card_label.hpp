// SPDX-License-Identifier: MIT
//
// DraggableCardLabel — QLabel subclass that mirrors DialGaugeWidget's
// drag-swap + right-click-config pattern so number-card dashboard
// widgets are first-class citizens alongside the dial gauges. Uses the
// same `application/x-gauge-widget-id` MIME type, so cards and dials
// can swap positions interchangeably.

#pragma once

#include <QLabel>
#include <QPoint>

#include <functional>
#include <string>

class QContextMenuEvent;
class QDragEnterEvent;
class QDropEvent;
class QMouseEvent;

class DraggableCardLabel : public QLabel {
public:
    using ConfigCallback = std::function<void(const std::string& widget_id)>;
    using SwapCallback = std::function<void(const std::string& from, const std::string& to)>;

    explicit DraggableCardLabel(QWidget* parent = nullptr);

    void set_widget_id(const std::string& id) { widget_id_ = id; }
    void set_config_callback(ConfigCallback cb) { config_cb_ = std::move(cb); }
    void set_swap_callback(SwapCallback cb) { swap_cb_ = std::move(cb); }

protected:
    void mousePressEvent(QMouseEvent* ev) override;
    void mouseMoveEvent(QMouseEvent* ev) override;
    void contextMenuEvent(QContextMenuEvent* ev) override;
    void dragEnterEvent(QDragEnterEvent* ev) override;
    void dropEvent(QDropEvent* ev) override;

private:
    ConfigCallback config_cb_;
    SwapCallback swap_cb_;
    std::string widget_id_;
    QPoint drag_start_;
};
