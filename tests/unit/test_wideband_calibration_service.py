"""Tests for WidebandCalibrationService — wideband O2 calibration table
generation for Speeduino calibration page 2.
"""
from __future__ import annotations

import struct

import pytest

from tuner.services.wideband_calibration_service import (
    PRESETS,
    PRESET_NAMES,
    WidebandCalibrationPage,
    WidebandCalibrationService,
    WidebandPreset,
)


class TestPresetCatalog:
    def test_at_least_five_presets(self) -> None:
        assert len(PRESETS) >= 5
        assert len(PRESET_NAMES) == len(PRESETS)

    def test_preset_lookup_by_name(self) -> None:
        svc = WidebandCalibrationService()
        for preset in PRESETS:
            assert svc.preset_by_name(preset.name) is preset

    def test_preset_lookup_unknown_returns_none(self) -> None:
        assert WidebandCalibrationService().preset_by_name("Bogus 9000") is None


class TestGenerate:
    def test_generates_32_entries(self) -> None:
        svc = WidebandCalibrationService()
        for preset in PRESETS:
            result = svc.generate(preset)
            assert len(result.afrs) == 32

    def test_zero_voltage_span_raises(self) -> None:
        bad = WidebandPreset(
            name="bad", voltage_low=2.5, afr_at_voltage_low=14.7,
            voltage_high=2.5, afr_at_voltage_high=14.7,
        )
        with pytest.raises(ValueError, match="zero voltage span"):
            WidebandCalibrationService().generate(bad)

    def test_aem_linear_endpoints_match_published_curve(self) -> None:
        """AEM 30-0300: 0 V → 10 AFR, 5 V → 20 AFR, 2.5 V → 15 AFR."""
        svc = WidebandCalibrationService()
        preset = svc.preset_by_name("AEM 30-0300 / 30-4110 / X-Series")
        assert preset is not None
        result = svc.generate(preset)
        assert result.afrs[0] == 10.0           # ADC=0   → 0 V
        assert result.afrs[-1] == 20.0          # ADC=1023 → 5 V
        # Halfway point ≈ 15 AFR (allow 1 bin worth of rounding)
        midpoint = result.afr_at_voltage(2.5)
        assert abs(midpoint - 15.0) < 0.5

    def test_innovate_linear_endpoints(self) -> None:
        svc = WidebandCalibrationService()
        preset = svc.preset_by_name("Innovate LC-1 / LC-2 / LM-1 / LM-2 (default)")
        assert preset is not None
        result = svc.generate(preset)
        assert result.afrs[0] == 7.35
        assert result.afrs[-1] == 22.39

    def test_monotonic_for_lean_going_preset(self) -> None:
        """Every Innovate-style preset has AFR rising with voltage; the
        generated table must be monotonically non-decreasing."""
        svc = WidebandCalibrationService()
        result = svc.generate(svc.preset_by_name(
            "Innovate LC-1 / LC-2 / LM-1 / LM-2 (default)"
        ))
        for a, b in zip(result.afrs, result.afrs[1:]):
            assert b >= a


class TestEncoding:
    def test_payload_is_64_bytes(self) -> None:
        svc = WidebandCalibrationService()
        for preset in PRESETS:
            payload = svc.generate(preset).encode_payload()
            assert len(payload) == 64

    def test_payload_is_big_endian_int16_afr_x10(self) -> None:
        svc = WidebandCalibrationService()
        result = svc.generate(svc.preset_by_name("AEM 30-0300 / 30-4110 / X-Series"))
        payload = result.encode_payload()
        # First entry corresponds to AFR=10 → 100 → big-endian int16
        first = struct.unpack(">h", payload[:2])[0]
        assert first == 100
        # Last entry → AFR=20 → 200
        last = struct.unpack(">h", payload[-2:])[0]
        assert last == 200

    def test_serial_command_header_targets_o2_page(self) -> None:
        svc = WidebandCalibrationService()
        result = svc.generate(svc.preset_by_name("AEM 30-0300 / 30-4110 / X-Series"))
        cmd = result.build_serial_command()
        assert len(cmd) == 71  # 7 byte header + 64 byte payload
        assert cmd[0:1] == b"t"
        assert cmd[1] == 0x00
        assert cmd[2] == int(WidebandCalibrationPage.O2)  # page 2
        assert cmd[3:5] == b"\x00\x00"          # offset
        assert cmd[5:7] == b"\x00\x40"          # length 64 big-endian


class TestActiveBandClamping:
    def test_spartan2_outside_active_range_clamps_to_endpoints(self) -> None:
        """A 14Point7-style preset with a 0.5–4.5 V active band would
        normally extrapolate outside that band; the implementation
        clamps to the endpoint AFR instead. We don't ship a 0.5/4.5
        preset by default, but we verify the clamp on a custom preset."""
        custom = WidebandPreset(
            name="Custom 0.5–4.5",
            voltage_low=0.5, afr_at_voltage_low=10.0,
            voltage_high=4.5, afr_at_voltage_high=20.0,
        )
        svc = WidebandCalibrationService()
        result = svc.generate(custom)
        # ADC=0 → 0 V, below voltage_low → clamps to 10.0
        assert result.afrs[0] == 10.0
        # ADC=1023 → ~5 V, above voltage_high → clamps to 20.0
        assert result.afrs[-1] == 20.0
