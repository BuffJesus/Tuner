"""Tests for MathExpressionEvaluator — the formula output channel evaluator.

Covers grammar extensions beyond ``VisibilityExpressionService``:

- arithmetic: ``+``, ``-``, ``*``, ``/``, ``%``
- unary ``-`` / ``+``
- bit-shifts: ``<<``, ``>>``
- C-style ternary ``? :``
- function calls: ``arrayValue(array.name, index)``
- multi-pass ``compute_all`` with cross-formula dependencies
- production-INI parity against the ~65 formula channels in the Speeduino
  DropBear INI
"""
from __future__ import annotations

from pathlib import Path

from tuner.domain.ecu_definition import FormulaOutputChannel
from tuner.parsers.ini_parser import IniParser
from tuner.services.math_expression_evaluator import MathExpressionEvaluator


FIXTURE_INI = (
    Path(__file__).parent.parent / "fixtures" / "speeduino-dropbear-v2.0.1.ini"
)


def _evaluate(expr: str, values=None, arrays=None) -> float:
    return MathExpressionEvaluator().evaluate(expr, values or {}, arrays)


# ---------------------------------------------------------------------------
# Boundaries and fail-safes
# ---------------------------------------------------------------------------

def test_empty_expression_returns_zero() -> None:
    assert _evaluate("") == 0.0
    assert _evaluate(None) == 0.0
    assert _evaluate("   ") == 0.0
    assert _evaluate("{}") == 0.0


def test_brace_stripping() -> None:
    assert _evaluate("{ 1 + 2 }") == 3.0


def test_parse_error_returns_zero() -> None:
    # Nonsense characters past the tokenizer still parse as "0" because
    # unknown identifiers fall back to 0 — exercise a real structural break.
    assert _evaluate("((") == 0.0


def test_unknown_identifier_is_zero() -> None:
    assert _evaluate("unknownChannel") == 0.0
    assert _evaluate("unknownChannel + 5") == 5.0


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------

def test_addition_and_subtraction() -> None:
    assert _evaluate("coolantRaw - 40", {"coolantRaw": 90}) == 50.0
    assert _evaluate("a + b + c", {"a": 1, "b": 2, "c": 3}) == 6.0


def test_multiplication_and_division() -> None:
    assert _evaluate("fuelPressure * 0.06894757", {"fuelPressure": 300}) == 300 * 0.06894757
    assert _evaluate("100 / 4") == 25.0


def test_modulo() -> None:
    assert _evaluate("10 % 3") == 1.0


def test_division_by_zero_is_zero() -> None:
    assert _evaluate("10 / 0") == 0.0
    assert _evaluate("10 % 0") == 0.0


def test_precedence_multiply_before_add() -> None:
    assert _evaluate("2 + 3 * 4") == 14.0


def test_parentheses_override_precedence() -> None:
    assert _evaluate("(2 + 3) * 4") == 20.0


def test_unary_minus() -> None:
    assert _evaluate("-5") == -5.0
    assert _evaluate("-rpm", {"rpm": 3000}) == -3000.0
    assert _evaluate("-(2 + 3)") == -5.0


def test_unary_plus() -> None:
    assert _evaluate("+5") == 5.0


# ---------------------------------------------------------------------------
# Bit-shift
# ---------------------------------------------------------------------------

def test_left_shift() -> None:
    assert _evaluate("1 << 3") == 8.0
    assert _evaluate("sync << 1", {"sync": 1}) == 2.0


def test_right_shift() -> None:
    assert _evaluate("16 >> 2") == 4.0


def test_shift_truncates_to_int_operands() -> None:
    # 3.9 should truncate to 3, then 3 << 1 = 6
    assert _evaluate("3.9 << 1") == 6.0


# ---------------------------------------------------------------------------
# Comparison / boolean (inherited from visibility grammar)
# ---------------------------------------------------------------------------

def test_equality() -> None:
    assert _evaluate("twoStroke == 1", {"twoStroke": 1}) == 1.0
    assert _evaluate("twoStroke == 1", {"twoStroke": 0}) == 0.0


def test_logical_and_or() -> None:
    assert _evaluate("boostCutFuel || boostCutSpark", {"boostCutFuel": 1, "boostCutSpark": 0}) == 1.0
    assert _evaluate("a && b", {"a": 1, "b": 0}) == 0.0


def test_logical_not() -> None:
    assert _evaluate("!x", {"x": 0}) == 1.0
    assert _evaluate("!x", {"x": 5}) == 0.0


# ---------------------------------------------------------------------------
# Ternary
# ---------------------------------------------------------------------------

def test_simple_ternary() -> None:
    assert _evaluate("twoStroke == 1 ? 1 : 2", {"twoStroke": 1}) == 1.0
    assert _evaluate("twoStroke == 1 ? 1 : 2", {"twoStroke": 0}) == 2.0


