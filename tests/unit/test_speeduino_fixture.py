"""Phase 0: fixture tests that validate the INI parser and page builder against
representative Speeduino INI content.

Two test suites:
  1. ``test_minimal_fixture_*`` — run against the curated minimal fixture that
     lives in the repo (tests/fixtures/speeduino_minimal.ini). Always runs.
  2. ``test_real_ini_*`` — run against the full local Speeduino INI when it is
     present on the machine. Skipped automatically otherwise.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from tuner.parsers.ini_parser import IniParser
from tuner.services.tuning_page_service import TuningPageService


FIXTURE_INI = Path(__file__).parent.parent / "fixtures" / "speeduino_minimal.ini"
REAL_INI = Path(r"C:\Users\Cornelio\Desktop\speeduino-202501.6\speeduino.ini")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_pages(groups):
    return [page for group in groups for page in group.pages]


def _page_titles(groups):
    return [page.title for page in _all_pages(groups)]


def _group_titles(groups):
    return [g.title for g in groups]


# ---------------------------------------------------------------------------
# Minimal fixture tests — always run
# ---------------------------------------------------------------------------

def test_minimal_fixture_parses_without_error() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    assert definition.name
    assert definition.scalars
    assert definition.tables


def test_minimal_fixture_scalars_from_constants() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    names = {s.name for s in definition.scalars}
    assert "reqFuel" in names
    assert "nCylinders" in names
    assert "sparkMode" in names   # bits
    assert "egoType" in names     # bits


def test_minimal_fixture_pc_variables_parsed() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    names = {s.name for s in definition.scalars}
    assert "rpmhigh" in names
    assert "rpmwarn" in names
    assert "maphigh" in names
    assert "idleUnits" in names   # bits in PcVariables


def test_minimal_fixture_pc_variable_has_no_offset() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    rpmhigh = next(s for s in definition.scalars if s.name == "rpmhigh")
    assert rpmhigh.offset is None
    assert rpmhigh.units == "rpm"
    assert rpmhigh.max_value == 30000.0


def test_minimal_fixture_requires_power_cycle() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    assert "sparkMode" in definition.requires_power_cycle
    assert "IgMap" in definition.requires_power_cycle
    assert "reqFuel" not in definition.requires_power_cycle


def test_minimal_fixture_help_text() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    req = next(s for s in definition.scalars if s.name == "reqFuel")
    assert req.help_text and "Required fuel" in req.help_text
    rpmhigh = next(s for s in definition.scalars if s.name == "rpmhigh")
    assert rpmhigh.help_text and "gauge" in rpmhigh.help_text.lower()


def test_minimal_fixture_enum_options() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    spark_mode = next(s for s in definition.scalars if s.name == "sparkMode")
    labels = [o.label for o in spark_mode.options]
    assert "Wasted Spark" in labels
    assert "Sequential" in labels


def test_minimal_fixture_table_editors_parsed() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    te_ids = {te.table_id for te in definition.table_editors}
    assert "veTable1Tbl" in te_ids
    assert "sparkTbl" in te_ids


def test_minimal_fixture_dialogs_parsed() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    dialog_ids = {d.dialog_id for d in definition.dialogs}
    assert "engine_constants" in dialog_ids
    assert "sparkSettings" in dialog_ids
    assert "egoControl" in dialog_ids
    assert "gaugeLimits" in dialog_ids


def test_minimal_fixture_menus_parsed() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    menu_titles = {m.title for m in definition.menus}
    assert "Settings" in menu_titles
    assert "&Tuning" in menu_titles
    assert "&Spark" in menu_titles


def test_minimal_fixture_visibility_on_menu_item() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    spark_menu = next(m for m in definition.menus if m.title == "&Spark")
    spark_tbl_item = next(
        (item for item in spark_menu.items if item.target == "sparkTbl" and item.visibility_expression),
        None,
    )
    assert spark_tbl_item is not None
    assert "IgMap" in spark_tbl_item.visibility_expression


def test_minimal_fixture_page_builder_produces_expected_pages() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    groups = TuningPageService().build_pages(definition)
    titles = _page_titles(groups)
    assert any("VE Table" in t for t in titles)
    assert any("Spark" in t for t in titles)
    assert any("Engine Constants" in t for t in titles)


def test_minimal_fixture_uses_descriptive_titles_from_menu_and_dialog_content() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    groups = TuningPageService().build_pages(definition)
    titles = _page_titles(groups)
    assert "Engine Constants" in titles
    assert "AFR/O2" in titles
    assert "Boost Control" in titles


def test_minimal_fixture_gauge_limits_page_contains_pc_variables() -> None:
    """rpmhigh/rpmwarn/maphigh come from [PcVariables] — they must appear on the
    Gauge Limits page instead of being silently dropped."""
    definition = IniParser().parse(FIXTURE_INI)
    groups = TuningPageService().build_pages(definition)
    pages = _all_pages(groups)
    gauge_page = next((p for p in pages if "Gauge" in p.title), None)
    assert gauge_page is not None, "Gauge Limits page not found"
    param_names = {p.name for p in gauge_page.parameters}
    assert "rpmhigh" in param_names
    assert "rpmwarn" in param_names
    assert "maphigh" in param_names


def test_minimal_fixture_ve_page_is_table_kind() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    groups = TuningPageService().build_pages(definition)
    ve_page = next((p for p in _all_pages(groups) if "VE Table" in p.title), None)
    assert ve_page is not None
    from tuner.domain.tuning_pages import TuningPageKind
    assert ve_page.kind == TuningPageKind.TABLE


def test_minimal_fixture_ego_dialog_visibility_on_field() -> None:
    """stoich and egoCount fields carry visibility expressions from the dialog."""
    definition = IniParser().parse(FIXTURE_INI)
    groups = TuningPageService().build_pages(definition)
    pages = _all_pages(groups)
    ego_page = next((p for p in pages if "AFR" in p.title or "O2" in p.title), None)
    assert ego_page is not None
    stoich_param = next((p for p in ego_page.parameters if p.name == "stoich"), None)
    assert stoich_param is not None
    assert stoich_param.visibility_expression is not None
    assert "egoType" in stoich_param.visibility_expression


def test_minimal_fixture_tool_declarations_parsed() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    assert len(definition.tool_declarations) == 2
    ids = {t.tool_id for t in definition.tool_declarations}
    assert "veTableGenerator" in ids
    assert "afrTableGenerator" in ids


def test_minimal_fixture_tool_labels_and_targets() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    ve_tool = next(t for t in definition.tool_declarations if t.tool_id == "veTableGenerator")
    assert ve_tool.label == "VE Table Generator"
    assert ve_tool.target_table_id == "veTable1Tbl"


def test_minimal_fixture_ve_analyze_map_parsed() -> None:
    """Default (no LAMBDA setting) must take the #else (AFR) branch."""
    definition = IniParser().parse(FIXTURE_INI)
    ve_map = next((m for m in definition.autotune_maps if m.section_name == "VeAnalyze"), None)
    assert ve_map is not None
    assert "veTable1Tbl" in ve_map.map_parts
    assert "afr" in ve_map.map_parts


