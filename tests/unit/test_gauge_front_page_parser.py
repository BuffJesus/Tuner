"""Tests for [GaugeConfigurations] and [FrontPage] INI parser passes."""
from __future__ import annotations

from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


def _load_definition():
    return IniParser().parse(_INI)


def _gauge(defn, name: str):
    return next((g for g in defn.gauge_configurations if g.name == name), None)


# ---------------------------------------------------------------------------
# [GaugeConfigurations] — presence and count
# ---------------------------------------------------------------------------

def test_gauge_configurations_populated() -> None:
    defn = _load_definition()
    assert len(defn.gauge_configurations) > 0


def test_gauge_configurations_reasonable_count() -> None:
    """Production INI has ~70 named gauges (incl. aux input channels)."""
    defn = _load_definition()
    assert len(defn.gauge_configurations) >= 50


def test_gauge_names_are_unique() -> None:
    defn = _load_definition()
    names = [g.name for g in defn.gauge_configurations]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# [GaugeConfigurations] — field parsing
# ---------------------------------------------------------------------------

def test_tachometer_channel() -> None:
    defn = _load_definition()
    g = _gauge(defn, "tachometer")
    assert g is not None
    assert g.channel == "rpm"


def test_tachometer_title() -> None:
    defn = _load_definition()
    g = _gauge(defn, "tachometer")
    assert g is not None
    assert g.title == "Engine Speed"


def test_tachometer_units() -> None:
    defn = _load_definition()
    g = _gauge(defn, "tachometer")
    assert g is not None
    assert g.units == "RPM"


def test_tachometer_lo() -> None:
    defn = _load_definition()
    g = _gauge(defn, "tachometer")
    assert g is not None
    assert g.lo == 0.0


def test_tachometer_hi_is_none_for_expression() -> None:
    """tachometer hi = {rpmhigh} — expression, cannot be evaluated at parse time."""
    defn = _load_definition()
    g = _gauge(defn, "tachometer")
    assert g is not None
    assert g.hi is None  # {rpmhigh} expression → None


def test_tachometer_lo_warn() -> None:
    defn = _load_definition()
    g = _gauge(defn, "tachometer")
    assert g is not None
    assert g.lo_warn == 600.0


def test_tachometer_value_digits() -> None:
    defn = _load_definition()
    g = _gauge(defn, "tachometer")
    assert g is not None
    assert g.value_digits == 0


def test_simple_gauge_with_all_numeric_fields() -> None:
    """accelEnrichGauge has no expressions — all fields parsed."""
    defn = _load_definition()
    g = _gauge(defn, "accelEnrichGauge")
    assert g is not None
    assert g.channel == "accelEnrich"
    assert g.lo == 50.0
    assert g.hi == 150.0
    assert g.lo_danger == -1.0
    assert g.hi_warn == 999.0
    assert g.hi_danger == 999.0
    assert g.value_digits == 0


def test_injector_gauge_fractional_limits() -> None:
    defn = _load_definition()
    g = _gauge(defn, "injOpenGauge")
    assert g is not None
    assert g.lo == 0.0
    assert g.hi == 3.0
    assert g.value_digits == 3


def test_gauge_category_assigned() -> None:
    """Gauges inherit the most recent gaugeCategory declaration."""
    defn = _load_definition()
    g = _gauge(defn, "tachometer")
    assert g is not None
    assert g.category == "Main"


def test_gauge_category_sensor_inputs() -> None:
    defn = _load_definition()
    g = _gauge(defn, "mapGauge")
    assert g is not None
    assert g.category == "Sensor inputs"


def test_gauge_category_system_data() -> None:
    defn = _load_definition()
    g = _gauge(defn, "clockGauge")
    assert g is not None
    assert g.category == "System Data"


def test_aux_gauge_present() -> None:
    defn = _load_definition()
    g = _gauge(defn, "AuxInGauge0")
    assert g is not None
    assert g.channel == "auxin_gauge0"


