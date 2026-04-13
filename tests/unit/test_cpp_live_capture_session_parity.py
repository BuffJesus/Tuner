"""Python <-> C++ parity harness for the live capture session formatters.

Pins the C++ `live_capture_session_*` helpers (port of the pure-logic
half of `LiveCaptureSessionService`) against the Python service across:

  - status_text (recording / stopped-with-rows / ready branches)
  - ordered column names (profile-first then record-insertion fallback)
  - format_value (digits-fixed and Python repr)
  - format_csv (header order, missing cells, multi-row, repr fallback)
  - random capture sessions (full to_csv parity)

I/O — file open / stream-write / close lifecycle — is out of scope.
"""
from __future__ import annotations

import importlib
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tuner.domain.datalog import DataLogRecord
from tuner.domain.datalog_profile import DatalogChannelEntry, DatalogProfile
from tuner.services.live_capture_session_service import (
    CaptureSessionStatus,
    LiveCaptureSessionService,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_cpp_record(elapsed_ms: float, kvs: dict[str, float]):
    rec = _tuner_core.CapturedRecord()
    rec.elapsed_ms = elapsed_ms
    rec.keys = list(kvs.keys())
    rec.values = list(kvs.values())
    return rec


def _build_session(profile: DatalogProfile,
                   rows: list[dict[str, float]]) -> LiveCaptureSessionService:
    """Drive the Python service through start -> append* -> stop and
    return it for full to_csv() inspection."""
    from tuner.domain.output_channels import (
        OutputChannelSnapshot,
        OutputChannelValue,
    )
    svc = LiveCaptureSessionService()
    svc.start(profile)
    base = datetime.now(UTC)
    for i, row in enumerate(rows):
        snap = OutputChannelSnapshot(
            timestamp=base + timedelta(milliseconds=i * 100),
            values=[OutputChannelValue(name=k, value=v) for k, v in row.items()],
        )
        svc.append(snap)
    svc.stop()
    return svc


def _digits_map(profile: DatalogProfile) -> dict[str, int]:
    out: dict[str, int] = {}
    for ch in profile.channels:
        out[ch.name] = ch.format_digits if ch.format_digits is not None else -1
    return out


def _records_to_cpp(svc: LiveCaptureSessionService):
    cpp_records = []
    if not svc._records:
        return cpp_records
    base = svc._records[0].timestamp
    for r in svc._records:
        elapsed_ms = (r.timestamp - base).total_seconds() * 1000.0
        cpp_records.append(_to_cpp_record(elapsed_ms, dict(r.values)))
    return cpp_records


# ---------------------------------------------------------------------------
# status_text parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("recording,row_count,elapsed", [
    (False, 0, 0.0),
    (False, 0, 12.5),       # ready (no rows wins over elapsed)
    (True, 0, 0.0),
    (True, 5, 1.234),
    (True, 1234, 95.67),
    (False, 5, 1.5),        # stopped with rows
    (False, 100, 60.0),
    (False, 1, 0.05),
])
def test_status_text_parity(recording, row_count, elapsed):
    py = CaptureSessionStatus(
        recording=recording,
        row_count=row_count,
        elapsed_seconds=elapsed,
        profile_name="(none)",
    ).status_text
    cpp = _tuner_core.live_capture_session_status_text(
        recording, row_count, elapsed)
    assert py == cpp


# ---------------------------------------------------------------------------
# ordered_column_names parity
# ---------------------------------------------------------------------------


def test_ordered_column_names_profile_first_then_records():
    profile = DatalogProfile(
        name="p",
        channels=[
            DatalogChannelEntry(name="rpm"),
            DatalogChannelEntry(name="map"),
            DatalogChannelEntry(name="afr"),
        ],
    )
    rows = [
        {"rpm": 800, "map": 30, "clt": 90},
        {"rpm": 850, "afr": 14.7, "iat": 25},
    ]
    svc = _build_session(profile, rows)
    py_cols = svc._ordered_column_names()

    cpp_cols = _tuner_core.live_capture_session_ordered_column_names(
        [ch.name for ch in profile.enabled_channels],
        _records_to_cpp(svc),
    )
    assert py_cols == cpp_cols


def test_ordered_column_names_no_profile_uses_record_insertion_order():
    # Drive directly without profile by faking a service with no
    # _profile attribute path. Use profile= None branch.
    svc = LiveCaptureSessionService()
    # Force _profile = None and inject records by hand for the no-
    # profile fallback path. The Python service only hits the
    # no-profile branch internally; tests can drive it via private state.
    svc._profile = None
    svc._records = [
        DataLogRecord(values={"a": 1.0, "b": 2.0}),
        DataLogRecord(values={"b": 3.0, "c": 4.0}),
        DataLogRecord(values={"c": 5.0, "a": 6.0}),
    ]
    py_cols = svc._ordered_column_names()

    cpp_records = []
    for r in svc._records:
        cpp_records.append(_to_cpp_record(0.0, dict(r.values)))
    cpp_cols = _tuner_core.live_capture_session_ordered_column_names(
        [], cpp_records)
    assert py_cols == cpp_cols


