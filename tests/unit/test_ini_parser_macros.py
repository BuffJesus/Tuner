"""Tests for INI parser #define macro expansion in bits-field options."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser


# ---------------------------------------------------------------------------
# _collect_defines
# ---------------------------------------------------------------------------

def _write_ini(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.ini"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_collect_defines_parses_simple_option_list(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        #define pinLayouts = "INVALID", "Board A", "Board B"
        [Constants]
    """)
    defines = IniParser()._collect_defines(ini)
    assert "pinLayouts" in defines
    assert defines["pinLayouts"] == ["INVALID", "Board A", "Board B"]


def test_collect_defines_handles_no_defines(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [Constants]
          reqFuel = scalar, U08, 0, "ms", 0.1, 0, 0, 25.5, 1
    """)
    defines = IniParser()._collect_defines(ini)
    assert defines == {}


def test_collect_defines_ignores_define_without_equals(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        #define SOME_CONST
        [Constants]
    """)
    defines = IniParser()._collect_defines(ini)
    assert defines == {}


# ---------------------------------------------------------------------------
# _expand_options
# ---------------------------------------------------------------------------

def test_expand_options_replaces_dollar_macro() -> None:
    defines = {"myBoards": ["Board A", "Board B", "Board C"]}
    result = IniParser._expand_options(["$myBoards"], defines)
    assert result == ["Board A", "Board B", "Board C"]


def test_expand_options_drops_brace_tokens() -> None:
    defines: dict = {}
    result = IniParser._expand_options(["{some condition}", "Option A"], defines)
    assert result == ["Option A"]


def test_expand_options_drops_unknown_dollar_token() -> None:
    defines: dict = {}
    result = IniParser._expand_options(["$unknownMacro", "Option A"], defines)
    assert result == ["Option A"]


def test_expand_options_recursion_limit() -> None:
    # Circular or deeply nested defines should not cause infinite recursion.
    defines = {"a": ["$b"], "b": ["$a"]}
    result = IniParser._expand_options(["$a"], defines)
    # Depth limit hit — result should be empty rather than raising.
    assert isinstance(result, list)


def test_expand_options_mixed_literals_and_macros() -> None:
    defines = {"boards": ["Board X", "Board Y"]}
    result = IniParser._expand_options(["Literal A", "$boards", "Literal B"], defines)
    assert result == ["Literal A", "Board X", "Board Y", "Literal B"]


# ---------------------------------------------------------------------------
# Full parse — bits field with $macro reference in [PcVariables]
# ---------------------------------------------------------------------------

def test_parse_pc_variables_expands_pinlayout_macro(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        #define pinLayouts = "INVALID", "Speeduino v0.2", "Drop Bear"
        [MegaTune]
          signature = "test"
          queryCommand = "S"
          versionInfo = "Q"
          pageSize = 128
        [Constants]
          page = 1
          reqFuel = scalar, U08, 0, "ms", 0.1, 0, 0, 25.5, 1
        [PcVariables]
          pinLayout = bits, U08, [0:7], $pinLayouts
        [TableEditor]
        [UserDefined]
        [Menu]
        [SettingContextHelp]
        [OutputChannels]
        [VeAnalyze]
        [WueAnalyze]
        [Tools]
    """)
    definition = IniParser().parse(ini)
    pin_param = next((s for s in definition.scalars if s.name == "pinLayout"), None)
    assert pin_param is not None, "pinLayout not parsed"
    assert pin_param.options is not None and len(pin_param.options) > 0, \
        "pinLayout options are empty — macro expansion failed"
    option_labels = [o.label for o in pin_param.options]
    # INVALID is filtered out (kept raw — expansion should produce all 3)
    assert "Speeduino v0.2" in option_labels
    assert "Drop Bear" in option_labels


def test_parse_constants_expands_bits_options_macro(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        #define strokes = "Four-stroke", "Two-stroke"
        [MegaTune]
          signature = "test"
          queryCommand = "S"
          versionInfo = "Q"
          pageSize = 128
        [Constants]
          page = 1
          twoStroke = bits, U08, 0, [0:0], $strokes
        [PcVariables]
        [TableEditor]
        [UserDefined]
        [Menu]
        [SettingContextHelp]
        [OutputChannels]
        [VeAnalyze]
        [WueAnalyze]
        [Tools]
    """)
    definition = IniParser().parse(ini)
    param = next((s for s in definition.scalars if s.name == "twoStroke"), None)
    assert param is not None
    assert param.options is not None
    labels = [o.label for o in param.options]
    assert "Four-stroke" in labels
    assert "Two-stroke" in labels


def test_parse_output_channels_expands_bits_options_macro(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        #define statusOpts = "Off", "On", "Fault"
        [MegaTune]
          signature = "test"
          queryCommand = "S"
          versionInfo = "Q"
          pageSize = 128
        [Constants]
          page = 1
          reqFuel = scalar, U08, 0, "ms", 0.1, 0, 0, 25.5, 1
        [PcVariables]
        [TableEditor]
        [UserDefined]
        [Menu]
        [SettingContextHelp]
        [OutputChannels]
          engineStatus = bits, U08, 0, [0:1], $statusOpts
        [VeAnalyze]
        [WueAnalyze]
        [Tools]
    """)
    definition = IniParser().parse(ini)
    param = next(
        (s for s in definition.output_channel_definitions if s.name == "engineStatus"),
        None,
    )
    assert param is not None
    assert param.options is not None
    labels = [o.label for o in param.options]
    assert "Off" in labels
    assert "On" in labels
    assert "Fault" in labels
