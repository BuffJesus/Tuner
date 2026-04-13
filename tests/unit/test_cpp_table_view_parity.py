"""Python ↔ C++ parity harness for tuner_core::table_view."""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

import pytest

from tuner.domain.tune import TuneValue
from tuner.services.table_view_service import TableViewService


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
    reason="tuner_core C++ extension not built.",
)


_py = TableViewService()


def _make_hints(rows=None, cols=None, shape_text=None):
    h = _tuner_core.TableViewShapeHints()
    h.rows = rows if rows is not None else -1
    h.cols = cols if cols is not None else -1
    h.shape_text = shape_text
    return h


def _run_both(values, *, py_rows=None, py_cols=None, shape=None,
              cpp_rows=None, cpp_cols=None, cpp_shape=None):
    """Run both implementations and compare resulting models.

    Values are normalized to Python floats so the Python side's
    `str(item)` and the C++ side's tune_value_preview repr produce
    identical strings (whole-number floats render as `"X.0"` on
    both sides). The C++ FFI doesn't carry int/float distinction
    across the boundary anyway — every value is a `double` there.
    """
    float_values = [float(v) for v in values]
    tv = TuneValue(name="t", value=float_values, rows=py_rows, cols=py_cols)
    py_model = _py.build_table_model(tv, shape=shape)
    hints = _make_hints(
        rows=(cpp_rows if cpp_rows is not None else py_rows),
        cols=(cpp_cols if cpp_cols is not None else py_cols),
        shape_text=(cpp_shape if cpp_shape is not None else shape),
    )
    cpp_model = _tuner_core.table_view_build_model(float_values, hints)
    return py_model, cpp_model


def _check(py_model, cpp_model):
    assert cpp_model.rows == py_model.rows
    assert cpp_model.columns == py_model.columns
    assert len(cpp_model.cells) == len(py_model.cells)
    for cpp_row, py_row in zip(cpp_model.cells, py_model.cells):
        assert list(cpp_row) == list(py_row)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def test_explicit_dimensions_match_python():
    py, cpp = _run_both(list(range(1, 17)), py_rows=4, py_cols=4)
    _check(py, cpp)


def test_shape_text_fallback_matches_python():
    py, cpp = _run_both([1, 2, 3, 4, 5, 6], shape="2x3")
    _check(py, cpp)


def test_shape_text_case_insensitive_matches_python():
    py, cpp = _run_both([1, 2, 3, 4], shape="2X2")
    _check(py, cpp)


def test_malformed_shape_text_falls_through_matches_python():
    py, cpp = _run_both([1, 2, 3, 4, 5], shape="garbage")
    _check(py, cpp)


def test_no_shape_falls_back_to_single_column_matches_python():
    py, cpp = _run_both([1, 2, 3])
    _check(py, cpp)


def test_short_row_padding_matches_python():
    py, cpp = _run_both([1, 2, 3], py_rows=2, py_cols=2)
    _check(py, cpp)


def test_fractional_values_match_python():
    py, cpp = _run_both([0.5, 3.14, 0.1, -1.25], py_rows=2, py_cols=2)
    _check(py, cpp)


def test_explicit_dims_override_shape_text_matches_python():
    py, cpp = _run_both(list(range(1, 17)), py_rows=4, py_cols=4, shape="8x2")
    _check(py, cpp)


def test_random_grid_matches_python():
    rng = random.Random(0xC0DE)
    for _ in range(20):
        rows = rng.randint(1, 8)
        cols = rng.randint(1, 8)
        values = [rng.uniform(-100.0, 100.0) for _ in range(rows * cols)]
        py, cpp = _run_both(values, py_rows=rows, py_cols=cols)
        _check(py, cpp)


def test_resolve_shape_explicit_matches_python():
    cpp = _tuner_core.table_view_resolve_shape(16, _make_hints(rows=4, cols=4))
    assert cpp == (4, 4)


def test_resolve_shape_text_matches_python():
    cpp = _tuner_core.table_view_resolve_shape(6, _make_hints(shape_text="2x3"))
    assert cpp == (2, 3)


def test_resolve_shape_fallback_matches_python():
    cpp = _tuner_core.table_view_resolve_shape(5, _make_hints())
    assert cpp == (5, 1)
