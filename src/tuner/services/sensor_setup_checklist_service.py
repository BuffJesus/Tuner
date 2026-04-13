"""Typed checklist items for sensor hardware setup pages.

Checks
------
- ego_type_configured: O2/EGO sensor type is set and not disabled
- wideband_cal:        Wideband calibration set when EGO type is wideband
- stoich_plausible:    Stoich AFR is within a physically plausible range (6–22)
- flex_calibration:    Flex fuel sensor frequency calibration is valid when enabled
- tps_range:           TPS min/max spread is >= 50 ADC counts (avoids zero-range errors)
- map_range:           MAP min/max kPa range is positive and non-trivial
- knock_pin_sensor:    Knock input pin assigned when knock mode is enabled
- oil_calibration:     Oil pressure min/max is valid when sensor is enabled
- baro_calibration:    External baro min/max is valid when sensor is enabled
"""
from __future__ import annotations

from tuner.domain.setup_checklist import ChecklistItemStatus, SetupChecklistItem
from tuner.domain.tuning_pages import TuningPage, TuningPageParameter
from tuner.services.local_tune_edit_service import LocalTuneEditService


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find(page: TuningPage, keywords: tuple[str, ...]) -> TuningPageParameter | None:
    lowered = tuple(k.lower() for k in keywords)
    for parameter in page.parameters:
        haystack = f"{parameter.name} {parameter.label}".lower()
        if any(kw in haystack for kw in lowered):
            return parameter
    return None


def _find_any(pages: tuple[TuningPage, ...], keywords: tuple[str, ...]) -> TuningPageParameter | None:
    for page in pages:
        result = _find(page, keywords)
        if result is not None:
            return result
    return None


def _numeric(
    parameter: TuningPageParameter | None,
    edits: LocalTuneEditService,
) -> float | None:
    if parameter is None:
        return None
    tv = edits.get_value(parameter.name)
    if tv is None:
        return None
    if isinstance(tv.value, (int, float)):
        return float(tv.value)
    return None


