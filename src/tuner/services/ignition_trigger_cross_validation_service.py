"""Cross-validates ignition and trigger hardware setup pages together.

Individual page validation (`HardwareSetupValidationService`) checks each page
in isolation.  This service checks relationships *between* the ignition and
trigger pages — things that neither page can catch alone.

Checks performed
----------------
- Dwell configured
  Dwell on the ignition page must be non-zero.

- Reference angle configured
  A trigger/reference angle must be set and non-zero (or explained).

- Trigger geometry valid
  Tooth count and missing-tooth count must be consistent.

- Knock pin configured when knock is enabled
  If knock mode is active on the ignition page, a knock pin must be set.

- Coil count plausible vs cylinder count
  When a coil-count parameter is present it should be consistent with the
  cylinder count (if known).

- Reference angle range plausible
  Trigger reference angle should be in a realistic BTDC range (0°–50°).  Larger
  values are not impossible but indicate potential configuration errors.

- Cam sync required for sequential operation
  Sequential injection (injLayout == 3) or sequential ignition (sparkMode == 3)
  require the ECU to know which stroke each cylinder is on.  Crank-only
  decoders cannot provide this.  Decoders with configurable secondary trigger
  (Missing Tooth at crank speed, Rover MEMS) must have a cam signal configured.

- Trigger topology summary
  Informational description of the combined crank/cam trigger setup, e.g.
  "36-1 crank-speed trigger with single-tooth cam sync".
"""
from __future__ import annotations

from tuner.domain.setup_checklist import ChecklistItemStatus, SetupChecklistItem
from tuner.domain.tuning_pages import TuningPage, TuningPageParameter
from tuner.services.local_tune_edit_service import LocalTuneEditService

# ---------------------------------------------------------------------------
# Speeduino TrigPattern index → human name
# Derived from the Speeduino u16p2 INI TrigPattern bits definition.
# ---------------------------------------------------------------------------

_TRIGGER_PATTERN_NAMES: dict[int, str] = {
    0:  "Missing Tooth",
    1:  "Basic Distributor",
    2:  "Dual Wheel",
    3:  "GM 7X",
    4:  "4G63 / Miata / 3000GT",
    5:  "GM 24X",
    6:  "Jeep 2000",
    7:  "Audi 135",
    8:  "Honda D17",
    9:  "Miata 99-05",
    10: "Mazda AU",
    11: "Non-360 Dual",
    12: "Nissan 360",
    13: "Subaru 6/7",
    14: "Daihatsu +1",
    15: "Harley EVO",
    16: "36-2-2-2",
    17: "36-2-1",
    18: "DSM 420a",
    19: "Weber-Marelli",
    20: "Ford ST170",
    21: "DRZ400",
    22: "Chrysler NGC",
    23: "Yamaha Vmax 1990+",
    24: "Renix",
    25: "Rover MEMS",
    26: "K6A",
    27: "Honda J32",
}

# trigPatternSec index → human name
_SECONDARY_TRIGGER_NAMES: dict[int, str] = {
    0: "Single tooth cam",
    1: "4-1 cam",
    2: "Poll level (cam level sensor)",
    3: "Rover 5-3-2 cam",
    4: "Toyota 3 Tooth",
}

# TrigPattern values where the secondary trigger is configured via trigPatternSec
# (Missing Tooth at crank speed and Rover MEMS).  All others either have
# inherent cam knowledge or no cam input at all.
_CAM_CONFIGURABLE_PATTERNS: frozenset[int] = frozenset({0, 25})

# Decoders that determine engine phase internally (no separate trigPatternSec
# needed for sequential operation).
_CAM_INHERENT_PATTERNS: frozenset[int] = frozenset({
    2,   # Dual Wheel — second wheel is the cam wheel
    4,   # 4G63 / Miata / 3000GT — inherent cam pattern
    8,   # Honda D17
    9,   # Miata 99-05
    11,  # Non-360 Dual
    12,  # Nissan 360
    13,  # Subaru 6/7
    14,  # Daihatsu +1
    18,  # DSM 420a
    19,  # Weber-Marelli
    20,  # Ford ST170
    21,  # DRZ400
    22,  # Chrysler NGC
    24,  # Renix
    26,  # K6A
    27,  # Honda J32
})

