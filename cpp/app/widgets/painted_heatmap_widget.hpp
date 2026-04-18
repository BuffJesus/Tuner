// SPDX-License-Identifier: MIT
//
// PaintedHeatmapWidget — single-QPainter replacement for the 256-QLabel grid.
// Sub-slice 147 of Phase 14 Slice 4. The old path created 256 QLabels +
// 256 CellClickFilter event filters = 512 QObjects + 256 setStyleSheet
// calls, taking ~430ms per page switch. This widget does the same work in
// a single paintEvent (<5ms). Mouse events (click, shift-click, drag,
// double-click) are mapped from pixel coordinates to (row, col) and
// dispatched through the same callback signatures the old CellClickFilter
// used, so the cell editor, selection, crosshair, copy/paste, and keyboard
// navigation all work unchanged.

#pragma once

#include <QColor>
#include <QPointF>
#include <QRect>
#include <QWidget>

#include <functional>
#include <string>
#include <utility>
#include <vector>

class QMouseEvent;
class QPaintEvent;

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

    explicit PaintedHeatmapWidget(QWidget* parent = nullptr);

    void set_grid(int rows, int cols,
                  const std::vector<std::vector<Cell>>& cells,
                  const std::vector<std::string>& x_labels,
                  const std::vector<std::string>& y_labels,
                  int cell_w, int cell_h, int cell_font_px, int axis_font_px);

    void set_cell_text(int r, int c, const std::string& text);
    std::string get_cell_text(int r, int c) const;
    void set_cell_bg(int r, int c, const QColor& bg);
    void set_cell_style(int r, int c, const QColor& bg, const QColor& fg);
    void set_highlight(int r, int c);
    void clear_highlight();
    void set_selection(int r0, int c0, int r1, int c1);
    void clear_selection();
    QRect cell_rect(int r, int c) const;

    int rows_ = 0, cols_ = 0;
    std::vector<std::vector<Cell>> cells_;

    EditCb on_double_click;
    SelectCb on_click;
    DragCb on_drag;

protected:
    void paintEvent(QPaintEvent*) override;
    void mousePressEvent(QMouseEvent* ev) override;
    void mouseMoveEvent(QMouseEvent* ev) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void mouseDoubleClickEvent(QMouseEvent* ev) override;

private:
    // Axis dims are cached by paintEvent to avoid the recursion
    // between axis_w→live_cell_size→axis_w that crashed earlier.
    // paintEvent computes them from the live font + label content,
    // stores here, and all other callers (cell_rect, pixel_to_cell)
    // read the cached values.
    int axis_w() const { return cached_axis_w_; }
    int axis_h() const { return cached_axis_h_; }
    void recompute_axis_dims();
    std::pair<int, int> live_cell_size() const;
    std::pair<int, int> pixel_to_cell(QPointF pos) const;

    mutable int cached_axis_w_ = 40;
    mutable int cached_axis_h_ = 22;
    std::vector<std::string> x_labels_, y_labels_;
    int cell_w_ = 34, cell_h_ = 15, cell_font_px_ = 9, axis_font_px_ = 9;
    int highlight_row_ = -1, highlight_col_ = -1;
    int sel_r0_ = -1, sel_c0_ = -1, sel_r1_ = -1, sel_c1_ = -1;
    bool dragging_ = false;
};
