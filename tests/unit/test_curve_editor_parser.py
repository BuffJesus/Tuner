"""Tests for [CurveEditor] INI parser pass → CurveDefinition domain model."""
from __future__ import annotations

from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_INI = _FIXTURES / "speeduino-dropbear-v2.0.1-u16p2-experimental.ini"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_definition():
    return IniParser().parse(_INI)


def _curve(defn, name: str):
    return next((c for c in defn.curve_definitions if c.name == name), None)


# ---------------------------------------------------------------------------
# Presence and count
# ---------------------------------------------------------------------------

def test_curve_definitions_are_populated() -> None:
    defn = _load_definition()
    assert len(defn.curve_definitions) > 0


def test_production_ini_has_expected_curve_count() -> None:
    """Production INI has 34 curve definitions."""
    # The experimental INI should have the same count as production.
    defn = _load_definition()
    assert len(defn.curve_definitions) >= 30


# ---------------------------------------------------------------------------
# Basic field parsing
# ---------------------------------------------------------------------------

def test_warmup_curve_has_correct_fields() -> None:
    defn = _load_definition()
    curve = _curve(defn, "warmup_curve")
    assert curve is not None
    assert curve.title == "Warmup Enrichment (WUE) Curve"
    assert curve.x_label == "Coolant"
    assert curve.y_label == "WUE %"


def test_warmup_curve_x_bins() -> None:
    defn = _load_definition()
    curve = _curve(defn, "warmup_curve")
    assert curve.x_bins_param == "wueBins"
    assert curve.x_channel == "coolant"


def test_warmup_curve_y_bins() -> None:
    defn = _load_definition()
    curve = _curve(defn, "warmup_curve")
    assert len(curve.y_bins_list) == 1
    assert curve.y_bins_list[0].param == "wueRates"


def test_warmup_curve_axes() -> None:
    defn = _load_definition()
    curve = _curve(defn, "warmup_curve")
    assert curve.x_axis is not None
    assert curve.x_axis.min == pytest.approx(-40.0)
    assert curve.x_axis.max == pytest.approx(210.0)
    assert curve.y_axis is not None
    assert curve.y_axis.min == pytest.approx(0.0)
    assert curve.y_axis.max == pytest.approx(240.0)


def test_warmup_curve_gauge_reference() -> None:
    defn = _load_definition()
    curve = _curve(defn, "warmup_curve")
    assert curve.gauge == "cltGauge"


def test_dwell_curve_no_output_channel_on_y() -> None:
    """y-axis bins have no channel — they are just the editable parameter."""
    defn = _load_definition()
    curve = _curve(defn, "dwell_correction_curve")
    assert curve is not None
    assert len(curve.y_bins_list) == 1
    assert curve.y_bins_list[0].param == "dwellRates"


def test_dwell_curve_battery_channel_on_x() -> None:
    defn = _load_definition()
    curve = _curve(defn, "dwell_correction_curve")
    assert curve.x_bins_param == "brvBins"
    assert curve.x_channel == "batteryVoltage"


def test_curve_with_topic_help() -> None:
    defn = _load_definition()
    curve = _curve(defn, "baroFuel_curve")
    assert curve is not None
    assert curve.topic_help is not None
    assert "speeduino.com" in curve.topic_help


def test_curve_with_size_hint() -> None:
    defn = _load_definition()
    curve = _curve(defn, "flex_fuel_curve")
    assert curve is not None
    assert curve.size == (400, 200)


def test_idle_advance_curve_size() -> None:
    defn = _load_definition()
    curve = _curve(defn, "idle_advance_curve")
    assert curve is not None
    assert curve.size == (450, 200)


# ---------------------------------------------------------------------------
# Multi-line curve (two yBins + lineLabels)
# ---------------------------------------------------------------------------

def test_warmup_analyzer_curve_has_two_y_bins() -> None:
    """warmup_analyzer_curve has two yBins (current WUE + recommended WUE)."""
    defn = _load_definition()
    curve = _curve(defn, "warmup_analyzer_curve")
    assert curve is not None
    assert len(curve.y_bins_list) == 2
    assert curve.y_bins_list[0].param == "wueRates"
    assert curve.y_bins_list[1].param == "wueRecommended"


def test_warmup_analyzer_curve_line_labels() -> None:
    defn = _load_definition()
    curve = _curve(defn, "warmup_analyzer_curve")
    labels = [yb.label for yb in curve.y_bins_list]
    assert "Current WUE" in labels
    assert "Recommended WUE" in labels


# ---------------------------------------------------------------------------
# Curve with no live output channel on x-axis
# ---------------------------------------------------------------------------

def test_rolling_prot_curve_x_bins_no_channel() -> None:
    """Some curves have xBins with only the parameter name (no output channel)."""
    defn = _load_definition()
    curve = _curve(defn, "rolling_prot_curve")
    assert curve is not None
    assert curve.x_bins_param == "rollingProtRPMDelta"
    assert curve.x_channel is None


# ---------------------------------------------------------------------------
# Specific curves that must be present
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "time_accel_tpsdot_curve",
    "time_accel_mapdot_curve",
    "dwell_correction_curve",
    "injector_voltage_curve",
    "injector_timing_curve",
    "airdensity_curve",
    "baroFuel_curve",
    "fuelTemp_curve",
    "iat_retard_curve",
    "clt_advance_curve",
    "idle_advance_curve",
    "pwm_fan_curve",
    "warmup_curve",
    "cranking_enrich_curve",
    "priming_pw_curve",
    "afterstart_enrichment_curve",
    "afterstart_enrichment_time",
    "flex_fuel_curve",
    "flex_adv_curve",
    "flex_boost_curve",
    "iacPwm_curve",
    "iacClosedLoop_curve",
    "warmup_analyzer_curve",
])
def test_expected_curve_is_present(name: str) -> None:
    defn = _load_definition()
    assert _curve(defn, name) is not None, f"Curve '{name}' not found in parsed definition"
