from __future__ import annotations

from tuner.domain.hardware_setup import HardwareIssueSeverity
from tuner.services.hardware_setup_validation_service import HardwareSetupValidationService


def _service() -> HardwareSetupValidationService:
    return HardwareSetupValidationService()


def _values(**kw: float):
    def get(name: str) -> float | None:
        return kw.get(name)
    return get


# ---------------------------------------------------------------------------
# Dwell checks
# ---------------------------------------------------------------------------

def test_excessive_dwell_raises_error() -> None:
    issues = _service().validate({"sparkDur"}, _values(sparkDur=15.0))
    assert any(i.severity == HardwareIssueSeverity.ERROR for i in issues)
    assert any("sparkDur" == i.parameter_name for i in issues)


def test_safe_dwell_no_issue() -> None:
    issues = _service().validate({"sparkDur"}, _values(sparkDur=3.5))
    dwell_issues = [i for i in issues if i.parameter_name == "sparkDur"]
    assert not dwell_issues


def test_dwell_at_boundary_no_issue() -> None:
    issues = _service().validate({"dwellTime"}, _values(dwellTime=10.0))
    assert not issues


def test_dwell_name_variations_detected() -> None:
    for name in ("dwellTime", "coilDwell", "sparkDur"):
        issues = _service().validate({name}, _values(**{name: 20.0}))
        assert any(i.parameter_name == name for i in issues), f"expected dwell issue for {name}"


# ---------------------------------------------------------------------------
# Trigger geometry checks
# ---------------------------------------------------------------------------

def test_missing_teeth_equal_total_is_error() -> None:
    issues = _service().validate(
        {"nTeeth", "missingTeeth"},
        _values(nTeeth=36.0, missingTeeth=36.0),
    )
    error_issues = [i for i in issues if i.severity == HardwareIssueSeverity.ERROR]
    assert error_issues
    assert any("missingTeeth" == i.parameter_name for i in error_issues)


def test_missing_teeth_greater_than_total_is_error() -> None:
    issues = _service().validate(
        {"nTeeth", "missingTeeth"},
        _values(nTeeth=36.0, missingTeeth=40.0),
    )
    assert any(i.severity == HardwareIssueSeverity.ERROR for i in issues)


def test_missing_teeth_more_than_half_is_warning() -> None:
    issues = _service().validate(
        {"nTeeth", "missingTeeth"},
        _values(nTeeth=36.0, missingTeeth=20.0),
    )
    assert any(i.severity == HardwareIssueSeverity.WARNING for i in issues)


def test_valid_trigger_geometry_no_issue() -> None:
    issues = _service().validate(
        {"nTeeth", "missingTeeth"},
        _values(nTeeth=36.0, missingTeeth=1.0),
    )
    trigger_issues = [i for i in issues if i.parameter_name == "missingTeeth"]
    assert not trigger_issues


def test_missing_trigger_names_skips_geometry_check() -> None:
    # Only tooth count, no missing teeth parameter → no geometry issue
    issues = _service().validate({"nTeeth"}, _values(nTeeth=36.0))
    geo_issues = [i for i in issues if i.parameter_name == "missingTeeth"]
    assert not geo_issues


# ---------------------------------------------------------------------------
# Dead time checks
# ---------------------------------------------------------------------------

def test_zero_dead_time_warns() -> None:
    issues = _service().validate({"deadTime"}, _values(deadTime=0.0))
    assert any(i.severity == HardwareIssueSeverity.WARNING and i.parameter_name == "deadTime" for i in issues)


def test_nonzero_dead_time_no_issue() -> None:
    issues = _service().validate({"deadTime"}, _values(deadTime=1.5))
    dead_issues = [i for i in issues if i.parameter_name == "deadTime"]
    assert not dead_issues


def test_injopen_zero_warns() -> None:
    issues = _service().validate({"injOpen"}, _values(injOpen=0.0))
    assert any("injOpen" == i.parameter_name for i in issues)


# ---------------------------------------------------------------------------
# Trigger angle checks
# ---------------------------------------------------------------------------

def test_zero_trigger_angle_warns() -> None:
    issues = _service().validate({"fixAng"}, _values(fixAng=0.0))
    assert any(i.severity == HardwareIssueSeverity.WARNING for i in issues)


