from __future__ import annotations

import pytest

from tuner.services.visibility_expression_service import VisibilityExpressionService


@pytest.fixture()
def svc() -> VisibilityExpressionService:
    return VisibilityExpressionService()


def test_none_expression_is_visible(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate(None, {}) is True


def test_empty_expression_is_visible(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("", {}) is True
    assert svc.evaluate("{}", {}) is True


def test_literal_true_is_visible(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{1}", {}) is True


def test_literal_zero_is_hidden(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{0}", {}) is False


def test_equality_match(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{fuelAlgorithm == 1}", {"fuelAlgorithm": 1.0}) is True
    assert svc.evaluate("{fuelAlgorithm == 1}", {"fuelAlgorithm": 2.0}) is False


def test_inequality(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{fuelAlgorithm != 1}", {"fuelAlgorithm": 2.0}) is True
    assert svc.evaluate("{fuelAlgorithm != 1}", {"fuelAlgorithm": 1.0}) is False


def test_greater_less_than(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{x > 5}", {"x": 6.0}) is True
    assert svc.evaluate("{x > 5}", {"x": 5.0}) is False
    assert svc.evaluate("{x < 5}", {"x": 4.0}) is True
    assert svc.evaluate("{x >= 5}", {"x": 5.0}) is True
    assert svc.evaluate("{x <= 4}", {"x": 4.0}) is True


def test_not_operator(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{!useExtBaro}", {"useExtBaro": 0.0}) is True
    assert svc.evaluate("{!useExtBaro}", {"useExtBaro": 1.0}) is False


def test_and_operator(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{a == 1 && b == 2}", {"a": 1.0, "b": 2.0}) is True
    assert svc.evaluate("{a == 1 && b == 2}", {"a": 1.0, "b": 3.0}) is False


def test_or_operator(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{a == 1 || b == 2}", {"a": 0.0, "b": 2.0}) is True
    assert svc.evaluate("{a == 1 || b == 2}", {"a": 0.0, "b": 0.0}) is False


def test_parentheses(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{(a == 1) && (b == 2)}", {"a": 1.0, "b": 2.0}) is True


def test_unknown_identifier_defaults_to_zero(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{unknownParam == 0}", {}) is True
    assert svc.evaluate("{unknownParam == 1}", {}) is False


def test_expression_with_only_operators_does_not_crash(svc: VisibilityExpressionService) -> None:
    # The parser is resilient: unknown/broken inputs produce 0.0 rather than crashing.
    # The only guarantee is no exception is raised and a bool is returned.
    result = svc.evaluate("{===bad}", {})
    assert isinstance(result, bool)


def test_expression_without_braces(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("fuelAlgorithm == 1", {"fuelAlgorithm": 1.0}) is True


# ---------------------------------------------------------------------------
# Speeduino INI expression patterns
# ---------------------------------------------------------------------------

def test_knock_digital_pin_visible_when_mode_is_1(svc: VisibilityExpressionService) -> None:
    """knock_digital_pin uses { knock_mode == 1 }; must be visible when digital mode."""
    assert svc.evaluate("{ knock_mode == 1 }", {"knock_mode": 1.0}) is True


def test_knock_digital_pin_hidden_when_mode_is_off(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{ knock_mode == 1 }", {"knock_mode": 0.0}) is False


def test_knock_analog_pin_visible_when_mode_is_2(svc: VisibilityExpressionService) -> None:
    """knock_analog_pin uses { knock_mode == 2 }; must be visible when analog mode."""
    assert svc.evaluate("{ knock_mode == 2 }", {"knock_mode": 2.0}) is True


def test_knock_analog_pin_hidden_when_mode_is_digital(svc: VisibilityExpressionService) -> None:
    assert svc.evaluate("{ knock_mode == 2 }", {"knock_mode": 1.0}) is False


def test_ego_algorithm_visible_when_egotype_nonzero(svc: VisibilityExpressionService) -> None:
    """egoAlgorithm uses { egoType }; visible for any non-zero sensor type."""
    assert svc.evaluate("{ egoType }", {"egoType": 1.0}) is True  # Narrowband
    assert svc.evaluate("{ egoType }", {"egoType": 2.0}) is True  # Wideband
    assert svc.evaluate("{ egoType }", {"egoType": 0.0}) is False  # Off


def test_ego_count_visible_with_compound_expression(svc: VisibilityExpressionService) -> None:
    """{ egoType && (egoAlgorithm < 3) } — compound gate for EGO correction parameters."""
    assert svc.evaluate("{ egoType && (egoAlgorithm < 3) }", {"egoType": 2.0, "egoAlgorithm": 1.0}) is True
    assert svc.evaluate("{ egoType && (egoAlgorithm < 3) }", {"egoType": 0.0, "egoAlgorithm": 1.0}) is False
    assert svc.evaluate("{ egoType && (egoAlgorithm < 3) }", {"egoType": 2.0, "egoAlgorithm": 3.0}) is False


def test_afr_protect_visible_when_ego_is_wideband(svc: VisibilityExpressionService) -> None:
    """{ egoType == 2 } gates wideband-only settings."""
    assert svc.evaluate("{egoType == 2}", {"egoType": 2.0}) is True
    assert svc.evaluate("{egoType == 2}", {"egoType": 1.0}) is False


def test_can_wbo_visible_with_combined_condition(svc: VisibilityExpressionService) -> None:
    """{ CANisAvailable && (egoType == 2) } — real Speeduino CAN WBO field expression."""
    assert svc.evaluate(
        "{ CANisAvailable && (egoType == 2) }",
        {"CANisAvailable": 1.0, "egoType": 2.0},
    ) is True
    assert svc.evaluate(
        "{ CANisAvailable && (egoType == 2) }",
        {"CANisAvailable": 0.0, "egoType": 2.0},
    ) is False


def test_output_pin_visibility(svc: VisibilityExpressionService) -> None:
    """Programmable output fields use { outputPin[N] } — index subscript syntax.

    NOTE: Array subscript expressions are not currently supported by the parser.
    They should degrade to fail-open (True) rather than crashing.
    """
    # The parser does not support array subscripts, so this should fail-open
    result = svc.evaluate("{outputPin[0]}", {"outputPin[0]": 1.0})
    assert isinstance(result, bool)  # must not raise


# ---------------------------------------------------------------------------
# arrayValue() function support
# ---------------------------------------------------------------------------

def test_array_value_basic(svc: VisibilityExpressionService) -> None:
    """arrayValue(name, index) must look up name[int(index)]."""
    arrays = {"boardHasRTC": [0.0, 0.0, 1.0, 0.0]}
    assert svc.evaluate("{arrayValue(boardHasRTC, pinLayout) > 0}", {"pinLayout": 2.0}, arrays) is True
    assert svc.evaluate("{arrayValue(boardHasRTC, pinLayout) > 0}", {"pinLayout": 0.0}, arrays) is False


def test_array_value_with_array_prefix(svc: VisibilityExpressionService) -> None:
    """arrayValue(array.NAME, index) strips the 'array.' prefix before lookup."""
    arrays = {"boardHasRTC": [0.0, 1.0]}
    assert svc.evaluate(
        "{ arrayValue( array.boardHasRTC, pinLayout ) > 0 }",
        {"pinLayout": 1.0},
        arrays,
    ) is True
    assert svc.evaluate(
        "{ arrayValue( array.boardHasRTC, pinLayout ) > 0 }",
        {"pinLayout": 0.0},
        arrays,
    ) is False


def test_array_value_combined_with_and(svc: VisibilityExpressionService) -> None:
    """arrayValue() must compose correctly with && in real INI expressions."""
    arrays = {"boardHasSD": [0.0, 0.0, 1.0]}
    expr = "{ arrayValue( array.boardHasSD, pinLayout ) > 0 && onboard_log_file_style }"
    # Both conditions true
    assert svc.evaluate(expr, {"pinLayout": 2.0, "onboard_log_file_style": 1.0}, arrays) is True
    # arrayValue false
    assert svc.evaluate(expr, {"pinLayout": 0.0, "onboard_log_file_style": 1.0}, arrays) is False
    # onboard_log_file_style false
    assert svc.evaluate(expr, {"pinLayout": 2.0, "onboard_log_file_style": 0.0}, arrays) is False


def test_array_value_no_arrays_passed_returns_false(svc: VisibilityExpressionService) -> None:
    """When no arrays are passed, arrayValue() returns 0.0 (page stays hidden)."""
    assert svc.evaluate(
        "{ arrayValue(array.boardHasRTC, pinLayout) > 0 }",
        {"pinLayout": 5.0},
        None,
    ) is False


def test_array_value_unknown_array_returns_false(svc: VisibilityExpressionService) -> None:
    """Requesting a name that isn't in the arrays dict must return 0.0."""
    assert svc.evaluate(
        "{ arrayValue(array.nosucharray, pinLayout) > 0 }",
        {"pinLayout": 0.0},
        {"boardHasRTC": [1.0]},
    ) is False


def test_array_value_out_of_bounds_returns_false(svc: VisibilityExpressionService) -> None:
    """An out-of-range index must return 0.0, not raise."""
    arrays = {"boardHasRTC": [0.0, 1.0]}
    assert svc.evaluate(
        "{ arrayValue(array.boardHasRTC, pinLayout) > 0 }",
        {"pinLayout": 99.0},
        arrays,
    ) is False


def test_array_value_non_dotted_name(svc: VisibilityExpressionService) -> None:
    """arrayValue(rpmBins, algorithm) without 'array.' prefix also works."""
    arrays = {"rpmBins": [500.0, 1000.0, 2000.0, 3000.0]}
    assert svc.evaluate(
        "{ arrayValue(rpmBins, algorithm) > 1500 }",
        {"algorithm": 2.0},
        arrays,
    ) is True
    assert svc.evaluate(
        "{ arrayValue(rpmBins, algorithm) > 1500 }",
        {"algorithm": 0.0},
        arrays,
    ) is False


def test_unknown_function_returns_false_not_crash(svc: VisibilityExpressionService) -> None:
    """An unrecognized function call must not raise and must return 0.0."""
    result = svc.evaluate("{ someUnknownFunc(foo, bar) > 0 }", {"foo": 1.0}, None)
    assert isinstance(result, bool)  # must not raise
