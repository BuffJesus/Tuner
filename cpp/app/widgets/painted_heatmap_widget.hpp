// SPDX-License-Identifier: MIT
//
// PaintedHeatmapWidget + CellClickFilter — single-QPainter replacement
// for the 256-QLabel table grid, plus the QLabel-based click filter the
// legacy grid still uses.
//
// Extracted from cpp/app/main.cpp. Header-only; no Q_OBJECT.
//
// PaintedHeatmapWidget: sub-slice 147 of Phase 14 Slice 4. The old path
// created 256 QLabels + 256 CellClickFilter event filters = 512 QObjects
// + 256 setStyleSheet calls, taking ~430ms per page switch. This widget
// does the same work in a single paintEvent (<5ms). Mouse events (click,
// shift-click, drag, double-click) are mapped from pixel coordinates to
// (row, col) and dispatched through the same callback signatures the old
// CellClickFilter used, so the cell editor, selection, crosshair,
// copy/paste, and keyboard navigation all work unchanged.

#pragma once

#include "../theme.hpp"

#include <QApplication>
#include <QColor>
#include <QEvent>
#include <QFont>
#include <QLabel>
#include <QMouseEvent>
#include <QObject>
#include <QPaintEvent>
#include <QPainter>
#include <QPen>
#include <QPoint>
#include <QPointF>
#include <QRect>
#include <QSizePolicy>
#include <QString>
#include <QWidget>
#include <Qt>

#include <algorithm>
#include <cstddef>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace tuner_app {

class PaintedHeatmapWidget : public QWidget {
public:
    struct Cell {
        std::string text;
        QColor bg;
        QColor fg;
    };

    using EditCb = std::function<void(int row, int col)>;
    using SelectCb = std::function<void(int row, int col, bool shift)>;
    using DragCb = std::function<void(int row, int col, bool start)>;

    explicit PaintedHeatmapWidget(QWidget* parent = nullptr)
        : QWidget(parent) {
        setMouseTracking(true);
        setFocusPolicy(Qt::StrongFocus);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    }

    void set_grid(int rows, int cols,
                  const std::vector<std::vector<Cell>>& cells,
                  const std::vector<std::string>& x_labels,
                  const std::vector<std::string>& y_labels,
                  int cell_w, int cell_h, int cell_font_px, int axis_font_px) {
        rows_ = rows; cols_ = cols;
        cells_ = cells;
        x_labels_ = x_labels; y_labels_ = y_labels;
        cell_w_ = cell_w; cell_h_ = cell_h;
        cell_font_px_ = cell_font_px; axis_font_px_ = axis_font_px;
        highlight_row_ = highlight_col_ = -1;
        sel_r0_ = sel_c0_ = sel_r1_ = sel_c1_ = -1;
        int aw = y_labels_.empty() ? 0 : 40;
        int ah = x_labels_.empty() ? 0 : 16;
        setMinimumSize(aw + cols_ * cell_w_ + 2, ah + rows_ * cell_h_ + 2);
        update();
    }

    void set_cell_text(int r, int c, const std::string& text) {
        if (r >= 0 && r < rows_ && c >= 0 && c < cols_) { cells_[r][c].text = text; update(); }
    }
    std::string get_cell_text(int r, int c) const {
        if (r >= 0 && r < rows_ && c >= 0 && c < cols_) return cells_[r][c].text;
        return {};
    }
    void set_cell_bg(int r, int c, const QColor& bg) {
        if (r >= 0 && r < rows_ && c >= 0 && c < cols_) { cells_[r][c].bg = bg; update(); }
    }
    void set_cell_style(int r, int c, const QColor& bg, const QColor& fg) {
        if (r >= 0 && r < rows_ && c >= 0 && c < cols_) {
            cells_[r][c].bg = bg; cells_[r][c].fg = fg; update();
        }
    }
    void set_highlight(int r, int c) { highlight_row_ = r; highlight_col_ = c; update(); }
    void clear_highlight() { highlight_row_ = highlight_col_ = -1; update(); }
    void set_selection(int r0, int c0, int r1, int c1) {
        sel_r0_ = std::min(r0, r1); sel_c0_ = std::min(c0, c1);
        sel_r1_ = std::max(r0, r1); sel_c1_ = std::max(c0, c1); update();
    }
    void clear_selection() { sel_r0_ = sel_c0_ = sel_r1_ = sel_c1_ = -1; update(); }
    QRect cell_rect(int r, int c) const {
        auto [cw, ch] = live_cell_size();
        return QRect(axis_w() + c * cw, axis_h() + r * ch, cw, ch);
    }

    int rows_ = 0, cols_ = 0;
    std::vector<std::vector<Cell>> cells_;

