"""Wideband O2 calibration table generation for Speeduino.

Generates the 32-point ADC → AFR lookup table used by Speeduino's wideband
oxygen sensor calibration page (calibration page 2). The table is written
to the ECU via the same ``'t'`` command path as the thermistor pages.

Reference:
    Speeduino firmware: comms.cpp ``processCalibrationNew`` (page 2 = O2)
    SpeeduinoControllerClient.write_calibration_table(page=2, payload=...)

The wire format mirrors the thermistor calibration packets:
  - 32 entries
  - Each entry is a big-endian signed 16-bit integer
  - Value = AFR × 10 (e.g. 14.7 stoich → 147)

Most aftermarket widebands map their 0–5 V output linearly to AFR. The
preset catalog below includes the well-known controllers; operators with
non-linear or non-standard sensors can supply a ``WidebandPreset`` with
custom endpoints.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADC_COUNT = 32          # Speeduino calibration table length
_ADC_MAX = 1023          # 10-bit ADC full scale
_SUPPLY_V = 5.0          # Speeduino sensor supply voltage

# Speeduino expects the AFR table as 32 × big-endian int16, AFR × 10.
# The two clamp limits below are intentionally generous so unusual
# sensors (alcohol, hydrogen, etc.) still encode without saturation.
_AFR_MIN = 5.0
_AFR_MAX = 30.0


class WidebandCalibrationPage(IntEnum):
    """Speeduino calibration page identifier for the wideband O2 sensor."""
    O2 = 2


# ---------------------------------------------------------------------------
# Preset definition
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class WidebandPreset:
    """A linear voltage → AFR mapping for an aftermarket wideband sensor.

    Defined by two endpoint voltages and the AFR each endpoint represents.
    The full 32-point table is interpolated linearly between them and
    extrapolated (clamped) outside the endpoint range.

    Endpoints below 0 V or above ``_SUPPLY_V`` are clamped to the supply
    range; this lets the catalog encode controllers like the 14Point7
    Spartan2 (0.5–4.5 V active range) without special-casing the
    extrapolation.
    """

    name: str
    voltage_low: float       # e.g. 0.0 V
    afr_at_voltage_low: float  # AFR represented at voltage_low
    voltage_high: float      # e.g. 5.0 V
    afr_at_voltage_high: float
    notes: str = ""


# ---------------------------------------------------------------------------
# Built-in presets — published transfer functions for popular widebands
# ---------------------------------------------------------------------------

PRESETS: tuple[WidebandPreset, ...] = (
    WidebandPreset(
        name="Innovate LC-1 / LC-2 / LM-1 / LM-2 (default)",
        voltage_low=0.0,
        afr_at_voltage_low=7.35,
        voltage_high=5.0,
        afr_at_voltage_high=22.39,
        notes="Innovate factory linear default; programmable on the device.",
    ),
    WidebandPreset(
        name="AEM 30-0300 / 30-4110 / X-Series",
        voltage_low=0.0,
        afr_at_voltage_low=10.0,
        voltage_high=5.0,
        afr_at_voltage_high=20.0,
        notes="AEM analog output #1 — 10 AFR @ 0 V, 20 AFR @ 5 V.",
    ),
    WidebandPreset(
        name="14Point7 Spartan 2",
        voltage_low=0.0,
        afr_at_voltage_low=9.996,
        voltage_high=5.0,
        afr_at_voltage_high=19.992,
        notes="Spartan 2 default linear output (10–20 AFR across 0–5 V).",
    ),
    WidebandPreset(
        name="Tech Edge 2J9 / WBo2",
        voltage_low=0.0,
        afr_at_voltage_low=9.0,
        voltage_high=5.0,
        afr_at_voltage_high=19.0,
        notes="Tech Edge default 0–5 V linear (9–19 AFR).",
    ),
    WidebandPreset(
        name="PLX SM-AFR / DM-6",
        voltage_low=0.0,
        afr_at_voltage_low=10.0,
        voltage_high=5.0,
        afr_at_voltage_high=20.0,
        notes="PLX 0–5 V linear default (10–20 AFR).",
    ),
)

PRESET_NAMES: tuple[str, ...] = tuple(p.name for p in PRESETS)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class WidebandCalibrationResult:
    """Generated 32-point AFR calibration table ready to send to the ECU.

    ``afrs`` is ordered from ADC=0 (low voltage) to ADC=1023 (high voltage);
    index *i* corresponds to ADC value ``i × 33`` and voltage ``i × 33 ×
    5.0 / 1023``.
    """

    preset_name: str
    afrs: tuple[float, ...]   # 32 values

    def encode_payload(self) -> bytes:
        """Return 64 bytes: 32 × big-endian int16 of AFR × 10.

        Matches the Speeduino calibration packet format used by
        ``processCalibrationNew`` for all three calibration pages.
        """
        result = bytearray()
        for afr in self.afrs:
            val = max(-32768, min(32767, round(afr * 10)))
            result += struct.pack(">h", val)
        return bytes(result)

    def build_serial_command(self) -> bytes:
        """Return the full 71-byte ``'t'`` serial command packet for page 2."""
        payload = self.encode_payload()
        length = len(payload)  # 64
        header = bytes([
            ord("t"),
            0x00,
            int(WidebandCalibrationPage.O2),
            0x00, 0x00,                           # offset, big-endian (always 0)
            (length >> 8) & 0xFF, length & 0xFF,  # length, big-endian
        ])
        return header + payload

    def afr_at_voltage(self, voltage: float) -> float:
        """Return the table value at the closest ADC bin for ``voltage``."""
        adc = max(0, min(_ADC_MAX, round(voltage * _ADC_MAX / _SUPPLY_V)))
        index = min(_ADC_COUNT - 1, adc // 33)
        return self.afrs[index]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class WidebandCalibrationService:
    """Generates Speeduino-format wideband O2 calibration tables.

    Wraps the linear voltage→AFR transfer function for each preset and
    encodes the result into the 64-byte payload Speeduino expects for
    calibration page 2.

    Usage::

        svc = WidebandCalibrationService()
        preset = svc.preset_by_name("AEM 30-0300 / 30-4110 / X-Series")
        result = svc.generate(preset)
        client.write_calibration_table(page=2, payload=result.encode_payload())
    """

    @property
    def presets(self) -> tuple[WidebandPreset, ...]:
        return PRESETS

    def preset_by_name(self, name: str) -> WidebandPreset | None:
        for p in PRESETS:
            if p.name == name:
                return p
        return None

    def generate(self, preset: WidebandPreset) -> WidebandCalibrationResult:
        """Generate a 32-point AFR table by linear interpolation.

        Voltages outside ``[voltage_low, voltage_high]`` clamp to the
        nearest endpoint AFR; this is the right behaviour for widebands
        with a restricted active range (e.g. 14Point7 Spartan2 at
        0.5–4.5 V) where readings outside the band are saturated.
        """
        v_low = preset.voltage_low
        v_high = preset.voltage_high
        if v_high == v_low:
            raise ValueError(
                f"Preset {preset.name!r} has zero voltage span — endpoints must differ."
            )
        slope = (preset.afr_at_voltage_high - preset.afr_at_voltage_low) / (v_high - v_low)
        afrs: list[float] = []
        for i in range(_ADC_COUNT):
            adc = i * 33  # Speeduino bins: 0, 33, ..., 1023
            voltage = adc * _SUPPLY_V / _ADC_MAX
            if voltage <= v_low:
                afr = preset.afr_at_voltage_low
            elif voltage >= v_high:
                afr = preset.afr_at_voltage_high
            else:
                afr = preset.afr_at_voltage_low + slope * (voltage - v_low)
            afr = max(_AFR_MIN, min(_AFR_MAX, afr))
            afrs.append(round(afr, 2))
        return WidebandCalibrationResult(
            preset_name=preset.name,
            afrs=tuple(afrs),
        )
