"""Python ↔ C++ parity harness for tuner_core::evidence_replay_comparison."""
from __future__ import annotations

import importlib
import random
import sys
from datetime import datetime
from pathlib import Path

import pytest

from tuner.services.evidence_replay_comparison_service import (
    EvidenceReplayComparisonService,
)
from tuner.services.evidence_replay_service import (
    EvidenceReplayChannel,
    EvidenceReplaySnapshot,
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


_py = EvidenceReplayComparisonService()


def _make_snapshot(channels):
    return EvidenceReplaySnapshot(
        captured_at=datetime(2026, 1, 1, 0, 0, 0),
        session_state="connected",
        connection_text="Connection",
        source_text="Source",
        sync_summary_text="Sync OK",
        sync_mismatch_details=(),
        staged_summary_text="No staged.",
        operation_summary_text="",
        operation_session_count=0,
        latest_write_text=None,
        latest_burn_text=None,
        runtime_summary_text="Runtime",
        runtime_channel_count=len(channels),
        runtime_age_seconds=0.0,
        runtime_channels=tuple(channels),
        evidence_summary_text="",
    )


def _to_cpp_channels(channels):
    out = []
    for ch in channels:
        c = _tuner_core.EvidenceReplayChannel()
        c.name = ch.name
        c.value = ch.value
        c.units = ch.units
        out.append(c)
    return out


def _run_both(baseline_channels, current_channels, relevant=()):
    baseline_snap = _make_snapshot(baseline_channels)
    current_snap = _make_snapshot(current_channels)
    py = _py.build(
        baseline_snapshot=baseline_snap,
        current_snapshot=current_snap,
        relevant_channel_names=tuple(relevant),
    )
    cpp = _tuner_core.evidence_replay_compare_channels(
        _to_cpp_channels(baseline_channels),
        _to_cpp_channels(current_channels),
        list(relevant),
    )
    return py, cpp


def _check(py, cpp):
    if py is None:
        assert cpp is None
        return
    assert cpp is not None
    assert cpp.summary_text == py.summary_text
    assert cpp.detail_text == py.detail_text
    assert len(cpp.changed_channels) == len(py.changed_channels)
    for c, p in zip(cpp.changed_channels, py.changed_channels):
        assert c.name == p.name
        assert c.previous_value == pytest.approx(p.previous_value)
        assert c.current_value == pytest.approx(p.current_value)
        assert c.delta_value == pytest.approx(p.delta_value)
        assert (c.units or None) == (p.units or None)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def test_no_overlap_returns_none():
    py, cpp = _run_both(
        [EvidenceReplayChannel("rpm", 5000.0)],
        [EvidenceReplayChannel("clt", 90.0)],
    )
    _check(py, cpp)
    assert py is None


def test_single_delta_matches_python():
    py, cpp = _run_both(
        [EvidenceReplayChannel("rpm", 5000.0, "rpm")],
        [EvidenceReplayChannel("rpm", 5500.0, "rpm")],
    )
    _check(py, cpp)


def test_top_4_by_absolute_delta_matches_python():
    py, cpp = _run_both(
        [
            EvidenceReplayChannel("a", 0.0),
            EvidenceReplayChannel("b", 0.0),
            EvidenceReplayChannel("c", 0.0),
            EvidenceReplayChannel("d", 0.0),
            EvidenceReplayChannel("e", 0.0),
            EvidenceReplayChannel("f", 0.0),
        ],
        [
            EvidenceReplayChannel("a", 1.0),
            EvidenceReplayChannel("b", 50.0),
            EvidenceReplayChannel("c", -100.0),
            EvidenceReplayChannel("d", 25.0),
            EvidenceReplayChannel("e", 200.0),
            EvidenceReplayChannel("f", 5.0),
        ],
    )
    _check(py, cpp)
    assert len(cpp.changed_channels) == 4


def test_case_insensitive_lookup_matches_python():
    py, cpp = _run_both(
        [EvidenceReplayChannel("RPM", 5000.0)],
        [EvidenceReplayChannel("rpm", 5500.0)],
        relevant=("RPM",),
    )
    _check(py, cpp)


def test_tiny_deltas_filtered_matches_python():
    py, cpp = _run_both(
        [EvidenceReplayChannel("rpm", 5000.0)],
        [EvidenceReplayChannel("rpm", 5000.0 + 1e-12)],
    )
    _check(py, cpp)


def test_relevant_filter_matches_python():
    py, cpp = _run_both(
        [
            EvidenceReplayChannel("rpm", 5000.0),
            EvidenceReplayChannel("clt", 80.0),
        ],
        [
            EvidenceReplayChannel("rpm", 5500.0),
            EvidenceReplayChannel("clt", 90.0),
        ],
        relevant=("rpm",),
    )
    _check(py, cpp)
    assert len(cpp.changed_channels) == 1
    assert cpp.changed_channels[0].name == "rpm"


def test_units_fall_back_when_current_missing_matches_python():
    py, cpp = _run_both(
        [EvidenceReplayChannel("rpm", 5000.0, "rpm")],
        [EvidenceReplayChannel("rpm", 5500.0)],
    )
    _check(py, cpp)


def test_detail_text_format_matches_python():
    py, cpp = _run_both(
        [EvidenceReplayChannel("rpm", 5000.0, "rpm")],
        [EvidenceReplayChannel("rpm", 5500.0, "rpm")],
    )
    _check(py, cpp)
    assert "rpm +500.0 rpm" in cpp.detail_text


def test_random_channel_set_matches_python():
    rng = random.Random(0xC0DE)
    for _ in range(10):
        names = ["rpm", "clt", "iat", "map", "tps", "afr", "ego"]
        baseline = [
            EvidenceReplayChannel(name, rng.uniform(0, 1000), "x")
            for name in names
        ]
        current = [
            EvidenceReplayChannel(name, rng.uniform(0, 1000), "x")
            for name in names
        ]
        py, cpp = _run_both(baseline, current)
        _check(py, cpp)
