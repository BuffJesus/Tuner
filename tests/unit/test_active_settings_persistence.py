from __future__ import annotations

from pathlib import Path

import pytest

from tuner.domain.ecu_definition import SettingGroupDefinition, SettingGroupOption
from tuner.domain.project import Project
from tuner.parsers.project_parser import ProjectParser
from tuner.services.project_service import ProjectService


# ---------------------------------------------------------------------------
# Project domain
# ---------------------------------------------------------------------------

def test_project_default_active_settings_is_empty() -> None:
    p = Project(name="test")
    assert p.active_settings == frozenset()


# ---------------------------------------------------------------------------
# ProjectParser round-trip
# ---------------------------------------------------------------------------

def test_parser_reads_active_settings(tmp_path: Path) -> None:
    project_file = tmp_path / "test.project"
    project_file.write_text(
        "projectName=Test\nactiveSettings=LAMBDA,mcu_teensy\n",
        encoding="utf-8",
    )
    project = ProjectParser().parse(project_file)
    assert "LAMBDA" in project.active_settings
    assert "mcu_teensy" in project.active_settings


def test_parser_returns_empty_active_settings_when_absent(tmp_path: Path) -> None:
    project_file = tmp_path / "test.project"
    project_file.write_text("projectName=Test\n", encoding="utf-8")
    project = ProjectParser().parse(project_file)
    assert project.active_settings == frozenset()


def test_parser_ignores_blank_active_settings(tmp_path: Path) -> None:
    project_file = tmp_path / "test.project"
    project_file.write_text("projectName=Test\nactiveSettings=\n", encoding="utf-8")
    project = ProjectParser().parse(project_file)
    assert project.active_settings == frozenset()


# ---------------------------------------------------------------------------
# ProjectService save + round-trip
# ---------------------------------------------------------------------------

def test_save_writes_active_settings(tmp_path: Path) -> None:
    project = Project(
        name="TestProj",
        active_settings=frozenset({"LAMBDA", "mcu_teensy"}),
    )
    service = ProjectService()
    path = service.save_project(project, tmp_path / "test.project")
    text = path.read_text(encoding="utf-8")
    assert "activeSettings=" in text
    assert "LAMBDA" in text
    assert "mcu_teensy" in text


def test_save_omits_active_settings_when_empty(tmp_path: Path) -> None:
    project = Project(name="TestProj")
    service = ProjectService()
    path = service.save_project(project, tmp_path / "test.project")
    text = path.read_text(encoding="utf-8")
    assert "activeSettings" not in text


def test_active_settings_round_trip(tmp_path: Path) -> None:
    service = ProjectService()
    project = Project(
        name="RoundTrip",
        active_settings=frozenset({"LAMBDA"}),
    )
    path = service.save_project(project, tmp_path / "rt.project")
    loaded = service.open_project(path)
    assert loaded.active_settings == frozenset({"LAMBDA"})


# ---------------------------------------------------------------------------
# SettingGroupDefinition domain
# ---------------------------------------------------------------------------

def test_setting_group_boolean_flag() -> None:
    g = SettingGroupDefinition(symbol="enablehardware_test", label="Enable Hardware Test Page")
    assert g.symbol == "enablehardware_test"
    assert g.options == []


def test_setting_group_with_options() -> None:
    g = SettingGroupDefinition(
        symbol="mcu",
        label="Controller in use",
        options=[
            SettingGroupOption(symbol="DEFAULT", label="Arduino Mega 2560"),
            SettingGroupOption(symbol="mcu_teensy", label="Teensy"),
        ],
    )
    assert len(g.options) == 2
    assert g.options[1].symbol == "mcu_teensy"


# ---------------------------------------------------------------------------
# IniParser setting groups
# ---------------------------------------------------------------------------

def test_ini_parser_parses_setting_groups(tmp_path: Path) -> None:
    from tuner.parsers.ini_parser import IniParser

    ini = tmp_path / "test.ini"
    ini.write_text(
        "[MegaTune]\nsignature = \"test\"\n"
        "[SettingGroups]\n"
        "settingGroup = enablehardware_test, \"Enable Hardware Test Page\"\n"
        "settingGroup = mcu, \"Controller in use\"\n"
        "settingOption = DEFAULT, \"Arduino Mega 2560\"\n"
        "settingOption = mcu_teensy, \"Teensy\"\n",
        encoding="utf-8",
    )
    definition = IniParser().parse(ini)
    assert len(definition.setting_groups) == 2
    hw_group = next(g for g in definition.setting_groups if g.symbol == "enablehardware_test")
    assert hw_group.label == "Enable Hardware Test Page"
    assert hw_group.options == []

    mcu_group = next(g for g in definition.setting_groups if g.symbol == "mcu")
    assert mcu_group.label == "Controller in use"
    assert len(mcu_group.options) == 2
    assert mcu_group.options[1].symbol == "mcu_teensy"


def test_ini_parser_setting_groups_empty_when_section_absent(tmp_path: Path) -> None:
    from tuner.parsers.ini_parser import IniParser

    ini = tmp_path / "minimal.ini"
    ini.write_text("[MegaTune]\nsignature = \"test\"\n", encoding="utf-8")
    definition = IniParser().parse(ini)
    assert definition.setting_groups == []
