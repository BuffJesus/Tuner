"""Unit tests for [LoggerDefinition] INI parser pass.

Uses the production fixture INI (speeduino-dropbear-v2.0.1.ini) which defines
four loggers: tooth, compositeLogger, compositeLogger2, compositeLogger3.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser

FIXTURE_INI = Path(__file__).parent.parent / "fixtures" / "speeduino-dropbear-v2.0.1.ini"


@pytest.fixture(scope="module")
def definition():
    parser = IniParser()
    return parser.parse(FIXTURE_INI)


# ---------------------------------------------------------------------------
# Logger count and names
# ---------------------------------------------------------------------------

def test_four_loggers_parsed(definition) -> None:
    assert len(definition.logger_definitions) == 4


def test_logger_names(definition) -> None:
    names = [d.name for d in definition.logger_definitions]
    assert "tooth" in names
    assert "compositeLogger" in names
    assert "compositeLogger2" in names
    assert "compositeLogger3" in names


def test_logger_display_names(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["tooth"].display_name == "Tooth Logger"
    assert by_name["compositeLogger"].display_name == "Composite Logger"
    assert by_name["compositeLogger2"].display_name == "Composite Logger 2nd Cam"
    assert by_name["compositeLogger3"].display_name == "Composite Logger Both cams"


# ---------------------------------------------------------------------------
# Logger kinds
# ---------------------------------------------------------------------------

def test_tooth_kind(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["tooth"].kind == "tooth"


def test_composite_kinds(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["compositeLogger"].kind == "composite"
    assert by_name["compositeLogger2"].kind == "composite"
    assert by_name["compositeLogger3"].kind == "composite"


# ---------------------------------------------------------------------------
# Start / stop commands
# ---------------------------------------------------------------------------

def test_tooth_start_stop_commands(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    tooth = by_name["tooth"]
    assert tooth.start_command == "H"
    assert tooth.stop_command == "h"


def test_composite1_start_stop_commands(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    c = by_name["compositeLogger"]
    assert c.start_command == "J"
    assert c.stop_command == "j"


def test_composite2_start_stop_commands(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    c = by_name["compositeLogger2"]
    assert c.start_command == "O"
    assert c.stop_command == "o"


def test_composite3_start_stop_commands(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    c = by_name["compositeLogger3"]
    assert c.start_command == "X"
    assert c.stop_command == "x"


# ---------------------------------------------------------------------------
# dataReadCommand decoding ($tsCanId + \xNN escapes)
# ---------------------------------------------------------------------------

def test_tooth_data_read_command_is_bytes(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    cmd = by_name["tooth"].data_read_command
    assert isinstance(cmd, bytes)
    assert len(cmd) > 0


def test_tooth_data_read_command_starts_with_T(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    cmd = by_name["tooth"].data_read_command
    assert cmd[0:1] == b"T"


def test_tooth_data_read_command_tsCanId_substituted(definition) -> None:
    """$tsCanId should be replaced with \x00\x00 (2 bytes), not the literal string."""
    by_name = {d.name: d for d in definition.logger_definitions}
    cmd = by_name["tooth"].data_read_command
    # The raw INI has $tsCanId after 'T'; after substitution bytes 1-2 should be 0x00 0x00
    assert cmd[1] == 0x00
    assert cmd[2] == 0x00


def test_tooth_data_read_command_no_literal_dollar(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    cmd = by_name["tooth"].data_read_command
    assert b"$" not in cmd


def test_composite_data_read_command_starts_with_T(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    cmd = by_name["compositeLogger"].data_read_command
    assert cmd[0:1] == b"T"


# ---------------------------------------------------------------------------
# Timeout and continuousRead
# ---------------------------------------------------------------------------

def test_tooth_timeout_ms(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["tooth"].data_read_timeout_ms == 5000


def test_composite1_timeout_ms(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["compositeLogger"].data_read_timeout_ms == 5000


def test_composite2_timeout_ms(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["compositeLogger2"].data_read_timeout_ms == 50000


def test_continuous_read_tooth(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["tooth"].continuous_read is True


def test_continuous_read_composite(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["compositeLogger"].continuous_read is True


# ---------------------------------------------------------------------------
# recordDef: header/footer/record lengths
# ---------------------------------------------------------------------------

def test_tooth_record_def(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    tooth = by_name["tooth"]
    assert tooth.record_header_len == 0
    assert tooth.record_footer_len == 0
    assert tooth.record_len == 4


def test_composite_record_def(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    comp = by_name["compositeLogger"]
    assert comp.record_header_len == 0
    assert comp.record_footer_len == 0
    assert comp.record_len == 5


# ---------------------------------------------------------------------------
# record_count derived correctly
# ---------------------------------------------------------------------------

def test_tooth_record_count(definition) -> None:
    # dataLength = 508 bytes (tooth), recordLen = 4 → 127 records
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["tooth"].record_count == 127


def test_composite_record_count(definition) -> None:
    # dataLength = 127 records (composite)
    by_name = {d.name: d for d in definition.logger_definitions}
    assert by_name["compositeLogger"].record_count == 127


# ---------------------------------------------------------------------------
# recordField parsing — tooth
# ---------------------------------------------------------------------------

def test_tooth_has_one_record_field(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    assert len(by_name["tooth"].record_fields) == 1


def test_tooth_record_field_name(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    field = by_name["tooth"].record_fields[0]
    assert field.name == "toothTime"
    assert field.header == "ToothTime"


def test_tooth_record_field_bit_layout(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    field = by_name["tooth"].record_fields[0]
    assert field.start_bit == 0
    assert field.bit_count == 32


def test_tooth_record_field_scale_and_units(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    field = by_name["tooth"].record_fields[0]
    assert field.scale == pytest.approx(1.0)
    assert field.units == "uS"


# ---------------------------------------------------------------------------
# recordField parsing — composite
# ---------------------------------------------------------------------------

def test_composite_has_seven_record_fields(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    # priLevel, secLevel, ThirdLevel, trigger, sync, cycle, refTime
    assert len(by_name["compositeLogger"].record_fields) == 7


def test_composite_priLevel_field(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    field = by_name["compositeLogger"].record_fields[0]
    assert field.name == "priLevel"
    assert field.header == "PriLevel"
    assert field.start_bit == 0
    assert field.bit_count == 1
    assert field.scale == pytest.approx(1.0)
    assert field.units == "Flag"


def test_composite_refTime_field(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    fields = {f.name: f for f in by_name["compositeLogger"].record_fields}
    ref = fields["refTime"]
    assert ref.header == "RefTime"
    assert ref.start_bit == 8
    assert ref.bit_count == 32
    assert ref.scale == pytest.approx(0.001)
    assert ref.units == "ms"


def test_composite_sync_field(definition) -> None:
    by_name = {d.name: d for d in definition.logger_definitions}
    fields = {f.name: f for f in by_name["compositeLogger"].record_fields}
    sync = fields["sync"]
    assert sync.start_bit == 4
    assert sync.bit_count == 1


# ---------------------------------------------------------------------------
# calcField lines are NOT included in record_fields
# ---------------------------------------------------------------------------

def test_calc_fields_not_in_record_fields(definition) -> None:
    """calcField lines (toothTime, maxTime, time) are derived — must not be parsed as recordField."""
    by_name = {d.name: d for d in definition.logger_definitions}
    composite_field_names = {f.name for f in by_name["compositeLogger"].record_fields}
    assert "maxTime" not in composite_field_names
    assert "time" not in composite_field_names
    # toothTime in composite is a calcField; the raw binary field is refTime
    assert "toothTime" not in composite_field_names