    EditCb on_double_click;
    SelectCb on_click;
    DragCb on_drag;

protected:
    void paintEvent(QPaintEvent*) override {
        namespace tt = tuner_theme;
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing, false);
        p.fillRect(rect(), QColor(QString::fromUtf8(tt::bg_elevated)));
        // Recompute axis dims from current widget size BEFORE
        // anything reads axis_w/axis_h. This breaks the recursion
        // cycle (axis→live_cell_size→axis) by computing axis dims
        // from an approximate cell height that doesn't depend on
        // axis dims.
        const_cast<PaintedHeatmapWidget*>(this)->recompute_axis_dims();
        int aw = axis_w(), ah = axis_h();
        auto [cw, ch] = live_cell_size();
        // Scale font with cell height so text stays readable at any size.
        int font_cap = std::max(16, ch / 2);
        int live_cell_font = std::clamp(ch * 2 / 3, cell_font_px_, font_cap);
        int live_axis_font = std::clamp(ch / 2, axis_font_px_, font_cap - 2);
        // X-axis
        if (!x_labels_.empty()) {
            QFont af; af.setFamily("monospace"); af.setBold(true); af.setPixelSize(live_axis_font);
            p.setFont(af); p.setPen(QColor(QString::fromUtf8(tt::text_muted)));
            for (int c = 0; c < std::min(static_cast<int>(x_labels_.size()), cols_); ++c)
                p.drawText(QRect(aw + c * cw, 0, cw, ah), Qt::AlignCenter, QString::fromUtf8(x_labels_[c].c_str()));
        }
        // Y-axis (inverted)
        if (!y_labels_.empty()) {
            QFont af; af.setFamily("monospace"); af.setBold(true); af.setPixelSize(live_axis_font);
            p.setFont(af); p.setPen(QColor(QString::fromUtf8(tt::text_muted)));
            int yl = std::min(static_cast<int>(y_labels_.size()), rows_);
            for (int r = 0; r < yl; ++r) {
                int inv = yl - 1 - r;
                p.drawText(QRect(0, ah + r * ch, aw - 4, ch), Qt::AlignRight | Qt::AlignVCenter,
                    QString::fromUtf8(y_labels_[inv < static_cast<int>(y_labels_.size()) ? inv : 0].c_str()));
            }
        }
        // Cells
        QFont cf; cf.setFamily("monospace"); cf.setPixelSize(live_cell_font); p.setFont(cf);
        for (int r = 0; r < rows_; ++r)
            for (int c = 0; c < cols_; ++c) {
                QRect cr(aw + c * cw, ah + r * ch, cw, ch);
                p.fillRect(cr, cells_[r][c].bg); p.setPen(cells_[r][c].fg);
                p.drawText(cr, Qt::AlignCenter, QString::fromUtf8(cells_[r][c].text.c_str()));
            }
        // Selection
        if (sel_r0_ >= 0) {
            p.setPen(QPen(QColor(QString::fromUtf8(tt::accent_primary)), 2)); p.setBrush(Qt::NoBrush);
            p.drawRect(QRect(aw + sel_c0_ * cw, ah + sel_r0_ * ch,
                (sel_c1_ - sel_c0_ + 1) * cw, (sel_r1_ - sel_r0_ + 1) * ch));
        }
        // Crosshair
        if (highlight_row_ >= 0 && highlight_col_ >= 0) {
            QRect hr = cell_rect(highlight_row_, highlight_col_);
            p.setPen(QPen(QColor(255, 255, 255), 2)); p.setBrush(Qt::NoBrush); p.drawRect(hr.adjusted(-1, -1, 1, 1));
            p.setPen(QPen(QColor(255, 68, 68), 1)); p.drawRect(hr.adjusted(-2, -2, 2, 2));
        }
    }
    void mousePressEvent(QMouseEvent* ev) override {
        auto [r, c] = pixel_to_cell(ev->position());
        if (r < 0) return;
        if (on_click) on_click(r, c, ev->modifiers() & Qt::ShiftModifier);
        if (on_drag) on_drag(r, c, true);
        dragging_ = true;
    }
    void mouseMoveEvent(QMouseEvent* ev) override {
        if (!dragging_) return;
        auto [r, c] = pixel_to_cell(ev->position());
        if (r < 0) return;
        if (on_drag) on_drag(r, c, false);
    }
    void mouseReleaseEvent(QMouseEvent*) override { dragging_ = false; }
    void mouseDoubleClickEvent(QMouseEvent* ev) override {
        auto [r, c] = pixel_to_cell(ev->position());
        if (r < 0) return;
        if (on_double_click) on_double_click(r, c);
    }

