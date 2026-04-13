"""Python <-> C++ parity harness for the reference-tables INI parser.

Pins the C++ `parse_reference_tables_section*` helpers against the
Python `IniParser._parse_reference_tables` across synthetic shapes
and the full production INI fixture.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.domain.ecu_definition import EcuDefinition
from tuner.parsers.common import preprocess_ini_lines
from tuner.parsers.ini_parser import IniParser


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CPP_BUILD_CANDIDATES = [
    _REPO_ROOT / "build" / "cpp",
    _REPO_ROOT / "build" / "cpp" / "Release",
    _REPO_ROOT / "build" / "cpp" / "Debug",
    _REPO_ROOT / "cpp" / "build",
]

_PROD_INI = _REPO_ROOT / "tests" / "fixtures" / "speeduino-dropbear-v2.0.1.ini"


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


def _parse_python(text: str, active_settings=frozenset()):
    import tempfile
    from pathlib import Path as _Path

    parser = IniParser()
    definition = EcuDefinition(name="test")
    parser._lines = preprocess_ini_lines(
        text.splitlines(), active_settings=active_settings)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False,
                                     encoding="utf-8") as f:
        f.write(text)
        f.flush()
        tmp_path = _Path(f.name)
    try:
        parser._parse_reference_tables(tmp_path, definition)
    finally:
        tmp_path.unlink(missing_ok=True)
    return definition.reference_tables


def _opt(v):
    return v if v is not None else None


def _compare(py_tables, cpp_section) -> None:
    assert len(py_tables) == len(cpp_section.tables)
    for py, cpp in zip(py_tables, cpp_section.tables):
        assert py.table_id == cpp.table_id
        assert (py.label or "") == cpp.label
        assert _opt(py.topic_help) == (cpp.topic_help or None)
        assert _opt(py.table_identifier) == (cpp.table_identifier or None)
        assert _opt(py.solutions_label) == (cpp.solutions_label or None)
        assert len(py.solutions) == len(cpp.solutions)
        for py_sol, cpp_sol in zip(py.solutions, cpp.solutions):
            assert py_sol.label == cpp_sol.label
            assert _opt(py_sol.expression) == (cpp_sol.expression or None)


_FULL = """
[UserDefined]
referenceTable = leanAtWot, "Lean at WOT"
topicHelp = "Diagnose lean running at wide-open throttle"
tableIdentifier = 4, 8
solutionsLabel = "Recommended Solutions"
solution = "Low fuel pressure", "fuelPress < 3"
solution = "Injector too small", "injFlow < 300"
"""


def test_full_table_parity():
    py = _parse_python(_FULL)
    cpp = _tuner_core.parse_reference_tables_section(_FULL)
    _compare(py, cpp)


def test_label_defaults_to_id_parity():
    text = """
[UserDefined]
referenceTable = onlyId
solution = "S", "e"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section(text)
    _compare(py, cpp)


def test_multiple_tables_parity():
    text = """
[UserDefined]
referenceTable = first, "First"
topicHelp = "first help"
solution = "A", "a"

referenceTable = second, "Second"
solution = "B", "b"
solution = "C", "c"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section(text)
    _compare(py, cpp)


def test_orphan_properties_ignored_parity():
    text = """
[UserDefined]
topicHelp = "Orphan"
solution = "Orphan", "x"
referenceTable = real, "Real"
solution = "Owned", "x"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section(text)
    _compare(py, cpp)


def test_solution_without_expression_parity():
    text = """
[UserDefined]
referenceTable = t, "T"
solution = "Check fuel pressure"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section(text)
    _compare(py, cpp)


def test_table_identifier_single_arg_parity():
    text = """
[UserDefined]
referenceTable = t, "T"
tableIdentifier = only_one
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section(text)
    _compare(py, cpp)


def test_section_switch_drops_in_flight_parity():
    text = """
[UserDefined]
referenceTable = t, "T"
solution = "A", "a"

[OtherSection]
solution = "Skipped", "x"

[UserDefined]
solution = "Still skipped because no block open after re-entry"
referenceTable = t2, "T2"
solution = "T2", "y"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section(text)
    _compare(py, cpp)


def test_case_insensitive_header_parity():
    text = """
[userdefined]
referenceTable = t, "T"
solution = "s", "e"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section(text)
    _compare(py, cpp)


def test_preprocessor_if_gating_parity():
    text = """
#set FEATURE_DIAG
[UserDefined]
#if FEATURE_DIAG
referenceTable = enabled, "On"
#else
referenceTable = disabled, "Off"
#endif
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section_preprocessed(text, set())
    _compare(py, cpp)


def test_empty_section_parity():
    text = "[UserDefined]\n"
    py = _parse_python(text)
    cpp = _tuner_core.parse_reference_tables_section(text)
    _compare(py, cpp)


@pytest.mark.skipif(not _PROD_INI.exists(), reason="production INI fixture missing")
def test_production_ini_parity():
    text = _PROD_INI.read_text(encoding="utf-8", errors="ignore")
    parser = IniParser()
    definition = parser.parse(_PROD_INI)
    py_tables = definition.reference_tables

    cpp = _tuner_core.parse_reference_tables_section_preprocessed(text, set())
    _compare(py_tables, cpp)
