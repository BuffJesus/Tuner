// SPDX-License-Identifier: MIT
//
// DialGaugeWidget — custom-painted analog gauge with arc, needle, zones.
//
// Extracted from cpp/app/main.cpp. Header-only; no Q_OBJECT, so MOC stays
// out of the picture. Uses the same `application/x-gauge-widget-id` MIME
// type as DraggableCardLabel and BarGaugeWidget so dashboard widgets of
// all three kinds can swap positions interchangeably.

#pragma once

#include "../theme.hpp"

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
#include <QPen>
#include <QPoint>
#include <QPointF>
#include <QRadialGradient>
#include <QRectF>
#include <QString>
#include <QWidget>
#include <Qt>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace tuner_app {

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

    explicit DialGaugeWidget(const Config& cfg, QWidget* parent = nullptr)
        : QWidget(parent), cfg_(cfg) {
        setMinimumSize(120, 120);
        setCursor(Qt::PointingHandCursor);
        setAcceptDrops(true);
    }

    void set_value(double v) { value_ = v; has_value_ = true; update(); }
    void clear_value() { has_value_ = false; update(); }
    void set_click_callback(ClickCallback cb) { click_cb_ = std::move(cb); }
    void set_config_callback(ConfigCallback cb) { config_cb_ = std::move(cb); }
    void set_swap_callback(SwapCallback cb) { swap_cb_ = std::move(cb); }
    void set_widget_id(const std::string& id) { widget_id_ = id; }

