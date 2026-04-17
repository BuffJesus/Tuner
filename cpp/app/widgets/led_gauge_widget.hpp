// SPDX-License-Identifier: MIT
//
// LedGaugeWidget — round glowing indicator colored by the active zone.
// Use case: boolean / status channels (sync / learn / fuel pump / warn
// flags) where the exact numeric value isn't interesting but the
// on/off / ok/warn/danger state is. Same drag/drop/config hooks as
// the other painter widgets.
//
// Extracted from cpp/app/main.cpp. Header-only; no Q_OBJECT.

#pragma once

#include <QAction>
#include <QByteArray>
#include <QColor>
#include <QContextMenuEvent>
#include <QCursor>
#include <QDrag>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QFont>
#include <QMenu>
#include <QMimeData>
#include <QMouseEvent>
#include <QObject>
#include <QPaintEvent>
#include <QPainter>
#include <QPoint>
#include <QPointF>
#include <QRadialGradient>
#include <QRectF>
#include <QString>
#include <QWidget>
#include <Qt>

#include <algorithm>
#include <cstdio>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace tuner_app {

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

    explicit LedGaugeWidget(const Config& cfg, QWidget* parent = nullptr)
        : QWidget(parent), cfg_(cfg) {
        setMinimumSize(80, 80);
        setAcceptDrops(true);
        setCursor(Qt::PointingHandCursor);
    }

    void set_value(double v) { value_ = v; has_value_ = true; update(); }
    void clear_value() { has_value_ = false; update(); }
    void set_widget_id(const std::string& id) { widget_id_ = id; }
    void set_config_callback(ConfigCallback cb) { config_cb_ = std::move(cb); }
    void set_swap_callback(SwapCallback cb) { swap_cb_ = std::move(cb); }

protected:
    void mousePressEvent(QMouseEvent* ev) override {
        if (ev->button() == Qt::LeftButton) {
            drag_start_ = ev->pos();
            ev->accept();
        } else {
            ev->ignore();
        }
    }

    void mouseMoveEvent(QMouseEvent* ev) override {
        if (!(ev->buttons() & Qt::LeftButton)) return;
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

    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);

        const double w = width(), h = height();
        const double title_h = 16.0;
        const double value_h = 16.0;
        const double led_area_h = std::max(20.0, h - title_h - value_h - 8.0);
        const double led_r = std::min(w * 0.35, led_area_h * 0.4);
        const double cx = w / 2.0;
        const double cy = title_h + 4.0 + led_area_h / 2.0;

        // Background card.
        p.setPen(Qt::NoPen);
        p.setBrush(QColor(24, 27, 34));
        p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 4, 4);

        // Title (top).
        {
            QFont f = font();
            f.setPixelSize(11);
            p.setFont(f);
            p.setPen(QColor(150, 154, 165));
            p.drawText(QRectF(4, 2, w - 8, title_h),
                       Qt::AlignHCenter | Qt::AlignVCenter,
                       QString::fromUtf8(cfg_.title.c_str()));
        }

        auto zone_color = [](const std::string& c) -> QColor {
            if (c == "ok")      return QColor(90, 214, 135);
            if (c == "warning") return QColor(214, 165, 90);
            if (c == "danger")  return QColor(214, 90, 90);
            return QColor(90, 154, 214);
        };

        // LED — dim when no value, lit zone color otherwise.
        QColor led = QColor(60, 64, 74);  // dim/off default
        if (has_value_) {
            led = QColor(90, 154, 214);  // primary fallback
            for (const auto& z : cfg_.zones) {
                if (value_ >= z.lo && value_ <= z.hi) {
                    led = zone_color(z.color);
                    break;
                }
            }
        }

        // Outer glow.
        QRadialGradient glow(cx, cy, led_r * 1.8);
        QColor glow_col = led; glow_col.setAlpha(70);
        glow.setColorAt(0.0, glow_col);
        glow.setColorAt(1.0, QColor(0, 0, 0, 0));
        p.setBrush(glow);
        p.drawEllipse(QPointF(cx, cy), led_r * 1.8, led_r * 1.8);

        // LED body.
        p.setBrush(led);
        p.drawEllipse(QPointF(cx, cy), led_r, led_r);

        // Highlight shine.
        QRadialGradient shine(cx - led_r * 0.3, cy - led_r * 0.3, led_r * 0.6);
        shine.setColorAt(0.0, QColor(255, 255, 255, 120));
        shine.setColorAt(1.0, QColor(255, 255, 255, 0));
        p.setBrush(shine);
        p.drawEllipse(QPointF(cx - led_r * 0.3, cy - led_r * 0.3),
                      led_r * 0.6, led_r * 0.6);

        // Value readout (bottom).
        {
            QFont f = font();
            f.setPixelSize(11);
            p.setFont(f);
            p.setPen(QColor(200, 204, 215));
            char buf[48];
            if (!has_value_) std::snprintf(buf, sizeof(buf), "%s", "\xe2\x80\x94");
            else if (value_ == static_cast<int>(value_))
                std::snprintf(buf, sizeof(buf), "%d %s",
                              static_cast<int>(value_), cfg_.units.c_str());
            else
                std::snprintf(buf, sizeof(buf), "%.1f %s",
                              value_, cfg_.units.c_str());
            p.drawText(QRectF(4, h - value_h - 2, w - 8, value_h),
                       Qt::AlignHCenter | Qt::AlignVCenter,
                       QString::fromUtf8(buf));
        }
    }

private:
    Config cfg_;
    double value_ = 0;
    bool has_value_ = false;
    ConfigCallback config_cb_;
    SwapCallback swap_cb_;
    std::string widget_id_;
    QPoint drag_start_;
};

}  // namespace tuner_app