def test_nonzero_trigger_angle_no_issue() -> None:
    issues = _service().validate({"fixAng"}, _values(fixAng=114.0))
    angle_issues = [i for i in issues if "fixAng" in (i.parameter_name or "")]
    assert not angle_issues


# ---------------------------------------------------------------------------
# Wideband calibration checks
# ---------------------------------------------------------------------------

def test_wideband_without_calibration_warns() -> None:
    # egoType == 2 means wideband; no calibration table present
    issues = _service().validate({"egoType"}, _values(egoType=2.0))
    assert any(i.severity == HardwareIssueSeverity.WARNING and i.parameter_name == "egoType" for i in issues)


def test_narrowband_no_calibration_warning() -> None:
    issues = _service().validate({"egoType"}, _values(egoType=1.0))
    ego_issues = [i for i in issues if i.parameter_name == "egoType"]
    assert not ego_issues


def test_wideband_with_calibration_table_no_issue() -> None:
    issues = _service().validate(
        {"egoType", "afrCal"},
        _values(egoType=2.0, afrCal=14.7),
    )
    cal_issues = [i for i in issues if i.parameter_name == "egoType"]
    assert not cal_issues


# ---------------------------------------------------------------------------
# Empty / unknown parameters
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Injector flow zero check
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Injector dead time plausibility check (implausibly high)
# ---------------------------------------------------------------------------

def test_injopen_above_5ms_warns() -> None:
    # 6ms is implausible — likely entered in µs instead of ms
    issues = _service().validate({"injOpen"}, _values(injOpen=6.0))
    assert any(
        i.severity == HardwareIssueSeverity.WARNING and i.parameter_name == "injOpen"
        for i in issues
    )


def test_injopen_typical_range_no_plausibility_warning() -> None:
    for val in (0.4, 0.7, 1.5, 2.0, 4.9):
        issues = _service().validate({"injOpen"}, _values(injOpen=val))
        plausibility_issues = [
            i for i in issues
            if i.parameter_name == "injOpen" and "implausibly" in (i.message or "")
        ]
        assert not plausibility_issues, f"unexpected plausibility warning for injOpen={val}"


def test_deadtime_above_5ms_warns() -> None:
    issues = _service().validate({"deadTime"}, _values(deadTime=10.0))
    assert any(
        i.severity == HardwareIssueSeverity.WARNING and "implausibly" in (i.message or "")
        for i in issues
    )


def test_injopen_zero_still_warns_zero_not_plausibility() -> None:
    # Zero value: should get the zero warning, not the plausibility warning
    issues = _service().validate({"injOpen"}, _values(injOpen=0.0))
    zero_issues = [i for i in issues if "zero" in (i.message or "").lower() or "non-zero" in (i.message or "").lower()]
    assert zero_issues


# ---------------------------------------------------------------------------


def test_zero_injector_flow_warns() -> None:
    issues = _service().validate({"injectorFlow"}, _values(injectorFlow=0.0))
    assert any(i.severity == HardwareIssueSeverity.WARNING and i.parameter_name == "injectorFlow" for i in issues)


def test_nonzero_injector_flow_no_issue() -> None:
    issues = _service().validate({"injectorFlow"}, _values(injectorFlow=550.0))
    flow_issues = [i for i in issues if i.parameter_name == "injectorFlow"]
    assert not flow_issues


def test_injflow_name_variant_detected() -> None:
    issues = _service().validate({"injFlow"}, _values(injFlow=0.0))
    assert any(i.parameter_name == "injFlow" for i in issues)


# ---------------------------------------------------------------------------
# Required fuel zero check
# ---------------------------------------------------------------------------

def test_zero_req_fuel_warns() -> None:
    issues = _service().validate({"reqFuel"}, _values(reqFuel=0.0))
    assert any(i.severity == HardwareIssueSeverity.WARNING and i.parameter_name == "reqFuel" for i in issues)


def test_nonzero_req_fuel_no_issue() -> None:
    issues = _service().validate({"reqFuel"}, _values(reqFuel=8.4))
    rf_issues = [i for i in issues if i.parameter_name == "reqFuel"]
    assert not rf_issues


def test_req_fuel_case_insensitive_match() -> None:
    # The rule matches only exact case-insensitive "reqfuel"
    issues = _service().validate({"reqfuel"}, _values(reqfuel=0.0))
    assert any(i.parameter_name == "reqfuel" for i in issues)


# ---------------------------------------------------------------------------
# Dwell zero check
# ---------------------------------------------------------------------------

