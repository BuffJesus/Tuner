"""Unit tests for [ControllerCommands] INI parser pass.

Uses the production fixture INI which defines injector/spark test commands,
STM32 reboot/bootloader, SD format, and VSS calibration commands.
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


@pytest.fixture(scope="module")
def cmd_map(definition):
    return {c.name: c.payload for c in definition.controller_commands}


# ---------------------------------------------------------------------------
# Basic count and structure
# ---------------------------------------------------------------------------

def test_controller_commands_parsed(definition) -> None:
    assert len(definition.controller_commands) > 0


def test_all_commands_have_nonempty_payload(definition) -> None:
    for cmd in definition.controller_commands:
        assert len(cmd.payload) > 0, f"{cmd.name} has empty payload"


def test_all_command_names_unique(definition) -> None:
    names = [c.name for c in definition.controller_commands]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Test mode commands
# ---------------------------------------------------------------------------

def test_stop_test_mode_command(cmd_map) -> None:
    assert cmd_map["cmdStopTestMode"] == b"E\x01\x00"


def test_enable_test_mode_command(cmd_map) -> None:
    assert cmd_map["cmdEnableTestMode"] == b"E\x01\x01"


# ---------------------------------------------------------------------------
# Injector commands — first injector
# ---------------------------------------------------------------------------

def test_injector1_on(cmd_map) -> None:
    assert cmd_map["cmdtestinj1on"] == b"E\x02\x01"


def test_injector1_off(cmd_map) -> None:
    assert cmd_map["cmdtestinj1off"] == b"E\x02\x02"


def test_injector1_pulsed(cmd_map) -> None:
    assert cmd_map["cmdtestinj1Pulsed"] == b"E\x02\x03"


def test_injector2_on(cmd_map) -> None:
    assert cmd_map["cmdtestinj2on"] == b"E\x02\x04"


def test_injector8_pulsed(cmd_map) -> None:
    assert cmd_map["cmdtestinj8Pulsed"] == b"E\x02\x18"


def test_all_eight_injectors_present(cmd_map) -> None:
    for n in range(1, 9):
        assert f"cmdtestinj{n}on" in cmd_map
        assert f"cmdtestinj{n}off" in cmd_map
        assert f"cmdtestinj{n}Pulsed" in cmd_map


# ---------------------------------------------------------------------------
# Spark commands
# ---------------------------------------------------------------------------

def test_spark1_on(cmd_map) -> None:
    assert cmd_map["cmdtestspk1on"] == b"E\x03\x01"


def test_spark1_off(cmd_map) -> None:
    assert cmd_map["cmdtestspk1off"] == b"E\x03\x02"


def test_spark1_pulsed(cmd_map) -> None:
    assert cmd_map["cmdtestspk1Pulsed"] == b"E\x03\x03"


def test_spark8_pulsed(cmd_map) -> None:
    assert cmd_map["cmdtestspk8Pulsed"] == b"E\x03\x18"


def test_all_eight_sparks_present(cmd_map) -> None:
    for n in range(1, 9):
        assert f"cmdtestspk{n}on" in cmd_map
        assert f"cmdtestspk{n}off" in cmd_map
        assert f"cmdtestspk{n}Pulsed" in cmd_map


# ---------------------------------------------------------------------------
# STM32 commands
# ---------------------------------------------------------------------------

def test_stm32_reboot(cmd_map) -> None:
    assert cmd_map["cmdstm32reboot"] == b"E\x32\x00"


def test_stm32_bootloader(cmd_map) -> None:
    assert cmd_map["cmdstm32bootloader"] == b"E\x32\x01"


# ---------------------------------------------------------------------------
# SD format
# ---------------------------------------------------------------------------

def test_format_sd(cmd_map) -> None:
    assert cmd_map["cmdFormatSD"] == b"E\x33\x01"


# ---------------------------------------------------------------------------
# VSS calibration
# ---------------------------------------------------------------------------

def test_vss_60kmh(cmd_map) -> None:
    assert cmd_map["cmdVSS60kmh"] == b"E\x99\x00"


def test_vss_ratio1(cmd_map) -> None:
    assert cmd_map["cmdVSSratio1"] == b"E\x99\x01"


def test_vss_ratio6(cmd_map) -> None:
    assert cmd_map["cmdVSSratio6"] == b"E\x99\x06"


def test_all_six_vss_ratios_present(cmd_map) -> None:
    for n in range(1, 7):
        assert f"cmdVSSratio{n}" in cmd_map


# ---------------------------------------------------------------------------
# Payload structure — all production commands start with 'E'
# ---------------------------------------------------------------------------

def test_all_commands_start_with_E(definition) -> None:
    for cmd in definition.controller_commands:
        assert cmd.payload[0:1] == b"E", (
            f"{cmd.name} payload does not start with 'E': {cmd.payload!r}"
        )


def test_all_commands_are_three_bytes(definition) -> None:
    """All production [ControllerCommands] entries are exactly 3 bytes: E + subtype + param."""
    for cmd in definition.controller_commands:
        assert len(cmd.payload) == 3, (
            f"{cmd.name} payload is {len(cmd.payload)} bytes, expected 3: {cmd.payload!r}"
        )


# ---------------------------------------------------------------------------
# Injector/spark byte layout matches E + subtype + sequential encoding
# ---------------------------------------------------------------------------

def test_injector_subtype_byte_is_0x02(definition) -> None:
    inj_cmds = [c for c in definition.controller_commands if c.name.startswith("cmdtestinj")]
    assert len(inj_cmds) > 0
    for cmd in inj_cmds:
        assert cmd.payload[1] == 0x02, f"{cmd.name}: subtype byte should be 0x02"


def test_spark_subtype_byte_is_0x03(definition) -> None:
    spk_cmds = [c for c in definition.controller_commands if c.name.startswith("cmdtestspk")]
    assert len(spk_cmds) > 0
    for cmd in spk_cmds:
        assert cmd.payload[1] == 0x03, f"{cmd.name}: subtype byte should be 0x03"


def test_injector_param_bytes_sequential(cmd_map) -> None:
    # inj1on=0x01, inj1off=0x02, inj1Pulsed=0x03, inj2on=0x04, ...
    expected = 0x01
    for n in range(1, 9):
        for mode in ("on", "off", "Pulsed"):
            key = f"cmdtestinj{n}{mode}"
            assert cmd_map[key][2] == expected, f"{key}: param byte mismatch"
            expected += 1


def test_spark_param_bytes_sequential(cmd_map) -> None:
    expected = 0x01
    for n in range(1, 9):
        for mode in ("on", "off", "Pulsed"):
            key = f"cmdtestspk{n}{mode}"
            assert cmd_map[key][2] == expected, f"{key}: param byte mismatch"
            expected += 1
