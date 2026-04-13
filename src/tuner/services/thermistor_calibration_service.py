"""Thermistor calibration table generation for Speeduino CLT/IAT sensors.

Generates the 32-point ADC → temperature lookup tables used by Speeduino for
coolant (CLT) and intake air temperature (IAT) sensors.  The tables are
written to the ECU via the ``'t'`` serial command (separate from the normal
tune-file page write path).

Reference:
    Speeduino firmware: comms.cpp ``processTemperatureCalibrationTableUpdate``
    TunerStudio INI:    ``std_ms2gentherm`` referenceTable block
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADC_COUNT = 32          # Speeduino calibration table length
_SUPPLY_V = 5.0          # sensor supply voltage
_KELVIN_OFFSET = 273.15  # 0 °C in Kelvin
_ADC_MAX = 1023          # 10-bit ADC full scale

# Speeduino stores calibration values with a +40 °C offset so that -40 °C
# can be represented as an unsigned zero.  The serial command sends values
# as Fahrenheit × 10 in big-endian 16-bit unsigned integers; the firmware
# converts back to Celsius and applies the offset on receipt.
_TEMP_MIN_C = -40.0
_TEMP_MAX_C = 350.0


class CalibrationSensor(IntEnum):
    """Speeduino calibration page identifiers."""
    CLT = 0
    IAT = 1


# ---------------------------------------------------------------------------
# Preset / custom point data types
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class ThermistorPoint:
    """One (temperature, resistance) calibration measurement."""
    temp_c: float
    resistance_ohms: float


@dataclass(slots=True, frozen=True)
class ThermistorPreset:
    """A named thermistor curve definition with three reference points.

    The three points should span a wide temperature range (e.g. -40 °C,
    30 °C, and 99 °C) for accurate Steinhart-Hart interpolation.
    """
    name: str
    pullup_ohms: float
    point1: ThermistorPoint
    point2: ThermistorPoint
    point3: ThermistorPoint
    source_note: str = "Generic thermistor preset mirrored from the Speeduino / TunerStudio preset catalog."
    source_url: str | None = None
    applicable_sensors: tuple[CalibrationSensor, ...] = (
        CalibrationSensor.CLT,
        CalibrationSensor.IAT,
    )


# ---------------------------------------------------------------------------
# Built-in presets — mirrored from TunerStudio / Speeduino INI thermOption list
# ---------------------------------------------------------------------------

PRESETS: tuple[ThermistorPreset, ...] = (
    ThermistorPreset(
        "GM",
        2490.0,
        ThermistorPoint(-40.0, 100_700.0),
        ThermistorPoint(30.0,   2_238.0),
        ThermistorPoint(99.0,     177.0),
    ),
    ThermistorPreset(
        "Chrysler 85+",
        2490.0,
        ThermistorPoint(5.5,  24_500.0),
        ThermistorPoint(30.5,  8_100.0),
        ThermistorPoint(88.3,    850.0),
    ),
    ThermistorPreset(
        "Ford",
        2490.0,
        ThermistorPoint(0.0,  94_000.0),
        ThermistorPoint(50.0, 11_000.0),
        ThermistorPoint(98.0,  2_370.0),
    ),
    ThermistorPreset(
        "Saab / Bosch",
        2490.0,
        ThermistorPoint(0.0,  5_800.0),
        ThermistorPoint(80.0,   320.0),
        ThermistorPoint(100.0,  180.0),
    ),
    ThermistorPreset(
        "Mazda",
        50_000.0,
        ThermistorPoint(-40.0, 2_022_000.0),
        ThermistorPoint(21.0,     68_273.0),
        ThermistorPoint(99.0,      3_715.0),
    ),
    ThermistorPreset(
        "Mitsubishi",
        2490.0,
        ThermistorPoint(-40.0, 100_490.0),
        ThermistorPoint(30.0,   1_875.0),
        ThermistorPoint(99.0,     125.0),
    ),
    ThermistorPreset(
        "Toyota",
        2490.0,
        ThermistorPoint(-40.0, 101_890.0),
        ThermistorPoint(30.0,   2_268.0),
        ThermistorPoint(99.0,     156.0),
    ),
    ThermistorPreset(
        "Mazda RX-7 CLT (S4/S5)",
        2490.0,
        ThermistorPoint(-20.0, 16_200.0),
        ThermistorPoint(20.0,   2_500.0),
        ThermistorPoint(80.0,     300.0),
        applicable_sensors=(CalibrationSensor.CLT,),
    ),
    ThermistorPreset(
        "Mazda RX-7 IAT (S5)",
        42_200.0,
        ThermistorPoint(20.0, 41_500.0),
        ThermistorPoint(50.0, 11_850.0),
        ThermistorPoint(85.0,  3_500.0),
        applicable_sensors=(CalibrationSensor.IAT,),
    ),
    ThermistorPreset(
        "VW L-Jet Cylinder Head",
        1_100.0,
        ThermistorPoint(-13.888, 11_600.0),
        ThermistorPoint(53.888,    703.0),
        ThermistorPoint(95.555,    207.0),
        applicable_sensors=(CalibrationSensor.CLT,),
    ),
    ThermistorPreset(
        "BMW E30 325i",
        2490.0,
        ThermistorPoint(-10.0, 9_300.0),
        ThermistorPoint(20.0,  2_500.0),
        ThermistorPoint(80.0,    335.0),
        applicable_sensors=(CalibrationSensor.CLT,),
    ),
    ThermistorPreset(
        "BMW M50 IAT",
        2490.0,
        ThermistorPoint(-30.0, 26_114.0),
        ThermistorPoint(20.0,   2_500.0),
        ThermistorPoint(80.0,     323.0),
        source_note="MS4X publishes the BMW M50 IAT resistance curve for the MS42/MS43 2.49k pull-up context.",
        source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
        applicable_sensors=(CalibrationSensor.IAT,),
    ),
    ThermistorPreset(
        "BMW M52 / M52TU / M54 IAT",
        2490.0,
        ThermistorPoint(-39.8, 168_058.0),
        ThermistorPoint(30.0,    4_025.0),
        ThermistorPoint(99.8,      343.0),
        source_note="MS4X publishes the BMW M52/M52TU/M54 IAT resistance curve for the MS42/MS43 2.49k pull-up context.",
        source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
        applicable_sensors=(CalibrationSensor.IAT,),
    ),
    ThermistorPreset(
        "BMW M52 / M52TU / M54 CLT",
        828.0,
        ThermistorPoint(-30.0, 39_366.0),
        ThermistorPoint(20.3,   2_826.0),
        ThermistorPoint(90.0,     207.0),
        source_note="MS4X publishes the BMW M52/M52TU/M54 CLT resistance curve for the MS42/MS43 828 ohm pull-up context.",
        source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
        applicable_sensors=(CalibrationSensor.CLT,),
    ),
    ThermistorPreset(
        "Bosch 4 Bar TMAP IAT",
        2490.0,
        ThermistorPoint(-40.0, 45_395.0),
        ThermistorPoint(20.0,   2_500.0),
        ThermistorPoint(80.0,     323.0),
        source_note="MS4X publishes the Bosch 4 Bar TMAP IAT resistance curve for the MS42/MS43 2.49k pull-up context.",
        source_url="https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data",
        applicable_sensors=(CalibrationSensor.IAT,),
    ),
)

PRESET_NAMES: tuple[str, ...] = tuple(p.name for p in PRESETS)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class ThermistorCalibrationResult:
    """Generated 32-point calibration table ready to send to the ECU.

    ``temperatures_c`` is ordered from ADC=0 (high resistance, cold / open)
    to ADC=1023 (low resistance, hot / shorted).  Index *i* corresponds to
    ADC value ``i × 33``.
    """
    sensor: CalibrationSensor
    preset_name: str
    temperatures_c: tuple[float, ...]   # 32 values, each in °C

    # ------------------------------------------------------------------
    # Payload encoding
    # ------------------------------------------------------------------

    def encode_payload(self) -> bytes:
        """Return 64 bytes: 32 × big-endian int16 temperatures in °F × 10.

        This is the exact format expected by Speeduino's
        ``processTemperatureCalibrationTableUpdate`` function (comms.cpp).
        Each value is a signed 16-bit integer (two's complement, big-endian)
        representing the temperature in degrees Fahrenheit multiplied by 10.
        Sub-zero Fahrenheit values are encoded as two's complement so they
        decode correctly on the firmware side.
        """
        import struct
        result = bytearray()
        for t_c in self.temperatures_c:
            t_f = t_c * 9.0 / 5.0 + 32.0
            val = max(-32768, min(32767, round(t_f * 10)))
            result += struct.pack(">h", val)
        return bytes(result)

    def build_serial_command(self) -> bytes:
        """Return the full 71-byte ``'t'`` serial command packet.

        Structure (Speeduino comms.cpp protocol):
          [0]    = 't'
          [1]    = 0x00 (reserved)
          [2]    = calibrationPage (0=CLT, 1=IAT)
          [3-4]  = offset, big-endian (always 0)
          [5-6]  = calibrationLength, big-endian (always 64)
          [7-70] = 64 bytes of temperature data
        """
        payload = self.encode_payload()
        length = len(payload)  # 64
        header = bytes([
            ord("t"),
            0x00,
            int(self.sensor),
            0x00, 0x00,                           # offset big-endian
            (length >> 8) & 0xFF, length & 0xFF,  # length big-endian
        ])
        return header + payload

    def preview_points(self) -> tuple[tuple[int, float], ...]:
        """Return (adc, temp_c) for a handful of representative points.

        Useful for displaying a quick table summary in the UI.
        """
        indices = [0, 4, 8, 12, 15, 16, 20, 24, 28, 31]
        return tuple(
            (i * 33, self.temperatures_c[i])
            for i in indices
            if i < len(self.temperatures_c)
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ThermistorCalibrationService:
    """Generates Speeduino-format thermistor calibration tables.

    Uses the Steinhart-Hart equation to interpolate temperature from
    resistance across the full ADC range given three reference points and
    a pull-up resistor value.

    Usage::

        svc = ThermistorCalibrationService()
        preset = svc.preset_by_name("GM")
        result = svc.generate(preset, CalibrationSensor.CLT)
        packet = result.build_serial_command()
        transport.write(packet)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def presets(self) -> tuple[ThermistorPreset, ...]:
        return PRESETS

    def presets_for_sensor(self, sensor: CalibrationSensor) -> tuple[ThermistorPreset, ...]:
        return tuple(
            preset for preset in PRESETS
            if sensor in preset.applicable_sensors
        )

    @staticmethod
    def source_confidence_label(preset: ThermistorPreset) -> str:
        if preset.source_url is None:
            return "Generic"
        domain = urlparse(preset.source_url).netloc.lower()
        if "ms4x.net" in domain:
            return "Trusted Secondary"
        return "Sourced"

    def preset_by_name(self, name: str) -> ThermistorPreset | None:
        """Return the preset with the given name, or None."""
        for p in PRESETS:
            if p.name == name:
                return p
        return None

    def generate(
        self,
        preset: ThermistorPreset,
        sensor: CalibrationSensor,
    ) -> ThermistorCalibrationResult:
        """Generate a 32-point calibration table from a preset or custom definition.

        Parameters
        ----------
        preset:
            Thermistor definition including pullup resistor and three
            temperature/resistance reference points.
        sensor:
            Which Speeduino calibration page to target (CLT or IAT).

        Returns
        -------
        ThermistorCalibrationResult
            Always returns a result; edge cases (sensor open/shorted) are
            clamped to the table limits (–40 °C / 350 °C).
        """
        A, B, C = self._steinhart_hart_coefficients(
            preset.point1, preset.point2, preset.point3
        )
        temps: list[float] = []
        for i in range(_ADC_COUNT):
            adc = i * 33  # Speeduino bins: 0, 33, 66, …, 1023
            t = self._temp_at_adc(adc, preset.pullup_ohms, A, B, C)
            t = max(_TEMP_MIN_C, min(_TEMP_MAX_C, t))
            temps.append(round(t, 1))
        return ThermistorCalibrationResult(
            sensor=sensor,
            preset_name=preset.name,
            temperatures_c=tuple(temps),
        )

    # ------------------------------------------------------------------
    # Steinhart-Hart implementation
    # ------------------------------------------------------------------

    @staticmethod
    def _steinhart_hart_coefficients(
        p1: ThermistorPoint,
        p2: ThermistorPoint,
        p3: ThermistorPoint,
    ) -> tuple[float, float, float]:
        """Solve for Steinhart-Hart A, B, C from three (T, R) points.

        All temperatures are converted to Kelvin internally.
        """
        L1 = math.log(p1.resistance_ohms)
        L2 = math.log(p2.resistance_ohms)
        L3 = math.log(p3.resistance_ohms)
        Y1 = 1.0 / (p1.temp_c + _KELVIN_OFFSET)
        Y2 = 1.0 / (p2.temp_c + _KELVIN_OFFSET)
        Y3 = 1.0 / (p3.temp_c + _KELVIN_OFFSET)

        g2 = (Y2 - Y1) / (L2 - L1)
        g3 = (Y3 - Y1) / (L3 - L1)

        C = (g3 - g2) / (L3 - L2) / (L1 + L2 + L3)
        B = g2 - C * (L1**2 + L1 * L2 + L2**2)
        A = Y1 - (B + L1**2 * C) * L1
        return A, B, C

    @staticmethod
    def _temp_at_adc(
        adc: int,
        pullup_ohms: float,
        A: float,
        B: float,
        C: float,
    ) -> float:
        """Temperature in °C for a given ADC reading using the S-H equation.

        Edge cases:
        - ADC = 0   → sensor open circuit → return maximum table value
        - ADC ≥ 1023 → sensor short circuit → return minimum table value
        """
        if adc == 0:
            return _TEMP_MAX_C
        if adc >= _ADC_MAX:
            return _TEMP_MIN_C
        V = adc * _SUPPLY_V / _ADC_MAX
        R = pullup_ohms * V / (_SUPPLY_V - V)
        if R <= 0.0:
            return _TEMP_MAX_C
        L = math.log(R)
        T_inv = A + B * L + C * L**3
        if T_inv == 0.0:
            return _TEMP_MAX_C
        T_kelvin = 1.0 / T_inv
        return T_kelvin - _KELVIN_OFFSET
