"""Python ↔ C++ parity harness for tuner_core::sync_state."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tuner.services.sync_state_service import SyncStateService


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


_py = SyncStateService()


def _make_definition(signature=None, page_sizes=None):
    d = Mock()
    d.firmware_signature = signature
    d.page_sizes = page_sizes or []
    return d


def _make_tune_constants(values):
    """Build a Mock TuneFile.constants list from a name→value dict.

    `Mock(name=...)` collides with the constructor's own `name`
    kwarg, so we set both attributes after construction.
    """
    out = []
    for k, v in values.items():
        m = Mock()
        m.name = k
        m.value = v
        out.append(m)
    return out


def _make_tune_file(signature=None, page_count=None, constants=None, pc_vars=None):
    t = Mock()
    t.signature = signature
    t.page_count = page_count
    t.constants = _make_tune_constants(constants or {})
    t.pc_variables = _make_tune_constants(pc_vars or {})
    return t


def _to_cpp_def(signature, page_sizes):
    d = _tuner_core.SyncStateDefinitionInputs()
    d.firmware_signature = signature
    d.page_sizes = page_sizes
    return d


def _to_cpp_tune(signature, page_count, base_dict):
    t = _tuner_core.SyncStateTuneFileInputs()
    t.signature = signature
    t.page_count = page_count
    t.base_values = list(base_dict.items())
    return t


def _check(py, cpp):
    assert cpp.has_ecu_ram == py.has_ecu_ram
    assert cpp.connection_state == py.connection_state
    assert cpp.is_clean() == py.is_clean
    assert len(cpp.mismatches) == len(py.mismatches)
    py_kinds = sorted(m.kind.value for m in py.mismatches)
    cpp_kinds = sorted(m.kind.name.lower() for m in cpp.mismatches)
    assert py_kinds == cpp_kinds
    py_details = sorted(m.detail for m in py.mismatches)
    cpp_details = sorted(m.detail for m in cpp.mismatches)
    assert py_details == cpp_details


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def test_no_inputs_clean_state():
    py = _py.build(None, None, None, False, "offline")
    cpp = _tuner_core.sync_state_build(None, None, None, False, "offline")
    _check(py, cpp)


def test_signature_mismatch_matches_python():
    py = _py.build(
        _make_definition("speeduino 202501-T41"),
        _make_tune_file("speeduino 202501-MEGA"),
        None, False, "connected",
    )
    cpp = _tuner_core.sync_state_build(
        _to_cpp_def("speeduino 202501-T41", []),
        _to_cpp_tune("speeduino 202501-MEGA", None, {}),
        None, False, "connected",
    )
    _check(py, cpp)


def test_matching_signatures_clean_matches_python():
    py = _py.build(
        _make_definition("sig"),
        _make_tune_file("sig"),
        None, False, "connected",
    )
    cpp = _tuner_core.sync_state_build(
        _to_cpp_def("sig", []),
        _to_cpp_tune("sig", None, {}),
        None, False, "connected",
    )
    _check(py, cpp)


def test_page_size_mismatch_matches_python():
    py = _py.build(
        _make_definition("sig", [128, 256, 128]),
        _make_tune_file("sig", page_count=5),
        None, False, "connected",
    )
    cpp = _tuner_core.sync_state_build(
        _to_cpp_def("sig", [128, 256, 128]),
        _to_cpp_tune("sig", 5, {}),
        None, False, "connected",
    )
    _check(py, cpp)


def test_ecu_vs_tune_diff_matches_python():
    py = _py.build(
        _make_definition("sig", [128]),
        _make_tune_file("sig", 1, constants={"reqFuel": 12.5, "nCylinders": 4.0}),
        {"reqFuel": 10.0, "nCylinders": 4.0},  # reqFuel differs
        False, "connected",
    )
    cpp = _tuner_core.sync_state_build(
        _to_cpp_def("sig", [128]),
        _to_cpp_tune("sig", 1, {"reqFuel": 12.5, "nCylinders": 4.0}),
        [("reqFuel", 10.0), ("nCylinders", 4.0)],
        False, "connected",
    )
    _check(py, cpp)


def test_ecu_vs_tune_with_more_than_5_diffs_matches_python():
    base = {f"p{i}": 0.0 for i in range(6)}
    ram = {f"p{i}": float(i + 1) for i in range(6)}
    py = _py.build(
        _make_definition("sig", [128]),
        _make_tune_file("sig", 1, constants=base),
        ram, False, "connected",
    )
    cpp = _tuner_core.sync_state_build(
        _to_cpp_def("sig", [128]),
        _to_cpp_tune("sig", 1, base),
        list(ram.items()),
        False, "connected",
    )
    _check(py, cpp)


def test_stale_staged_matches_python():
    py = _py.build(None, None, None, True, "offline")
    cpp = _tuner_core.sync_state_build(None, None, None, True, "offline")
    _check(py, cpp)


def test_has_staged_with_ecu_ram_no_stale_matches_python():
    py = _py.build(
        _make_definition("sig", [128]),
        _make_tune_file("sig", 1),
        {},
        True, "connected",
    )
    cpp = _tuner_core.sync_state_build(
        _to_cpp_def("sig", [128]),
        _to_cpp_tune("sig", 1, {}),
        [],
        True, "connected",
    )
    _check(py, cpp)


def test_combined_mismatches_match_python():
    """Multiple mismatch kinds firing in one call."""
    py = _py.build(
        _make_definition("sig-a", [128, 128]),
        _make_tune_file("sig-b", page_count=3, constants={"x": 1.0}),
        {"x": 2.0},  # diff → ECU_VS_TUNE
        False, "connected",
    )
    cpp = _tuner_core.sync_state_build(
        _to_cpp_def("sig-a", [128, 128]),
        _to_cpp_tune("sig-b", 3, {"x": 1.0}),
        [("x", 2.0)],
        False, "connected",
    )
    _check(py, cpp)
    assert len(cpp.mismatches) == 3
