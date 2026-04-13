"""Python ↔ C++ parity harness for tuner_core::hardware_setup_validation.

Pins the C++ validator against
`HardwareSetupValidationService.validate` issue-by-issue, including
rejection messages and detail strings.

Set-iteration order: the Python service builds `present = set(parameter_names)`,
which is non-deterministic across runs in CPython. To compare across
implementations, both sides' issue lists are normalised to a sorted
multiset of `(severity, parameter_name, message, detail)` tuples.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.domain.hardware_setup import HardwareIssueSeverity
from tuner.services.hardware_setup_validation_service import (
    HardwareSetupValidationService,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CPP_BUILD_CANDIDATES = [
    _REPO_ROOT / "build" / "cpp",
    _REPO_ROOT / "build" / "cpp" / "Release",
    _REPO_ROOT / "build" / "cpp" / "Debug",
    _REPO_ROOT / "cpp" / "build",
]


def _try_import_tuner_core():
    try:
        return importlib.import_module("tuner._native.tuner_core")
    except ImportError:
        pass
    for candidate in _CPP_BUILD_CANDIDATES:
        if not candidate.exists():
            continue
        added = str(candidate)
        if added not in sys.path:
            sys.path.insert(0, added)
        try:
            return importlib.import_module("tuner_core")
        except ImportError:
            sys.path.remove(added)
            continue
    return None


_tuner_core = _try_import_tuner_core()

pytestmark = pytest.mark.skipif(
    _tuner_core is None,
    reason="tuner_core C++ extension not built.",
)


_py_validator = HardwareSetupValidationService()


def _normalize(issues, severity_attr_path):
    """Normalize an issue list to a sorted multiset of comparable tuples.

    `severity_attr_path` is "value" for the Python StrEnum and `name`
    for the C++ nb::enum_; both convert to a string for comparison.
    """
    out = []
    for i in issues:
        sev = severity_attr_path(i.severity)
        out.append((
            sev,
            i.parameter_name or "",
            i.message,
            i.detail or "",
        ))
    return sorted(out)


def _py_sev(s):
    return s.value if isinstance(s, HardwareIssueSeverity) else str(s)


def _cpp_sev(s):
    # nanobind enum: name is "WARNING" / "ERROR"; Python uses "warning" / "error".
    return s.name.lower()


def _run_both(parameter_names, value_dict):
    py = _py_validator.validate(
        parameter_names, lambda n: value_dict.get(n)
    )
    values_pairs = list(value_dict.items())
    cpp = _tuner_core.hardware_setup_validate(parameter_names, values_pairs)
    return py, cpp


def _check_parity(parameter_names, value_dict):
    py, cpp = _run_both(parameter_names, value_dict)
    assert _normalize(py, _py_sev) == _normalize(cpp, _cpp_sev)


# ---------------------------------------------------------------------------
# Per-rule parity
# ---------------------------------------------------------------------------

def test_dwell_excessive_matches_python():
    _check_parity(["dwellRun"], {"dwellRun": 12.5})


def test_dwell_zero_matches_python():
    _check_parity(["dwellRun"], {"dwellRun": 0.0})


def test_dwell_implausible_range_matches_python():
    _check_parity(["dwellRun"], {"dwellRun": 8.0})
    _check_parity(["dwellRun"], {"dwellRun": 1.0})


def test_dwell_inside_plausible_range_produces_no_issue():
    _check_parity(["dwellRun"], {"dwellRun": 3.0})


def test_trigger_geometry_error_matches_python():
    _check_parity(
        ["nTeeth", "missingTeeth"],
        {"nTeeth": 36.0, "missingTeeth": 36.0},
    )


def test_trigger_geometry_warning_matches_python():
    _check_parity(
        ["nTeeth", "missingTeeth"],
        {"nTeeth": 36.0, "missingTeeth": 20.0},
    )


def test_trigger_geometry_clean_matches_python():
    _check_parity(
        ["nTeeth", "missingTeeth"],
        {"nTeeth": 36.0, "missingTeeth": 1.0},
    )


def test_dead_time_zero_matches_python():
    _check_parity(["injOpen"], {"injOpen": 0.0})


def test_dead_time_implausible_high_matches_python():
    _check_parity(["injOpen"], {"injOpen": 7.5})


def test_injector_flow_zero_matches_python():
    _check_parity(["injectorFlow"], {"injectorFlow": 0.0})


def test_required_fuel_zero_matches_python():
    _check_parity(["reqFuel"], {"reqFuel": 0.0})


def test_trigger_angle_zero_matches_python():
    _check_parity(["triggerAngle"], {"triggerAngle": 0.0})


def test_wideband_without_calibration_matches_python():
    _check_parity(["egoType"], {"egoType": 2.0})


def test_wideband_with_calibration_matches_python():
    _check_parity(["egoType", "afrCalTable"], {"egoType": 2.0})


def test_narrowband_no_calibration_required_matches_python():
    _check_parity(["egoType"], {"egoType": 1.0})


def test_clean_full_setup_matches_python():
    _check_parity(
        ["dwellRun", "nTeeth", "missingTeeth", "injOpen", "injectorFlow",
         "reqFuel", "triggerAngle"],
        {
            "dwellRun": 3.0,
            "nTeeth": 36.0,
            "missingTeeth": 1.0,
            "injOpen": 1.0,
            "injectorFlow": 220.0,
            "reqFuel": 12.5,
            "triggerAngle": 60.0,
        },
    )


def test_multiple_problems_at_once_matches_python():
    _check_parity(
        ["dwellRun", "nTeeth", "missingTeeth", "injOpen", "injectorFlow",
         "reqFuel", "triggerAngle", "egoType"],
        {
            "dwellRun": 12.5,        # excessive ERROR
            "nTeeth": 36.0,
            "missingTeeth": 36.0,    # error
            "injOpen": 7.5,          # implausibly high warning
            "injectorFlow": 0.0,     # warning
            "reqFuel": 0.0,          # warning
            "triggerAngle": 0.0,     # warning
            "egoType": 2.0,          # warning
        },
    )
