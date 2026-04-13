"""Python ↔ C++ parity harness for tuner_core::tuning_page_diff."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tuner.domain.tune import TuneValue
from tuner.services.tuning_page_diff_service import TuningPageDiffService


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


_py = TuningPageDiffService()


def _make_page(parameter_names):
    page = Mock()
    page.parameter_names = tuple(parameter_names)
    return page


def _make_edit_service(staged, base, dirty):
    edit = Mock()
    edit.is_dirty = lambda name: name in dirty
    edit.get_value = lambda name: (
        TuneValue(name=name, value=staged[name]) if name in staged else None
    )
    edit.get_base_value = lambda name: (
        TuneValue(name=name, value=base[name]) if name in base else None
    )
    return edit


def _run_both(parameter_names, dirty, staged, base):
    page = _make_page(parameter_names)
    edit = _make_edit_service(staged, base, dirty)
    py_result = _py.build_page_diff(page, edit)
    cpp_result = _tuner_core.tuning_page_diff_build(
        list(parameter_names),
        set(dirty),
        list(staged.items()),
        list(base.items()),
    )
    return py_result, cpp_result


def _check_entries(py, cpp):
    assert len(py.entries) == len(cpp.entries)
    for p, c in zip(py.entries, cpp.entries):
        assert c.name == p.name
        assert c.before_preview == p.before_preview
        assert c.after_preview == p.after_preview


def _check_summary(py, cpp):
    assert _tuner_core.tuning_page_diff_summary(cpp) == py.summary


def _check_detail(py, cpp):
    assert _tuner_core.tuning_page_diff_detail_text(cpp) == py.detail_text


def _check_all(py, cpp):
    _check_entries(py, cpp)
    _check_summary(py, cpp)
    _check_detail(py, cpp)


# ---------------------------------------------------------------------------
# build_page_diff parity
# ---------------------------------------------------------------------------

def test_empty_page_matches_python():
    py, cpp = _run_both([], set(), {}, {})
    _check_all(py, cpp)


def test_no_dirty_parameters_matches_python():
    py, cpp = _run_both(["a", "b"], set(),
                        {"a": 1.0, "b": 2.0},
                        {"a": 0.0, "b": 0.0})
    _check_all(py, cpp)


def test_single_dirty_scalar_matches_python():
    py, cpp = _run_both(["a", "b", "c"], {"b"},
                        {"a": 1.0, "b": 2.0, "c": 3.0},
                        {"a": 0.0, "b": 0.0, "c": 0.0})
    _check_all(py, cpp)
    assert len(cpp.entries) == 1
    assert cpp.entries[0].name == "b"


def test_dirty_with_missing_staged_value_is_skipped():
    py, cpp = _run_both(["a"], {"a"}, {}, {"a": 0.0})
    _check_all(py, cpp)
    assert len(cpp.entries) == 0


def test_dirty_with_missing_base_value_falls_back_to_na():
    py, cpp = _run_both(["newParam"], {"newParam"},
                        {"newParam": 5.0}, {})
    _check_all(py, cpp)
    assert cpp.entries[0].before_preview == "n/a"


def test_input_order_is_preserved():
    py, cpp = _run_both(["zeta", "alpha", "mu"],
                        {"zeta", "alpha", "mu"},
                        {"zeta": 1.0, "alpha": 2.0, "mu": 3.0},
                        {})
    _check_all(py, cpp)
    assert [e.name for e in cpp.entries] == ["zeta", "alpha", "mu"]


def test_list_valued_diff_uses_list_preview():
    py, cpp = _run_both(["veRow"], {"veRow"},
                        {"veRow": [75.0, 80.0, 85.0, 90.0, 95.0]},
                        {"veRow": [70.0, 75.0, 80.0, 85.0, 90.0]})
    _check_all(py, cpp)


def test_full_page_diff_shape_matches_python():
    py, cpp = _run_both(
        ["reqFuel", "nCylinders", "veRow0", "afrTarget", "ignAdv", "untouched"],
        {"reqFuel", "veRow0", "ignAdv"},
        {
            "reqFuel": 12.5,
            "nCylinders": 4.0,
            "veRow0": [75.0, 80.0, 85.0, 90.0, 95.0],
            "afrTarget": 14.7,
            "ignAdv": 25.0,
            "untouched": 1.0,
        },
        {
            "reqFuel": 10.0,
            "nCylinders": 4.0,
            "afrTarget": 14.7,
            "ignAdv": 23.0,
            "untouched": 1.0,
        },
    )
    _check_all(py, cpp)


# ---------------------------------------------------------------------------
# summary / detail_text parity
# ---------------------------------------------------------------------------

def test_summary_singular_vs_plural_matches_python():
    py1, cpp1 = _run_both(["a"], {"a"}, {"a": 1.0}, {})
    _check_summary(py1, cpp1)
    py2, cpp2 = _run_both(["a", "b"], {"a", "b"},
                          {"a": 1.0, "b": 2.0}, {})
    _check_summary(py2, cpp2)
