"""Python <-> C++ parity harness for the [SettingContextHelp] INI parser.

Pins the C++ `parse_setting_context_help_section*` helpers against
the Python `IniParser._parse_setting_context_help` across synthetic
shapes and the full production INI fixture.
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
    """Drive IniParser._parse_setting_context_help against a tmp file.

    Same pattern documented in sub-slice 109's setting-groups parity
    test: pre-populate `parser._lines` via `preprocess_ini_lines`
    then invoke the leaf method directly so we don't need to exercise
    the full `parse()` orchestration.
    """
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
        parser._parse_setting_context_help(tmp_path, definition)
    finally:
        tmp_path.unlink(missing_ok=True)
    return definition.setting_help


def _compare(py_help: dict, cpp_section) -> None:
    py_items = {k: (v or "") for k, v in py_help.items()}
    cpp_items = dict(cpp_section.help_by_name)
    assert py_items == cpp_items


# ---------------------------------------------------------------------------
# Synthetic shapes
# ---------------------------------------------------------------------------


_SIMPLE = """
[SettingContextHelp]
dwellLim = "Coil dwell time limit"
nCylinders = "Number of cylinders"
reqFuel = "Required fuel pulse width"
"""


def test_simple_parity():
    py = _parse_python(_SIMPLE)
    cpp = _tuner_core.parse_setting_context_help_section(_SIMPLE)
    _compare(py, cpp)


def test_quotes_and_semicolon_comment_parity():
    text = """
[SettingContextHelp]
paramA = "Quoted help"
paramB = "Help ends here"; trailing comment
paramC = Bare help text without quotes
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_context_help_section(text)
    _compare(py, cpp)


def test_lines_outside_section_ignored_parity():
    text = """
[Constants]
skipped = "Should be ignored"

[SettingContextHelp]
wanted = "Kept"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_context_help_section(text)
    _compare(py, cpp)


def test_case_insensitive_header_parity():
    text = """
[settingcontexthelp]
p = "lowercase section"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_context_help_section(text)
    _compare(py, cpp)


def test_comments_and_blank_lines_parity():
    text = """
[SettingContextHelp]
; comment
paramA = "A"
# also a comment
paramB = "B"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_context_help_section(text)
    _compare(py, cpp)


def test_empty_section_parity():
    text = "[SettingContextHelp]\n"
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_context_help_section(text)
    _compare(py, cpp)


def test_preprocessor_if_gating_parity():
    text = """
#set FEATURE_X
[SettingContextHelp]
#if FEATURE_X
paramX = "X enabled"
#else
paramX = "X disabled"
#endif
"""
    py = _parse_python(text, active_settings=frozenset())
    cpp = _tuner_core.parse_setting_context_help_section_preprocessed(text, set())
    _compare(py, cpp)


def test_active_settings_override_parity():
    text = """
#set DEFAULT_FEATURE
[SettingContextHelp]
#if USER_FEATURE
wanted = "user mode"
#else
wanted = "default mode"
#endif
"""
    py = _parse_python(text, active_settings=frozenset({"USER_FEATURE"}))
    cpp = _tuner_core.parse_setting_context_help_section_preprocessed(
        text, {"USER_FEATURE"})
    _compare(py, cpp)


# ---------------------------------------------------------------------------
# Production INI parity
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PROD_INI.exists(), reason="production INI fixture missing")
def test_production_ini_parity():
    text = _PROD_INI.read_text(encoding="utf-8", errors="ignore")
    # Drive the full Python parser so setting_help lands on the real
    # definition object.
    parser = IniParser()
    definition = parser.parse(_PROD_INI)
    py_help = definition.setting_help

    cpp = _tuner_core.parse_setting_context_help_section_preprocessed(text, set())
    _compare(py_help, cpp)
    # Production INI has plenty of help entries.
    assert len(py_help) >= 20