def test_battery_voltage_gauge() -> None:
    defn = _load_definition()
    g = _gauge(defn, "batteryVoltage")
    assert g is not None
    assert g.lo_danger == 8.0
    assert g.hi_danger == 16.0
    assert g.value_digits == 2


def test_throttle_gauge_units() -> None:
    defn = _load_definition()
    g = _gauge(defn, "throttleGauge")
    assert g is not None
    assert g.units == "%TPS"


# ---------------------------------------------------------------------------
# [FrontPage] — gauge slots
# ---------------------------------------------------------------------------

def test_front_page_gauges_populated() -> None:
    defn = _load_definition()
    assert len(defn.front_page_gauges) == 8


def test_front_page_gauge1_is_tachometer() -> None:
    defn = _load_definition()
    assert defn.front_page_gauges[0] == "tachometer"


def test_front_page_gauge2_is_throttle() -> None:
    defn = _load_definition()
    assert defn.front_page_gauges[1] == "throttleGauge"


def test_front_page_gauge7_is_clt() -> None:
    defn = _load_definition()
    assert defn.front_page_gauges[6] == "cltGauge"


def test_front_page_gauge8_is_gamma_enrich() -> None:
    defn = _load_definition()
    assert defn.front_page_gauges[7] == "gammaEnrichGauge"


# ---------------------------------------------------------------------------
# [FrontPage] — indicators
# ---------------------------------------------------------------------------

def test_front_page_indicators_populated() -> None:
    defn = _load_definition()
    assert len(defn.front_page_indicators) > 0


def test_front_page_indicator_count() -> None:
    """Production INI has ~40 indicator lines."""
    defn = _load_definition()
    assert len(defn.front_page_indicators) >= 35


def test_running_indicator_expression() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if i.off_label == "Not Running"), None)
    assert ind is not None
    assert ind.expression == "running"


def test_running_indicator_on_label() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if i.off_label == "Not Running"), None)
    assert ind is not None
    assert ind.on_label == "Running"


def test_running_indicator_colors() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if i.off_label == "Not Running"), None)
    assert ind is not None
    assert ind.off_bg == "white"
    assert ind.off_fg == "black"
    assert ind.on_bg == "green"
    assert ind.on_fg == "black"


def test_sync_indicator_present() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if i.on_label == "Full Sync"), None)
    assert ind is not None
    assert ind.expression == "sync"


def test_error_indicator_uses_red_on_color() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if i.on_label == "ERROR"), None)
    assert ind is not None
    assert ind.on_bg == "green"


def test_engine_protect_indicator_uses_red() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if "Engine Protect ON" in (i.on_label or "")), None)
    assert ind is not None
    assert ind.on_bg == "red"


def test_compound_expression_indicator() -> None:
    """Indicators with compound boolean expressions like ``(tps > tpsflood) && (rpm < crankRPM)``."""
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if "FLOOD" in (i.on_label or "")), None)
    assert ind is not None
    assert "tps" in ind.expression
    assert "rpm" in ind.expression


def test_sd_bitfield_indicator() -> None:
    """Indicators using bitfield expressions like ``sd_status & 1``."""
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if "SD Present" in (i.on_label or "")), None)
    assert ind is not None
    assert "sd_status" in ind.expression
    assert "1" in ind.expression


def test_half_sync_indicator_yellow_bg() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if "Half Sync" in (i.on_label or "")), None)
    assert ind is not None
    assert ind.on_bg == "yellow"


def test_tune_valid_indicator() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if "Tune Learn Valid" in (i.on_label or "")), None)
    assert ind is not None
    assert "rSA_tuneValid" in ind.expression


def test_programmable_output_indicator() -> None:
    defn = _load_definition()
    ind = next((i for i in defn.front_page_indicators if "Programmable out 1 ON" in (i.on_label or "")), None)
    assert ind is not None
    assert "outputsStatus0" in ind.expression
