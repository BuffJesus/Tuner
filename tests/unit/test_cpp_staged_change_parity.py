"""Python ↔ C++ parity harness for tuner_core::staged_change.

Pins the C++ summarize() function against
`StagedChangeService.summarize` byte-for-byte across the staged
review surface — entry order, preview formatting, page-title
fallback, and is_written membership.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tuner.domain.tune import TuneValue
from tuner.services.staged_change_service import StagedChangeService


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


_py = StagedChangeService()


def _make_edit_service(staged: dict, base: dict | None = None):
    """Build a Mock that satisfies LocalTuneEditService for summarize()."""
    base = base or {}
    edit = Mock()
    edit.staged_values = {
        name: TuneValue(name=name, value=value)
        for name, value in staged.items()
    }
    def get_base(name):
        if name in base:
            return TuneValue(name=name, value=base[name])
        return None
    edit.get_base_value = get_base
    return edit


def _run_both(staged, base=None, page_titles=None, written=None):
    base = base or {}
    page_titles = page_titles or {}
    written = written or set()

    edit = _make_edit_service(staged, base)
    py_entries = _py.summarize(
        edit, page_titles=page_titles, written_names=written
    )
    cpp_entries = _tuner_core.staged_change_summarize(
        list(staged.items()),
        list(base.items()),
        list(page_titles.items()),
        written,
    )
    return py_entries, cpp_entries


def _check(py_entries, cpp_entries):
    assert len(py_entries) == len(cpp_entries)
    for p, c in zip(py_entries, cpp_entries):
        assert c.name == p.name
        assert c.preview == p.preview
        assert c.before_preview == p.before_preview
        assert c.page_title == p.page_title
        assert c.is_written == p.is_written


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def test_empty_staged_dict_matches_python():
    py, cpp = _run_both({})
    _check(py, cpp)


def test_single_scalar_entry_matches_python():
    py, cpp = _run_both(
        {"reqFuel": 12.5},
        {"reqFuel": 10.0},
        {"reqFuel": "Engine Constants"},
    )
    _check(py, cpp)


def test_missing_base_value_falls_back_to_na():
    py, cpp = _run_both({"newParam": 5.0})
    _check(py, cpp)
    assert cpp[0].before_preview == "n/a"


def test_missing_page_title_falls_back_to_other():
    py, cpp = _run_both({"x": 1.0}, base={"x": 0.0})
    _check(py, cpp)
    assert cpp[0].page_title == "Other"


def test_is_written_membership_matches_python():
    py, cpp = _run_both(
        {"a": 1.0, "b": 2.0, "c": 3.0},
        written={"a", "c"},
    )
    _check(py, cpp)


def test_entries_are_sorted_lexicographically():
    py, cpp = _run_both({"zeta": 1.0, "alpha": 2.0, "mu": 3.0})
    _check(py, cpp)
    assert [e.name for e in cpp] == ["alpha", "mu", "zeta"]


def test_list_valued_entry_uses_list_preview():
    py, cpp = _run_both(
        {"veRow": [75.0, 80.0, 85.0, 90.0, 95.0]},
        {"veRow": [70.0, 75.0, 80.0, 85.0, 90.0]},
    )
    _check(py, cpp)


def test_full_workspace_review_shape_matches_python():
    py, cpp = _run_both(
        {
            "reqFuel": 12.5,
            "nCylinders": 4.0,
            "veRow0": [70.0, 75.0, 80.0, 85.0, 90.0],
            "afrTarget": 14.7,
            "ignAdv": 25.0,
        },
        base={
            "reqFuel": 10.0,
            "nCylinders": 4.0,
            "afrTarget": 13.5,
        },
        page_titles={
            "reqFuel": "Engine Constants",
            "nCylinders": "Engine Constants",
            "veRow0": "VE Table",
            "afrTarget": "AFR Table",
        },
        written={"reqFuel"},
    )
    _check(py, cpp)
