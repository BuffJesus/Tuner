"""Tests for the table cell width fit helper extracted from
``TuningWorkspace._fit_table_column_widths`` (Phase 5 polish).
"""
from __future__ import annotations

from tuner.ui.tuning_workspace import (
    _TABLE_CELL_MAX_WIDTH,
    _TABLE_CELL_MIN_WIDTH,
    compute_table_cell_width,
)


def test_zero_columns_returns_min_width() -> None:
    assert compute_table_cell_width(1920, 0) == _TABLE_CELL_MIN_WIDTH


def test_narrow_viewport_clamps_to_min() -> None:
    # 320 px / 16 cols → 16 px raw → clamps to 44.
    assert compute_table_cell_width(320, 16) == _TABLE_CELL_MIN_WIDTH


def test_wide_viewport_with_few_columns_clamps_to_max() -> None:
    # 1920 px / 8 cols ≈ 240 px raw → clamps to 80.
    assert compute_table_cell_width(1920, 8) == _TABLE_CELL_MAX_WIDTH


def test_balanced_viewport_returns_proportional_width() -> None:
    # 800 px / 10 cols → 76 px raw → inside bounds.
    width = compute_table_cell_width(800, 10)
    assert _TABLE_CELL_MIN_WIDTH <= width <= _TABLE_CELL_MAX_WIDTH
    assert width == 76


def test_wider_viewport_increases_cell_width_until_cap() -> None:
    """Monotonic non-decreasing in viewport_width up to the cap."""
    widths = [compute_table_cell_width(w, 12) for w in (480, 720, 960, 1440, 1920)]
    assert widths == sorted(widths)
    assert widths[-1] == _TABLE_CELL_MAX_WIDTH


def test_more_columns_decreases_cell_width() -> None:
    """Same viewport, more columns → narrower cells (until floor)."""
    widths = [compute_table_cell_width(1600, c) for c in (8, 12, 16, 20)]
    assert widths == sorted(widths, reverse=True)


def test_phase5_polish_widens_cells_on_wide_viewport_vs_old_cap() -> None:
    """Document the polish: a 1440p-class viewport with a 12-column
    VE table now produces cells wider than the previous 56 px cap."""
    # 1440p workspace ≈ 1700 px wide minus side panels → ~1500 px
    # available for the table. 12-column VE table.
    width = compute_table_cell_width(1500, 12)
    assert width > 56  # the previous ceiling
    assert width == 80  # the new ceiling