def test_minimal_fixture_ve_analyze_lambda_targets() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    ve_map = next(m for m in definition.autotune_maps if m.section_name == "VeAnalyze")
    assert "afrTable1" in ve_map.lambda_target_tables
    assert "afrTSCustom" in ve_map.lambda_target_tables


def test_minimal_fixture_ve_analyze_standard_filters() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    ve_map = next(m for m in definition.autotune_maps if m.section_name == "VeAnalyze")
    gate_names = {g.name for g in ve_map.filter_gates}
    assert "std_xAxisMin" in gate_names
    assert "std_DeadLambda" in gate_names
    assert "std_Custom" in gate_names


def test_minimal_fixture_ve_analyze_parameterised_filter() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    ve_map = next(m for m in definition.autotune_maps if m.section_name == "VeAnalyze")
    clt_gate = next((g for g in ve_map.filter_gates if g.name == "minCltFilter"), None)
    assert clt_gate is not None
    assert clt_gate.label == "Minimum CLT"
    assert clt_gate.channel == "coolant"
    assert clt_gate.operator == "<"
    assert clt_gate.threshold == 71.0
    assert clt_gate.default_enabled is True


def test_minimal_fixture_ve_analyze_disabled_by_default_filter() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    ve_map = next(m for m in definition.autotune_maps if m.section_name == "VeAnalyze")
    accel_gate = next((g for g in ve_map.filter_gates if g.name == "accelFilter"), None)
    assert accel_gate is not None
    assert accel_gate.default_enabled is False


def test_minimal_fixture_wue_analyze_parsed() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    wue_map = next((m for m in definition.autotune_maps if m.section_name == "WueAnalyze"), None)
    assert wue_map is not None
    assert len(wue_map.filter_gates) >= 4


def test_minimal_fixture_both_autotune_maps_present() -> None:
    definition = IniParser().parse(FIXTURE_INI)
    section_names = {m.section_name for m in definition.autotune_maps}
    assert "VeAnalyze" in section_names
    assert "WueAnalyze" in section_names


