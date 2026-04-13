"""Python <-> C++ parity harness for the [ConstantsExtensions] INI parser.

Pins the C++ `parse_constants_extensions_section*` helpers against
the Python `IniParser._parse_constants_extensions` across synthetic
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


def _parse_python(text: str, active_settings=frozenset()) -> set[str]:
    """Drive IniParser._parse_constants_extensions against a tmp file.

    Uses the same pre-populate `_lines` + leaf-method-directly pattern
    documented in sub-slice 109 (setting_groups parity).
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
        parser._parse_constants_extensions(tmp_path, definition)
    finally:
        tmp_path.unlink(missing_ok=True)
    return definition.requires_power_cycle


def _compare(py_set: set[str], cpp_section) -> None:
    assert set(py_set) == set(cpp_section.requires_power_cycle)


# ---------------------------------------------------------------------------
# Synthetic shapes
# ---------------------------------------------------------------------------


def test_simple_parity():
    text = """
[ConstantsExtensions]
requiresPowerCycle = canBroadcast, canInput, tsCanId
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section(text)
    _compare(py, cpp)


def test_whitespace_tolerated_parity():
    text = """
[ConstantsExtensions]
requiresPowerCycle =  foo , bar ,baz  , qux
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section(text)
    _compare(py, cpp)


def test_trailing_semicolon_comment_parity():
    text = """
[ConstantsExtensions]
requiresPowerCycle = alpha, beta ; comment here
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section(text)
    _compare(py, cpp)


def test_unknown_keys_ignored_parity():
    text = """
[ConstantsExtensions]
unknownKey = foo, bar
requiresPowerCycle = kept
someOtherMetadata = ignored
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section(text)
    _compare(py, cpp)


def test_empty_entries_dropped_parity():
    text = """
[ConstantsExtensions]
requiresPowerCycle = , alpha, , beta,
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section(text)
    _compare(py, cpp)


def test_multiple_lines_accumulate_parity():
    text = """
[ConstantsExtensions]
requiresPowerCycle = a, b
requiresPowerCycle = c, d
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section(text)
    _compare(py, cpp)


def test_lines_outside_section_ignored_parity():
    text = """
[Constants]
requiresPowerCycle = wrong_section

[ConstantsExtensions]
requiresPowerCycle = correct_section
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section(text)
    _compare(py, cpp)


def test_preprocessor_if_gating_parity():
    text = """
#set FEATURE_CAN
[ConstantsExtensions]
#if FEATURE_CAN
requiresPowerCycle = canBroadcast, canInput
#else
requiresPowerCycle = noCan
#endif
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section_preprocessed(text, set())
    _compare(py, cpp)


def test_active_settings_override_parity():
    text = """
#set DEFAULT_FEATURE
[ConstantsExtensions]
#if USER_FEATURE
requiresPowerCycle = user_param
#else
requiresPowerCycle = default_param
#endif
"""
    py = _parse_python(text, active_settings=frozenset({"USER_FEATURE"}))
    cpp = _tuner_core.parse_constants_extensions_section_preprocessed(
        text, {"USER_FEATURE"})
    _compare(py, cpp)


def test_empty_section_parity():
    text = "[ConstantsExtensions]\n"
    py = _parse_python(text)
    cpp = _tuner_core.parse_constants_extensions_section(text)
    _compare(py, cpp)


# ---------------------------------------------------------------------------
# Production INI parity
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PROD_INI.exists(), reason="production INI fixture missing")
def test_production_ini_parity():
    text = _PROD_INI.read_text(encoding="utf-8", errors="ignore")
    parser = IniParser()
    definition = parser.parse(_PROD_INI)
    py_set = definition.requires_power_cycle

    cpp = _tuner_core.parse_constants_extensions_section_preprocessed(text, set())
    _compare(py_set, cpp)
