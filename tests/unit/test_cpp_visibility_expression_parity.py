"""Python ↔ C++ parity harness for tuner_core::visibility_expression.

Pins the C++ evaluator against `VisibilityExpressionService.evaluate`
across the supported grammar (comparisons, logical and/or/not, parens,
arrayValue, dotted identifiers, fail-open). All cases are pure-logic
— no fixture INI required.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.services.visibility_expression_service import VisibilityExpressionService


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


_py = VisibilityExpressionService()


def _run(expression, values, arrays=None):
    py = _py.evaluate(expression, values, arrays)
    cpp = _tuner_core.evaluate_visibility_expression(expression, values, arrays)
    return py, cpp


@pytest.mark.parametrize(
    "expression,values",
    [
        ("", {}),
        ("{}", {}),
        ("   ", {}),
        ("{ x }", {"x": 1.0}),
        ("{ x }", {"x": 0.0}),
        ("fuelAlgorithm == 1", {"fuelAlgorithm": 1.0}),
        ("fuelAlgorithm == 1", {"fuelAlgorithm": 2.0}),
        ("rpm > 5000", {"rpm": 5500.0}),
        ("rpm > 5000", {"rpm": 4500.0}),
        ("rpm >= 5500", {"rpm": 5500.0}),
        ("rpm <= 5499", {"rpm": 5500.0}),
        ("a && b", {"a": 1.0, "b": 0.0}),
        ("a || b", {"a": 1.0, "b": 0.0}),
        ("a && b", {"a": 1.0, "b": 1.0}),
        ("!x", {"x": 0.0}),
        ("!!x", {"x": 1.0}),
        ("(a || c) && b", {"a": 1.0, "b": 1.0, "c": 0.0}),
        ("missing > 0", {}),
        ("missing == 0", {}),
        ("foo.bar.baz > 4", {"foo.bar.baz": 5.0}),
        ("3.14 > 3", {}),
        ("0.5 < 1", {}),
        # Mismatched grammar — should fail-open to True on both sides.
        ("x ==", {}),
        ("(((", {}),
        # Multi-clause realistic shape from production INI
        ("fuelAlgorithm == 1 && useDFCO == 1", {"fuelAlgorithm": 1.0, "useDFCO": 1.0}),
        ("fuelAlgorithm == 1 && useDFCO == 1", {"fuelAlgorithm": 1.0, "useDFCO": 0.0}),
        ("fuelAlgorithm == 1 || boostEnabled", {"fuelAlgorithm": 0.0, "boostEnabled": 1.0}),
        ("(fuelAlgorithm == 1) && (rpm < 6500)",
         {"fuelAlgorithm": 1.0, "rpm": 6000.0}),
    ],
)
def test_evaluate_matches_python(expression, values):
    py, cpp = _run(expression, values)
    assert cpp == py, f"{expression!r} cpp={cpp} py={py}"


@pytest.mark.parametrize(
    "expression,values,arrays,expected",
    [
        ("arrayValue(array.someArr, 1) == 20", {},
         {"someArr": [10.0, 20.0, 30.0]}, True),
        ("arrayValue(someArr, 2) > 25", {},
         {"someArr": [10.0, 20.0, 30.0]}, True),
        ("arrayValue(someArr, 99)", {},
         {"someArr": [10.0, 20.0, 30.0]}, False),
        # No arrays map ⇒ arrayValue → 0
        ("arrayValue(array.x, 0)", {}, None, False),
        ("arrayValue(array.x, 0) == 0", {}, None, True),
        # Unknown function fail-safe
        ("unknownFn(1, 2, 3) > 0", {}, None, False),
        ("unknownFn(1, 2, 3) == 0", {}, None, True),
    ],
)
def test_function_calls_match_python(expression, values, arrays, expected):
    py, cpp = _run(expression, values, arrays)
    assert cpp == py == expected
