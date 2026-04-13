"""Python <-> C++ parity harness for the legacy `.project` file format.

Pins the C++ `legacy_project_*` helpers (port of the pure-logic
parse + write surface for the legacy text-based project file) against
the Python originals across:

  - `parse_key_value_lines` (the underlying common parser)
  - `ProjectParser._parse_default_connection_profile`
  - `ProjectService._sanitize_name`
  - `ProjectService.save_project` line-builder body

I/O — Path resolution, mkdir, file read/write, the
`_resolve_optional_path` arithmetic — is out of scope. The Python
parity targets are the static helpers and the in-memory text body
the writer would produce, captured before the file write.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.domain.project import ConnectionProfile, Project
from tuner.parsers.common import parse_key_value_lines
from tuner.parsers.project_parser import ProjectParser
from tuner.services.project_service import ProjectService


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
# parse_key_value_lines parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lines", [
    [],
    ["", "  ", "\t"],
    ["# comment", "; semi", "// slash"],
    ["projectName=My Project"],
    ["a=b", "c=d", "e=f"],
    ["  spaced  =  value  "],
    ["k1: value", "k2: also"],
    ["a=b:c"],         # = wins
    ["no-separator", "key=value"],
    ["#defines", "PROJECT=demo", "; trailing comment"],
])
def test_parse_key_value_lines_parity(lines):
    py = parse_key_value_lines(lines)
    cpp = _tuner_core.legacy_project_parse_key_value_lines(lines)
    assert py == dict(cpp)


# ---------------------------------------------------------------------------
# parse_default_connection_profile parity
# ---------------------------------------------------------------------------


def _profile_to_tuple(profile: ConnectionProfile | None):
    if profile is None:
        return None
    return (
        profile.name, profile.transport, profile.protocol, profile.host,
        profile.port, profile.serial_port, profile.baud_rate,
    )


def _cpp_profile_to_tuple(profile):
    if profile is None:
        return None
    return (
        profile.name, profile.transport, profile.protocol, profile.host,
        profile.port, profile.serial_port, profile.baud_rate,
    )


@pytest.mark.parametrize("metadata", [
    {},
    {"projectName": "X"},  # no connection.* keys -> None
    {"connection.default.host": "localhost"},
    {
        "connection.default.name":      "Speeduino TCP",
        "connection.default.transport": "tcp",
        "connection.default.protocol":  "speeduino",
        "connection.default.host":      "192.168.4.1",
        "connection.default.port":      "2000",
        "connection.default.baudRate":  "115200",
    },
    {
        "connection.default.name":      "USB",
        "connection.default.transport": "serial",
        "connection.default.serialPort":"COM3",
        "connection.default.baudRate":  "115200",
    },
    {
        "connection.default.port": "not-a-number",
        "connection.default.baudRate": "115200abc",
    },
    {
        "connection.default.port": "+42",
        "connection.default.baudRate": "-1",
    },
])
def test_parse_default_connection_profile_parity(metadata):
    py = ProjectParser._parse_default_connection_profile(metadata)
    cpp = _tuner_core.legacy_project_parse_default_connection_profile(metadata)
    assert _profile_to_tuple(py) == _cpp_profile_to_tuple(cpp)


# ---------------------------------------------------------------------------
# sanitize_project_name parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "",
    "   ",
    "Speeduino-Project_42",
    "My Project Name",
    "a/b\\c",
    "___leading",
    "trailing___",
    "___both___",
    "  spaced  ",
    "$$$",
    "Ford 300 Twin GT28",
    "test.project",     # `.` is not alnum/-/_
])
def test_sanitize_project_name_parity(name):
    # The C++ port operates on raw bytes; Python's `isalnum()` operates
    # on Unicode code points. The two agree for ASCII project names,
    # which is the contract — non-ASCII names produce different
    # underscore counts on each side and are documented as ASCII-only
    # on the C++ port. Project file names in practice are ASCII.
    py = ProjectService._sanitize_name(name)
    cpp = _tuner_core.legacy_project_sanitize_name(name)
    assert py == cpp


# ---------------------------------------------------------------------------
# format_legacy_project_file parity — drive Python's save_project against
# a tmp_path and compare the resulting file body byte-for-byte.
# ---------------------------------------------------------------------------


def _model_from_python(project: Project, *, ecu_def: str | None = None,
                       tune_file: str | None = None):
    """Build the C++ LegacyProjectModel from a Python Project.

    The C++ model takes already-resolved relative path strings — the
    Python writer's `_relative_path` is called explicitly here so the
    parity comparison stays line-for-line.
    """
    model = _tuner_core.LegacyProjectModel()
    model.name = project.name
    model.ecu_definition_path = ecu_def
    model.tune_file_path = tune_file
    model.dashboards = list(project.dashboards)
    model.active_settings = sorted(project.active_settings)
    model.metadata = dict(project.metadata)
    cpp_profiles = []
    for p in project.connection_profiles:
        cp = _tuner_core.LegacyConnectionProfile()
        cp.name = p.name
        cp.transport = p.transport
        cp.protocol = p.protocol
        cp.host = p.host
        cp.port = p.port
        cp.serial_port = p.serial_port
        cp.baud_rate = p.baud_rate
        cpp_profiles.append(cp)
    model.connection_profiles = cpp_profiles
    return model


def test_format_legacy_project_file_minimal(tmp_path):
    project = Project(name="Bare", project_path=tmp_path / "bare.project")
    svc = ProjectService()
    written = svc.save_project(project)
    py_text = written.read_text(encoding="utf-8")
    cpp_text = _tuner_core.legacy_project_format_file(_model_from_python(project))
    assert py_text == cpp_text


def test_format_legacy_project_file_full(tmp_path):
    project = Project(
        name="Ford 300 Twin GT28",
        project_path=tmp_path / "ford.project",
        ecu_definition_path=tmp_path / "defs" / "speeduino.ini",
        tune_file_path=tmp_path / "tunes" / "base.msq",
        dashboards=["primary", "secondary"],
        connection_profiles=[ConnectionProfile(
            name="Speeduino USB",
            transport="serial",
            protocol="speeduino",
            serial_port="COM3",
            baud_rate=115200,
        )],
        metadata={"customNote": "remember to recheck dwell"},
        active_settings=frozenset({"LAMBDA", "mcu_teensy"}),
    )
    svc = ProjectService()
    written = svc.save_project(project)
    py_text = written.read_text(encoding="utf-8")
    # Re-derive the relative paths the Python writer used.
    import os
    ecu_rel = os.path.relpath(
        (tmp_path / "defs" / "speeduino.ini").resolve(),
        start=(tmp_path).resolve())
    tune_rel = os.path.relpath(
        (tmp_path / "tunes" / "base.msq").resolve(),
        start=(tmp_path).resolve())
    cpp_text = _tuner_core.legacy_project_format_file(
        _model_from_python(project, ecu_def=ecu_rel, tune_file=tune_rel))
    assert py_text == cpp_text


def test_format_legacy_project_file_active_settings_sorted(tmp_path):
    project = Project(
        name="Sorting",
        project_path=tmp_path / "sort.project",
        active_settings=frozenset({"zeta", "alpha", "mike"}),
    )
    svc = ProjectService()
    written = svc.save_project(project)
    py_text = written.read_text(encoding="utf-8")
    cpp_text = _tuner_core.legacy_project_format_file(_model_from_python(project))
    assert py_text == cpp_text


def test_format_legacy_project_file_metadata_skips_structured_keys(tmp_path):
    project = Project(
        name="Spillover",
        project_path=tmp_path / "spill.project",
        ecu_definition_path=tmp_path / "defs.ini",
        metadata={
            # These should NOT spill into the output — the structured
            # field above already wrote ecuDefinition, and the writer's
            # skip-list excludes the rest.
            "projectName": "should-be-skipped",
            "ecuDefinition": "should-be-skipped",
            "tuneFile": "should-be-skipped",
            "dashboards": "should-be-skipped",
            "activeSettings": "should-be-skipped",
            "connection.default.name": "should-be-skipped",
            "customField": "kept",
        },
    )
    svc = ProjectService()
    written = svc.save_project(project)
    py_text = written.read_text(encoding="utf-8")
    import os
    ecu_rel = os.path.relpath(
        (tmp_path / "defs.ini").resolve(),
        start=(tmp_path).resolve())
    cpp_text = _tuner_core.legacy_project_format_file(
        _model_from_python(project, ecu_def=ecu_rel))
    assert py_text == cpp_text
