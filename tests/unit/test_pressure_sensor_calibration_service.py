from __future__ import annotations

from tuner.services.hardware_preset_service import HardwarePresetService
from tuner.services.pressure_sensor_calibration_service import PressureSensorCalibrationService


def test_map_assessment_matches_curated_preset() -> None:
    assessment = PressureSensorCalibrationService().assess(
        minimum_value=20.0,
        maximum_value=250.0,
        presets=HardwarePresetService().map_sensor_presets(),
        sensor_kind="map",
    )
    assert assessment.matching_preset is not None
    assert assessment.matching_preset.key == "nxp_mpxh6250a_dropbear"
    assert "matches" in assessment.guidance.lower()
    assert assessment.warning is None


def test_baro_assessment_warns_for_wide_nonstandard_range() -> None:
    assessment = PressureSensorCalibrationService().assess(
        minimum_value=20.0,
        maximum_value=250.0,
        presets=HardwarePresetService().baro_sensor_presets(),
        sensor_kind="baro",
    )
    assert assessment.matching_preset is not None
    assert "matches" in assessment.guidance.lower()
    assert assessment.warning is not None
    assert "atmospheric" in assessment.warning.lower()
