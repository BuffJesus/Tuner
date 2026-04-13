"""Python ↔ C++ parity harness for tuner_core::tune_value_preview.

The C++ scalar formatter is pinned against Python's `str(float)` and
the list formatter is pinned against the `_list_preview` /
`_preview` helpers in both `StagedChangeService` and
`TuningPageDiffService` (they share the same shape).
"""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

import pytest

from tuner.services.staged_change_service import StagedChangeService
from tuner.services.tuning_page_diff_service import TuningPageDiffService


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


# ---------------------------------------------------------------------------
# scalar repr — pinned against Python `str(float)`
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    [
        0.0, 1.0, -1.0, 2.0, -2.0, 100.0, -100.0,
        0.1, 0.5, -0.5, 3.14, -1.25,
        12.5, 100.5, -42.5,
        0.001, 1000.0,
        # Whole-number floats that often surface from staged tune values
        14.7, 220.0, 5500.0, 7000.0,
    ],
)
def test_scalar_repr_matches_python_str_float(value):
    py = str(float(value))
    cpp = _tuner_core.tune_value_format_scalar_python_repr(value)
    assert cpp == py, f"{value}: cpp={cpp!r} py={py!r}"


def test_scalar_repr_matches_random_floats():
    rng = random.Random(0xC0FFEE)
    for _ in range(200):
        # Pick a finite double in a typical tune-value range.
        v = rng.uniform(-1000.0, 1000.0)
        py = str(v)
        cpp = _tuner_core.tune_value_format_scalar_python_repr(v)
        assert cpp == py, f"{v!r}: cpp={cpp!r} py={py!r}"


# ---------------------------------------------------------------------------
# list preview — pinned against StagedChangeService._preview / _list_preview
# ---------------------------------------------------------------------------

# Both StagedChangeService and TuningPageDiffService implement the
# same shape, but TuningPageDiffService also uses a 4-item truncation
# rule. We pin against StagedChangeService.

_staged = StagedChangeService()
_diff = TuningPageDiffService()


def _py_list_preview(values):
    # Reach into the static helper directly so the test doesn't need
    # to construct a TuneValue.
    return TuningPageDiffService._list_preview(list(values))


@pytest.mark.parametrize(
    "values",
    [
        [],
        [1.0],
        [1.0, 2.0],
        [1.0, 2.0, 3.0],
        [1.0, 2.0, 3.0, 4.0],
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        [0.5, 1.5, 2.5, 3.5],
        [0.1, 0.2, 0.3],
        # Real VE table row shapes
        [70.0, 75.0, 80.0, 85.0, 90.0, 95.0],
        # Negative values (S08 trims)
        [-5.0, -2.5, 0.0, 2.5, 5.0],
    ],
)
def test_list_preview_matches_python(values):
    py = _py_list_preview(values)
    cpp = _tuner_core.tune_value_format_list_preview(values)
    assert cpp == py


def test_staged_change_service_uses_same_preview():
    """Cross-check: StagedChangeService._preview produces the same output
    as TuningPageDiffService._list_preview for list values, so the C++
    implementation matches both services simultaneously."""
    from tuner.domain.tune import TuneValue
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    py_via_staged = StagedChangeService._preview(TuneValue(name="x", value=values))
    py_via_diff = TuningPageDiffService._list_preview(values)
    assert py_via_staged == py_via_diff
    cpp = _tuner_core.tune_value_format_list_preview(values)
    assert cpp == py_via_staged
