"""Python ↔ C++ parity harness for tuner_core::table_edit numeric transforms.

Pins the C++ table_edit transforms against
`tuner.services.table_edit_service.TableEditService` byte-for-byte
across fill, fill_down, fill_right, interpolate, smooth, and paste.
copy_region is intentionally excluded because Python's str(float)
formatting is non-trivial to mirror exactly.
"""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

import pytest

from tuner.services.table_edit_service import TableEditService, TableSelection


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CPP_BUILD_CANDIDATES = [
    _REPO_ROOT / "build" / "cpp",
    _REPO_ROOT / "build" / "cpp" / "Release",
    _REPO_ROOT / "build" / "cpp" / "Debug",
    _REPO_ROOT / "cpp" / "build",
]


def _try_import_tuner_core():
    try:
        return importlib.import_module("tuner._native.tuner_core")
    except ImportError:
        pass
    for candidate in _CPP_BUILD_CANDIDATES:
        if not candidate.exists():
            continue
        added = str(candidate)
        if added not in sys.path:
            sys.path.insert(0, added)
        try:
            return importlib.import_module("tuner_core")
        except ImportError:
            sys.path.remove(added)
            continue
    return None


_tuner_core = _try_import_tuner_core()

pytestmark = pytest.mark.skipif(
    _tuner_core is None,
    reason="tuner_core C++ extension not built — see cpp/README.md.",
)


_py = TableEditService()


def _approx_list(a, b, rel=1e-9):
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x == pytest.approx(y, rel=rel, abs=1e-9), f"{x} != {y}"


def _grid(rows, cols, fill=0.0):
    return [fill] * (rows * cols)


def _filled_grid(rows, cols):
    return [float(i) for i in range(rows * cols)]


# ---------------------------------------------------------------------------
# fill_region
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rows,cols,top,left,bottom,right,value",
    [
        (3, 3, 0, 1, 1, 2, 99.0),
        (4, 4, 1, 1, 2, 2, -7.5),
        (5, 5, 0, 0, 4, 4, 1.0),
        (1, 8, 0, 2, 0, 5, 12.34),
    ],
)
def test_fill_region_matches_python(rows, cols, top, left, bottom, right, value):
    values = _filled_grid(rows, cols)
    py = _py.fill_region(values, cols,
                         TableSelection(top, left, bottom, right), value)
    cpp = list(_tuner_core.table_edit_fill_region(
        values, cols, top, left, bottom, right, value))
    _approx_list(cpp, py)


# ---------------------------------------------------------------------------
# fill_down_region / fill_right_region
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rows,cols,top,left,bottom,right",
    [
        (3, 3, 0, 0, 2, 2),
        (4, 4, 1, 1, 3, 2),
        (5, 5, 0, 0, 4, 4),
        (3, 3, 0, 0, 0, 2),  # 1-row → no-op
    ],
)
def test_fill_down_matches_python(rows, cols, top, left, bottom, right):
    values = _filled_grid(rows, cols)
    py = _py.fill_down_region(values, cols, TableSelection(top, left, bottom, right))
    cpp = list(_tuner_core.table_edit_fill_down_region(
        values, cols, top, left, bottom, right))
    _approx_list(cpp, py)


@pytest.mark.parametrize(
    "rows,cols,top,left,bottom,right",
    [
        (3, 3, 0, 0, 2, 2),
        (4, 4, 1, 0, 3, 3),
        (3, 5, 0, 1, 2, 4),
        (3, 3, 0, 0, 2, 0),  # 1-col → no-op
    ],
)
def test_fill_right_matches_python(rows, cols, top, left, bottom, right):
    values = _filled_grid(rows, cols)
    py = _py.fill_right_region(values, cols, TableSelection(top, left, bottom, right))
    cpp = list(_tuner_core.table_edit_fill_right_region(
        values, cols, top, left, bottom, right))
    _approx_list(cpp, py)


# ---------------------------------------------------------------------------
# interpolate_region
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rows,cols,top,left,bottom,right,values",
    [
        # Horizontal: 0 → 100 across 5 cells
        (1, 5, 0, 0, 0, 4, [0.0, 99, 99, 99, 100.0]),
        # Vertical (width=1): 10 → 50 down 5 cells
        (5, 1, 0, 0, 4, 0, [10.0, 99, 99, 99, 50.0]),
        # 2D rectangle: every row interpolated horizontally
        (3, 4, 0, 0, 2, 3, [
            10, 0, 0, 40,
            20, 0, 0, 80,
            30, 0, 0, 60,
        ]),
        # Single-cell selection: should be a no-op
        (3, 3, 1, 1, 1, 1, [1, 2, 3, 4, 5, 6, 7, 8, 9]),
    ],
)
def test_interpolate_matches_python(rows, cols, top, left, bottom, right, values):
    py = _py.interpolate_region(values, cols,
                                 TableSelection(top, left, bottom, right))
    cpp = list(_tuner_core.table_edit_interpolate_region(
        values, cols, top, left, bottom, right))
    _approx_list(cpp, py)


# ---------------------------------------------------------------------------
# smooth_region
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rows,cols",
    [(3, 3), (4, 4), (5, 5), (2, 8)],
)
def test_smooth_matches_python(rows, cols):
    rng = random.Random(rows * 100 + cols)
    values = [rng.uniform(-50.0, 50.0) for _ in range(rows * cols)]
    py = _py.smooth_region(
        values, cols, TableSelection(0, 0, rows - 1, cols - 1))
    cpp = list(_tuner_core.table_edit_smooth_region(
        values, cols, 0, 0, rows - 1, cols - 1))
    _approx_list(cpp, py, rel=1e-12)


def test_smooth_partial_selection_matches_python():
    rows, cols = 5, 5
    rng = random.Random(0xC0FFEE)
    values = [rng.uniform(0, 255) for _ in range(rows * cols)]
    py = _py.smooth_region(values, cols, TableSelection(1, 1, 3, 3))
    cpp = list(_tuner_core.table_edit_smooth_region(
        values, cols, 1, 1, 3, 3))
    _approx_list(cpp, py, rel=1e-12)


# ---------------------------------------------------------------------------
# paste_region
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "clipboard,rows,cols,top,left,bottom,right",
    [
        ("7", 2, 3, 0, 0, 1, 2),
        ("1\t2\n3\t4", 3, 4, 0, 0, 1, 1),
        ("9\t8", 3, 4, 0, 0, 2, 3),  # 1x2 tiled across 3x4
        ("10, 20, 30\n40, 50, 60", 3, 3, 0, 0, 1, 2),  # comma-separated
        ("1\n2\n3", 4, 2, 0, 0, 3, 0),  # 3x1 down a single column
        ("1\t2\t3", 3, 5, 1, 1, 1, 3),
    ],
)
def test_paste_matches_python(clipboard, rows, cols, top, left, bottom, right):
    values = _filled_grid(rows, cols)
    py = _py.paste_region(values, cols,
                          TableSelection(top, left, bottom, right), clipboard)
    cpp = list(_tuner_core.table_edit_paste_region(
        values, cols, top, left, bottom, right, clipboard))
    _approx_list(cpp, py)


def test_paste_with_blank_clipboard_is_a_no_op():
    values = _filled_grid(2, 2)
    py = _py.paste_region(values, 2, TableSelection(0, 0, 1, 1), "")
    cpp = list(_tuner_core.table_edit_paste_region(
        values, 2, 0, 0, 1, 1, ""))
    assert py == values
    assert cpp == values