def test_ternary_with_rpm_guard() -> None:
    # revolutionTime = rpm ? ( 60000.0 / rpm ) : 0
    assert _evaluate("rpm ? ( 60000.0 / rpm) : 0", {"rpm": 6000}) == 10.0
    assert _evaluate("rpm ? ( 60000.0 / rpm) : 0", {"rpm": 0}) == 0.0


def test_nested_ternary_right_associative() -> None:
    # fuelLoad2 = fuel2Algorithm == 0 ? map : fuel2Algorithm == 1 ? tps : ...
    values = {"fuel2Algorithm": 1, "map": 90, "tps": 42}
    expr = "fuel2Algorithm == 0 ? map : fuel2Algorithm == 1 ? tps : 0"
    assert _evaluate(expr, values) == 42.0


def test_ternary_inside_parentheses() -> None:
    expr = "(ignAlgorithm == 0 || ignAlgorithm == 2) ? 511 : 100.0"
    assert _evaluate(expr, {"ignAlgorithm": 0}) == 511.0
    assert _evaluate(expr, {"ignAlgorithm": 1}) == 100.0


# ---------------------------------------------------------------------------
# arrayValue
# ---------------------------------------------------------------------------

def test_array_value_with_prefix() -> None:
    arrays = {"boardFuelOutputs": [4.0, 8.0, 8.0]}
    assert _evaluate("arrayValue(array.boardFuelOutputs, 0)", arrays=arrays) == 4.0
    assert _evaluate("arrayValue(array.boardFuelOutputs, 2)", arrays=arrays) == 8.0


def test_array_value_index_from_channel() -> None:
    arrays = {"boardFuelOutputs": [4.0, 8.0, 16.0]}
    values = {"pinLayout": 2.0}
    assert _evaluate(
        "arrayValue( array.boardFuelOutputs, pinLayout )",
        values=values,
        arrays=arrays,
    ) == 16.0


def test_array_value_out_of_range_is_zero() -> None:
    arrays = {"boardFuelOutputs": [4.0, 8.0]}
    assert _evaluate("arrayValue(array.boardFuelOutputs, 99)", arrays=arrays) == 0.0


def test_array_value_missing_array_is_zero() -> None:
    assert _evaluate("arrayValue(array.unknown, 0)", arrays={}) == 0.0


def test_unknown_function_returns_zero() -> None:
    assert _evaluate("mysteryFn(1, 2)") == 0.0


# ---------------------------------------------------------------------------
# compute_all — cross-formula dependency resolution
# ---------------------------------------------------------------------------

def test_compute_all_respects_declaration_order() -> None:
    formulas = [
        FormulaOutputChannel(name="revolutionTime", formula_expression="rpm ? ( 60000.0 / rpm) : 0"),
        FormulaOutputChannel(name="strokeMultipler", formula_expression="twoStroke == 1 ? 1 : 2"),
        FormulaOutputChannel(name="cycleTime", formula_expression="revolutionTime * strokeMultipler"),
    ]
    values = {"rpm": 6000, "twoStroke": 0}
    result = MathExpressionEvaluator().compute_all(formulas, values)
    assert result["revolutionTime"] == 10.0
    assert result["strokeMultipler"] == 2.0
    assert result["cycleTime"] == 20.0


def test_compute_all_does_not_mutate_input() -> None:
    formulas = [FormulaOutputChannel(name="x2", formula_expression="x * 2")]
    values = {"x": 5.0}
    MathExpressionEvaluator().compute_all(formulas, values)
    assert "x2" not in values


# ---------------------------------------------------------------------------
# Production INI parity — sanity-check every formula channel parses and
# evaluates without raising, against a synthetic channel snapshot.
# ---------------------------------------------------------------------------

def _production_channel_snapshot() -> dict[str, float]:
    """A plausible runtime snapshot big enough to feed every production
    formula. Any channel missing from here falls back to 0.0 via the
    evaluator's unknown-identifier rule, which is the correct runtime
    behaviour when the firmware doesn't publish a channel."""
    return {
        "coolantRaw": 90,
        "iatRaw": 60,
        "fuelTempRaw": 45,
        "timeNow": 12345.0,
        "secl": 67,
        "fuelPressure": 300,
        "oilPressure": 450,
        "tps": 42,
        "rpm": 3000,
        "twoStroke": 0,
        "nSquirts": 2,
        "pinLayout": 2,
        "nCylinders": 6,
        "stagingEnabled": 0,
        "pulseWidth": 5000,
        "pulseWidth3": 0,
        "boostCutFuel": 0,
        "boostCutSpark": 0,
        "afr": 13.5,
        "afrTarget": 14.7,
        "stoich": 14.7,
        "map": 95,
        "baro": 101,
        "loopsPerSecond": 4000,
        "reqFuel": 12.3,
        "battVCorMode": 0,
        "batCorrection": 100,
        "injOpen": 980,
        "ASECurr": 0,
        "multiplyMAP": 1,
        "vss": 50,
        "algorithm": 0,
        "ignAlgorithm": 0,
        "fuel2Algorithm": 0,
        "spark2Algorithm": 0,
        "spark2Mode": 0,
        "vvtLoadSource": 0,
        "wmiMode": 0,
        "iacAlgorithm": 0,
        "boostType": 0,
        "CLIdleTarget": 900,
        "halfSync": 1,
        "sync": 1,
        "enable_secondarySerial": 1,
        "secondarySerialProtocol": 2,
        "ignLoad": 0,
    }