# ---------------------------------------------------------------------------
# format_value parity (round-trip via the Python format strings)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value,digits,expected", [
    (3.14159, 2, "3.14"),
    (0.0, 3, "0.000"),
    (-1.5, 1, "-1.5"),
    (100.0, 0, "100"),
])
def test_format_value_fixed_digits_parity(value, digits, expected):
    # Python equivalent: f"{value:.{digits}f}"
    py = f"{value:.{digits}f}"
    cpp = _tuner_core.live_capture_session_format_value(value, digits)
    assert py == expected
    assert cpp == expected


@pytest.mark.parametrize("value,expected_repr", [
    (42.0, "42.0"),
    (0.0, "0.0"),
    (3.14, "3.14"),
    (-1.5, "-1.5"),
    (0.001, "0.001"),
    (123456.789, "123456.789"),
])
def test_format_value_repr_parity(value, expected_repr):
    # Repr falls through to tune_value_preview::format_scalar_python_repr,
    # which already has its own parity coverage in
    # tests/unit/test_cpp_tune_value_preview_parity.py — we just spot-
    # check the integration here over reasonable mid-range values that
    # both implementations agree on.
    py = str(value)
    cpp = _tuner_core.live_capture_session_format_value(value, -1)
    assert py == expected_repr
    assert cpp == expected_repr
    assert py == cpp


# ---------------------------------------------------------------------------
# format_csv full parity
# ---------------------------------------------------------------------------


def test_format_csv_single_row_full_parity():
    profile = DatalogProfile(
        name="p",
        channels=[
            DatalogChannelEntry(name="rpm", format_digits=0),
            DatalogChannelEntry(name="map", format_digits=1),
            DatalogChannelEntry(name="afr", format_digits=2),
        ],
    )
    svc = _build_session(profile, [{"rpm": 800.0, "map": 30.5, "afr": 14.72}])
    py_csv = svc.to_csv()
    cpp_csv = _tuner_core.live_capture_session_format_csv(
        _records_to_cpp(svc),
        svc._ordered_column_names(),
        _digits_map(profile),
    )
    assert py_csv == cpp_csv


def test_format_csv_missing_cells_render_empty():
    profile = DatalogProfile(
        name="p",
        channels=[
            DatalogChannelEntry(name="rpm", format_digits=0),
            DatalogChannelEntry(name="map", format_digits=0),
        ],
    )
    svc = _build_session(profile, [
        {"rpm": 800.0, "map": 30.0},
        {"rpm": 850.0},  # map missing
    ])
    py_csv = svc.to_csv()
    cpp_csv = _tuner_core.live_capture_session_format_csv(
        _records_to_cpp(svc),
        svc._ordered_column_names(),
        _digits_map(profile),
    )
    assert py_csv == cpp_csv


def test_format_csv_repr_fallback_for_unconfigured_columns():
    profile = DatalogProfile(
        name="p",
        channels=[
            DatalogChannelEntry(name="v", format_digits=None),
        ],
    )
    svc = _build_session(profile, [{"v": 3.14}])
    py_csv = svc.to_csv()
    cpp_csv = _tuner_core.live_capture_session_format_csv(
        _records_to_cpp(svc),
        svc._ordered_column_names(),
        _digits_map(profile),
    )
    assert py_csv == cpp_csv


def test_format_csv_empty_records_returns_empty_string():
    profile = DatalogProfile(
        name="p",
        channels=[DatalogChannelEntry(name="x", format_digits=0)],
    )
    svc = LiveCaptureSessionService()
    svc.start(profile)
    svc.stop()
    py_csv = svc.to_csv()
    cpp_csv = _tuner_core.live_capture_session_format_csv(
        _records_to_cpp(svc),
        svc._ordered_column_names(),
        _digits_map(profile),
    )
    assert py_csv == cpp_csv == ""


def test_format_csv_random_session_parity():
    rng = random.Random(0xCAFEFEED)
    channels = [
        DatalogChannelEntry(name=f"ch{i}",
                            format_digits=rng.choice([0, 1, 2, 3, None]))
        for i in range(6)
    ]
    profile = DatalogProfile(name="p", channels=channels)

    rows: list[dict[str, float]] = []
    for _ in range(40):
        # Each row drops 0..2 channels at random to exercise the
        # missing-cell branch + the Python dict insertion-order path.
        present = list(channels)
        rng.shuffle(present)
        drop_n = rng.randint(0, 2)
        kept = present[: len(present) - drop_n]
        row: dict[str, float] = {}
        for ch in kept:
            row[ch.name] = rng.uniform(-1000.0, 1000.0)
        rows.append(row)

    svc = _build_session(profile, rows)
    py_csv = svc.to_csv()
    cpp_csv = _tuner_core.live_capture_session_format_csv(
        _records_to_cpp(svc),
        svc._ordered_column_names(),
        _digits_map(profile),
    )
    assert py_csv == cpp_csv
