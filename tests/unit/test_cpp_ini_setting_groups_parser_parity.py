"""Python <-> C++ parity harness for the [SettingGroups] INI parser.

Pins the C++ `parse_setting_groups_section*` helpers against the
Python `IniParser._parse_setting_groups` across synthetic shapes and
the full production INI fixture.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.domain.ecu_definition import EcuDefinition
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
    """Drive IniParser._parse_setting_groups against a tmp file.

    We set `parser._lines` directly via the same `preprocess_ini_lines`
    pipeline that `parser.parse()` uses, then invoke the leaf method
    with a tmp path that exists (the method only reads the path for
    an `.exists()` guard; the actual line source is `self._lines`).
    """
    import tempfile
    from pathlib import Path as _Path
    from tuner.parsers.common import preprocess_ini_lines

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
        parser._parse_setting_groups(tmp_path, definition)
    finally:
        tmp_path.unlink(missing_ok=True)
    return definition.setting_groups


def _compare(py_groups, cpp_section):
    assert len(py_groups) == len(cpp_section.groups)
    for py, cpp in zip(py_groups, cpp_section.groups):
        assert py.symbol == cpp.symbol
        assert (py.label or "") == cpp.label
        assert len(py.options) == len(cpp.options)
        for py_opt, cpp_opt in zip(py.options, cpp.options):
            assert py_opt.symbol == cpp_opt.symbol
            assert (py_opt.label or "") == cpp_opt.label


# ---------------------------------------------------------------------------
# Synthetic shapes
# ---------------------------------------------------------------------------


_SIMPLE_TEXT = """
[SettingGroups]
settingGroup = mcu, "Controller in use"
settingOption = mcu_mega2560, "Arduino Mega 2560"
settingOption = mcu_teensy, "Teensy 3.5/3.6/4.1"

settingGroup = LAMBDA, "Wideband lambda"
settingOption = DEFAULT, "Off"
settingOption = LAMBDA, "On"
"""


def test_simple_parity():
    py = _parse_python(_SIMPLE_TEXT)
    cpp = _tuner_core.parse_setting_groups_section(_SIMPLE_TEXT)
    _compare(py, cpp)


def test_boolean_flag_parity():
    text = """
[SettingGroups]
settingGroup = enablehardware_test, "Enable hardware test"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_groups_section(text)
    _compare(py, cpp)


def test_section_change_flush_parity():
    text = """
[SettingGroups]
settingGroup = mcu, "Controller"
settingOption = mcu_teensy, "Teensy"

[OtherSection]
irrelevant = value
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_groups_section(text)
    _compare(py, cpp)


def test_missing_label_defaults_to_symbol_parity():
    text = """
[SettingGroups]
settingGroup = onlySymbol
settingOption = optOnly
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_groups_section(text)
    _compare(py, cpp)


def test_comments_and_blank_lines_parity():
    text = """
[SettingGroups]
; comment line
settingGroup = mcu, "Controller"
# another comment
settingOption = mcu_teensy, "Teensy"

settingOption = mcu_stm32, "STM32"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_groups_section(text)
    _compare(py, cpp)


def test_empty_section_parity():
    text = "[SettingGroups]\n"
    py = _parse_python(text)
    cpp = _tuner_core.parse_setting_groups_section(text)
    _compare(py, cpp)


def test_preprocessor_if_gating_parity():
    text = """
#set FEATURE_X
[SettingGroups]
#if FEATURE_X
settingGroup = x_on, "X enabled"
#else
settingGroup = x_off, "X disabled"
#endif
"""
    py = _parse_python(text, active_settings=frozenset())
    cpp = _tuner_core.parse_setting_groups_section_preprocessed(text, set())
    _compare(py, cpp)


def test_preprocessor_active_settings_override_parity():
    text = """
#set DEFAULT_FEATURE
[SettingGroups]
#if USER_FEATURE
settingGroup = user_mode, "User mode"
#else
settingGroup = default_mode, "Default mode"
#endif
"""
    py = _parse_python(text, active_settings=frozenset({"USER_FEATURE"}))
    cpp = _tuner_core.parse_setting_groups_section_preprocessed(
        text, {"USER_FEATURE"})
    _compare(py, cpp)


# ---------------------------------------------------------------------------
# Production INI parity
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PROD_INI.exists(), reason="production INI fixture missing")
def test_production_ini_parity():
    text = _PROD_INI.read_text(encoding="utf-8", errors="ignore")

    # Drive the full Python parser so setting_groups lands on the
    # real definition object.
    parser = IniParser()
    definition = parser.parse(_PROD_INI)
    py_groups = definition.setting_groups

    cpp = _tuner_core.parse_setting_groups_section_preprocessed(text, set())
    _compare(py_groups, cpp)
    assert len(py_groups) >= 1  # smoke check: production has at least one group
