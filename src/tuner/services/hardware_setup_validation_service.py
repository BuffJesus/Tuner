from __future__ import annotations

from collections.abc import Callable, Iterable

from tuner.domain.hardware_setup import HardwareIssueSeverity, HardwareSetupIssue

# Maximum safe dwell time in milliseconds before coil damage risk.
_DWELL_MAX_MS = 10.0

# Implausible dwell range: typical running dwell is 1.5–6.0 ms.
# Values outside this range suggest a configuration error.
_DWELL_MIN_PLAUSIBLE_MS = 1.5
_DWELL_MAX_PLAUSIBLE_MS = 6.0


def _check_dwell_excessive(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> list[HardwareSetupIssue]:
    issues = []
    for name in present:
        lower = name.lower()
        if "dwell" in lower or lower in ("sparkdur", "coildwell", "dwelltime"):
            val = get_value(name)
            if val is not None and val > _DWELL_MAX_MS:
                issues.append(
                    HardwareSetupIssue(
                        severity=HardwareIssueSeverity.ERROR,
                        parameter_name=name,
                        message=f"Dwell time {val:.1f} ms is excessive and may damage ignition coils.",
                        detail=f"Safe maximum is {_DWELL_MAX_MS:.0f} ms. "
                               "Check coil specifications before proceeding.",
                    )
                )
    return issues


def _check_trigger_geometry(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> HardwareSetupIssue | None:
    tooth_name: str | None = None
    missing_name: str | None = None
    for name in present:
        lower = name.lower()
        if tooth_name is None and ("nteeth" in lower or lower in ("toothcount", "triggerteeth", "crankteeth")):
            tooth_name = name
        if missing_name is None and ("missingteeth" in lower or "missingtooth" in lower):
            missing_name = name

    if tooth_name is None or missing_name is None:
        return None

    teeth = get_value(tooth_name)
    missing = get_value(missing_name)
    if teeth is None or missing is None:
        return None

    if missing >= teeth:
        return HardwareSetupIssue(
            severity=HardwareIssueSeverity.ERROR,
            parameter_name=missing_name,
            message=(
                f"Missing tooth count ({missing:.0f}) must be less than "
                f"total tooth count ({teeth:.0f})."
            ),
            detail="The ECU will fail to sync if missing teeth >= total teeth.",
        )

    if teeth > 0 and missing >= teeth / 2:
        return HardwareSetupIssue(
            severity=HardwareIssueSeverity.WARNING,
            parameter_name=missing_name,
            message=(
                f"Missing tooth count ({missing:.0f}) is more than half of "
                f"total teeth ({teeth:.0f}). Verify this matches your physical wheel."
            ),
        )

    return None


def _check_dead_time_zero(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> list[HardwareSetupIssue]:
    issues = []
    for name in present:
        lower = name.lower()
        if "deadtime" in lower or "injopen" in lower or lower in ("injectoropen", "opentime"):
            val = get_value(name)
            if val is not None and val == 0.0:
                issues.append(
                    HardwareSetupIssue(
                        severity=HardwareIssueSeverity.WARNING,
                        parameter_name=name,
                        message=f"Injector dead time '{name}' is zero. "
                                "Most injectors require a non-zero dead time for accurate fuelling.",
                    )
                )
    return issues


def _check_trigger_angle_zero(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> HardwareSetupIssue | None:
    for name in present:
        lower = name.lower()
        if lower in ("triggerangle", "crankangle", "tdcangle", "fixang", "crankedge"):
            val = get_value(name)
            if val is not None and val == 0.0:
                return HardwareSetupIssue(
                    severity=HardwareIssueSeverity.WARNING,
                    parameter_name=name,
                    message=f"Trigger angle '{name}' is zero. "
                            "Verify this is intentional — most engines require a non-zero TDC reference.",
                )
    return None


def _check_injector_flow_zero(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> list[HardwareSetupIssue]:
    issues = []
    for name in present:
        lower = name.lower()
        if any(kw in lower for kw in ("injectorflow", "injflow", "injsize")):
            val = get_value(name)
            if val is not None and val == 0.0:
                issues.append(
                    HardwareSetupIssue(
                        severity=HardwareIssueSeverity.WARNING,
                        parameter_name=name,
                        message=f"Injector flow rate '{name}' is zero. "
                                "Enter the rated flow (cc/min) from the injector datasheet before first start.",
                    )
                )
    return issues


def _check_injopen_range(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> list[HardwareSetupIssue]:
    """Warn when injector open time is implausibly high (likely a scale error).

    Typical injector dead time is 0.3 – 2.0 ms.  Values above 5.0 ms almost
    always indicate the value was entered in microseconds instead of
    milliseconds, or the scale factor was not applied correctly.
    """
    _INJOPEN_MAX_PLAUSIBLE_MS = 5.0
    issues = []
    for name in present:
        lower = name.lower()
        if "deadtime" in lower or "injopen" in lower or lower in ("injectoropen", "opentime"):
            val = get_value(name)
            if val is not None and val > 0.0 and val > _INJOPEN_MAX_PLAUSIBLE_MS:
                issues.append(
                    HardwareSetupIssue(
                        severity=HardwareIssueSeverity.WARNING,
                        parameter_name=name,
                        message=(
                            f"Injector dead time '{name}' is {val:.1f} ms — "
                            "this is implausibly high and may indicate a scale or units error. "
                            "Typical values are 0.3–2.0 ms."
                        ),
                        detail="Check whether the value was entered in microseconds rather than milliseconds.",
                    )
                )
    return issues


def _check_required_fuel_zero(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> list[HardwareSetupIssue]:
    issues = []
    for name in present:
        if name.lower() == "reqfuel":
            val = get_value(name)
            if val is not None and val == 0.0:
                issues.append(
                    HardwareSetupIssue(
                        severity=HardwareIssueSeverity.WARNING,
                        parameter_name=name,
                        message="Required fuel is zero. "
                                "Calculate and enter the required fuel value before writing or running the engine.",
                    )
                )
    return issues


def _check_dwell_implausible_range(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> list[HardwareSetupIssue]:
    """Warn when running dwell is outside the plausible 1.5–6.0 ms window.

    The ``dwellrun`` parameter specifically represents the running (not cranking)
    coil charge time.  Values below 1.5 ms may not give a reliable spark;
    values above 6.0 ms risk coil overheating before the excessive-dwell rule
    (> 10 ms) triggers an error.  This rule catches the middle zone where the
    value is non-zero but still implausible for most coils.
    """
    issues = []
    for name in present:
        lower = name.lower()
        # Only target the running dwell parameter, not cranking dwell
        if lower not in ("dwellrun",):
            continue
        val = get_value(name)
        if val is None or val == 0.0:
            continue  # zero is caught by _check_dwell_zero
        if val > _DWELL_MAX_MS:
            continue  # excessive case is caught by _check_dwell_excessive
        if val < _DWELL_MIN_PLAUSIBLE_MS or val > _DWELL_MAX_PLAUSIBLE_MS:
            issues.append(
                HardwareSetupIssue(
                    severity=HardwareIssueSeverity.WARNING,
                    parameter_name=name,
                    message=(
                        f"Running dwell '{name}' is {val:.1f} ms — "
                        f"outside the typical 1.5–6.0 ms range. "
                        "Verify against your coil's datasheet."
                    ),
                    detail=(
                        "Very low dwell (<1.5 ms) may produce a weak spark. "
                        "Dwell above 6.0 ms may cause coil overheating at idle."
                    ),
                )
            )
    return issues


def _check_dwell_zero(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> list[HardwareSetupIssue]:
    issues = []
    for name in present:
        lower = name.lower()
        if "dwell" in lower or lower in ("sparkdur", "coildwell", "dwelltime", "dwellrun"):
            val = get_value(name)
            if val is not None and val == 0.0:
                issues.append(
                    HardwareSetupIssue(
                        severity=HardwareIssueSeverity.WARNING,
                        parameter_name=name,
                        message=f"Dwell time '{name}' is zero. "
                                "Coils will not charge and the engine will not fire. "
                                "Set dwell from the coil datasheet before enabling ignition.",
                    )
                )
    return issues


def _check_wideband_without_calibration(
    present: set[str],
    get_value: Callable[[str], float | None],
) -> HardwareSetupIssue | None:
    ego_name: str | None = None
    for name in present:
        lower = name.lower()
        if lower in ("egotype", "afrsensortype", "o2sensortype", "lambdatype"):
            ego_name = name
            break
    if ego_name is None:
        return None

    val = get_value(ego_name)
    if val is None or val < 2:
        return None  # not wideband

    cal_present = any(
        "afrcal" in n.lower() or "widebandcal" in n.lower() or "lambdacal" in n.lower()
        for n in present
    )
    if not cal_present:
        return HardwareSetupIssue(
            severity=HardwareIssueSeverity.WARNING,
            parameter_name=ego_name,
            message="Wideband sensor selected but no calibration table found on this page. "
                    "Verify AFR calibration is configured before relying on autotune.",
        )
    return None


_RULES: list[Callable[[set[str], Callable[[str], float | None]], HardwareSetupIssue | list[HardwareSetupIssue] | None]] = [
    _check_dwell_excessive,
    _check_dwell_zero,
    _check_dwell_implausible_range,
    _check_trigger_geometry,
    _check_dead_time_zero,
    _check_injopen_range,
    _check_injector_flow_zero,
    _check_required_fuel_zero,
    _check_trigger_angle_zero,
    _check_wideband_without_calibration,
]


class HardwareSetupValidationService:
    """Validates hardware setup parameters for dangerous or inconsistent values.

    Each rule receives the set of parameter names present on hardware setup pages
    and a callable to look up the current numeric value for any parameter.
    """

    def validate(
        self,
        parameter_names: Iterable[str],
        get_value: Callable[[str], float | None],
    ) -> list[HardwareSetupIssue]:
        present = set(parameter_names)
        issues: list[HardwareSetupIssue] = []
        for rule in _RULES:
            result = rule(present, get_value)
            if isinstance(result, list):
                issues.extend(result)
            elif result is not None:
                issues.append(result)
        return issues
