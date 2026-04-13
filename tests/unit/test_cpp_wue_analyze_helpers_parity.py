"""Python ↔ C++ parity harness for tuner_core::wue_analyze_helpers."""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

import pytest

from tuner.services.wue_analyze_service import (
    _AFR_UNIT_MIN,
    _STOICH_AFR,
    _clt_from_record,
    _confidence,
    _is_clt_axis,
    _nearest_index,
    _numeric_axis,
    _parse_cell_float,
    _target_lambda_from_table,
)


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


def _items(d):
    return list(d.items())


# ---------------------------------------------------------------------------
# confidence_label
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 2, 3, 5, 9, 10, 15, 29, 30, 100, 9999])
def test_confidence_label_matches_python(n):
    assert _tuner_core.wue_confidence_label(n) == _confidence(n)


# ---------------------------------------------------------------------------
# is_clt_axis
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "clt", "Coolant", "warmupTemp", "wueBins", "ColdEnrich",
        "intakeTemp", "rpm", "map", "", "RPM",
    ],
)
def test_is_clt_axis_matches_python(name):
    cpp = _tuner_core.wue_is_clt_axis(name)
    py = _is_clt_axis(name if name else None)
    assert cpp == py


# ---------------------------------------------------------------------------
# clt_from_record
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "values",
    [
        {"rpm": 5500.0, "clt": 90.0},
        {"coolantTemp": 75.0},
        {"rpm": 5500.0},
        {},
        {"clt": 60.0, "coolantTemp": 100.0},  # first match wins
    ],
)
def test_clt_from_record_matches_python(values):
    cpp = _tuner_core.wue_clt_from_record(_items(values))
    py = _clt_from_record(values)
    assert cpp == py


# ---------------------------------------------------------------------------
# nearest_index
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "axis,value",
    [
        ([-40, -20, 0, 20, 40, 60, 80], -50),
        ([-40, -20, 0, 20, 40, 60, 80], 0),
        ([-40, -20, 0, 20, 40, 60, 80], 30),    # tie → earlier index
        ([-40, -20, 0, 20, 40, 60, 80], 19),
        ([-40, -20, 0, 20, 40, 60, 80], 1000),
        ([42.0], 0.0),
        ([1, 2, 3, 4, 5], 3.5),                 # tie → earlier index
    ],
)
def test_nearest_index_matches_python(axis, value):
    cpp = _tuner_core.wue_nearest_index(list(map(float, axis)), float(value))
    py = _nearest_index(tuple(axis), float(value))
    assert cpp == py


def test_nearest_index_random_matches_python():
    rng = random.Random(0xC0DE)
    for _ in range(50):
        axis = sorted([rng.uniform(-100, 200) for _ in range(8)])
        value = rng.uniform(-150, 250)
        assert _tuner_core.wue_nearest_index(axis, value) == _nearest_index(
            tuple(axis), value
        )


# ---------------------------------------------------------------------------
# numeric_axis
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "labels",
    [
        ["-40", "0", "40", "80"],
        ["1.5", "2.5", "3.5"],
        ["0", "20", "not-a-number"],   # → empty
        [],
        ["1"],
    ],
)
def test_numeric_axis_matches_python(labels):
    cpp = list(_tuner_core.wue_numeric_axis(labels))
    py = list(_numeric_axis(tuple(labels)))
    assert cpp == py


# ---------------------------------------------------------------------------
# parse_cell_float
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cell", ["3.14", "0", "-1.5", "", "nope", None, "1e6"],
)
def test_parse_cell_float_matches_python(cell):
    cpp = _tuner_core.wue_parse_cell_float(cell)
    py = _parse_cell_float(cell)
    if py is None:
        assert cpp is None
    else:
        assert cpp == pytest.approx(py)


# ---------------------------------------------------------------------------
# target_lambda_from_cell
# ---------------------------------------------------------------------------

# Python's `_target_lambda_from_table` operates on a TablePageSnapshot;
# we re-implement its scalar/cell branch here so the parity test stays
# free of TablePageSnapshot construction.
def _py_target_lambda_from_cell(raw, fallback):
    if raw is None or raw <= 0:
        return fallback
    if raw > _AFR_UNIT_MIN:
        return raw / _STOICH_AFR
    return raw


@pytest.mark.parametrize(
    "raw,fallback",
    [
        (14.7, 1.0),
        (12.5, 1.0),
        (0.85, 1.0),
        (1.05, 1.0),
        (0.0, 1.0),
        (-1.0, 0.95),
        (2.0, 1.0),    # boundary
        (2.5, 1.0),    # just above AFR_UNIT_MIN
    ],
)
def test_target_lambda_from_cell_matches_python(raw, fallback):
    cpp = _tuner_core.wue_target_lambda_from_cell(raw, fallback)
    py = _py_target_lambda_from_cell(raw, fallback)
    assert cpp == pytest.approx(py)
