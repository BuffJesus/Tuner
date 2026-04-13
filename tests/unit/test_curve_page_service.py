"""Tests for CurvePageService — compiles CurveDefinitions into TuningPage objects."""
from __future__ import annotations

from pathlib import Path

from tuner.domain.tuning_pages import TuningPageKind, TuningPageParameterRole
from tuner.parsers.ini_parser import IniParser
from tuner.services.curve_page_service import CurvePageService

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_INI = _FIXTURES / "speeduino-dropbear-v2.0.1-u16p2-experimental.ini"


def _load():
    defn = IniParser().parse(_INI)
    service = CurvePageService()
    groups = service.build_curve_pages(defn)
    return defn, groups


def _find_page(groups, curve_name: str):
    for g in groups:
        for p in g.pages:
            if p.curve_name == curve_name:
                return p
    return None


# ---------------------------------------------------------------------------
# Groups are produced
# ---------------------------------------------------------------------------

def test_curve_page_service_returns_groups() -> None:
    _defn, groups = _load()
    assert len(groups) > 0


def test_curve_pages_are_all_curve_kind() -> None:
    _defn, groups = _load()
    for g in groups:
        for p in g.pages:
            assert p.kind == TuningPageKind.CURVE


def test_total_curve_pages_matches_definition() -> None:
    defn, groups = _load()
    total = sum(len(g.pages) for g in groups)
    assert total == len(defn.curve_definitions)


# ---------------------------------------------------------------------------
# WUE curve page fields
# ---------------------------------------------------------------------------

def test_warmup_curve_page_title() -> None:
    _defn, groups = _load()
    page = _find_page(groups, "warmup_curve")
    assert page is not None
    assert page.title == "Warmup Enrichment (WUE) Curve"


def test_warmup_curve_page_id() -> None:
    _defn, groups = _load()
    page = _find_page(groups, "warmup_curve")
    assert page.page_id == "curve:warmup_curve"


def test_warmup_curve_x_bins_param() -> None:
    _defn, groups = _load()
    page = _find_page(groups, "warmup_curve")
    assert page.curve_x_bins_param == "wueBins"


def test_warmup_curve_x_channel() -> None:
    _defn, groups = _load()
    page = _find_page(groups, "warmup_curve")
    assert page.curve_x_channel == "coolant"


def test_warmup_curve_y_bins_params() -> None:
    _defn, groups = _load()
    page = _find_page(groups, "warmup_curve")
    assert "wueRates" in page.curve_y_bins_params


def test_warmup_curve_gauge() -> None:
    _defn, groups = _load()
    page = _find_page(groups, "warmup_curve")
    assert page.curve_gauge == "cltGauge"


def test_warmup_curve_help_topic() -> None:
    """WUE curve does not have topicHelp; baroFuel_curve does."""
    _defn, groups = _load()
    page = _find_page(groups, "baroFuel_curve")
    assert page is not None
    assert page.help_topic is not None
    assert "speeduino.com" in page.help_topic


# ---------------------------------------------------------------------------
# Parameter roles
# ---------------------------------------------------------------------------

def test_warmup_curve_parameters_have_x_and_y_roles() -> None:
    defn, groups = _load()
    page = _find_page(groups, "warmup_curve")
    roles = {p.role for p in page.parameters}
    assert TuningPageParameterRole.X_AXIS in roles
    assert TuningPageParameterRole.Y_AXIS in roles


def test_dwell_curve_x_axis_param_name() -> None:
    defn, groups = _load()
    page = _find_page(groups, "dwell_correction_curve")
    x_params = [p for p in page.parameters if p.role == TuningPageParameterRole.X_AXIS]
    assert x_params
    assert x_params[0].name == "brvBins"


def test_dwell_curve_y_axis_param_name() -> None:
    defn, groups = _load()
    page = _find_page(groups, "dwell_correction_curve")
    y_params = [p for p in page.parameters if p.role == TuningPageParameterRole.Y_AXIS]
    assert y_params
    assert y_params[0].name == "dwellRates"


# ---------------------------------------------------------------------------
# Multi-line curve (warmup_analyzer_curve)
# ---------------------------------------------------------------------------

def test_warmup_analyzer_has_two_y_bins_params() -> None:
    _defn, groups = _load()
    page = _find_page(groups, "warmup_analyzer_curve")
    assert page is not None
    assert len(page.curve_y_bins_params) == 2
    assert "wueRates" in page.curve_y_bins_params
    assert "wueRecommended" in page.curve_y_bins_params


def test_warmup_analyzer_line_labels() -> None:
    _defn, groups = _load()
    page = _find_page(groups, "warmup_analyzer_curve")
    assert "Current WUE" in page.curve_line_labels
    assert "Recommended WUE" in page.curve_line_labels


def test_warmup_analyzer_two_y_parameters() -> None:
    defn, groups = _load()
    page = _find_page(groups, "warmup_analyzer_curve")
    y_params = [p for p in page.parameters if p.role == TuningPageParameterRole.Y_AXIS]
    assert len(y_params) == 2


# ---------------------------------------------------------------------------
# Group classification
# ---------------------------------------------------------------------------

def test_warmup_curve_lands_in_enrich_group() -> None:
    _defn, groups = _load()
    for g in groups:
        if any(p.curve_name == "warmup_curve" for p in g.pages):
            assert "enrich" in g.group_id.lower() or "Startup" in g.title
            return
    raise AssertionError("warmup_curve not found in any group")


def test_dwell_curve_lands_in_ignition_group() -> None:
    _defn, groups = _load()
    for g in groups:
        if any(p.curve_name == "dwell_correction_curve" for p in g.pages):
            assert "ignition" in g.group_id.lower() or "Ignition" in g.title
            return
    raise AssertionError("dwell_correction_curve not found in any group")


def test_iac_curve_lands_in_idle_group() -> None:
    _defn, groups = _load()
    for g in groups:
        if any(p.curve_name == "iacClosedLoop_curve" for p in g.pages):
            assert "idle" in g.group_id.lower() or "Idle" in g.title
            return
    raise AssertionError("iacClosedLoop_curve not found in any group")


# ---------------------------------------------------------------------------
# No curves = empty result
# ---------------------------------------------------------------------------

def test_empty_definition_returns_no_groups() -> None:
    from tuner.domain.ecu_definition import EcuDefinition
    service = CurvePageService()
    result = service.build_curve_pages(EcuDefinition(name="empty"))
    assert result == []
