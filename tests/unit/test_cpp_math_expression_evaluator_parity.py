"""Python ↔ C++ parity harness for tuner_core::math_expression_evaluator.

Pins the C++ evaluator against ``MathExpressionEvaluator.evaluate`` across
the arithmetic / shift / ternary / unary-minus grammar extensions plus the
full set of formula channels shipped in the production Speeduino DropBear
INI.
"""
from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser
from tuner.services.math_expression_evaluator import MathExpressionEvaluator


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


_py = MathExpressionEvaluator()
FIXTURE_INI = (
    Path(__file__).parent.parent / "fixtures" / "speeduino-dropbear-v2.0.1.ini"
)


def _run(expression, values, arrays=None):
    py = _py.evaluate(expression, values, arrays)
    cpp = _tuner_core.evaluate_math_expression(expression, values, arrays)
    return py, cpp


@pytest.mark.parametrize(
    "expression,values",
    [
        ("", {}),
        ("{}", {}),
        ("   ", {}),
        ("{ x }", {"x": 1.0}),
        ("coolantRaw - 40", {"coolantRaw": 90.0}),
        ("a + b + c", {"a": 1.0, "b": 2.0, "c": 3.0}),
        ("2 + 3 * 4", {}),
        ("(2 + 3) * 4", {}),
        ("100 / 4", {}),
        ("10 % 3", {}),
        ("10 / 0", {}),
        ("10 % 0", {}),
        ("-5", {}),
        ("-rpm", {"rpm": 3000.0}),
        ("-(2 + 3)", {}),
        ("+5", {}),
        ("1 << 3", {}),
        ("16 >> 2", {}),
        ("3.9 << 1", {}),
        ("halfSync + (sync << 1)", {"halfSync": 1.0, "sync": 1.0}),
        ("halfSync + (sync << 1)", {"halfSync": 0.0, "sync": 1.0}),
        ("twoStroke == 1 ? 1 : 2", {"twoStroke": 1.0}),
        ("twoStroke == 1 ? 1 : 2", {"twoStroke": 0.0}),
        ("rpm ? ( 60000.0 / rpm ) : 0", {"rpm": 6000.0}),
        ("rpm ? ( 60000.0 / rpm ) : 0", {"rpm": 0.0}),
        (
            "fuel2Algorithm == 0 ? map : fuel2Algorithm == 1 ? tps : 0",
            {"fuel2Algorithm": 1.0, "map": 90.0, "tps": 42.0},
        ),
        (
            "(ignAlgorithm == 0 || ignAlgorithm == 2) ? 511 : 100.0",
            {"ignAlgorithm": 0.0},
        ),
        (
            "(ignAlgorithm == 0 || ignAlgorithm == 2) ? 511 : 100.0",
            {"ignAlgorithm": 1.0},
        ),
        ("afr / stoich", {"afr": 14.7, "stoich": 14.7}),
        ("(coolantRaw - 40) * 1.8 + 32", {"coolantRaw": 90.0}),
        ("(map - baro) * 0.145038", {"map": 201.0, "baro": 101.0}),
        # Fail-safe
        ("((", {}),
        ("unknownChannel + 5", {}),
    ],
)
def test_evaluate_matches_python(expression, values):
    py, cpp = _run(expression, values)
    assert cpp == pytest.approx(py), f"{expression!r} cpp={cpp} py={py}"


@pytest.mark.parametrize(
    "expression,values,arrays",
    [
        (
            "arrayValue( array.boardFuelOutputs, pinLayout )",
            {"pinLayout": 2.0},
            {"boardFuelOutputs": [4.0, 8.0, 16.0]},
        ),
        (
            "arrayValue(array.boardFuelOutputs, 99)",
            {},
            {"boardFuelOutputs": [4.0, 8.0]},
        ),
        ("arrayValue(array.unknown, 0)", {}, {}),
        ("mysteryFn(1, 2)", {}, None),
    ],
)
def test_function_calls_match_python(expression, values, arrays):
    py, cpp = _run(expression, values, arrays)
    assert cpp == pytest.approx(py)


# ---------------------------------------------------------------------------
# Production INI parity — every formula channel parses + evaluates identically
# ---------------------------------------------------------------------------

def _production_snapshot():
    return {
        "coolantRaw": 90.0, "iatRaw": 60.0, "fuelTempRaw": 45.0,
        "timeNow": 12345.0, "secl": 67.0,
        "fuelPressure": 300.0, "oilPressure": 450.0,
        "tps": 42.0, "rpm": 3000.0, "twoStroke": 0.0, "nSquirts": 2.0,
        "pinLayout": 2.0, "nCylinders": 6.0,
        "stagingEnabled": 0.0, "pulseWidth": 5000.0, "pulseWidth3": 0.0,
        "boostCutFuel": 0.0, "boostCutSpark": 0.0,
        "afr": 13.5, "afrTarget": 14.7, "stoich": 14.7,
        "map": 95.0, "baro": 101.0, "loopsPerSecond": 4000.0,
        "reqFuel": 12.3, "battVCorMode": 0.0, "batCorrection": 100.0,
        "injOpen": 980.0, "ASECurr": 0.0, "multiplyMAP": 1.0, "vss": 50.0,
        "algorithm": 0.0, "ignAlgorithm": 0.0, "fuel2Algorithm": 0.0,
        "spark2Algorithm": 0.0, "spark2Mode": 0.0, "vvtLoadSource": 0.0,
        "wmiMode": 0.0, "iacAlgorithm": 0.0, "boostType": 0.0,
        "CLIdleTarget": 900.0, "halfSync": 1.0, "sync": 1.0,
        "enable_secondarySerial": 1.0, "secondarySerialProtocol": 2.0,
        "ignLoad": 0.0,
    }


def _production_arrays():
    return {
        "boardFuelOutputs": [4.0, 4.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0,
                             8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0],
        "boardIgnOutputs": [4.0, 4.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0,
                            8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0],
    }


def test_production_formula_channels_cpp_matches_python():
    d = IniParser().parse(FIXTURE_INI)
    values = _production_snapshot()
    arrays = _production_arrays()
    py_result = _py.compute_all(d.formula_output_channels, values, arrays)
    # C++ compute_all takes bound IniFormulaOutputChannel objects. The
    # Python and C++ FormulaOutputChannel shapes have identical data so we
    # evaluate each expression individually through the single-expression
    # entry point to keep the parity harness simple.
    working = dict(values)
    for f in d.formula_output_channels:
        cpp_val = _tuner_core.evaluate_math_expression(
            f.formula_expression, working, arrays
        )
        py_val = py_result[f.name]
        assert math.isfinite(cpp_val)
        assert cpp_val == pytest.approx(py_val), (
            f"{f.name}: cpp={cpp_val} py={py_val} expr={f.formula_expression!r}"
        )
        working[f.name] = cpp_val
