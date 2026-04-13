from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tuner.services.hardware_preset_service import HardwarePresetService, PressureSensorPreset


@dataclass(slots=True, frozen=True)
class PressureCalibrationAssessment:
    minimum_value: float | None
    maximum_value: float | None
    matching_preset: PressureSensorPreset | None
    guidance: str
    warning: str | None = None


class PressureSensorCalibrationService:
    """Matches live MAP/baro calibration values to curated sensor presets."""

    _MATCH_TOLERANCE_KPA = 0.5

    def assess(
        self,
        *,
        minimum_value: float | None,
        maximum_value: float | None,
        presets: tuple[PressureSensorPreset, ...],
        sensor_kind: Literal["map", "baro"],
    ) -> PressureCalibrationAssessment:
        if minimum_value is None or maximum_value is None:
            return PressureCalibrationAssessment(
                minimum_value=minimum_value,
                maximum_value=maximum_value,
                matching_preset=None,
                guidance=f"No {sensor_kind.upper()} calibration range is available yet.",
            )

        preset = self.find_matching_preset(
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            presets=presets,
        )
        warning: str | None = None
        if sensor_kind == "baro" and maximum_value > 150.0:
            warning = (
                "External baro calibration spans well beyond normal atmospheric pressure. "
                "Verify that a dedicated MAP/TMAP-style sensor is intentionally being used for baro."
            )
        if preset is not None:
            confidence = HardwarePresetService.source_confidence_label(
                source_note=preset.source_note,
                source_url=preset.source_url,
            )
            return PressureCalibrationAssessment(
                minimum_value=minimum_value,
                maximum_value=maximum_value,
                matching_preset=preset,
                guidance=(
                    f"Current {sensor_kind.upper()} calibration matches {preset.label} "
                    f"({preset.minimum_value:.0f}-{preset.maximum_value:.0f} {preset.units}). "
                    f"[{confidence}] {preset.source_note}"
                ),
                warning=warning,
            )

        return PressureCalibrationAssessment(
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            matching_preset=None,
            guidance=(
                f"Current {sensor_kind.upper()} calibration is {minimum_value:.0f}-{maximum_value:.0f} kPa "
                "and does not match a curated preset."
            ),
            warning=warning,
        )

    def find_matching_preset(
        self,
        *,
        minimum_value: float,
        maximum_value: float,
        presets: tuple[PressureSensorPreset, ...],
    ) -> PressureSensorPreset | None:
        for preset in presets:
            if (
                abs(preset.minimum_value - minimum_value) <= self._MATCH_TOLERANCE_KPA
                and abs(preset.maximum_value - maximum_value) <= self._MATCH_TOLERANCE_KPA
            ):
                return preset
        return None
