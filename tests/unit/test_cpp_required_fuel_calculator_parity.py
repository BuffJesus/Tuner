"""Python ↔ C++ parity harness for tuner_core::required_fuel_calculator."""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

import pytest

from tuner.services.required_fuel_calculator_service import (
    RequiredFuelCalculatorService,
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
    reason="tuner_core C++ extension not built — see cpp/README.md.",
)


_py = RequiredFuelCalculatorService()


@pytest.mark.parametrize(
    "displacement_cc,cylinders,injflow,afr",
    [
        (2000.0, 4, 220.0, 14.7),     # Mazda Miata-ish
        (1300.0, 4, 190.0, 14.7),     # B16/Civic-ish
        (5000.0, 8, 350.0, 14.7),     # LS-ish
        (1600.0, 4, 1000.0, 14.7),    # Forced induction high-flow injectors
        (4900.0, 6, 1700.0, 14.7),    # Ford 300 twin GT28 (matches the fixture project)
        (1000.0, 3, 150.0, 14.7),     # Triple
        (998.0, 2, 80.0, 14.7),       # Tiny twin
        (3000.0, 6, 250.0, 14.7),
    ],
)
def test_calculate_matches_python(displacement_cc, cylinders, injflow, afr):
    py = _py.calculate(displacement_cc, cylinders, injflow, afr)
    cpp = _tuner_core.calculate_required_fuel(
        displacement_cc, cylinders, injflow, afr
    )
    assert cpp.is_valid == py.is_valid
    assert cpp.req_fuel_ms == pytest.approx(py.req_fuel_ms, rel=1e-12)
    assert cpp.req_fuel_stored == py.req_fuel_stored
    assert cpp.inputs_summary == py.inputs_summary
    assert cpp.cylinder_count == py.cylinder_count
    assert cpp.target_afr == pytest.approx(py.target_afr)


@pytest.mark.parametrize(
    "displacement_cc,cylinders,injflow,afr",
    [
        (0.0, 4, 220.0, 14.7),
        (-1.0, 4, 220.0, 14.7),
        (2000.0, 0, 220.0, 14.7),
        (2000.0, -2, 220.0, 14.7),
        (2000.0, 4, 0.0, 14.7),
        (2000.0, 4, 220.0, 0.0),
        (2000.0, 4, 220.0, -1.0),
    ],
)
def test_invalid_inputs_match_python(displacement_cc, cylinders, injflow, afr):
    py = _py.calculate(displacement_cc, cylinders, injflow, afr)
    cpp = _tuner_core.calculate_required_fuel(
        displacement_cc, cylinders, injflow, afr
    )
    assert cpp.is_valid is False
    assert py.is_valid is False
    assert cpp.req_fuel_ms == 0.0
    assert cpp.req_fuel_stored == 0
    assert cpp.inputs_summary == py.inputs_summary


def test_clipping_matches_python():
    # Tiny injectors + huge engine — both implementations clip to 255.
    py = _py.calculate(8000.0, 8, 50.0, 14.7)
    cpp = _tuner_core.calculate_required_fuel(8000.0, 8, 50.0, 14.7)
    assert cpp.req_fuel_stored == py.req_fuel_stored == 255


def test_random_inputs_match_python():
    rng = random.Random(0xC0FEE)
    for _ in range(100):
        d = rng.uniform(500.0, 8000.0)
        c = rng.randint(1, 12)
        flow = rng.uniform(50.0, 2000.0)
        afr = rng.uniform(8.0, 22.0)
        py = _py.calculate(d, c, flow, afr)
        cpp = _tuner_core.calculate_required_fuel(d, c, flow, afr)
        assert cpp.req_fuel_ms == pytest.approx(py.req_fuel_ms, rel=1e-12)
        assert cpp.req_fuel_stored == py.req_fuel_stored
        assert cpp.inputs_summary == py.inputs_summary