def test_minimal_fixture_blocking_factor_parsed() -> None:
    """blockingFactor and tableBlockingFactor must be parsed from [MegaTune] into EcuDefinition."""
    definition = IniParser().parse(FIXTURE_INI)
    assert definition.blocking_factor == 121
    assert definition.table_blocking_factor == 512


def test_minimal_fixture_hardware_testing_menu_hidden_by_default() -> None:
    """#unset enablehardware_test at the top of the fixture must suppress the
    Hardware Testing menu (#if enablehardware_test block) from the parsed menus."""
    definition = IniParser().parse(FIXTURE_INI)
    menu_titles = {m.title for m in definition.menus}
    assert "Hardware Testing" not in menu_titles


def test_minimal_fixture_hardware_testing_menu_visible_when_enabled() -> None:
    """Passing active_settings={'enablehardware_test'} to the parser must include
    the conditionally-gated Hardware Testing menu."""
    definition = IniParser().parse(FIXTURE_INI, active_settings=frozenset({"enablehardware_test"}))
    menu_titles = {m.title for m in definition.menus}
    assert "Hardware Testing" in menu_titles


def test_minimal_fixture_ve_analyze_uses_afr_branch_by_default() -> None:
    """Without LAMBDA in active_settings, the #else branch of the VeAnalyze
    conditional must be taken, referencing the AFR table."""
    definition = IniParser().parse(FIXTURE_INI)
    ve_map = next(m for m in definition.autotune_maps if m.section_name == "VeAnalyze")
    assert "afrTable1" in ve_map.map_parts
    assert "lambdaTable1" not in ve_map.map_parts


def test_minimal_fixture_ve_analyze_uses_lambda_branch_when_enabled() -> None:
    """With LAMBDA in active_settings, the #if branch must be taken, referencing
    the lambda table."""
    definition = IniParser().parse(FIXTURE_INI, active_settings=frozenset({"LAMBDA"}))
    ve_map = next(m for m in definition.autotune_maps if m.section_name == "VeAnalyze")
    assert "lambdaTable1" in ve_map.map_parts
    assert "afrTable1" not in ve_map.map_parts


# ---------------------------------------------------------------------------
# Real INI smoke test — skipped when the file is absent
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL_INI.exists(), reason="Full Speeduino INI not present on this machine")
def test_real_ini_parses_without_error() -> None:
    definition = IniParser().parse(REAL_INI)
    assert definition.name
    assert len(definition.scalars) > 50
    assert len(definition.tables) > 10
    assert definition.dialogs
    assert definition.menus


@pytest.mark.skipif(not REAL_INI.exists(), reason="Full Speeduino INI not present on this machine")
def test_real_ini_pc_variables_parsed() -> None:
    definition = IniParser().parse(REAL_INI)
    names = {s.name for s in definition.scalars}
    assert "rpmhigh" in names
    assert "rpmwarn" in names
    assert "maphigh" in names


@pytest.mark.skipif(not REAL_INI.exists(), reason="Full Speeduino INI not present on this machine")
def test_real_ini_hardware_testing_menu_hidden_by_default() -> None:
    """#unset enablehardware_test at the top of speeduino.ini must suppress
    the Hardware Testing menu from appearing in the parsed definition."""
    definition = IniParser().parse(REAL_INI)
    menu_titles = {m.title for m in definition.menus}
    assert "Hardware Testing" not in menu_titles


@pytest.mark.skipif(not REAL_INI.exists(), reason="Full Speeduino INI not present on this machine")
def test_real_ini_key_pages_generated() -> None:
    definition = IniParser().parse(REAL_INI)
    groups = TuningPageService().build_pages(definition)
    titles = _page_titles(groups)
    assert any("VE Table" in t for t in titles), f"VE Table page missing. Got: {titles[:20]}"
    assert any("Spark" in t for t in titles), "Spark page missing"
    assert any("AFR" in t or "O2" in t for t in titles), "AFR page missing"
    assert any("Idle" in t for t in titles), "Idle page missing"
    assert any("Engine" in t for t in titles), "Engine constants page missing"


@pytest.mark.skipif(not REAL_INI.exists(), reason="Full Speeduino INI not present on this machine")
def test_real_ini_gauge_limits_page_has_pc_variables() -> None:
    definition = IniParser().parse(REAL_INI)
    groups = TuningPageService().build_pages(definition)
    pages = _all_pages(groups)
    gauge_page = next((p for p in pages if "Gauge" in p.title), None)
    assert gauge_page is not None, "Gauge Limits page not found"
    param_names = {p.name for p in gauge_page.parameters}
    assert "rpmhigh" in param_names
