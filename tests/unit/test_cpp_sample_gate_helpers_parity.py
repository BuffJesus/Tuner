"""Python ↔ C++ parity harness for tuner_core::sample_gate_helpers.

Pins the C++ helpers against the Python module-level functions in
`tuner.services.replay_sample_gate_service` and the
`_normalise_operator` / `_apply_operator` helpers in
`tuner.services.autotune_filter_gate_evaluator`. All cases are pure
logic — no fixture INI required.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.services.autotune_filter_gate_evaluator import (
    _apply_operator as _py_apply_operator,
    _normalise_operator as _py_normalise_operator,
)
from tuner.services.replay_sample_gate_service import (
    _afr_value as _py_afr_value,
    _lambda_value as _py_lambda_value,
    _resolve_channel as _py_resolve_channel,
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
    reason="tuner_core C++ extension not built — see cpp/README.md.",
)


def _items(d: dict[str, float]) -> list[tuple[str, float]]:
    """Convert a Python dict to the (key, value) list the C++ binding expects.

    Python 3.7+ dicts preserve insertion order; we forward that order
    explicitly to the C++ side so the resolver matches the Python
    `for key, value in values.items()` iteration.
    """
    return list(d.items())


# ---------------------------------------------------------------------------
# normalise_operator / apply_operator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "op", ["=", "==", "!=", "<", ">", "<=", ">=", "&", " < ", "  ==  "],
)
def test_normalise_operator_matches_python(op: str) -> None:
    cpp = _tuner_core.sample_gate_normalise_operator(op)
    py = _py_normalise_operator(op)
    assert cpp == py


@pytest.mark.parametrize(
    "value,op,threshold",
    [
        (5.0, "<", 10.0),
        (10.0, "<", 10.0),
        (10.0, ">", 5.0),
        (5.0, "<=", 5.0),
        (5.0, ">=", 5.0),
        (5.0, "==", 5.0),
        (5.0, "==", 5.1),
        (5.0, "!=", 6.0),
        (5.0, "=", 5.0),
        (0x12, "&", 0x10),
        (0x10, "&", 0x01),
        (1.0, "??", 2.0),
        (-1.0, "<", 0.0),
    ],
)
def test_apply_operator_matches_python(value, op, threshold):
    cpp = _tuner_core.sample_gate_apply_operator(value, op, threshold)
    py = _py_apply_operator(value, op, threshold)
    assert cpp == py


# ---------------------------------------------------------------------------
# resolve_channel
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,values",
    [
        ("rpm", {"rpm": 5500.0, "clt": 90.0}),
        ("coolant", {"clt": 90.0}),
        ("coolant", {"coolantTemp": 90.0}),
        ("ego", {"egoCorrection": 1.05}),
        ("ego", {"afr1": 14.7}),       # ego falls back to afr substring
        ("load", {"mapKpa": 100.0}),
        ("missing", {"rpm": 5500.0}),
        ("rpm", {}),
        # First match wins (insertion order)
        ("map", {"map1": 100.0, "map2": 200.0}),
        # Bare name not in alias table — falls back to lowercased name
        ("custom", {"customStuff": 42.0}),
    ],
)
def test_resolve_channel_matches_python(name, values):
    cpp = _tuner_core.sample_gate_resolve_channel(name, _items(values))
    py = _py_resolve_channel(name, values)
    assert cpp == py


# ---------------------------------------------------------------------------
# lambda_value / afr_value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "values",
    [
        {"lambda1": 1.05},
        {"afr1": 14.7},
        {"egoCorrection": 1.0},
        {"lambda": 1.0, "afr": 14.7},  # lambda preferred
        {"afr": 14.7, "lambda": 1.0},  # lambda still preferred (substring scan)
        {},
        {"rpm": 5500.0},                # nothing matches → None
    ],
)
def test_lambda_value_matches_python(values):
    cpp = _tuner_core.sample_gate_lambda_value(_items(values))
    py = _py_lambda_value(values)
    if py is None:
        assert cpp is None
    else:
        assert cpp == pytest.approx(py)


@pytest.mark.parametrize(
    "values",
    [
        {"afr1": 14.7},
        {"lambda": 1.0},
        {"lambda": 1.0, "afr1": 14.7},  # lambda comes first → ×14.7 path
        {"afr1": 12.5, "lambda": 0.85},  # afr first → returned directly
        {},
        {"rpm": 5500.0},
    ],
)
def test_afr_value_matches_python(values):
    cpp = _tuner_core.sample_gate_afr_value(_items(values))
    py = _py_afr_value(values)
    if py is None:
        assert cpp is None
    else:
        assert cpp == pytest.approx(py)
