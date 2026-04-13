"""Python ↔ C++ parity harness for tuner_core::release_manifest."""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

from tuner.services.release_manifest_service import ReleaseManifestService


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


_py = ReleaseManifestService()


def _write_manifest(payload: dict) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="tuner-rm-"))
    (tmp_dir / "release_manifest.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return tmp_dir


def _check_entry_pair(py_entry, cpp_entry):
    assert cpp_entry.file_name == py_entry.file_name
    py_board = py_entry.board_family.name if py_entry.board_family else None
    cpp_board = cpp_entry.board_family.name if cpp_entry.board_family else None
    assert cpp_board == py_board
    assert cpp_entry.version_label == py_entry.version_label
    assert cpp_entry.is_experimental == py_entry.is_experimental
    assert cpp_entry.artifact_kind.name.lower() == py_entry.artifact_kind.value
    assert cpp_entry.preferred == py_entry.preferred
    assert cpp_entry.definition_file_name == py_entry.definition_file_name
    assert cpp_entry.tune_file_name == py_entry.tune_file_name
    assert cpp_entry.firmware_signature == py_entry.firmware_signature


def _check_round_trip(payload: dict):
    text = json.dumps(payload)
    cpp_text = _tuner_core.release_manifest_parse_text(text)
    tmp = _write_manifest(payload)
    py = _py.load(tmp)
    cpp_load = _tuner_core.release_manifest_load(tmp)
    assert py is not None
    assert len(cpp_text.firmware) == len(py.firmware)
    assert len(cpp_load.firmware) == len(py.firmware)
    for cpp_entry, py_entry in zip(cpp_text.firmware, py.firmware):
        _check_entry_pair(py_entry, cpp_entry)
    for cpp_entry, py_entry in zip(cpp_load.firmware, py.firmware):
        _check_entry_pair(py_entry, cpp_entry)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_empty_manifest_matches_python():
    _check_round_trip({"firmware": []})


def test_minimal_entry_matches_python():
    _check_round_trip({"firmware": [{"file": "speeduino.hex"}]})


def test_full_entry_matches_python():
    _check_round_trip({
        "firmware": [
            {
                "file": "speeduino-dropbear-v2.0.1.hex",
                "board_family": "TEENSY41",
                "version": "v2.0.1",
                "is_experimental": False,
                "artifact_kind": "standard",
                "preferred": True,
                "definition_file": "speeduino-dropbear-v2.0.1.ini",
                "tune_file": "Ford300_TwinGT28_BaseStartup.msq",
                "firmware_signature": "speeduino 202501-T41",
            }
        ]
    })


def test_diagnostic_entry_matches_python():
    _check_round_trip({
        "firmware": [
            {"file": "diag.hex", "is_experimental": True, "artifact_kind": "diagnostic"}
        ]
    })


def test_multi_entry_manifest_matches_python():
    _check_round_trip({
        "firmware": [
            {"file": "speeduino-mega2560.hex", "board_family": "ATMEGA2560"},
            {"file": "speeduino-teensy35.hex", "board_family": "TEENSY35"},
            {"file": "speeduino-dropbear.hex", "board_family": "TEENSY41",
             "preferred": True},
            {"file": "diagnostic.hex", "artifact_kind": "diagnostic"},
        ]
    })


# ---------------------------------------------------------------------------
# Error paths — both implementations should raise on the same inputs
# ---------------------------------------------------------------------------

def _check_both_raise(payload):
    text = json.dumps(payload)
    with pytest.raises(Exception):
        _tuner_core.release_manifest_parse_text(text)
    with pytest.raises(Exception):
        tmp = _write_manifest(payload)
        _py.load(tmp)


def test_missing_file_field_both_raise():
    _check_both_raise({"firmware": [{"board_family": "TEENSY41"}]})


def test_blank_file_field_both_raise():
    _check_both_raise({"firmware": [{"file": "  "}]})


def test_unknown_board_family_both_raise():
    _check_both_raise({"firmware": [{"file": "a.hex", "board_family": "NOT_A_BOARD"}]})


def test_unknown_artifact_kind_both_raise():
    _check_both_raise({"firmware": [{"file": "a.hex", "artifact_kind": "weird"}]})


def test_firmware_must_be_list_both_raise():
    _check_both_raise({"firmware": "not-a-list"})


# ---------------------------------------------------------------------------
# load() returns None on missing manifest
# ---------------------------------------------------------------------------

def test_missing_manifest_returns_none():
    tmp = Path(tempfile.mkdtemp(prefix="tuner-rm-empty-"))
    py = _py.load(tmp)
    cpp = _tuner_core.release_manifest_load(tmp)
    assert py is None
    assert cpp is None
