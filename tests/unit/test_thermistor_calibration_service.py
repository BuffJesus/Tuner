from __future__ import annotations

import struct

import pytest

from tuner.services.thermistor_calibration_service import (
    CalibrationSensor,
    PRESETS,
    ThermistorCalibrationService,
    ThermistorPoint,
    ThermistorPreset,
    _ADC_COUNT,
    _TEMP_MAX_C,
    _TEMP_MIN_C,
)


def _svc() -> ThermistorCalibrationService:
    return ThermistorCalibrationService()


# ---------------------------------------------------------------------------
# Preset inventory
# ---------------------------------------------------------------------------

def test_preset_count() -> None:
    assert len(PRESETS) == 15


def test_all_preset_names_unique() -> None:
    names = [p.name for p in PRESETS]
    assert len(names) == len(set(names))


def test_preset_by_name_found() -> None:
    result = _svc().preset_by_name("GM")
    assert result is not None
    assert result.name == "GM"
    assert result.pullup_ohms == 2490.0


def test_ms4x_temperature_presets_are_available() -> None:
    iat = _svc().preset_by_name("BMW M52 / M52TU / M54 IAT")
    clt = _svc().preset_by_name("BMW M52 / M52TU / M54 CLT")
    tmap = _svc().preset_by_name("Bosch 4 Bar TMAP IAT")

    assert iat is not None
    assert iat.pullup_ohms == 2490.0
    assert clt is not None
    assert clt.pullup_ohms == 828.0
    assert "MS4X" in clt.source_note
    assert tmap is not None
    assert tmap.point3.resistance_ohms == 323.0


def test_presets_for_sensor_filters_out_irrelevant_entries() -> None:
    clt_names = {preset.name for preset in _svc().presets_for_sensor(CalibrationSensor.CLT)}
    iat_names = {preset.name for preset in _svc().presets_for_sensor(CalibrationSensor.IAT)}

    assert "BMW M52 / M52TU / M54 CLT" in clt_names
    assert "BMW M52 / M52TU / M54 CLT" not in iat_names
    assert "Bosch 4 Bar TMAP IAT" in iat_names
    assert "Bosch 4 Bar TMAP IAT" not in clt_names
    assert "GM" in clt_names
    assert "GM" in iat_names


def test_preset_by_name_not_found_returns_none() -> None:
    assert _svc().preset_by_name("NoSuchSensor") is None


# ---------------------------------------------------------------------------
# Table dimensions and basic validity
# ---------------------------------------------------------------------------

def test_table_has_32_values() -> None:
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    assert len(result.temperatures_c) == _ADC_COUNT


def test_all_values_within_limits() -> None:
    for preset in PRESETS:
        result = _svc().generate(preset, CalibrationSensor.CLT)
        for t in result.temperatures_c:
            assert _TEMP_MIN_C <= t <= _TEMP_MAX_C, (
                f"Preset {preset.name}: temp {t} out of [{_TEMP_MIN_C}, {_TEMP_MAX_C}]"
            )


def test_sensor_stored_in_result() -> None:
    preset = _svc().preset_by_name("GM")
    for sensor in CalibrationSensor:
        result = _svc().generate(preset, sensor)
        assert result.sensor == sensor


def test_preset_name_stored_in_result() -> None:
    preset = _svc().preset_by_name("Ford")
    result = _svc().generate(preset, CalibrationSensor.IAT)
    assert result.preset_name == "Ford"


# ---------------------------------------------------------------------------
# Physical shape: higher ADC → hotter (sensor getting shorter-circuit)
# ---------------------------------------------------------------------------

def test_temperature_decreases_with_adc_for_gm() -> None:
    """Higher ADC = higher resistance = open circuit = colder (NTC pullup divider).

    In a pullup voltage divider, Vout = Vcc * Rtherm / (Rtherm + Rpull).
    Higher ADC → higher Vout → higher Rtherm → lower NTC temperature.
    ADC=0 (shorted) is the hottest; ADC=1023 (open circuit) is the coldest.
    """
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    temps = result.temperatures_c
    # Overall trend: first entries (low ADC = hot) > last entries (high ADC = cold)
    hot_avg = sum(temps[:10]) / 10
    cold_avg = sum(temps[22:]) / 10
    assert hot_avg > cold_avg, "Expected temperature to decrease with ADC value"


@pytest.mark.parametrize("preset_name", [p.name for p in PRESETS])
def test_monotone_trend_all_presets(preset_name: str) -> None:
    """Temperatures should generally decrease with ADC (NTC pullup divider physics)."""
    preset = _svc().preset_by_name(preset_name)
    result = _svc().generate(preset, CalibrationSensor.CLT)
    temps = result.temperatures_c
    # Allow a couple of flat/reversed steps at extremes, but overall must trend down
    decreases = sum(1 for i in range(1, len(temps)) if temps[i] < temps[i - 1])
    assert decreases >= len(temps) // 2, (
        f"Preset {preset_name}: expected mostly decreasing temps, got {decreases}/{len(temps)}"
    )