def _production_arrays() -> dict[str, list[float]]:
    return {
        "boardFuelOutputs": [4, 4, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8],
        "boardIgnOutputs": [4, 4, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8],
    }


def test_production_formula_channels_all_evaluate_without_error() -> None:
    d = IniParser().parse(FIXTURE_INI)
    assert len(d.formula_output_channels) >= 30
    values = _production_channel_snapshot()
    arrays = _production_arrays()
    result = MathExpressionEvaluator().compute_all(
        d.formula_output_channels, values, arrays
    )
    # Every channel must have produced a finite numeric value.
    import math
    for name, v in result.items():
        assert isinstance(v, float), name
        assert math.isfinite(v), f"{name} = {v}"


def test_production_coolant_fahrenheit_conversion() -> None:
    """coolant = (coolantRaw - 40) * 1.8 + 32 — 90 raw → 50°C → 122°F."""
    d = IniParser().parse(FIXTURE_INI)
    by_name = {f.name: f for f in d.formula_output_channels}
    values = {"coolantRaw": 90}
    result = MathExpressionEvaluator().evaluate(by_name["coolant"].formula_expression, values)
    assert result == 122.0


def test_production_map_psi() -> None:
    """map_psi = (map - baro) * 0.145038."""
    d = IniParser().parse(FIXTURE_INI)
    by_name = {f.name: f for f in d.formula_output_channels}
    values = {"map": 201, "baro": 101}
    result = MathExpressionEvaluator().evaluate(by_name["map_psi"].formula_expression, values)
    assert result == (201 - 101) * 0.145038


def test_production_revolution_time_guard() -> None:
    d = IniParser().parse(FIXTURE_INI)
    by_name = {f.name: f for f in d.formula_output_channels}
    ev = MathExpressionEvaluator()
    assert ev.evaluate(by_name["revolutionTime"].formula_expression, {"rpm": 6000}) == 10.0
    assert ev.evaluate(by_name["revolutionTime"].formula_expression, {"rpm": 0}) == 0.0


def test_production_lambda() -> None:
    """lambda = afr / stoich."""
    d = IniParser().parse(FIXTURE_INI)
    by_name = {f.name: f for f in d.formula_output_channels}
    values = {"afr": 14.7, "stoich": 14.7}
    result = MathExpressionEvaluator().evaluate(by_name["lambda"].formula_expression, values)
    assert result == 1.0


def test_production_sync_status_uses_bitshift() -> None:
    """syncStatus = halfSync + (sync << 1)."""
    d = IniParser().parse(FIXTURE_INI)
    by_name = {f.name: f for f in d.formula_output_channels}
    expr = by_name["syncStatus"].formula_expression
    ev = MathExpressionEvaluator()
    assert ev.evaluate(expr, {"halfSync": 0, "sync": 0}) == 0.0
    assert ev.evaluate(expr, {"halfSync": 1, "sync": 0}) == 1.0
    assert ev.evaluate(expr, {"halfSync": 0, "sync": 1}) == 2.0
    assert ev.evaluate(expr, {"halfSync": 1, "sync": 1}) == 3.0


def test_production_map_vacboost_unary_minus() -> None:
    """map_vacboost = map < baro ? -map_inhg : map_psi."""
    d = IniParser().parse(FIXTURE_INI)
    ev = MathExpressionEvaluator()
    # In boost (map > baro): returns map_psi (positive PSI of boost)
    high = ev.compute_all(d.formula_output_channels, {"map": 200, "baro": 100})
    assert high["map_psi"] > 0
    assert high["map_vacboost"] == high["map_psi"]
    # In vacuum (map < baro): returns -map_inhg. map_inhg is positive in
    # vacuum, so the unary minus flips it negative — exercises unary minus
    # on an identifier.
    low = ev.compute_all(d.formula_output_channels, {"map": 50, "baro": 100})
    assert low["map_inhg"] > 0
    assert low["map_vacboost"] == -low["map_inhg"]
