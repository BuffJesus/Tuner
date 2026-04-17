// SPDX-License-Identifier: MIT
//
// LogTimelineWidget — scrubbable timeline for standalone datalog viewing
// (Phase 16 item 5). Stacks up to ~6 channel tracks on a shared time
// axis; left click + drag moves the red cursor and fires a callback so
// the existing row-spinner + values-card update in lockstep.
//
// Extracted from cpp/app/main.cpp. Header-only; no Q_OBJECT.

#pragma once

#include "../theme.hpp"

#include <QColor>
#include <QCursor>
#include <QFont>
#include <QMouseEvent>
#include <QPaintEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QWidget>
#include <Qt>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <iterator>
#include <limits>
#include <string>
#include <utility>
#include <vector>

namespace tuner_app {

class LogTimelineWidget : public QWidget {
public:
    struct Config {
        std::vector<double> times;  // seconds from start
        std::vector<std::string> channel_names;
        std::vector<std::vector<double>> channel_values;  // parallel to times
    };

    explicit LogTimelineWidget(QWidget* parent = nullptr) : QWidget(parent) {
        setMinimumSize(420, 200);
        setMouseTracking(false);
        setCursor(Qt::CrossCursor);
    }

    void set_config(const Config& cfg) {
        cfg_ = cfg;
        channel_ranges_.clear();
        for (const auto& vals : cfg_.channel_values) {
            double mn =  std::numeric_limits<double>::infinity();
            double mx = -std::numeric_limits<double>::infinity();
            for (double v : vals) {
                if (std::isfinite(v)) {
                    if (v < mn) mn = v;
                    if (v > mx) mx = v;
                }
            }
            if (!std::isfinite(mn)) { mn = 0; mx = 1; }
            if (mn == mx) mx = mn + 1;
            channel_ranges_.emplace_back(mn, mx);
        }
        cursor_idx_ = 0;
        if (cfg_.times.size() >= 2) {
            view_start_ = cfg_.times.front();
            view_end_   = cfg_.times.back();
        } else {
            view_start_ = 0;
            view_end_   = 1;
        }
        zoom_drag_active_ = false;
        update();
    }

    void clear_config() {
        cfg_ = {};
        channel_ranges_.clear();
        cursor_idx_ = 0;
        view_start_ = 0;
        view_end_   = 1;
        zoom_drag_active_ = false;
        update();
    }

    void reset_zoom() {
        if (cfg_.times.size() < 2) return;
        view_start_ = cfg_.times.front();
        view_end_   = cfg_.times.back();
        zoom_drag_active_ = false;
        update();
    }

    double view_start() const { return view_start_; }
    double view_end()   const { return view_end_;   }

    void set_cursor_index(int idx) {
        if (cfg_.times.empty()) return;
        int clamped = std::clamp(idx, 0,
            static_cast<int>(cfg_.times.size()) - 1);
        if (clamped == cursor_idx_) return;
        cursor_idx_ = clamped;
        update();
    }

