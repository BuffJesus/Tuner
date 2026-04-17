// SPDX-License-Identifier: MIT
//
// DraggableCardLabel — QLabel subclass that mirrors DialGaugeWidget's
// drag-swap + right-click-config pattern so number-card dashboard
// widgets are first-class citizens alongside the dial gauges. Uses the
// same `application/x-gauge-widget-id` MIME type, so cards and dials
// can swap positions interchangeably.
//
// Extracted from cpp/app/main.cpp. Header-only; no Q_OBJECT.

#pragma once

#include <QAction>
#include <QByteArray>
#include <QContextMenuEvent>
#include <QCursor>
#include <QDrag>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QLabel>
#include <QMenu>
#include <QMimeData>
#include <QMouseEvent>
#include <QObject>
#include <QPoint>
#include <QWidget>
#include <Qt>

#include <functional>
#include <string>
#include <utility>

namespace tuner_app {

class DraggableCardLabel : public QLabel {
public:
    using ConfigCallback = std::function<void(const std::string& widget_id)>;
    using SwapCallback = std::function<void(const std::string& from, const std::string& to)>;

    explicit DraggableCardLabel(QWidget* parent = nullptr) : QLabel(parent) {
        setAcceptDrops(true);
        setCursor(Qt::PointingHandCursor);
    }

    void set_widget_id(const std::string& id) { widget_id_ = id; }
    void set_config_callback(ConfigCallback cb) { config_cb_ = std::move(cb); }
    void set_swap_callback(SwapCallback cb) { swap_cb_ = std::move(cb); }

protected:
    void mousePressEvent(QMouseEvent* ev) override {
        if (ev->button() == Qt::LeftButton) {
            drag_start_ = ev->pos();
            ev->accept();
        } else {
            QLabel::mousePressEvent(ev);  // lets contextMenuEvent fire
        }
    }

    void mouseMoveEvent(QMouseEvent* ev) override {
        if (!(ev->buttons() & Qt::LeftButton)) { QLabel::mouseMoveEvent(ev); return; }
        if (widget_id_.empty()) return;
        if ((ev->pos() - drag_start_).manhattanLength() < 12) return;
        auto* drag = new QDrag(this);
        auto* mime = new QMimeData;
        mime->setData("application/x-gauge-widget-id",
            QByteArray::fromStdString(widget_id_));
        drag->setMimeData(mime);
        drag->exec(Qt::MoveAction);
    }

    void contextMenuEvent(QContextMenuEvent* ev) override {
        if (!config_cb_) return;
        QMenu menu(this);
        auto* action = menu.addAction("Configure Gauge...");
        QObject::connect(action, &QAction::triggered,
                         [this]() { if (config_cb_) config_cb_(widget_id_); });
        menu.exec(ev->globalPos());
        ev->accept();
    }

    void dragEnterEvent(QDragEnterEvent* ev) override {
        if (ev->mimeData()->hasFormat("application/x-gauge-widget-id")) {
            auto from_id = ev->mimeData()->data("application/x-gauge-widget-id").toStdString();
            if (from_id != widget_id_) ev->acceptProposedAction();
        }
    }

    void dropEvent(QDropEvent* ev) override {
        auto from_id = ev->mimeData()->data("application/x-gauge-widget-id").toStdString();
        if (swap_cb_ && from_id != widget_id_) swap_cb_(from_id, widget_id_);
        ev->acceptProposedAction();
    }

private:
    ConfigCallback config_cb_;
    SwapCallback swap_cb_;
    std::string widget_id_;
    QPoint drag_start_;
};

}  // namespace tuner_app