protected:
    // Drag-vs-click disambiguation: left press records the anchor and
    // arms a click. mouseMoveEvent starts a QDrag once the pointer
    // crosses the threshold and marks the interaction as a drag so
    // the release handler knows to skip the navigation callback.
    // Without this split, operators couldn't drag at all because
    // `mousePressEvent` fired the navigation callback immediately.
    void mousePressEvent(QMouseEvent* ev) override {
        if (ev->button() == Qt::LeftButton) {
            drag_start_ = ev->pos();
            dragged_ = false;
            click_armed_ = true;
            ev->accept();
        } else {
            ev->ignore();  // let contextMenuEvent fire on right-click
        }
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

    void mouseMoveEvent(QMouseEvent* ev) override {
        if (!(ev->buttons() & Qt::LeftButton)) return;
        if (widget_id_.empty()) return;
        if ((ev->pos() - drag_start_).manhattanLength() < 12) return;
        // Past the drag threshold — this is a drag, not a click.
        dragged_ = true;
        click_armed_ = false;
        auto* drag = new QDrag(this);
        auto* mime = new QMimeData;
        mime->setData("application/x-gauge-widget-id",
            QByteArray::fromStdString(widget_id_));
        drag->setMimeData(mime);
        drag->exec(Qt::MoveAction);
    }

    void mouseReleaseEvent(QMouseEvent* ev) override {
        if (ev->button() == Qt::LeftButton && click_armed_ && !dragged_) {
            if (click_cb_) click_cb_(cfg_.title);
        }
        click_armed_ = false;
        dragged_ = false;
    }

    void dragEnterEvent(QDragEnterEvent* ev) override {
        if (ev->mimeData()->hasFormat("application/x-gauge-widget-id")) {
            auto from_id = ev->mimeData()->data("application/x-gauge-widget-id").toStdString();
            if (from_id != widget_id_)
                ev->acceptProposedAction();
        }
    }

    void dropEvent(QDropEvent* ev) override {
        auto from_id = ev->mimeData()->data("application/x-gauge-widget-id").toStdString();
        if (swap_cb_ && from_id != widget_id_)
            swap_cb_(from_id, widget_id_);
        ev->acceptProposedAction();
    }

    void paintEvent(QPaintEvent*) override {
        namespace tt = tuner_theme;
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);

        const double w = width(), h = height();
        const double side = std::min(w, h);
        const double cx = w / 2.0, cy = h / 2.0;
        const double r = side / 2.0 * 0.86;
        const double track_w = r * 0.14;
        const double span = cfg_.max_value - cfg_.min_value;
        constexpr double SWEEP = 270.0;
        constexpr double START = 225.0;
        constexpr double PI = 3.14159265358979323846;

        // Outer bezel ring — subtle metallic edge.
        p.setPen(Qt::NoPen);
        {
            QRadialGradient bezel(cx, cy, r + track_w * 0.9);
            bezel.setColorAt(0.85, QColor(34, 38, 48));
            bezel.setColorAt(0.95, QColor(52, 56, 66));
            bezel.setColorAt(1.0,  QColor(28, 32, 40));
            p.setBrush(bezel);
            p.drawEllipse(QPointF(cx, cy), r + track_w * 0.9, r + track_w * 0.9);
        }

        // Background circle.
        p.setBrush(QColor(18, 21, 28));
        p.drawEllipse(QPointF(cx, cy), r + track_w * 0.5, r + track_w * 0.5);

        // Background arc track.
        QRectF arc_rect(cx - r, cy - r, r * 2, r * 2);
        QPen bg_pen(QColor(40, 44, 52));
        bg_pen.setWidthF(track_w);
        bg_pen.setCapStyle(Qt::FlatCap);
        p.setPen(bg_pen);
        p.drawArc(arc_rect, int(START * 16), int(-SWEEP * 16));

        // Zone arcs.
        auto zone_color = [](const std::string& c) -> QColor {
            if (c == "ok")      return QColor(90, 214, 135);
            if (c == "warning") return QColor(214, 165, 90);
            if (c == "danger")  return QColor(214, 90, 90);
            return QColor(120, 120, 120);
        };

        if (span > 0) {
            for (const auto& z : cfg_.zones) {
                double lo_f = std::max(0.0, (z.lo - cfg_.min_value) / span);
                double hi_f = std::min(1.0, (z.hi - cfg_.min_value) / span);
                if (hi_f <= lo_f) continue;
                QPen zp(zone_color(z.color));
                zp.setWidthF(track_w);
                zp.setCapStyle(Qt::FlatCap);
                p.setPen(zp);
                double start_deg = START - lo_f * SWEEP;
                double span_deg = -(hi_f - lo_f) * SWEEP;
                p.drawArc(arc_rect, int(start_deg * 16), int(span_deg * 16));
            }
        }

        // Minor tick marks (40 subdivisions).
        for (int i = 0; i <= 40; ++i) {
            double frac = i / 40.0;
            double angle = (START - frac * SWEEP) * PI / 180.0;
            double outer = r - track_w * 0.5;
            bool major = (i % 5 == 0);
            double inner = major ? outer - r * 0.10 : outer - r * 0.05;
            double pen_w = major ? std::max(1.5, side * 0.014) : std::max(0.8, side * 0.006);
            QColor tick_color = major ? QColor(110, 116, 130) : QColor(60, 64, 72);
            p.setPen(QPen(tick_color, pen_w));
            p.drawLine(
                QPointF(cx + outer * std::cos(angle), cy - outer * std::sin(angle)),
                QPointF(cx + inner * std::cos(angle), cy - inner * std::sin(angle)));

            // Tick labels on major marks only.
            if (major && span > 0) {
                double val = cfg_.min_value + frac * span;
                char lbl[16];
                if (val == static_cast<int>(val) && std::abs(val) < 100000)
                    std::snprintf(lbl, sizeof(lbl), "%d", static_cast<int>(val));
                else
                    std::snprintf(lbl, sizeof(lbl), "%.0f", val);
                QFont tf;
                tf.setPixelSize(std::max(8, static_cast<int>(side * 0.07)));
                p.setFont(tf);
                p.setPen(QColor(140, 146, 160));
                double label_r = inner - r * 0.09;
                QPointF lp(cx + label_r * std::cos(angle), cy - label_r * std::sin(angle));
                p.drawText(QRectF(lp.x() - 22, lp.y() - 9, 44, 18),
                           Qt::AlignCenter, QString::fromUtf8(lbl));
            }
        }

        // Needle.
        if (has_value_ && span > 0) {
            double frac = std::clamp((value_ - cfg_.min_value) / span, 0.0, 1.0);
            double angle = (START - frac * SWEEP) * PI / 180.0;
            double tip = r * 0.68;

            // Needle color from active zone.
            QColor nc(210, 210, 210);
            for (auto it = cfg_.zones.rbegin(); it != cfg_.zones.rend(); ++it) {
                if (value_ >= it->lo && value_ <= it->hi) {
                    nc = zone_color(it->color);
                    break;
                }
            }

            // Tapered needle — triangle polygon for a premium look.
            double needle_w = std::max(2.0, side * 0.025);
            double perp = angle + PI / 2.0;
            QPointF tip_pt(cx + tip * std::cos(angle), cy - tip * std::sin(angle));
            QPointF base_l(cx + needle_w * std::cos(perp), cy - needle_w * std::sin(perp));
            QPointF base_r(cx - needle_w * std::cos(perp), cy + needle_w * std::sin(perp));
            // Needle shadow/glow.
            {
                QColor glow = nc;
                glow.setAlpha(40);
                p.setPen(Qt::NoPen);
                p.setBrush(glow);
                QPointF glow_pts[3] = {
                    QPointF(tip_pt.x() + 1, tip_pt.y() + 1),
                    QPointF(base_l.x() + 1, base_l.y() + 1),
                    QPointF(base_r.x() + 1, base_r.y() + 1)
                };
                p.drawPolygon(glow_pts, 3);
            }
            // Needle body.
            p.setPen(Qt::NoPen);
            p.setBrush(nc);
            QPointF needle_pts[3] = { tip_pt, base_l, base_r };
            p.drawPolygon(needle_pts, 3);

            // Hub — double ring with colored center.
            double hub_r = r * 0.10;
            p.setPen(Qt::NoPen);
            p.setBrush(QColor(38, 42, 52));
            p.drawEllipse(QPointF(cx, cy), hub_r, hub_r);
            p.setBrush(QColor(52, 56, 66));
            p.drawEllipse(QPointF(cx, cy), hub_r * 0.7, hub_r * 0.7);
            p.setBrush(nc);
            p.drawEllipse(QPointF(cx, cy), hub_r * 0.4, hub_r * 0.4);
        }

        // Value readout.
        {
            QFont vf;
            vf.setPixelSize(std::max(10, static_cast<int>(side * 0.16)));
            vf.setBold(true);
            p.setFont(vf);
            p.setPen(QColor(225, 228, 235));
            char val_buf[32];
            if (!has_value_)
                std::snprintf(val_buf, sizeof(val_buf), "%s", "\xe2\x80\x94");
            else if (value_ == static_cast<int>(value_))
                std::snprintf(val_buf, sizeof(val_buf), "%d", static_cast<int>(value_));
            else
                std::snprintf(val_buf, sizeof(val_buf), "%.1f", value_);
            p.drawText(QRectF(cx - r * 0.5, cy + r * 0.15, r, r * 0.35),
                       Qt::AlignCenter, QString::fromUtf8(val_buf));
        }

        // Units.
        if (!cfg_.units.empty()) {
            QFont uf;
            uf.setPixelSize(std::max(tt::font_micro, static_cast<int>(side * 0.075)));
            p.setFont(uf);
            p.setPen(QColor(90, 96, 110));
            p.drawText(QRectF(cx - r * 0.4, cy + r * 0.46, r * 0.8, r * 0.2),
                       Qt::AlignCenter, QString::fromUtf8(cfg_.units.c_str()));
        }

        // Title — use the full widget width so longer titles like
        // "Engine Speed" and "Throttle Position" don't clip. The prior
        // rect width was `r` (half the dial), which clipped anything
        // longer than ~6 characters at small gauge sizes.
        {
            QFont tf;
            tf.setPixelSize(std::max(tt::font_micro, static_cast<int>(side * 0.085)));
            p.setFont(tf);
            p.setPen(QColor(130, 135, 148));
            p.drawText(QRectF(2, cy + r * 0.65, side - 4, r * 0.22),
                       Qt::AlignCenter, QString::fromUtf8(cfg_.title.c_str()));
        }
    }

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

}  // namespace tuner_app