    std::function<void(int)> on_cursor_changed;

protected:
    void paintEvent(QPaintEvent*) override {
        namespace tt = tuner_theme;
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        const double w = width(), h = height();

        p.fillRect(rect(), QColor(tt::bg_deep));
        p.setPen(QPen(QColor(tt::border), 1));
        p.drawRect(0, 0, static_cast<int>(w) - 1, static_cast<int>(h) - 1);

        if (cfg_.times.size() < 2 || cfg_.channel_values.empty()) {
            p.setPen(QColor(tt::text_muted));
            QFont f; f.setPixelSize(tt::font_small); p.setFont(f);
            p.drawText(rect(), Qt::AlignCenter, QString::fromUtf8(
                "Import a CSV datalog to see the timeline"));
            return;
        }

        const int ml = 72, mr = 44, mt = 22, mb = 24;
        const double pw = w - ml - mr;
        const double ph = h - mt - mb;
        if (pw <= 0 || ph <= 0) return;

        double t_start = view_start_;
        double t_end   = view_end_;
        double t_span  = std::max(1e-9, t_end - t_start);

        const int n_ch = static_cast<int>(cfg_.channel_values.size());
        const double track_h = ph / n_ch;

        const char* colors[] = {
            tt::accent_primary, tt::accent_warning, tt::accent_ok,
            tt::accent_special, tt::accent_danger, tt::text_secondary
        };

        for (int ch = 0; ch < n_ch; ++ch) {
            double ty0 = mt + ch * track_h;
            double ty1 = ty0 + track_h;
            const char* color = colors[ch % 6];

            p.setPen(QColor(color));
            QFont lf; lf.setPixelSize(tt::font_small); lf.setBold(true); p.setFont(lf);
            p.drawText(QRectF(0, ty0, ml - 6, track_h),
                Qt::AlignRight | Qt::AlignVCenter,
                QString::fromUtf8(cfg_.channel_names[ch].c_str()));

            auto [mn, mx] = channel_ranges_[ch];
            QFont rf; rf.setPixelSize(tt::font_micro); p.setFont(rf);
            p.setPen(QColor(tt::text_dim));
            char mxb[16], mnb[16];
            std::snprintf(mxb, sizeof(mxb), "%.0f", mx);
            std::snprintf(mnb, sizeof(mnb), "%.0f", mn);
            p.drawText(QRectF(ml + pw + 2, ty0, mr - 4, 12),
                Qt::AlignLeft | Qt::AlignTop, QString::fromUtf8(mxb));
            p.drawText(QRectF(ml + pw + 2, ty1 - 12, mr - 4, 12),
                Qt::AlignLeft | Qt::AlignBottom, QString::fromUtf8(mnb));

            if (ch > 0) {
                p.setPen(QPen(QColor(tt::border_soft), 1));
                p.drawLine(QPointF(ml, ty0), QPointF(ml + pw, ty0));
            }

            const auto& vals = cfg_.channel_values[ch];
            auto lo_it = std::lower_bound(cfg_.times.begin(),
                cfg_.times.end(), t_start);
            auto hi_it = std::upper_bound(cfg_.times.begin(),
                cfg_.times.end(), t_end);
            int lo = static_cast<int>(std::distance(cfg_.times.begin(), lo_it));
            int hi = static_cast<int>(std::distance(cfg_.times.begin(), hi_it));
            if (lo > 0) --lo;
            if (hi < static_cast<int>(cfg_.times.size())) ++hi;
            int visible = std::max(1, hi - lo);
            int stride = std::max(1, visible / static_cast<int>(std::max(1.0, pw)));
            QPainterPath path;
            bool started = false;
            double range = mx - mn;
            p.save();
            p.setClipRect(QRectF(ml, mt, pw, ph));
            for (int i = lo; i < hi; i += stride) {
                double v = vals[i];
                if (!std::isfinite(v)) continue;
                double x = ml + ((cfg_.times[i] - t_start) / t_span) * pw;
                double y = ty1 - ((v - mn) / range) * (track_h - 4) - 2;
                if (!started) { path.moveTo(x, y); started = true; }
                else { path.lineTo(x, y); }
            }
            p.setPen(QPen(QColor(color), 1.3));
            p.drawPath(path);
            p.restore();
        }

        QFont af; af.setPixelSize(tt::font_micro); p.setFont(af);
        p.setPen(QColor(tt::text_muted));
        for (int i = 0; i <= 4; ++i) {
            double t = t_start + t_span * i / 4.0;
            double x = ml + pw * i / 4.0;
            char buf[16]; std::snprintf(buf, sizeof(buf), "%.1fs", t);
            p.drawText(QRectF(x - 28, mt + ph + 2, 56, 16),
                Qt::AlignCenter, QString::fromUtf8(buf));
        }

        if (cursor_idx_ >= 0 && cursor_idx_ < static_cast<int>(cfg_.times.size())) {
            double t = cfg_.times[cursor_idx_];
            if (t >= t_start && t <= t_end) {
                double x = ml + ((t - t_start) / t_span) * pw;
                p.setPen(QPen(QColor(tt::accent_danger), 1.5));
                p.drawLine(QPointF(x, mt), QPointF(x, mt + ph));
                QFont tf; tf.setPixelSize(tt::font_small); tf.setBold(true); p.setFont(tf);
                p.setPen(QColor(tt::accent_danger));
                char tb[24]; std::snprintf(tb, sizeof(tb), "%.2fs", t);
                p.drawText(QPointF(x + 4, mt - 4), QString::fromUtf8(tb));
            }
        }

        // Zoom-drag overlay — translucent selection rect while the
        // operator holds Shift and drags. On release the view snaps to
        // the selected range (see mouseReleaseEvent).
        if (zoom_drag_active_) {
            double x0 = std::clamp(zoom_drag_start_x_, (double)ml, ml + pw);
            double x1 = std::clamp(zoom_drag_current_x_, (double)ml, ml + pw);
            if (x1 < x0) std::swap(x0, x1);
            QColor fill(tt::accent_primary);
            fill.setAlpha(60);
            p.fillRect(QRectF(x0, mt, x1 - x0, ph), fill);
            p.setPen(QPen(QColor(tt::accent_primary), 1, Qt::DashLine));
            p.drawRect(QRectF(x0, mt, x1 - x0, ph));
        }

        // Zoom hint — shows the active zoom fraction + "Shift-drag"
        // prompt on the top right when we're not at full span.
        double full_span = std::max(1e-9,
            cfg_.times.back() - cfg_.times.front());
        double visible_span = t_end - t_start;
        if (visible_span < full_span * 0.999) {
            QFont hf; hf.setPixelSize(tt::font_micro); hf.setBold(true); p.setFont(hf);
            p.setPen(QColor(tt::accent_primary));
            char hb[64];
            std::snprintf(hb, sizeof(hb),
                "zoom %.0f%% \xc2\xb7 shift-drag to zoom",
                (visible_span / full_span) * 100.0);
            p.drawText(QRectF(ml, 4, pw, 14),
                Qt::AlignRight | Qt::AlignVCenter, QString::fromUtf8(hb));
        } else {
            QFont hf; hf.setPixelSize(tt::font_micro); p.setFont(hf);
            p.setPen(QColor(tt::text_dim));
            p.drawText(QRectF(ml, 4, pw, 14),
                Qt::AlignRight | Qt::AlignVCenter,
                QString::fromUtf8("shift-drag to zoom"));
        }
    }