def _option_label(
    parameter: TuningPageParameter | None,
    edits: LocalTuneEditService,
) -> str | None:
    if parameter is None:
        return None
    tv = edits.get_value(parameter.name)
    if tv is None:
        return None
    if parameter.options and isinstance(tv.value, (int, float)):
        value_text = str(int(tv.value)) if float(tv.value).is_integer() else str(tv.value)
        option_values = parameter.option_values or tuple(str(index) for index, _ in enumerate(parameter.options))
        for label, option_value in zip(parameter.options, option_values):
            if option_value == value_text:
                return label
        idx = int(tv.value)
        if 0 <= idx < len(parameter.options):
            return parameter.options[idx]
    return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SensorSetupChecklistService:
    """Produce typed checklist items for sensor hardware setup pages.

    Call :meth:`validate` with the sensor pages (may be a single page or
    several) and the live tune edit service.

    Returns a tuple of :class:`~tuner.domain.setup_checklist.SetupChecklistItem`
    objects ordered from most critical to least.
    """

    def validate(
        self,
        *,
        sensor_pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> tuple[SetupChecklistItem, ...]:
        items: list[SetupChecklistItem] = []

        items.extend(self._check_ego_type(sensor_pages, edits))
        items.extend(self._check_wideband_cal(sensor_pages, edits))
        items.extend(self._check_stoich(sensor_pages, edits))
        items.extend(self._check_flex_calibration(sensor_pages, edits))
        items.extend(self._check_tps(sensor_pages, edits))
        items.extend(self._check_map(sensor_pages, edits))
        items.extend(self._check_knock_pin(sensor_pages, edits))
        items.extend(self._check_oil_calibration(sensor_pages, edits))
        items.extend(self._check_baro_calibration(sensor_pages, edits))

        return tuple(items)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_ego_type(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        param = _find_any(pages, ("egotype", "afrsensortype", "o2sensortype", "lambdatype"))
        if param is None:
            return []
        val = _numeric(param, edits)
        if val is None:
            return [SetupChecklistItem(
                key="ego_type_configured",
                title="Set O2/EGO sensor type",
                status=ChecklistItemStatus.NEEDED,
                detail="Select the O2 sensor type (Narrow Band, Wide Band, or Disabled).",
                parameter_name=param.name,
            )]
        ego_type = int(val)
        if ego_type == 0:
            return [SetupChecklistItem(
                key="ego_type_configured",
                title="O2 sensor disabled",
                status=ChecklistItemStatus.INFO,
                detail="EGO/O2 sensor is disabled. Enable it for closed-loop fueling or wideband logging.",
                parameter_name=param.name,
            )]
        label = param.options[ego_type] if param.options and ego_type < len(param.options) else (
            "Narrow Band" if ego_type == 1 else "Wide Band" if ego_type == 2 else f"type {ego_type}"
        )
        return [SetupChecklistItem(
            key="ego_type_configured",
            title="O2/EGO type set",
            status=ChecklistItemStatus.OK,
            detail=f"O2 sensor configured as {label}.",
            parameter_name=param.name,
        )]

    @staticmethod
    def _check_wideband_cal(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        ego_param = _find_any(pages, ("egotype", "afrsensortype", "o2sensortype", "lambdatype"))
        ego_val = _numeric(ego_param, edits)
        if ego_val is None or int(ego_val) != 2:
            return []  # Only check when wideband is selected

        cal_param = _find_any(pages, ("afrCal", "wbCal", "widebandcal", "lambdacal"))
        if cal_param is None:
            return [SetupChecklistItem(
                key="wideband_cal",
                title="Wideband calibration parameter not found",
                status=ChecklistItemStatus.WARNING,
                detail="Wide band EGO is selected but no calibration parameter was found on these pages. "
                       "Verify the calibration table is set on the sensor page.",
                parameter_name=None,
            )]
        cal_val = _numeric(cal_param, edits)
        if cal_val is None or cal_val == 0:
            return [SetupChecklistItem(
                key="wideband_cal",
                title="Set wideband calibration",
                status=ChecklistItemStatus.NEEDED,
                detail="Wide band EGO is selected but the calibration value is zero or missing. "
                       "Match the calibration to your wideband sensor model.",
                parameter_name=cal_param.name,
            )]
        return [SetupChecklistItem(
            key="wideband_cal",
            title="Wideband calibration set",
            status=ChecklistItemStatus.OK,
            detail=f"Wideband calibration is set (value: {cal_val:.0f}).",
            parameter_name=cal_param.name,
        )]

    @staticmethod
    def _check_stoich(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        param = _find_any(pages, ("stoich",))
        if param is None:
            return []
        val = _numeric(param, edits)
        if val is None:
            return []
        if val < 6.0 or val > 22.0:
            return [SetupChecklistItem(
                key="stoich_plausible",
                title="Stoich AFR looks incorrect",
                status=ChecklistItemStatus.WARNING,
                detail=f"Stoich AFR is {val:.1f}:1. Expected range: ~6.5 (methanol) to 22 (hydrogen). "
                       "Petrol ≈ 14.7, E85 ≈ 9.8.",
                parameter_name=param.name,
            )]
        if 14.0 <= val <= 15.2:
            fuel_label = "petrol"
        elif 9.0 <= val <= 10.5:
            fuel_label = "E85"
        elif val <= 7.0:
            fuel_label = "methanol"
        else:
            fuel_label = "fuel"
        return [SetupChecklistItem(
            key="stoich_plausible",
            title="Stoich AFR plausible",
            status=ChecklistItemStatus.OK,
            detail=f"Stoich AFR is {val:.1f}:1 ({fuel_label}).",
            parameter_name=param.name,
        )]

    @staticmethod
    def _check_flex_calibration(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        enabled_param = _find_any(pages, ("flexenabled", "flexsensor", "ethanolsensor"))
        if enabled_param is None:
            return []
        enabled_val = _numeric(enabled_param, edits)
        if enabled_val is None or enabled_val <= 0:
            return []

        low_param = _find_any(pages, ("flexfreqlow", "ethanolfreqlow"))
        high_param = _find_any(pages, ("flexfreqhigh", "ethanolfreqhigh"))
        if low_param is None or high_param is None:
            return [SetupChecklistItem(
                key="flex_calibration",
                title="Verify flex sensor calibration",
                status=ChecklistItemStatus.WARNING,
                detail="Flex fuel is enabled but the low/high ethanol frequency calibration is not exposed on these pages.",
                parameter_name=enabled_param.name,
            )]

        low = _numeric(low_param, edits)
        high = _numeric(high_param, edits)
        if low is None or high is None:
            return [SetupChecklistItem(
                key="flex_calibration",
                title="Set flex sensor frequency calibration",
                status=ChecklistItemStatus.NEEDED,
                detail="Flex fuel is enabled but the low or high frequency value is missing.",
                parameter_name=low_param.name,
            )]
        if high <= low:
            return [SetupChecklistItem(
                key="flex_calibration",
                title="Flex sensor calibration invalid",
                status=ChecklistItemStatus.ERROR,
                detail=f"Flex sensor high frequency ({high:.0f} Hz) must be greater than low frequency ({low:.0f} Hz).",
                parameter_name=low_param.name,
            )]
        if low < 10.0 or high > 250.0:
            return [SetupChecklistItem(
                key="flex_calibration",
                title="Review flex sensor calibration",
                status=ChecklistItemStatus.WARNING,
                detail=f"Flex sensor frequency span is {low:.0f}–{high:.0f} Hz. Standard GM/Continental sensors are typically 50–150 Hz.",
                parameter_name=low_param.name,
            )]
        return [SetupChecklistItem(
            key="flex_calibration",
            title="Flex sensor calibration OK",
            status=ChecklistItemStatus.OK,
            detail=f"Flex sensor frequency span is {low:.0f}–{high:.0f} Hz.",
            parameter_name=low_param.name,
        )]

    @staticmethod
    def _check_tps(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        min_param = _find_any(pages, ("tpsmin", "tps_min", "throttlemin"))
        max_param = _find_any(pages, ("tpsmax", "tps_max", "throttlemax"))
        if min_param is None or max_param is None:
            return []
        tps_min = _numeric(min_param, edits)
        tps_max = _numeric(max_param, edits)
        if tps_min is None or tps_max is None:
            return []
        spread = tps_max - tps_min
        if spread < 0:
            return [SetupChecklistItem(
                key="tps_range",
                title="TPS calibration inverted",
                status=ChecklistItemStatus.ERROR,
                detail=f"TPS max ({tps_max:.0f}) is less than TPS min ({tps_min:.0f}). "
                       "Closed throttle should be the lower ADC count — swap the values.",
                parameter_name=min_param.name,
            )]
        if spread < 50:
            return [SetupChecklistItem(
                key="tps_range",
                title="TPS calibration range too narrow",
                status=ChecklistItemStatus.WARNING,
                detail=f"TPS span is only {spread:.0f} ADC counts (min={tps_min:.0f}, max={tps_max:.0f}). "
                       "Most sensors span 500+ counts; a narrow range reduces pedal resolution.",
                parameter_name=min_param.name,
            )]
        return [SetupChecklistItem(
            key="tps_range",
            title="TPS calibration range OK",
            status=ChecklistItemStatus.OK,
            detail=f"TPS span is {spread:.0f} ADC counts (min={tps_min:.0f}, max={tps_max:.0f}).",
            parameter_name=min_param.name,
        )]

    @staticmethod
    def _check_map(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        min_param = _find_any(pages, ("mapmin", "map_min"))
        max_param = _find_any(pages, ("mapmax", "map_max"))
        if min_param is None or max_param is None:
            return []
        map_min = _numeric(min_param, edits)
        map_max = _numeric(max_param, edits)
        if map_min is None or map_max is None:
            return []
        spread = map_max - map_min
        if spread <= 0:
            return [SetupChecklistItem(
                key="map_range",
                title="MAP calibration range invalid",
                status=ChecklistItemStatus.ERROR,
                detail=f"MAP max ({map_max:.0f} kPa) must be greater than MAP min ({map_min:.0f} kPa). "
                       "Correct the values to match your sensor's output voltage range.",
                parameter_name=min_param.name,
            )]
        if spread < 50:
            return [SetupChecklistItem(
                key="map_range",
                title="MAP calibration range looks narrow",
                status=ChecklistItemStatus.WARNING,
                detail=f"MAP range is only {spread:.0f} kPa ({map_min:.0f}–{map_max:.0f}). "
                       "A 100–300 kPa range is typical for NA; boost applications need higher max kPa.",
                parameter_name=min_param.name,
            )]
        return [SetupChecklistItem(
            key="map_range",
            title="MAP calibration range OK",
            status=ChecklistItemStatus.OK,
            detail=f"MAP sensor calibrated {map_min:.0f}–{map_max:.0f} kPa ({spread:.0f} kPa span).",
            parameter_name=min_param.name,
        )]

    @staticmethod
    def _check_knock_pin(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        """Check knock sensor pin assignment from the sensor-page perspective."""
        mode_param = _find_any(pages, ("knock_mode", "knockmode", "knocksensormode"))
        if mode_param is None:
            return []
        mode_val = _numeric(mode_param, edits)
        if mode_val is None or int(mode_val) == 0:
            return []  # Knock disabled — not a sensor issue

        mode_label = "Digital" if int(mode_val) == 1 else "Analog"
        pin_keywords: tuple[str, ...]
        if int(mode_val) == 1:
            pin_keywords = ("knock_digital_pin", "knockdigitalpin", "knockpindigital")
        else:
            pin_keywords = ("knock_analog_pin", "knockanalogpin", "knockpinanalog")

        pin_param = _find_any(pages, pin_keywords)
        if pin_param is None:
            return [SetupChecklistItem(
                key="knock_pin_sensor",
                title="Knock pin parameter not visible",
                status=ChecklistItemStatus.WARNING,
                detail=f"Knock mode is {mode_label} but the pin parameter is not on these pages. "
                       "Verify the pin assignment on the Hardware Setup ignition page.",
                parameter_name=mode_param.name,
            )]
        pin_label = _option_label(pin_param, edits)
        if pin_label is not None and pin_label.upper() in ("INVALID", "NONE", "DISABLED", ""):
            return [SetupChecklistItem(
                key="knock_pin_sensor",
                title="Assign knock sensor input pin",
                status=ChecklistItemStatus.NEEDED,
                detail=f"Knock mode is {mode_label} but no input pin is assigned. "
                       "Select the pin the knock sensor is wired to.",
                parameter_name=pin_param.name,
            )]
        pin_val = _numeric(pin_param, edits)
        display = pin_label or (str(int(pin_val)) if pin_val is not None else "?")
        return [SetupChecklistItem(
            key="knock_pin_sensor",
            title="Knock sensor pin assigned",
            status=ChecklistItemStatus.OK,
            detail=f"Knock sensor ({mode_label}) assigned to pin {display}.",
            parameter_name=pin_param.name,
        )]

    @staticmethod
    def _check_oil_calibration(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        enable_param = _find_any(pages, ("oilpressureenable", "oilpressureenabled", "useoilpressure"))
        if enable_param is None:
            return []
        enable_val = _numeric(enable_param, edits)
        if enable_val is None or int(enable_val) == 0:
            return []  # Disabled

        min_param = _find_any(pages, ("oilpressuremin", "oilpressure_min"))
        max_param = _find_any(pages, ("oilpressuremax", "oilpressure_max"))
        oil_min = _numeric(min_param, edits)
        oil_max = _numeric(max_param, edits)

        if oil_min is None or oil_max is None:
            return [SetupChecklistItem(
                key="oil_calibration",
                title="Oil pressure calibration incomplete",
                status=ChecklistItemStatus.NEEDED,
                detail="Oil pressure sensor is enabled but min/max calibration values are missing.",
                parameter_name=enable_param.name,
            )]
        if oil_max <= oil_min:
            return [SetupChecklistItem(
                key="oil_calibration",
                title="Oil pressure calibration range invalid",
                status=ChecklistItemStatus.ERROR,
                detail=f"Oil pressure max ({oil_max:.1f} bar) must be greater than min ({oil_min:.1f} bar). "
                       "Check sensor voltage range against the physical pressure range.",
                parameter_name=min_param.name if min_param else None,
            )]
        return [SetupChecklistItem(
            key="oil_calibration",
            title="Oil pressure calibration OK",
            status=ChecklistItemStatus.OK,
            detail=f"Oil pressure sensor calibrated {oil_min:.1f}–{oil_max:.1f} bar.",
            parameter_name=enable_param.name,
        )]

    @staticmethod
    def _check_baro_calibration(
        pages: tuple[TuningPage, ...],
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        enable_param = _find_any(pages, ("useextbaro", "extbaroenable", "useexternalbaro", "barosensorenable"))
        if enable_param is None:
            return []
        enable_val = _numeric(enable_param, edits)
        if enable_val is None or int(enable_val) == 0:
            return []  # Disabled

        min_param = _find_any(pages, ("baromin", "baro_min", "extbaromin"))
        max_param = _find_any(pages, ("baromax", "baro_max", "extbaromax"))
        baro_min = _numeric(min_param, edits)
        baro_max = _numeric(max_param, edits)

        if baro_min is None or baro_max is None:
            return [SetupChecklistItem(
                key="baro_calibration",
                title="Baro sensor calibration incomplete",
                status=ChecklistItemStatus.NEEDED,
                detail="External barometric sensor is enabled but min/max calibration values are missing.",
                parameter_name=enable_param.name,
            )]
        if baro_max <= baro_min:
            return [SetupChecklistItem(
                key="baro_calibration",
                title="Baro sensor calibration range invalid",
                status=ChecklistItemStatus.ERROR,
                detail=f"Baro max ({baro_max:.0f} kPa) must be greater than min ({baro_min:.0f} kPa).",
                parameter_name=min_param.name if min_param else None,
            )]
        return [SetupChecklistItem(
            key="baro_calibration",
            title="Baro sensor calibration OK",
            status=ChecklistItemStatus.OK,
            detail=f"External baro sensor calibrated {baro_min:.0f}–{baro_max:.0f} kPa.",
            parameter_name=enable_param.name,
        )]
