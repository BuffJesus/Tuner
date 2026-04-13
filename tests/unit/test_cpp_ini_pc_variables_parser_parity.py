"""Python <-> C++ parity harness for the [PcVariables] INI parser.

Pins the C++ `parse_pc_variables_section*` helpers against the Python
`IniParser._parse_pc_variables` across synthetic shapes and the full
production INI fixture. The Python parser appends into
`definition.scalars` / `definition.tables` — the SAME lists that
`_parse_constant_definitions` populates — so parity checks have to
isolate the PC-variables-only subset by running the leaf method on a
freshly-built `EcuDefinition` with no prior constants catalog.
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
    """Drive IniParser._parse_pc_variables against a tmp file.

    Pre-populates `parser._lines` via `preprocess_ini_lines`, collects
    the `#define` macros from those same lines, and calls the leaf
    method with `defines=` so bit-option expansion matches what the
    full `parser.parse()` orchestration would produce. The Python
    leaf method appends to definition.scalars / .tables, so we start
    with an empty `EcuDefinition` — whatever ends up in those lists
    is the PC-variables-only subset.
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
        defines = parser._collect_defines(tmp_path)
        parser._parse_pc_variables(tmp_path, definition, defines)
    finally:
        tmp_path.unlink(missing_ok=True)
    return definition.scalars, definition.tables


def _opt(v):
    return v if v is not None else None


def _compare_scalars(py_scalars, cpp_scalars) -> None:
    assert len(py_scalars) == len(cpp_scalars)
    for py, cpp in zip(py_scalars, cpp_scalars):
        assert py.name == cpp.name
        assert py.data_type == cpp.data_type
        assert _opt(py.units) == (cpp.units if cpp.units is not None else None)
        # PC variables never have page/offset.
        assert py.page is None
        assert py.offset is None
        assert cpp.page is None
        assert cpp.offset is None
        assert _opt(py.scale) == (cpp.scale if cpp.scale is not None else None)
        assert _opt(py.translate) == (cpp.translate if cpp.translate is not None else None)
        assert _opt(py.digits) == (cpp.digits if cpp.digits is not None else None)
        assert _opt(py.min_value) == (cpp.min_value if cpp.min_value is not None else None)
        assert _opt(py.max_value) == (cpp.max_value if cpp.max_value is not None else None)
        assert _opt(py.bit_offset) == (cpp.bit_offset if cpp.bit_offset is not None else None)
        assert _opt(py.bit_length) == (cpp.bit_length if cpp.bit_length is not None else None)
        # Options: Python stores a tuple of FieldOptionDefinition; C++
        # stores a plain list of label strings. Compare labels only.
        py_labels = [opt.label for opt in py.options]
        assert py_labels == list(cpp.options)


def _compare_arrays(py_tables, cpp_arrays) -> None:
    assert len(py_tables) == len(cpp_arrays)
    for py, cpp in zip(py_tables, cpp_arrays):
        assert py.name == cpp.name
        assert py.data_type == cpp.data_type
        assert py.rows == cpp.rows
        assert py.columns == cpp.columns
        assert _opt(py.units) == (cpp.units if cpp.units is not None else None)
        assert py.page is None
        assert py.offset is None
        assert cpp.page is None
        assert cpp.offset is None


def _compare(py_pair, cpp_section) -> None:
    py_scalars, py_tables = py_pair
    _compare_scalars(py_scalars, cpp_section.scalars)
    _compare_arrays(py_tables, cpp_section.arrays)


# ---------------------------------------------------------------------------
# Synthetic shapes
# ---------------------------------------------------------------------------


def test_scalar_parity():
    text = """
[PcVariables]
myVar = scalar, F32, "%", 1.0, 0.0, 0.0, 100.0, 2
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


def test_bits_parity():
    text = """
[PcVariables]
myFlag = bits, U08, [0:0], "Off", "On"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


def test_array_2d_parity():
    text = """
[PcVariables]
myTable = array, F32, [4x8], "ms", 1.0, 0.0, 0.0, 50.0, 3
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


def test_array_1d_parity():
    text = """
[PcVariables]
oneD = array, U08, [10], "count"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


def test_multiple_entries_parity():
    text = """
[PcVariables]
first = scalar, U08, "a"
second = scalar, F32, "b"
third = array, U16, [2x2], "c"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


def test_lines_outside_section_ignored_parity():
    # Python `_parse_pc_variables` only reads lines inside
    # `[PcVariables]` — lines inside `[Constants]` are ignored
    # because the leaf method is only looking at its own section.
    text = """
[Constants]
page = 1
wrong = scalar, U08, 0, "ignored"

[PcVariables]
correct = scalar, U08, "kept"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


def test_case_insensitive_header_parity():
    text = """
[pcvariables]
x = scalar, U08, "x"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


def test_comments_and_blank_lines_parity():
    text = """
[PcVariables]
; comment
first = scalar, U08, "a"

# also a comment
second = scalar, F32, "b"
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


def test_preprocessor_if_gating_parity():
    text = """
#set FEATURE_EXTRA
[PcVariables]
#if FEATURE_EXTRA
enabled = scalar, U08, "enabled"
#else
disabled = scalar, U08, "disabled"
#endif
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section_preprocessed(text, set())
    _compare(py, cpp)


def test_empty_section_parity():
    text = "[PcVariables]\n"
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section(text)
    _compare(py, cpp)


# ---------------------------------------------------------------------------
# Production INI parity
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PROD_INI.exists(), reason="production INI fixture missing")
def test_production_ini_parity():
    text = _PROD_INI.read_text(encoding="utf-8", errors="ignore")
    py = _parse_python(text)
    cpp = _tuner_core.parse_pc_variables_section_preprocessed(text, set())
    _compare(py, cpp)
