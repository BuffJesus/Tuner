"""Python ↔ C++ parity harness for tuner_core::pressure_sensor_calibration."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.services.hardware_preset_service import (
    HardwarePresetService,
    PressureSensorPreset,
)
from tuner.services.pressure_sensor_calibration_service import (
    PressureSensorCalibrationService,
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


_py = PressureSensorCalibrationService()


def _to_cpp_preset(p: PressureSensorPreset):
    cp = _tuner_core.PressureSensorPreset()
    cp.key = p.key
    cp.label = p.label
    cp.description = p.description
    cp.minimum_value = p.minimum_value
    cp.maximum_value = p.maximum_value
    cp.units = p.units
    cp.source_note = p.source_note
    cp.source_url = p.source_url
    return cp


def _make_preset(key, label, lo, hi, source_note, source_url=None):
    return PressureSensorPreset(
        key=key,
        label=label,
        description=label,
        minimum_value=lo,
        maximum_value=hi,
        units="kPa",
        source_note=source_note,
        source_url=source_url,
    )


# ---------------------------------------------------------------------------
# source_confidence_label
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "note,url",
    [
        ("Inferred starter preset", None),
        ("Conservative inferred", "https://example.com/x"),
        ("Datasheet", None),
        ("ID datasheet", "https://injectordynamics.com/x"),
        ("Holley", "https://documents.holley.com/y.pdf"),
        ("NXP", "https://www.nxp.com/docs/MPX4250.pdf"),
        ("Chevy", "https://www.chevrolet.com/parts/123"),
        ("DTec AU", "https://dtec.net.au/something"),
        ("MS4X wiki", "https://www.ms4x.net/index.php?title=Air_Sensors"),
        ("MSExtra", "https://www.msextra.com/forums/viewtopic.php?t=12345"),
        ("Random blog", "https://random-blog.example/post/123"),
        ("Anything", "https://injector-rehab.com/foo"),
    ],
)
def test_source_confidence_label_matches_python(note, url):
    py = HardwarePresetService.source_confidence_label(
        source_note=note, source_url=url
    )
    cpp = _tuner_core.pressure_source_confidence_label(note, url)
    assert cpp == py


# ---------------------------------------------------------------------------
# find_matching_preset
# ---------------------------------------------------------------------------

def _preset_set():
    return [
        _make_preset("p100", "100 kPa MAP", 10.0, 100.0, "Inferred"),
        _make_preset("p250", "250 kPa MAP", 10.0, 250.0,
                     "From datasheet", "https://www.nxp.com/x.pdf"),
        _make_preset("p400", "400 kPa MAP", 10.0, 400.0, "Inferred"),
    ]


@pytest.mark.parametrize(
    "lo,hi,expected_key",
    [
        (10.0, 100.0, "p100"),
        (10.4, 100.5, "p100"),       # within tolerance
        (10.0, 250.0, "p250"),
        (9.5, 249.5, "p250"),
        (10.0, 400.0, "p400"),
        (10.0, 105.0, None),          # out of tolerance
        (50.0, 250.0, None),
    ],
)
def test_find_matching_preset_matches_python(lo, hi, expected_key):
    presets = _preset_set()
    py = _py.find_matching_preset(
        minimum_value=lo, maximum_value=hi, presets=tuple(presets)
    )
    cpp = _tuner_core.pressure_find_matching_preset(
        lo, hi, [_to_cpp_preset(p) for p in presets]
    )
    assert (py.key if py else None) == (cpp.key if cpp else None) == expected_key


# ---------------------------------------------------------------------------
# assess
# ---------------------------------------------------------------------------

def _check_assessment(py_result, cpp_result):
    assert py_result.guidance == cpp_result.guidance
    assert (py_result.warning or "") == (cpp_result.warning or "")
    py_key = py_result.matching_preset.key if py_result.matching_preset else None
    cpp_key = cpp_result.matching_preset.key if cpp_result.matching_preset else None
    assert py_key == cpp_key


def test_assess_no_calibration_matches_python():
    presets = _preset_set()
    for kind in ("map", "baro"):
        py = _py.assess(
            minimum_value=None,
            maximum_value=None,
            presets=tuple(presets),
            sensor_kind=kind,
        )
        cpp = _tuner_core.pressure_assess_calibration(
            None, None, [_to_cpp_preset(p) for p in presets],
            _tuner_core.PressureSensorKind.MAP if kind == "map"
            else _tuner_core.PressureSensorKind.BARO,
        )
        _check_assessment(py, cpp)


@pytest.mark.parametrize(
    "lo,hi,kind",
    [
        (10.0, 100.0, "map"),         # matches Inferred (Starter)
        (10.0, 250.0, "map"),         # matches Official
        (10.0, 400.0, "map"),         # matches Inferred (Starter)
        (50.0, 320.0, "map"),         # no match
        (0.0, 110.0, "baro"),         # no warning
        (0.0, 200.0, "baro"),         # warning + no match
        (10.0, 250.0, "baro"),        # warning + matched
    ],
)
def test_assess_matches_python(lo, hi, kind):
    presets = _preset_set()
    py = _py.assess(
        minimum_value=lo,
        maximum_value=hi,
        presets=tuple(presets),
        sensor_kind=kind,
    )
    cpp_kind = (_tuner_core.PressureSensorKind.MAP if kind == "map"
                else _tuner_core.PressureSensorKind.BARO)
    cpp = _tuner_core.pressure_assess_calibration(
        lo, hi, [_to_cpp_preset(p) for p in presets], cpp_kind,
    )
    _check_assessment(py, cpp)