# ---------------------------------------------------------------------------
# Payload encoding
# ---------------------------------------------------------------------------

def test_payload_is_64_bytes() -> None:
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    assert len(result.encode_payload()) == 64


def test_payload_decodes_to_reasonable_fahrenheit() -> None:
    """Decode the payload back to °F and verify they match the °C values."""
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    payload = result.encode_payload()
    for i, t_c in enumerate(result.temperatures_c):
        raw = struct.unpack(">h", payload[2 * i : 2 * i + 2])[0]  # signed int16
        t_f_decoded = raw / 10.0
        t_c_recovered = (t_f_decoded - 32.0) * 5.0 / 9.0
        assert abs(t_c_recovered - t_c) < 0.2, (
            f"Index {i}: encoded {t_c}°C → decoded {t_c_recovered:.1f}°C (via {t_f_decoded}°F×10)"
        )


def test_payload_big_endian_order() -> None:
    """High byte must come before low byte (big-endian per Speeduino protocol)."""
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    payload = result.encode_payload()
    # Spot-check: value at index 15 (mid-range, known positive temperature)
    t_c = result.temperatures_c[15]
    t_f = t_c * 9.0 / 5.0 + 32.0
    expected = round(t_f * 10)
    hi = payload[30]
    lo = payload[31]
    actual = (hi << 8) | lo
    assert actual == expected


# ---------------------------------------------------------------------------
# Serial command
# ---------------------------------------------------------------------------

def test_serial_command_length() -> None:
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    cmd = result.build_serial_command()
    assert len(cmd) == 71  # 7-byte header + 64-byte payload


def test_serial_command_header_clt() -> None:
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    cmd = result.build_serial_command()
    assert cmd[0] == ord("t")
    assert cmd[1] == 0x00
    assert cmd[2] == 0   # CLT page
    assert cmd[3] == 0x00 and cmd[4] == 0x00  # offset = 0
    assert (cmd[5] << 8) | cmd[6] == 64        # length = 64


def test_serial_command_header_iat() -> None:
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.IAT)
    cmd = result.build_serial_command()
    assert cmd[2] == 1   # IAT page


def test_serial_command_payload_matches_encode_payload() -> None:
    preset = _svc().preset_by_name("Ford")
    result = _svc().generate(preset, CalibrationSensor.IAT)
    cmd = result.build_serial_command()
    assert cmd[7:] == result.encode_payload()


# ---------------------------------------------------------------------------
# Custom preset
# ---------------------------------------------------------------------------

def test_custom_preset_generates_table() -> None:
    custom = ThermistorPreset(
        name="Custom",
        pullup_ohms=2490.0,
        point1=ThermistorPoint(-40.0, 100_700.0),
        point2=ThermistorPoint(30.0, 2_238.0),
        point3=ThermistorPoint(99.0, 177.0),
    )
    result = _svc().generate(custom, CalibrationSensor.CLT)
    assert len(result.temperatures_c) == 32
    for t in result.temperatures_c:
        assert _TEMP_MIN_C <= t <= _TEMP_MAX_C


def test_custom_preset_matches_gm_preset() -> None:
    """A custom preset with GM values should produce the same table as the built-in GM preset."""
    gm = _svc().preset_by_name("GM")
    custom = ThermistorPreset(
        name="Custom",
        pullup_ohms=gm.pullup_ohms,
        point1=gm.point1,
        point2=gm.point2,
        point3=gm.point3,
    )
    result_gm = _svc().generate(gm, CalibrationSensor.CLT)
    result_custom = _svc().generate(custom, CalibrationSensor.CLT)
    for a, b in zip(result_gm.temperatures_c, result_custom.temperatures_c):
        assert abs(a - b) < 0.01


# ---------------------------------------------------------------------------
# Preview points
# ---------------------------------------------------------------------------

def test_preview_points_non_empty() -> None:
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    pts = result.preview_points()
    assert len(pts) > 0


def test_preview_points_adc_values_are_multiples_of_33() -> None:
    preset = _svc().preset_by_name("GM")
    result = _svc().generate(preset, CalibrationSensor.CLT)
    for adc, _ in result.preview_points():
        assert adc % 33 == 0


# ---------------------------------------------------------------------------
# CalibrationSensor enum
# ---------------------------------------------------------------------------

def test_clt_page_is_zero() -> None:
    assert int(CalibrationSensor.CLT) == 0


def test_iat_page_is_one() -> None:
    assert int(CalibrationSensor.IAT) == 1