# Decoders that are crank-only and cannot determine engine phase.
# Sequential injection/ignition is not possible without an additional cam input
# that Speeduino cannot use with these patterns.
_CRANK_ONLY_PATTERNS: frozenset[int] = frozenset({
    3,   # GM 7X — 7 crank teeth only
    5,   # GM 24X — 24 crank teeth only
    6,   # Jeep 2000
    7,   # Audi 135
    10,  # Mazda AU
    15,  # Harley EVO
    16,  # 36-2-2-2
    17,  # 36-2-1
    23,  # Yamaha Vmax 1990+
})

# Basic Distributor (1) is deliberately excluded from _CRANK_ONLY_PATTERNS:
# a distributor provides per-cylinder phasing inherently via its rotor position,
# so sequential injection is possible in principle.


def _find(page: TuningPage, keywords: tuple[str, ...]) -> TuningPageParameter | None:
    lowered = tuple(k.lower() for k in keywords)
    for parameter in page.parameters:
        haystack = f"{parameter.name} {parameter.label}".lower()
        if any(kw in haystack for kw in lowered):
            return parameter
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
    """Return the selected option label for an enum/bits parameter, or None."""
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


class IgnitionTriggerCrossValidationService:
    """Produce cross-page checklist items for ignition + trigger setup.

    Call :meth:`validate` with:
    - *ignition_page*: the ignition/spark setup page (may be ``None`` if not loaded)
    - *trigger_page*: the trigger wheel setup page (may be ``None`` if not loaded)
    - *edits*: the live tune edit service

    Returns a tuple of :class:`~tuner.domain.setup_checklist.SetupChecklistItem`
    objects ordered from most critical to least.
    """

    def validate(
        self,
        *,
        ignition_page: TuningPage | None,
        trigger_page: TuningPage | None,
        edits: LocalTuneEditService,
    ) -> tuple[SetupChecklistItem, ...]:
        items: list[SetupChecklistItem] = []

        items.extend(self._check_dwell(ignition_page, trigger_page, edits))
        items.extend(self._check_reference_angle(ignition_page, trigger_page, edits))
        items.extend(self._check_trigger_geometry(trigger_page, edits))
        items.extend(self._check_knock_pin(ignition_page, trigger_page, edits))
        items.extend(self._check_coil_vs_cylinders(ignition_page, trigger_page, edits))
        items.extend(self._check_sequential_cam_sync(ignition_page, trigger_page, edits))
        topology = self._trigger_topology_summary(ignition_page, trigger_page, edits)
        if topology is not None:
            items.append(topology)

        return tuple(items)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_dwell(
        ign: TuningPage | None,
        trig: TuningPage | None,
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        dwell_param = _find(ign, ("dwell", "sparkdur")) if ign else None
        cross = dwell_param is None

        if dwell_param is None and trig is not None:
            dwell_param = _find(trig, ("dwell", "sparkdur"))

        if dwell_param is None:
            return [SetupChecklistItem(
                key="dwell_configured",
                title="Set dwell time",
                status=ChecklistItemStatus.NEEDED,
                detail="No dwell parameter found on the ignition or trigger page. "
                       "Check the coil driver page for dwell settings.",
                cross_page=True,
            )]

        val = _numeric(dwell_param, edits)
        if val is None:
            return [SetupChecklistItem(
                key="dwell_configured",
                title="Set dwell time",
                status=ChecklistItemStatus.NEEDED,
                detail=f"Dwell parameter '{dwell_param.name}' has no value in the tune file.",
                parameter_name=dwell_param.name,
                cross_page=cross,
            )]
        if val == 0.0:
            return [SetupChecklistItem(
                key="dwell_configured",
                title="Set dwell time",
                status=ChecklistItemStatus.ERROR,
                detail=f"Dwell is zero — coils will not charge and the engine will not fire. "
                       f"Enter the coil dwell from the datasheet (typically 2–4 ms).",
                parameter_name=dwell_param.name,
                cross_page=cross,
            )]
        if val > 10.0:
            return [SetupChecklistItem(
                key="dwell_configured",
                title="Check dwell time",
                status=ChecklistItemStatus.ERROR,
                detail=f"Dwell is {val:.1f} ms — this is above the safe maximum (10 ms) and may damage coils.",
                parameter_name=dwell_param.name,
                cross_page=cross,
            )]
        if val < 1.0 or val > 6.0:
            return [SetupChecklistItem(
                key="dwell_configured",
                title="Check dwell time",
                status=ChecklistItemStatus.WARNING,
                detail=f"Dwell is {val:.1f} ms — outside the typical 1–6 ms range. "
                       "Verify against the coil datasheet.",
                parameter_name=dwell_param.name,
                cross_page=cross,
            )]
        return [SetupChecklistItem(
            key="dwell_configured",
            title="Dwell configured",
            status=ChecklistItemStatus.OK,
            detail=f"Dwell is {val:.1f} ms.",
            parameter_name=dwell_param.name,
            cross_page=cross,
        )]

    @staticmethod
    def _check_reference_angle(
        ign: TuningPage | None,
        trig: TuningPage | None,
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        _ANGLE_KEYS = ("triggerangle", "fixang", "crankangle", "tdcangle")
        angle_param = _find(trig, _ANGLE_KEYS) if trig else None
        cross = angle_param is None
        if angle_param is None and ign is not None:
            angle_param = _find(ign, _ANGLE_KEYS)

        if angle_param is None:
            return [SetupChecklistItem(
                key="reference_angle",
                title="Set reference (TDC) angle",
                status=ChecklistItemStatus.NEEDED,
                detail="No trigger reference angle found. "
                       "The ECU needs the TDC reference to calculate ignition timing correctly.",
                cross_page=True,
            )]

        val = _numeric(angle_param, edits)
        if val is None:
            return [SetupChecklistItem(
                key="reference_angle",
                title="Set reference (TDC) angle",
                status=ChecklistItemStatus.NEEDED,
                detail=f"Reference angle '{angle_param.name}' has no value.",
                parameter_name=angle_param.name,
                cross_page=cross,
            )]
        if val == 0.0:
            return [SetupChecklistItem(
                key="reference_angle",
                title="Verify reference angle",
                status=ChecklistItemStatus.WARNING,
                detail="Reference angle is 0°. This is valid for some trigger patterns but "
                       "confirm with a timing light before running under load.",
                parameter_name=angle_param.name,
                cross_page=cross,
            )]
        if val > 50.0:
            return [SetupChecklistItem(
                key="reference_angle",
                title="Check reference angle",
                status=ChecklistItemStatus.WARNING,
                detail=f"Reference angle is {val:.0f}°, which is unusually large. "
                       "Verify this matches your trigger wheel specification.",
                parameter_name=angle_param.name,
                cross_page=cross,
            )]
        return [SetupChecklistItem(
            key="reference_angle",
            title="Reference angle configured",
            status=ChecklistItemStatus.OK,
            detail=f"Reference angle is {val:.0f}°. Confirm with a timing light after changes.",
            parameter_name=angle_param.name,
            cross_page=cross,
        )]

    @staticmethod
    def _check_trigger_geometry(
        trig: TuningPage | None,
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        if trig is None:
            return []

        teeth_param = _find(trig, ("nteeth", "toothcount", "triggerteeth", "crankteeth", "numteeth"))
        missing_param = _find(trig, ("missingteeth", "missingtooth"))

        if teeth_param is None or missing_param is None:
            return []  # geometry not exposed on this page; no check possible

        teeth = _numeric(teeth_param, edits)
        missing = _numeric(missing_param, edits)

        if teeth is None or missing is None:
            return [SetupChecklistItem(
                key="trigger_geometry",
                title="Set trigger wheel tooth count",
                status=ChecklistItemStatus.NEEDED,
                detail="Tooth count or missing-tooth count has no value. "
                       "Enter the values from the physical trigger wheel.",
                parameter_name=teeth_param.name,
            )]

        if missing >= teeth:
            return [SetupChecklistItem(
                key="trigger_geometry",
                title="Fix trigger geometry",
                status=ChecklistItemStatus.ERROR,
                detail=f"Missing teeth ({missing:.0f}) must be less than total teeth ({teeth:.0f}). "
                       "The ECU cannot sync with this configuration.",
                parameter_name=missing_param.name,
            )]

        if teeth > 0 and missing >= teeth / 2:
            return [SetupChecklistItem(
                key="trigger_geometry",
                title="Verify trigger geometry",
                status=ChecklistItemStatus.WARNING,
                detail=f"Missing teeth ({missing:.0f}) is more than half of total teeth ({teeth:.0f}). "
                       "Verify this matches the physical trigger wheel.",
                parameter_name=missing_param.name,
            )]

        return [SetupChecklistItem(
            key="trigger_geometry",
            title="Trigger geometry set",
            status=ChecklistItemStatus.OK,
            detail=f"Wheel: {int(teeth)}-{int(missing)} (total minus missing).",
            parameter_name=teeth_param.name,
        )]

    @staticmethod
    def _check_knock_pin(
        ign: TuningPage | None,
        trig: TuningPage | None,
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        if ign is None:
            return []

        knock_mode_param = _find(ign, ("knock_mode", "knockmode", "knockdetect"))
        if knock_mode_param is None:
            return []

        mode_val = _numeric(knock_mode_param, edits)
        if mode_val is None or mode_val == 0.0:
            return []  # knock off — no pin check needed

        # Knock is active — check for pin configuration
        _DIGITAL_PIN_KEYS = ("knock_digital_pin", "knockdigitalpin", "knockinput", "knockpin", "knocksensorpin")
        _ANALOG_PIN_KEYS = ("knock_analog_pin", "knockanalogpin",)

        if mode_val == 1.0:
            # Digital mode: look for digital pin
            pin_param = _find(ign, _DIGITAL_PIN_KEYS)
            cross = False
            if pin_param is None and trig is not None:
                pin_param = _find(trig, _DIGITAL_PIN_KEYS)
                cross = True
        else:
            # Analog mode (mode_val == 2)
            pin_param = _find(ign, _ANALOG_PIN_KEYS)
            cross = False
            if pin_param is None and trig is not None:
                pin_param = _find(trig, _ANALOG_PIN_KEYS)
                cross = True

        mode_label = _option_label(knock_mode_param, edits) or f"mode {int(mode_val)}"

        if pin_param is None:
            return [SetupChecklistItem(
                key="knock_pin_configured",
                title="Configure knock input pin",
                status=ChecklistItemStatus.WARNING,
                detail=f"Knock detection is enabled ({mode_label}) but the knock input pin "
                       "setting is not visible on this page. "
                       "Verify the pin is configured on another hardware page.",
                parameter_name=knock_mode_param.name,
                cross_page=True,
            )]

        pin_val = _numeric(pin_param, edits)
        # Most Speeduino boards use 0 or a sentinel value for "not assigned".
        # Check option label for "INVALID" as well.
        pin_label = _option_label(pin_param, edits)
        unassigned = (
            pin_val is not None and pin_val == 0.0
        ) or (
            pin_label is not None and pin_label.upper() in {"INVALID", "NONE", "UNASSIGNED", ""}
        )

        if unassigned:
            return [SetupChecklistItem(
                key="knock_pin_configured",
                title="Assign knock input pin",
                status=ChecklistItemStatus.WARNING,
                detail=f"Knock detection is enabled ({mode_label}) but the pin is not assigned. "
                       "Select the physical pin connected to the knock sensor.",
                parameter_name=pin_param.name,
                cross_page=cross,
            )]

        return [SetupChecklistItem(
            key="knock_pin_configured",
            title="Knock pin assigned",
            status=ChecklistItemStatus.OK,
            detail=f"Knock detection ({mode_label}) is active with a pin assigned.",
            parameter_name=pin_param.name,
            cross_page=cross,
        )]

    @staticmethod
    def _check_coil_vs_cylinders(
        ign: TuningPage | None,
        trig: TuningPage | None,
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        """Verify coil count is consistent with cylinder count when both are present."""
        if ign is None:
            return []

        cyl_param = (
            _find(ign, ("ncylinders", "cylindercount", "cylcount", "numcyl"))
            or (trig and _find(trig, ("ncylinders", "cylindercount", "cylcount", "numcyl")))
        )
        coil_param = _find(ign, ("ncoils", "coilcount", "coils", "ignitiontype", "sparkmode", "coilmode"))

        if cyl_param is None or coil_param is None:
            return []

        cyls = _numeric(cyl_param, edits)
        coils = _numeric(coil_param, edits)

        if cyls is None or coils is None:
            return []

        # coil_param is often an enum (spark mode) not a raw coil count; skip numeric mismatch
        # unless the parameter name contains "coil" and looks like a count field.
        if not any(kw in coil_param.name.lower() for kw in ("ncoil", "coilcount", "coils")):
            return []

        if coils > cyls:
            return [SetupChecklistItem(
                key="coil_vs_cylinders",
                title="Check coil count",
                status=ChecklistItemStatus.WARNING,
                detail=f"Coil count ({int(coils)}) is greater than cylinder count ({int(cyls)}). "
                       "Verify the ignition wiring matches the coil configuration.",
                parameter_name=coil_param.name,
            )]

        return [SetupChecklistItem(
            key="coil_vs_cylinders",
            title="Coil count consistent",
            status=ChecklistItemStatus.OK,
            detail=f"Coil count ({int(coils)}) is consistent with cylinder count ({int(cyls)}).",
            parameter_name=coil_param.name,
        )]

    @staticmethod
    def _check_sequential_cam_sync(
        ign: TuningPage | None,
        trig: TuningPage | None,
        edits: LocalTuneEditService,
    ) -> list[SetupChecklistItem]:
        """Warn when sequential injection or ignition is selected without cam sync.

        Sequential operation requires the ECU to know which stroke each cylinder
        is on (phase), which needs a cam signal.  Crank-only decoders cannot
        provide this; decoders with configurable secondary trigger must have a
        cam signal type selected.
        """
        if trig is None and ign is None:
            return []

        # --- read TrigPattern and TrigSpeed ---------------------------------
        trig_pattern_param = _find(trig, ("trigpattern", "trig_pattern")) if trig else None
        if trig_pattern_param is None and ign is not None:
            trig_pattern_param = _find(ign, ("trigpattern", "trig_pattern"))

        trig_speed_param = _find(trig, ("trigspeed", "trig_speed")) if trig else None
        if trig_speed_param is None and ign is not None:
            trig_speed_param = _find(ign, ("trigspeed", "trig_speed"))

        pattern_idx = _numeric(trig_pattern_param, edits)
        trig_speed = _numeric(trig_speed_param, edits)

        if pattern_idx is None:
            return []  # no TrigPattern visible on these pages

        pidx = int(pattern_idx)

        # --- read sequential modes ------------------------------------------
        spark_mode_param = _find(ign, ("sparkmode", "spark_mode")) if ign else None
        if spark_mode_param is None and trig is not None:
            spark_mode_param = _find(trig, ("sparkmode", "spark_mode"))
        inj_layout_param = _find(ign, ("injlayout", "inj_layout")) if ign else None
        if inj_layout_param is None and trig is not None:
            inj_layout_param = _find(trig, ("injlayout", "inj_layout"))

        spark_mode = _numeric(spark_mode_param, edits)
        inj_layout = _numeric(inj_layout_param, edits)

        sequential_ignition = spark_mode is not None and int(spark_mode) == 3
        sequential_injection = inj_layout is not None and int(inj_layout) == 3

        if not sequential_ignition and not sequential_injection:
            return []  # not running sequential — no cam sync check needed

        mode_label = ", ".join(filter(None, [
            "sequential ignition" if sequential_ignition else None,
            "sequential injection" if sequential_injection else None,
        ]))

        # --- evaluate cam sync capability -----------------------------------
        if pidx in _CRANK_ONLY_PATTERNS:
            decoder_name = _TRIGGER_PATTERN_NAMES.get(pidx, f"pattern {pidx}")
            return [SetupChecklistItem(
                key="sequential_cam_sync",
                title="Cam sync required for sequential operation",
                status=ChecklistItemStatus.WARNING,
                detail=(
                    f"{mode_label.capitalize()} is selected but the {decoder_name} decoder "
                    "does not have a cam input.  Sequential operation requires phase "
                    "knowledge (1 pulse per 2 crank revolutions).  Consider switching to "
                    "a decoder that supports a secondary cam trigger."
                ),
                parameter_name=trig_pattern_param.name if trig_pattern_param else None,
            )]

        if pidx in _CAM_CONFIGURABLE_PATTERNS:
            # Missing Tooth at crank speed (TrigSpeed == 0) or Rover MEMS:
            # cam is optional.  Check if TrigSpeed selects cam-speed mode.
            is_cam_speed = trig_speed is not None and int(trig_speed) == 1  # cam speed
            if is_cam_speed:
                # Missing Tooth at cam speed — phase is inherent; no further check.
                return []

            # Crank-speed Missing Tooth: secondary trigger type must be something
            # other than "Poll level" (trigPatternSec == 2) for sequential to work
            # reliably.  "Poll level" is a cam-level sensor — it does work but
            # behaves differently from a pulsed cam signal.
            trig_pattern_sec_param = _find(trig, ("trigpatternsec", "trig_pattern_sec")) if trig else None
            trig_pattern_sec = _numeric(trig_pattern_sec_param, edits)

            if trig_pattern_sec is None:
                # trigPatternSec not visible on these pages — warn that it should be configured.
                return [SetupChecklistItem(
                    key="sequential_cam_sync",
                    title="Verify cam sync for sequential operation",
                    status=ChecklistItemStatus.WARNING,
                    detail=(
                        f"{mode_label.capitalize()} is selected with a crank-speed Missing "
                        "Tooth decoder.  Confirm that a secondary cam trigger (trigPatternSec) "
                        "is configured on the trigger setup page for reliable sequential operation."
                    ),
                    parameter_name=trig_pattern_param.name if trig_pattern_param else None,
                    cross_page=True,
                )]

            sec_name = _SECONDARY_TRIGGER_NAMES.get(int(trig_pattern_sec), f"type {int(trig_pattern_sec)}")
            return [SetupChecklistItem(
                key="sequential_cam_sync",
                title="Cam sync configured for sequential operation",
                status=ChecklistItemStatus.OK,
                detail=(
                    f"{mode_label.capitalize()} with Missing Tooth crank decoder.  "
                    f"Secondary cam signal: {sec_name}.  "
                    "Verify the cam sensor is wired and syncing correctly on first start."
                ),
                parameter_name=trig_pattern_sec_param.name if trig_pattern_sec_param else None,
            )]

        # Inherent cam or distributor pattern — sequential is supported.
        return []

    @staticmethod
    def _trigger_topology_summary(
        ign: TuningPage | None,
        trig: TuningPage | None,
        edits: LocalTuneEditService,
    ) -> SetupChecklistItem | None:
        """Return an INFO item describing the full trigger topology, or None if unknown."""
        # Read primary decoder
        trig_pattern_param = _find(trig, ("trigpattern", "trig_pattern")) if trig else None
        if trig_pattern_param is None and ign is not None:
            trig_pattern_param = _find(ign, ("trigpattern", "trig_pattern"))

        if trig_pattern_param is None:
            return None

        pattern_idx = _numeric(trig_pattern_param, edits)
        if pattern_idx is None:
            return None

        pidx = int(pattern_idx)
        primary_name = _TRIGGER_PATTERN_NAMES.get(pidx, f"Pattern {pidx}")

        # Read tooth geometry for Missing Tooth summary
        teeth_param = _find(trig, ("nteeth", "numteeth", "triggerteeth", "crankteeth")) if trig else None
        missing_param = _find(trig, ("missingteeth", "missingtooth")) if trig else None
        teeth = _numeric(teeth_param, edits) if teeth_param else None
        missing = _numeric(missing_param, edits) if missing_param else None

        if pidx == 0 and teeth is not None and missing is not None:
            primary_name = f"Missing Tooth ({int(teeth)}-{int(missing)})"

        # Read TrigSpeed for Missing Tooth (crank vs cam speed)
        trig_speed_param = _find(trig, ("trigspeed", "trig_speed")) if trig else None
        if trig_speed_param is None and ign is not None:
            trig_speed_param = _find(ign, ("trigspeed", "trig_speed"))
        trig_speed = _numeric(trig_speed_param, edits) if trig_speed_param else None

        speed_label = ""
        if pidx == 0 and trig_speed is not None:
            speed_label = " (cam speed)" if int(trig_speed) == 1 else " (crank speed)"

        # Secondary trigger for configurable patterns
        sec_label = ""
        if pidx in _CAM_CONFIGURABLE_PATTERNS and (trig_speed is None or int(trig_speed) == 0):
            trig_pattern_sec_param = _find(trig, ("trigpatternsec", "trig_pattern_sec")) if trig else None
            trig_pattern_sec = _numeric(trig_pattern_sec_param, edits) if trig_pattern_sec_param else None
            if trig_pattern_sec is not None:
                sec_name = _SECONDARY_TRIGGER_NAMES.get(int(trig_pattern_sec), f"secondary type {int(trig_pattern_sec)}")
                sec_label = f" with {sec_name}"
        elif pidx in _CAM_INHERENT_PATTERNS:
            sec_label = " (cam sync inherent)"

        summary = f"{primary_name}{speed_label}{sec_label}"
        return SetupChecklistItem(
            key="trigger_topology",
            title="Trigger topology",
            status=ChecklistItemStatus.INFO,
            detail=summary,
            parameter_name=trig_pattern_param.name,
        )
