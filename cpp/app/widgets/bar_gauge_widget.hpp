// SPDX-License-Identifier: MIT
//
// BarGaugeWidget — horizontal bar gauge. Renders a filled track with
// zone coloring, the current value + units overlaid. Shares the
// DialGaugeWidget drag/drop/config pattern so bars can swap positions
// with cards and dials interchangeably (same MIME type).
//
// Extracted from cpp/app/main.cpp. Header-only; no Q_OBJECT.

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
#include <QPainterPath>
#include <QPen>
#include <QPoint>
#include <QRectF>
#include <QString>
#include <QWidget>
#include <Qt>

#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace tuner_app {

class BarGaugeWidget : public QWidget {
public:
    struct Config {
        std::string title;
        std::string units;
        double min_value = 0;
        double max_value = 100;
        struct Zone { double lo; double hi; std::string color; };
        std::vector<Zone> zones;
    };

    using ConfigCallback = std::function<void(const std::string& widget_id)>;
    using SwapCallback = std::function<void(const std::string& from, const std::string& to)>;

    explicit BarGaugeWidget(const Config& cfg, QWidget* parent = nullptr)
        : QWidget(parent), cfg_(cfg) {
        setMinimumHeight(60);
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
            // Pass through so contextMenuEvent fires for right-click.
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
        // exec() blocks until the operator picks or dismisses. popup()
        // returned immediately and was dismissed by the release event
        // that follows the right-click, so the menu flashed and vanished.
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
        namespace tt = tuner_theme;
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);

        const double w = width(), h = height();
        const double pad = 10.0;
        const double head_h = 22.0;
        const double foot_h = 12.0;
        const double bar_h = std::max(10.0, h - head_h - foot_h - 2 * pad);
        const double bar_y = pad + head_h;
        QRectF track(pad, bar_y, w - 2 * pad, bar_h);

        // Theme colors — pulled from tt:: tokens so the widget reads as
        // the same visual tier as number cards and dial gauges.
        const QColor bg_card(QString::fromUtf8(tt::bg_panel));
        const QColor bg_track(QString::fromUtf8(tt::bg_inset));
        const QColor col_border(QString::fromUtf8(tt::border));
        const QColor col_title(QString::fromUtf8(tt::text_muted));
        const QColor col_value(QString::fromUtf8(tt::text_primary));
        const QColor col_tick(QString::fromUtf8(tt::text_dim));

        auto zone_color = [](const std::string& c) -> QColor {
            if (c == "ok")      return QColor(QString::fromUtf8(tt::accent_ok));
            if (c == "warning") return QColor(QString::fromUtf8(tt::accent_warning));
            if (c == "danger")  return QColor(QString::fromUtf8(tt::accent_danger));
            return QColor(QString::fromUtf8(tt::accent_primary));
        };

        // Current value zone + fill color.
        QColor fill = QColor(QString::fromUtf8(tt::accent_primary));
        for (const auto& z : cfg_.zones) {
            if (has_value_ && value_ >= z.lo && value_ <= z.hi) {
                fill = zone_color(z.color);
                break;
            }
        }

        // Background card with a subtle border, matching the number-card
        // tier so bars and cards don't read as different generations of UI.
        {
            QRectF card(1, 1, w - 2, h - 2);
            p.setPen(QPen(col_border, 1));
            p.setBrush(bg_card);
            p.drawRoundedRect(card, tt::radius_md, tt::radius_md);
        }

        // Top accent strip — matches the number-card `border-top: Npx
        // solid accent` so bars, number cards, and the sidebar-item
        // "active" rail all read as the same visual grammar.
        {
            const double accent_h = 2.5;
            QPainterPath top_clip;
            top_clip.addRoundedRect(QRectF(1, 1, w - 2, h - 2),
                                    tt::radius_md, tt::radius_md);
            p.save();
            p.setClipPath(top_clip);
            p.setPen(Qt::NoPen);
            p.setBrush(fill);
            p.drawRect(QRectF(1, 1, w - 2, accent_h));
            p.restore();
        }

        // Header row — title left, value right. Value outside the bar
        // is always readable regardless of fill position.
        QFont title_font = font();
        title_font.setPixelSize(tt::font_small);
        p.setFont(title_font);
        p.setPen(col_title);
        p.drawText(QRectF(pad, pad, w - 2 * pad, head_h),
                   Qt::AlignLeft | Qt::AlignVCenter,
                   QString::fromUtf8(cfg_.title.c_str()));

        {
            QFont vf = font();
            vf.setPixelSize(tt::font_label);
            vf.setBold(true);
            p.setFont(vf);
            p.setPen(col_value);
            char buf[64];
            if (!has_value_) std::snprintf(buf, sizeof(buf), "\xe2\x80\x94");
            else if (cfg_.units.empty())
                std::snprintf(buf, sizeof(buf),
                              (value_ == static_cast<int>(value_)) ? "%.0f" : "%.1f",
                              value_);
            else
                std::snprintf(buf, sizeof(buf),
                              (value_ == static_cast<int>(value_)) ? "%.0f %s" : "%.1f %s",
                              value_, cfg_.units.c_str());
            p.drawText(QRectF(pad, pad, w - 2 * pad, head_h),
                       Qt::AlignRight | Qt::AlignVCenter,
                       QString::fromUtf8(buf));
        }

        // Bar track.
        p.setPen(Qt::NoPen);
        p.setBrush(bg_track);
        p.drawRoundedRect(track, bar_h / 2.0, bar_h / 2.0);

        const double span = cfg_.max_value - cfg_.min_value;
        if (span > 0 && has_value_) {
            double frac = std::clamp((value_ - cfg_.min_value) / span, 0.0, 1.0);
            if (frac > 0.001) {
                double fw = std::max(bar_h, track.width() * frac);
                QRectF filled(track.left(), track.top(), fw, track.height());
                // Clip the fill to the track so rounded corners on the
                // right edge stay inside the track instead of spilling out.
                QPainterPath clip;
                clip.addRoundedRect(track, bar_h / 2.0, bar_h / 2.0);
                p.save();
                p.setClipPath(clip);
                p.setBrush(fill);
                p.drawRoundedRect(filled, bar_h / 2.0, bar_h / 2.0);
                p.restore();
            }
        }

        // Footer ticks — min, mid, max labels keep the scale discoverable
        // without adding gridlines that would clash with the rounded bar.
        {
            QFont ff = font();
            ff.setPixelSize(tt::font_micro);
            p.setFont(ff);
            p.setPen(col_tick);
            char lo[24], md[24], hi[24];
            auto fmt = [&](char* b, std::size_t n, double v) {
                if (v == static_cast<int>(v))
                    std::snprintf(b, n, "%.0f", v);
                else
                    std::snprintf(b, n, "%.1f", v);
            };
            fmt(lo, sizeof(lo), cfg_.min_value);
            fmt(md, sizeof(md), (cfg_.min_value + cfg_.max_value) / 2.0);
            fmt(hi, sizeof(hi), cfg_.max_value);
            QRectF foot(pad, bar_y + bar_h + 1.0, w - 2 * pad, foot_h);
            p.drawText(foot, Qt::AlignLeft | Qt::AlignVCenter,
                       QString::fromUtf8(lo));
            p.drawText(foot, Qt::AlignHCenter | Qt::AlignVCenter,
                       QString::fromUtf8(md));
            p.drawText(foot, Qt::AlignRight | Qt::AlignVCenter,
                       QString::fromUtf8(hi));
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