    void mousePressEvent(QMouseEvent* e) override {
        const int ml = 72, mr = 44;
        double pw = width() - ml - mr;
        if (pw <= 0) return;
        if (e->button() == Qt::LeftButton
            && (e->modifiers() & Qt::ShiftModifier)) {
            zoom_drag_active_ = true;
            zoom_drag_start_x_ = e->position().x();
            zoom_drag_current_x_ = zoom_drag_start_x_;
            update();
            return;
        }
        handle_seek(e);
    }
    void mouseMoveEvent(QMouseEvent* e) override {
        if (zoom_drag_active_) {
            zoom_drag_current_x_ = e->position().x();
            update();
            return;
        }
        if (e->buttons() & Qt::LeftButton) handle_seek(e);
    }
    void mouseReleaseEvent(QMouseEvent* e) override {
        if (!zoom_drag_active_) return;
        zoom_drag_active_ = false;
        const int ml = 72, mr = 44;
        double pw = width() - ml - mr;
        if (pw <= 0) { update(); return; }
        double x0 = std::clamp(zoom_drag_start_x_, (double)ml, ml + pw);
        double x1 = std::clamp(e->position().x(), (double)ml, ml + pw);
        if (x1 < x0) std::swap(x0, x1);
        // Require at least a few pixels so a tiny accidental drag
        // doesn't collapse the view to a single sample.
        if (x1 - x0 < 6.0) { update(); return; }
        double span = std::max(1e-9, view_end_ - view_start_);
        double new_start = view_start_ + ((x0 - ml) / pw) * span;
        double new_end   = view_start_ + ((x1 - ml) / pw) * span;
        // Prevent zooming below a 3-sample span (ill-defined plot).
        if (new_end - new_start <= 1e-6) { update(); return; }
        view_start_ = new_start;
        view_end_   = new_end;
        update();
    }

private:
    void handle_seek(QMouseEvent* e) {
        if (cfg_.times.size() < 2) return;
        const int ml = 72, mr = 44;
        double pw = width() - ml - mr;
        if (pw <= 0) return;
        double frac = std::clamp(
            (e->position().x() - ml) / pw, 0.0, 1.0);
        double t_target = view_start_
            + frac * (view_end_ - view_start_);
        auto it = std::lower_bound(
            cfg_.times.begin(), cfg_.times.end(), t_target);
        int idx;
        if (it == cfg_.times.begin()) idx = 0;
        else if (it == cfg_.times.end())
            idx = static_cast<int>(cfg_.times.size()) - 1;
        else {
            int i1 = static_cast<int>(std::distance(cfg_.times.begin(), it));
            int i0 = i1 - 1;
            idx = (std::abs(cfg_.times[i0] - t_target)
                 < std::abs(cfg_.times[i1] - t_target)) ? i0 : i1;
        }
        if (idx != cursor_idx_) {
            cursor_idx_ = idx;
            update();
            if (on_cursor_changed) on_cursor_changed(idx);
        }
    }

    Config cfg_;
    std::vector<std::pair<double, double>> channel_ranges_;
    int cursor_idx_ = 0;
    double view_start_ = 0;
    double view_end_   = 1;
    bool zoom_drag_active_ = false;
    double zoom_drag_start_x_ = 0;
    double zoom_drag_current_x_ = 0;
};

}  // namespace tuner_app