private:
    // Axis dims are cached by paintEvent to avoid the recursion
    // between axis_w→live_cell_size→axis_w that crashed earlier.
    // paintEvent computes them from the live font + label content,
    // stores here, and all other callers (cell_rect, pixel_to_cell)
    // read the cached values.
    int axis_w() const { return cached_axis_w_; }
    int axis_h() const { return cached_axis_h_; }
    void recompute_axis_dims() {
        if (y_labels_.empty()) { cached_axis_w_ = 0; }
        else {
            std::size_t max_len = 1;
            for (const auto& l : y_labels_)
                if (l.size() > max_len) max_len = l.size();
            // Use the LIVE axis font (same one paintEvent uses).
            int ch_approx = (rows_ > 0) ? std::max(cell_h_, (height() - 30) / rows_) : cell_h_;
            int font_px = std::clamp(ch_approx / 2, axis_font_px_, std::max(14, ch_approx / 2));
            int char_w = font_px * 6 / 10;
            cached_axis_w_ = std::max(40, static_cast<int>(max_len) * char_w + 10);
        }
        if (x_labels_.empty()) { cached_axis_h_ = 0; }
        else {
            int ch_approx = (rows_ > 0) ? std::max(cell_h_, (height() - 30) / rows_) : cell_h_;
            int font_px = std::clamp(ch_approx / 2, axis_font_px_, std::max(14, ch_approx / 2));
            cached_axis_h_ = std::max(22, font_px + 10);
        }
    }
    mutable int cached_axis_w_ = 40;
    mutable int cached_axis_h_ = 22;
    // Compute cell dimensions from actual widget size so the heatmap
    // fills available space instead of sitting at the fixed minimum.
    std::pair<int, int> live_cell_size() const {
        if (rows_ == 0 || cols_ == 0) return {cell_w_, cell_h_};
        int avail_w = width() - axis_w() - 2;
        int avail_h = height() - axis_h() - 2;
        int cw = std::max(cell_w_, avail_w / cols_);
        int ch = std::max(cell_h_, avail_h / rows_);
        return {cw, ch};
    }
    std::pair<int, int> pixel_to_cell(QPointF pos) const {
        if (rows_ == 0 || cols_ == 0) return {-1, -1};
        auto [cw, ch] = live_cell_size();
        int c = static_cast<int>((pos.x() - axis_w()) / cw);
        int r = static_cast<int>((pos.y() - axis_h()) / ch);
        return (r < 0 || r >= rows_ || c < 0 || c >= cols_) ? std::pair{-1, -1} : std::pair{r, c};
    }
    std::vector<std::string> x_labels_, y_labels_;
    int cell_w_ = 34, cell_h_ = 15, cell_font_px_ = 9, axis_font_px_ = 9;
    int highlight_row_ = -1, highlight_col_ = -1;
    int sel_r0_ = -1, sel_c0_ = -1, sel_r1_ = -1, sel_c1_ = -1;
    bool dragging_ = false;
};

// Event filter for click / double-click / drag on heatmap cells.
// Single click: select cell (Shift extends selection range).
// Double click: open inline editor overlay.
// Click + drag: rectangle selection from anchor to current cell.
class CellClickFilter : public QObject {
public:
    using EditCallback = std::function<void(int row, int col, QLabel* lbl)>;
    using SelectCallback = std::function<void(int row, int col, bool shift)>;
    using DragCallback = std::function<void(int row, int col, bool start)>;
    CellClickFilter(int row, int col, EditCallback edit_cb, SelectCallback sel_cb,
                    DragCallback drag_cb = nullptr, QObject* parent = nullptr)
        : QObject(parent), row_(row), col_(col),
          edit_cb_(std::move(edit_cb)), sel_cb_(std::move(sel_cb)),
          drag_cb_(std::move(drag_cb)) {}
protected:
    bool eventFilter(QObject* obj, QEvent* ev) override {
        if (ev->type() == QEvent::MouseButtonDblClick) {
            edit_cb_(row_, col_, qobject_cast<QLabel*>(obj));
            return true;
        }
        if (ev->type() == QEvent::MouseButtonPress) {
            auto* me = static_cast<QMouseEvent*>(ev);
            bool shift = (me->modifiers() & Qt::ShiftModifier) != 0;
            sel_cb_(row_, col_, shift);
            if (drag_cb_) drag_cb_(row_, col_, /*start=*/true);
            return false;
        }
        if (ev->type() == QEvent::MouseMove && drag_cb_) {
            // During drag, find which cell the mouse is currently over
            // and extend the selection rectangle.
            auto* me = static_cast<QMouseEvent*>(ev);
            if (me->buttons() & Qt::LeftButton) {
                auto* widget = qobject_cast<QWidget*>(obj);
                if (widget) {
                    QPoint global_pos = widget->mapToGlobal(me->pos());
                    auto* under = QApplication::widgetAt(global_pos);
                    if (under) {
                        // Check if the widget under the cursor has a
                        // CellClickFilter — if so, use its (row, col).
                        for (auto* child : under->children()) {
                            auto* filter = dynamic_cast<CellClickFilter*>(child);
                            if (filter) {
                                drag_cb_(filter->row_, filter->col_, /*start=*/false);
                                return false;
                            }
                        }
                    }
                }
            }
            return false;
        }
        if (ev->type() == QEvent::MouseButtonRelease && drag_cb_) {
            drag_cb_(-1, -1, /*start=*/false);  // end drag
            return false;
        }
        return QObject::eventFilter(obj, ev);
    }
private:
    int row_, col_;
    EditCallback edit_cb_;
    SelectCallback sel_cb_;
    DragCallback drag_cb_;
};

}  // namespace tuner_app
