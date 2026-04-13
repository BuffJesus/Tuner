"""Python <-> C++ parity harness for the [Tools] INI parser.

Pins the C++ `parse_tools_section*` helpers against the Python
`IniParser._parse_tools` across synthetic shapes and the full
production INI fixture.
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
        parser._parse_tools(tmp_path, definition)
    finally:
        tmp_path.unlink(missing_ok=True)
    return definition.tool_declarations


def _compare(py_decls, cpp_section) -> None:
    assert len(py_decls) == len(cpp_section.declarations)
    for py, cpp in zip(py_decls, cpp_section.declarations):
        assert py.tool_id == cpp.tool_id
        assert (py.label or "") == cpp.label
        py_target = py.target_table_id
        cpp_target = cpp.target_table_id
        assert (py_target or None) == (cpp_target if cpp_target is not None else None)


def test_simple_full_line_parity():
    text = """
[Tools]
addTool = veAnalyze, "VE Analyze", veTable1Tbl
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section(text)
    _compare(py, cpp)


def test_missing_target_table_parity():
    text = """
[Tools]
addTool = globalHelper, "Global Helper"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section(text)
    _compare(py, cpp)


def test_missing_label_defaults_to_tool_id_parity():
    text = """
[Tools]
addTool = onlyId
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section(text)
    _compare(py, cpp)


def test_multiple_declarations_parity():
    text = """
[Tools]
addTool = veAnalyze, "VE Analyze", veTable1Tbl
addTool = wueAnalyze, "WUE Analyze", wueTbl
addTool = globalReset, "Global Reset"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section(text)
    _compare(py, cpp)


def test_unknown_keys_ignored_parity():
    text = """
[Tools]
unknownKey = foo
addTool = realTool, "Real", realTbl
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section(text)
    _compare(py, cpp)


def test_lines_outside_section_ignored_parity():
    text = """
[Constants]
addTool = wrong, "Wrong", x

[Tools]
addTool = correct, "Right", y
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section(text)
    _compare(py, cpp)


def test_case_insensitive_header_parity():
    text = """
[tools]
addTool = x, "X", xTbl
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section(text)
    _compare(py, cpp)


def test_preprocessor_if_gating_parity():
    text = """
#set FEATURE_VE
[Tools]
#if FEATURE_VE
addTool = veAnalyze, "VE Analyze", veTbl
#else
addTool = veAnalyzeDisabled, "VE Analyze disabled"
#endif
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section_preprocessed(text, set())
    _compare(py, cpp)


def test_empty_section_parity():
    text = "[Tools]\n"
    py = _parse_python(text)
    cpp = _tuner_core.parse_tools_section(text)
    _compare(py, cpp)


@pytest.mark.skipif(not _PROD_INI.exists(), reason="production INI fixture missing")
def test_production_ini_parity():
    text = _PROD_INI.read_text(encoding="utf-8", errors="ignore")
    parser = IniParser()
    definition = parser.parse(_PROD_INI)
    py_decls = definition.tool_declarations

    cpp = _tuner_core.parse_tools_section_preprocessed(text, set())
    _compare(py_decls, cpp)
