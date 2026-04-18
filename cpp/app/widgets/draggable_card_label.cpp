// SPDX-License-Identifier: MIT

#include "widgets/draggable_card_label.hpp"

#include <QAction>
#include <QByteArray>
#include <QContextMenuEvent>
#include <QDrag>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QMenu>
#include <QMimeData>
#include <QMouseEvent>

DraggableCardLabel::DraggableCardLabel(QWidget* parent) : QLabel(parent) {
    setAcceptDrops(true);
    setCursor(Qt::PointingHandCursor);
}

void DraggableCardLabel::mousePressEvent(QMouseEvent* ev) {
    if (ev->button() == Qt::LeftButton) {
        drag_start_ = ev->pos();
        ev->accept();
    } else {
        QLabel::mousePressEvent(ev);  // lets contextMenuEvent fire
    }
}

void DraggableCardLabel::mouseMoveEvent(QMouseEvent* ev) {
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

void DraggableCardLabel::contextMenuEvent(QContextMenuEvent* ev) {
    if (!config_cb_) return;
    QMenu menu(this);
    auto* action = menu.addAction("Configure Gauge...");
    QObject::connect(action, &QAction::triggered,
                     [this]() { if (config_cb_) config_cb_(widget_id_); });
    menu.exec(ev->globalPos());
    ev->accept();
}

void DraggableCardLabel::dragEnterEvent(QDragEnterEvent* ev) {
    if (ev->mimeData()->hasFormat("application/x-gauge-widget-id")) {
        auto from_id = ev->mimeData()->data("application/x-gauge-widget-id").toStdString();
        if (from_id != widget_id_) ev->acceptProposedAction();
    }
}

void DraggableCardLabel::dropEvent(QDropEvent* ev) {
    auto from_id = ev->mimeData()->data("application/x-gauge-widget-id").toStdString();
    if (swap_cb_ && from_id != widget_id_) swap_cb_(from_id, widget_id_);
    ev->acceptProposedAction();
}
