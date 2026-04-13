"""Tests for formula (virtual / computed) output channel parsing.

Covers the ``name = { expression } [, "units"] [, digits]`` form in the
``[OutputChannels]`` section of the INI — the Phase 14 slice that introduces
``FormulaOutputChannel`` and ``EcuDefinition.formula_output_channels``.

Evaluation of the expressions is out of scope for this slice; only catalog
state is asserted here.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from tuner.domain.ecu_definition import FormulaOutputChannel
from tuner.parsers.ini_parser import IniParser


FIXTURE_INI = Path(__file__).parent.parent / "fixtures" / "speeduino-dropbear-v2.0.1.ini"


def _write_ini(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.ini"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

def test_single_formula_channel_with_no_trailing_metadata(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [OutputChannels]
           coolant = { coolantRaw - 40 }
    """)
    d = IniParser().parse(ini)
    assert d.formula_output_channels == [
        FormulaOutputChannel(
            name="coolant",
            formula_expression="coolantRaw - 40",
            units=None,
            digits=None,
        )
    ]


def test_formula_channel_with_units(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [OutputChannels]
           throttle = { tps }, "%"
    """)
    d = IniParser().parse(ini)
    assert len(d.formula_output_channels) == 1
    f = d.formula_output_channels[0]
    assert f.name == "throttle"
    assert f.formula_expression == "tps"
    assert f.units == "%"
    assert f.digits is None


def test_formula_channel_with_units_and_digits(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [OutputChannels]
           map_psi = { (map - baro) * 0.145038 }, "PSI", 2
    """)
    d = IniParser().parse(ini)
    assert len(d.formula_output_channels) == 1
    f = d.formula_output_channels[0]
    assert f.name == "map_psi"
    assert f.formula_expression == "(map - baro) * 0.145038"
    assert f.units == "PSI"
    assert f.digits == 2


def test_formula_channel_inline_comment_is_stripped(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [OutputChannels]
           coolant = { coolantRaw - 40 } ; Temperature readings are offset by 40
    """)
    d = IniParser().parse(ini)
    assert len(d.formula_output_channels) == 1
    assert d.formula_output_channels[0].formula_expression == "coolantRaw - 40"


def test_formula_channel_ternary_expression_preserved_verbatim(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [OutputChannels]
           strokeMultipler = { twoStroke == 1 ? 1 : 2 }
    """)
    d = IniParser().parse(ini)
    assert (
        d.formula_output_channels[0].formula_expression
        == "twoStroke == 1 ? 1 : 2"
    )


def test_formula_channel_arrayValue_call_preserved(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [OutputChannels]
           nFuelChannels = { arrayValue( array.boardFuelOutputs, pinLayout ) }
    """)
    d = IniParser().parse(ini)
    expr = d.formula_output_channels[0].formula_expression
    assert "arrayValue" in expr
    assert "boardFuelOutputs" in expr
    assert "pinLayout" in expr


def test_formula_channels_coexist_with_scalar_channels(tmp_path: Path) -> None:
    # Scalar entries containing ``{ expression }`` in their units/scale slots
    # must *not* be reclassified as formula channels — the formula branch
    # requires ``= {`` immediately after the name.
    ini = _write_ini(tmp_path, """
        [OutputChannels]
           idleLoad = scalar, U08, 38, { bitStringValue( idleUnits , iacAlgorithm ) }, 1.0, 0.0
           coolant  = { coolantRaw - 40 }
    """)
    d = IniParser().parse(ini)
    scalar_names = [c.name for c in d.output_channel_definitions]
    formula_names = [c.name for c in d.formula_output_channels]
    assert "idleLoad" in scalar_names
    assert "idleLoad" not in formula_names
    assert formula_names == ["coolant"]


def test_formula_channel_multiple_entries_order_preserved(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [OutputChannels]
           coolant  = { coolantRaw - 40 }
           iat      = { iatRaw - 40 }
           fuelTemp = { fuelTempRaw - 40 }
    """)
    d = IniParser().parse(ini)
    assert [c.name for c in d.formula_output_channels] == [
        "coolant",
        "iat",
        "fuelTemp",
    ]


def test_formula_channel_outside_output_channels_section_ignored(tmp_path: Path) -> None:
    ini = _write_ini(tmp_path, """
        [PcVariables]
           foo = { bar + 1 }
        [OutputChannels]
           coolant = { coolantRaw - 40 }
    """)
    d = IniParser().parse(ini)
    names = [c.name for c in d.formula_output_channels]
    assert "foo" not in names
    assert names == ["coolant"]


# ---------------------------------------------------------------------------
# Production INI parity
# ---------------------------------------------------------------------------

def test_production_ini_has_expected_formula_channel_count() -> None:
    d = IniParser().parse(FIXTURE_INI)
    # The production INI ships dozens of formula channels: temperatures,
    # pressure conversions, timing derivatives, lambda, boost derivations,
    # map pressure conversions, etc. Guard at a floor of 30 so a regression
    # that silently drops the branch would be caught.
    assert len(d.formula_output_channels) >= 30


def test_production_ini_contains_core_formula_channels() -> None:
    d = IniParser().parse(FIXTURE_INI)
    names = {c.name for c in d.formula_output_channels}
    expected = {
        "coolant",
        "iat",
        "map_psi",
        "map_bar",
        "lambda",
        "throttle",
        "dutyCycle",
        "boostCutOut",
        "revolutionTime",
        "strokeMultipler",
    }
    missing = expected - names
    assert not missing, f"missing formula channels in production INI: {missing}"


def test_production_ini_map_psi_expression_shape() -> None:
    d = IniParser().parse(FIXTURE_INI)
    by_name = {c.name: c for c in d.formula_output_channels}
    f = by_name["map_psi"]
    # Exact verbatim match — locks that we strip braces and collapse no
    # internal whitespace.
    assert f.formula_expression == "(map - baro) * 0.145038"


def test_production_ini_throttle_has_percent_units() -> None:
    d = IniParser().parse(FIXTURE_INI)
    by_name = {c.name: c for c in d.formula_output_channels}
    assert by_name["throttle"].units == "%"


def test_production_ini_formula_channel_names_do_not_collide_with_scalars() -> None:
    # A formula channel and a hardware scalar output channel must not share
    # a name — the operator would not be able to tell which one the runtime
    # dashboard is showing.
    d = IniParser().parse(FIXTURE_INI)
    scalar_names = {c.name for c in d.output_channel_definitions}
    formula_names = {c.name for c in d.formula_output_channels}
    collisions = scalar_names & formula_names
    assert not collisions, f"formula/scalar name collisions: {collisions}"
