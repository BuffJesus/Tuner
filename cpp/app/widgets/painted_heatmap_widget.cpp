// SPDX-License-Identifier: MIT

#include "widgets/painted_heatmap_widget.hpp"

#include "theme.hpp"

#include <QColor>
#include <QFont>
#include <QMouseEvent>
#include <QPaintEvent>
#include <QPainter>
#include <QPen>
#include <QRect>
#include <QSizePolicy>
#include <QString>

#include <algorithm>
#include <cstddef>

namespace tt = tuner_theme;

PaintedHeatmapWidget::PaintedHeatmapWidget(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
}

void PaintedHeatmapWidget::set_grid(int rows, int cols,
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

void PaintedHeatmapWidget::set_cell_text(int r, int c, const std::string& text) {
    if (r >= 0 && r < rows_ && c >= 0 && c < cols_) { cells_[r][c].text = text; update(); }
}

std::string PaintedHeatmapWidget::get_cell_text(int r, int c) const {
    if (r >= 0 && r < rows_ && c >= 0 && c < cols_) return cells_[r][c].text;
    return {};
}

void PaintedHeatmapWidget::set_cell_bg(int r, int c, const QColor& bg) {
    if (r >= 0 && r < rows_ && c >= 0 && c < cols_) { cells_[r][c].bg = bg; update(); }
}

void PaintedHeatmapWidget::set_cell_style(int r, int c, const QColor& bg, const QColor& fg) {
    if (r >= 0 && r < rows_ && c >= 0 && c < cols_) {
        cells_[r][c].bg = bg; cells_[r][c].fg = fg; update();
    }
}

void PaintedHeatmapWidget::set_highlight(int r, int c) {
    highlight_row_ = r; highlight_col_ = c; update();
}

void PaintedHeatmapWidget::clear_highlight() {
    highlight_row_ = highlight_col_ = -1; update();
}

void PaintedHeatmapWidget::set_selection(int r0, int c0, int r1, int c1) {
    sel_r0_ = std::min(r0, r1); sel_c0_ = std::min(c0, c1);
    sel_r1_ = std::max(r0, r1); sel_c1_ = std::max(c0, c1); update();
}

void PaintedHeatmapWidget::clear_selection() {
    sel_r0_ = sel_c0_ = sel_r1_ = sel_c1_ = -1; update();
}

QRect PaintedHeatmapWidget::cell_rect(int r, int c) const {
    auto [cw, ch] = live_cell_size();
    return QRect(axis_w() + c * cw, axis_h() + r * ch, cw, ch);
}

void PaintedHeatmapWidget::paintEvent(QPaintEvent*) {
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

void PaintedHeatmapWidget::mousePressEvent(QMouseEvent* ev) {
    auto [r, c] = pixel_to_cell(ev->position());
    if (r < 0) return;
    if (on_click) on_click(r, c, ev->modifiers() & Qt::ShiftModifier);
    if (on_drag) on_drag(r, c, true);
    dragging_ = true;
}

void PaintedHeatmapWidget::mouseMoveEvent(QMouseEvent* ev) {
    if (!dragging_) return;
    auto [r, c] = pixel_to_cell(ev->position());
    if (r < 0) return;
    if (on_drag) on_drag(r, c, false);
}

void PaintedHeatmapWidget::mouseReleaseEvent(QMouseEvent*) {
    dragging_ = false;
}

void PaintedHeatmapWidget::mouseDoubleClickEvent(QMouseEvent* ev) {
    auto [r, c] = pixel_to_cell(ev->position());
    if (r < 0) return;
    if (on_double_click) on_double_click(r, c);
}

void PaintedHeatmapWidget::recompute_axis_dims() {
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

std::pair<int, int> PaintedHeatmapWidget::live_cell_size() const {
    if (rows_ == 0 || cols_ == 0) return {cell_w_, cell_h_};
    int avail_w = width() - axis_w() - 2;
    int avail_h = height() - axis_h() - 2;
    int cw = std::max(cell_w_, avail_w / cols_);
    int ch = std::max(cell_h_, avail_h / rows_);
    return {cw, ch};
}

std::pair<int, int> PaintedHeatmapWidget::pixel_to_cell(QPointF pos) const {
    if (rows_ == 0 || cols_ == 0) return {-1, -1};
    auto [cw, ch] = live_cell_size();
    int c = static_cast<int>((pos.x() - axis_w()) / cw);
    int r = static_cast<int>((pos.y() - axis_h()) / ch);
    return (r < 0 || r >= rows_ || c < 0 || c >= cols_) ? std::pair{-1, -1} : std::pair{r, c};
}
