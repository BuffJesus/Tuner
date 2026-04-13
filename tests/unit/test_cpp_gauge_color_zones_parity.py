"""Python ↔ C++ parity harness for tuner_core::gauge_color_zones.

Pins the C++ derive_zones function against
`DashboardLayoutService._zones_from_gauge_config` byte-for-byte
across every threshold combination the dashboard exercises.
"""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

import pytest

from tuner.domain.ecu_definition import GaugeConfiguration
from tuner.services.dashboard_layout_service import DashboardLayoutService


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


def _make_gc(name="g", lo_danger=None, lo_warn=None, hi_warn=None, hi_danger=None):
    return GaugeConfiguration(
        name=name,
        channel="ch",
        title=name,
        units="",
        lo=None,
        hi=None,
        lo_danger=lo_danger,
        lo_warn=lo_warn,
        hi_warn=hi_warn,
        hi_danger=hi_danger,
    )


def _make_thresholds(lo_danger, lo_warn, hi_warn, hi_danger):
    t = _tuner_core.GaugeThresholds()
    t.lo_danger = lo_danger
    t.lo_warn = lo_warn
    t.hi_warn = hi_warn
    t.hi_danger = hi_danger
    return t


def _check(py_zones, cpp_zones):
    assert len(py_zones) == len(cpp_zones)
    for p, c in zip(py_zones, cpp_zones):
        assert c.lo == pytest.approx(p.lo)
        assert c.hi == pytest.approx(p.hi)
        assert c.color == p.color


def _run_both(lo, hi, lo_danger, lo_warn, hi_warn, hi_danger):
    gc = _make_gc(
        lo_danger=lo_danger, lo_warn=lo_warn,
        hi_warn=hi_warn, hi_danger=hi_danger,
    )
    py_zones = DashboardLayoutService._zones_from_gauge_config(gc, lo, hi)
    cpp_zones = _tuner_core.gauge_derive_color_zones(
        lo, hi,
        _make_thresholds(lo_danger, lo_warn, hi_warn, hi_danger),
    )
    _check(py_zones, cpp_zones)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def test_no_thresholds_yields_empty():
    _run_both(0.0, 8000.0, None, None, None, None)


def test_only_high_warn_and_danger_matches_python():
    _run_both(0.0, 8000.0, None, None, 6500.0, 7500.0)


def test_full_5_band_layout_matches_python():
    _run_both(0.0, 16.0, 8.0, 11.0, 14.0, 15.0)


def test_lo_danger_equals_lo_drops_band_matches_python():
    _run_both(0.0, 16.0, 0.0, 11.0, None, None)


def test_hi_danger_equals_hi_drops_band_matches_python():
    _run_both(0.0, 8000.0, None, None, 6500.0, 8000.0)


def test_only_lo_warn_matches_python():
    _run_both(0.0, 16.0, None, 11.0, None, None)


def test_only_hi_warn_matches_python():
    _run_both(0.0, 16.0, None, None, 11.0, None)


def test_zero_width_warning_band_dropped_matches_python():
    _run_both(0.0, 10.0, 5.0, 5.0, None, None)


def test_battery_voltage_shape_matches_python():
    # From the default Speeduino battery widget: 8..16V with
    # warning 11..12 and danger 8..11
    _run_both(8.0, 16.0, 11.0, 12.0, None, None)


def test_coolant_shape_matches_python():
    # From the default coolant widget: -40..130 with warn 90..110 and danger 110..130
    _run_both(-40.0, 130.0, None, 90.0, 110.0, None)


def test_random_threshold_combinations_match_python():
    rng = random.Random(0xC0DE)
    for _ in range(50):
        lo = rng.uniform(-100, 0)
        hi = rng.uniform(50, 200)
        # Sample 4 sorted values for the threshold ladder, with each
        # field independently 50% likely to be present.
        ladder = sorted(rng.uniform(lo, hi) for _ in range(4))
        lo_danger = ladder[0] if rng.random() < 0.7 else None
        lo_warn = ladder[1] if rng.random() < 0.7 else None
        hi_warn = ladder[2] if rng.random() < 0.7 else None
        hi_danger = ladder[3] if rng.random() < 0.7 else None
        _run_both(lo, hi, lo_danger, lo_warn, hi_warn, hi_danger)
