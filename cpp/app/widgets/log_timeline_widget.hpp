// SPDX-License-Identifier: MIT
//
// LogTimelineWidget — scrubbable timeline for standalone datalog viewing
// (Phase 16 item 5). Stacks up to ~6 channel tracks on a shared time
// axis; left click + drag moves the red cursor and fires a callback so
// the existing row-spinner + values-card update in lockstep. Shift-drag
// to zoom the visible range.

#pragma once

#include <QWidget>

#include <functional>
#include <string>
#include <utility>
#include <vector>

class QMouseEvent;
class QPaintEvent;

class LogTimelineWidget : public QWidget {
public:
    struct Config {
        std::vector<double> times;  // seconds from start
        std::vector<std::string> channel_names;
        std::vector<std::vector<double>> channel_values;  // parallel to times
    };

    explicit LogTimelineWidget(QWidget* parent = nullptr);

    void set_config(const Config& cfg);
    void clear_config();
    void reset_zoom();

    double view_start() const { return view_start_; }
    double view_end()   const { return view_end_;   }

    void set_cursor_index(int idx);

    std::function<void(int)> on_cursor_changed;

protected:
    void paintEvent(QPaintEvent*) override;
    void mousePressEvent(QMouseEvent* e) override;
    void mouseMoveEvent(QMouseEvent* e) override;
    void mouseReleaseEvent(QMouseEvent* e) override;

private:
    void handle_seek(QMouseEvent* e);

    Config cfg_;
    std::vector<std::pair<double, double>> channel_ranges_;
    int cursor_idx_ = 0;
    double view_start_ = 0;
    double view_end_   = 1;
    bool zoom_drag_active_ = false;
    double zoom_drag_start_x_ = 0;
    double zoom_drag_current_x_ = 0;
};