def test_zero_dwell_warns() -> None:
    issues = _service().validate({"dwellRun"}, _values(dwellRun=0.0))
    assert any(i.severity == HardwareIssueSeverity.WARNING and i.parameter_name == "dwellRun" for i in issues)


def test_nonzero_dwell_no_zero_issue() -> None:
    issues = _service().validate({"dwellRun"}, _values(dwellRun=3.2))
    zero_issues = [i for i in issues if i.parameter_name == "dwellRun" and "zero" in (i.message or "").lower()]
    assert not zero_issues


def test_dwell_zero_does_not_duplicate_excessive_check() -> None:
    # Zero dwell should get a zero warning, not an excessive-dwell error.
    issues = _service().validate({"dwellRun"}, _values(dwellRun=0.0))
    assert not any(i.severity == HardwareIssueSeverity.ERROR for i in issues)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Dwell implausible range check (dwellrun only)
# ---------------------------------------------------------------------------

def test_dwellrun_below_min_plausible_warns() -> None:
    # 0.5 ms is below the 1.5 ms plausible floor
    issues = _service().validate({"dwellrun"}, _values(dwellrun=0.5))
    range_issues = [i for i in issues if i.parameter_name == "dwellrun" and "typical" in (i.message or "").lower()]
    assert range_issues, "expected implausible range warning for dwellrun=0.5"


def test_dwellrun_just_below_min_warns() -> None:
    issues = _service().validate({"dwellrun"}, _values(dwellrun=1.4))
    range_issues = [i for i in issues if i.parameter_name == "dwellrun" and "typical" in (i.message or "").lower()]
    assert range_issues


def test_dwellrun_at_min_boundary_no_range_warning() -> None:
    issues = _service().validate({"dwellrun"}, _values(dwellrun=1.5))
    range_issues = [
        i for i in issues
        if i.parameter_name == "dwellrun" and "typical" in (i.message or "").lower()
    ]
    assert not range_issues


def test_dwellrun_typical_value_no_range_warning() -> None:
    for val in (1.5, 3.0, 4.5, 6.0):
        issues = _service().validate({"dwellrun"}, _values(dwellrun=val))
        range_issues = [
            i for i in issues
            if i.parameter_name == "dwellrun" and "typical" in (i.message or "").lower()
        ]
        assert not range_issues, f"unexpected range warning for dwellrun={val}"


def test_dwellrun_above_max_plausible_warns() -> None:
    # 6.5 ms is above 6.0 ms plausible ceiling but below 10 ms excessive threshold
    issues = _service().validate({"dwellrun"}, _values(dwellrun=6.5))
    range_issues = [i for i in issues if i.parameter_name == "dwellrun" and "typical" in (i.message or "").lower()]
    assert range_issues, "expected implausible range warning for dwellrun=6.5"


def test_dwellrun_zero_not_range_warned() -> None:
    # Zero is handled by the zero rule; range rule skips it
    issues = _service().validate({"dwellrun"}, _values(dwellrun=0.0))
    range_issues = [
        i for i in issues
        if i.parameter_name == "dwellrun" and "typical" in (i.message or "").lower()
    ]
    assert not range_issues


def test_dwellrun_excessive_not_range_warned() -> None:
    # 15 ms is handled by the excessive rule; range rule skips values above _DWELL_MAX_MS
    issues = _service().validate({"dwellrun"}, _values(dwellrun=15.0))
    range_issues = [
        i for i in issues
        if i.parameter_name == "dwellrun" and "typical" in (i.message or "").lower()
    ]
    assert not range_issues


def test_other_dwell_names_not_range_checked() -> None:
    # The range rule only targets dwellrun, not dwellcrank or sparkDur
    for name in ("dwellcrank", "sparkDur", "coilDwell"):
        issues = _service().validate({name}, _values(**{name: 0.5}))
        range_issues = [
            i for i in issues
            if i.parameter_name == name and "typical" in (i.message or "").lower()
        ]
        assert not range_issues, f"unexpected range warning for {name}=0.5"


def test_empty_parameter_set_returns_no_issues() -> None:
    issues = _service().validate(set(), lambda _: None)
    assert not issues


def test_unknown_parameters_return_no_issues() -> None:
    issues = _service().validate({"someRandomParam", "anotherParam"}, _values(someRandomParam=999.0))
    assert not issues
