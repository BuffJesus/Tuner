"""Python <-> C++ parity harness for the [VeAnalyze] / [WueAnalyze] parser.

Pins the C++ `parse_autotune_sections*` helpers against the Python
`IniParser._parse_autotune_sections` across synthetic shapes and the
full production INI fixture.

The C++ port uses a variant-based filter gate (StandardGate vs
ParameterisedGate) and a GateOperator enum instead of the Python's
nullable-field AutotuneFilterGate. Parity comparison bridges the two
representations.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tuner.domain.ecu_definition import EcuDefinition, AutotuneFilterGate
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


# ---------------------------------------------------------------
# Python parser helper
# ---------------------------------------------------------------

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
        parser._parse_autotune_sections(tmp_path, definition)
    finally:
        tmp_path.unlink(missing_ok=True)
    return definition.autotune_maps


# ---------------------------------------------------------------
# Operator mapping: Python string -> C++ enum name
# ---------------------------------------------------------------

_OP_MAP = {
    "<": "Lt",
    ">": "Gt",
    "<=": "Le",
    ">=": "Ge",
    "==": "Eq",
    "=": "Eq",
    "!=": "Ne",
    "&": "BitAnd",
}


def _compare(py_maps, cpp_result) -> None:
    """Bridge Python AutotuneMapDefinition list against C++ IniAutotuneSectionsResult."""
    cpp_maps = cpp_result.maps
    assert len(py_maps) == len(cpp_maps), (
        f"map count mismatch: py={len(py_maps)} cpp={len(cpp_maps)}")

    for py_map, cpp_map in zip(py_maps, cpp_maps):
        assert py_map.section_name == cpp_map.section_name
        assert list(py_map.map_parts) == list(cpp_map.map_parts)
        assert list(py_map.lambda_target_tables) == list(cpp_map.lambda_target_tables)
        assert len(py_map.filter_gates) == len(cpp_map.filter_gates), (
            f"gate count mismatch in {py_map.section_name}: "
            f"py={len(py_map.filter_gates)} cpp={len(cpp_map.filter_gates)}")

        for py_gate, cpp_gate in zip(py_map.filter_gates, cpp_map.filter_gates):
            _compare_gate(py_gate, cpp_gate)


def _compare_gate(py_gate: AutotuneFilterGate, cpp_gate) -> None:
    """Compare a Python AutotuneFilterGate against a C++ variant gate."""
    # Check which variant the C++ side produced.
    is_parameterised = hasattr(cpp_gate, "channel")

    if py_gate.channel is not None and py_gate.operator is not None:
        # Python thinks this is parameterised.
        assert is_parameterised, (
            f"Python gate '{py_gate.name}' is parameterised but C++ produced StandardGate")
        assert py_gate.name == cpp_gate.name
        assert (py_gate.label or py_gate.name) == cpp_gate.label
        assert py_gate.channel == cpp_gate.channel
        # Compare operator via enum name.
        expected_op = _OP_MAP.get(py_gate.operator, "Unknown")
        assert str(cpp_gate.op) == f"GateOperator.{expected_op}", (
            f"op mismatch: py='{py_gate.operator}' -> expected {expected_op}, "
            f"got {cpp_gate.op}")
        if py_gate.threshold is not None:
            assert cpp_gate.threshold == pytest.approx(py_gate.threshold)
        assert py_gate.default_enabled == cpp_gate.default_enabled
    else:
        # Standard gate.
        assert not is_parameterised, (
            f"Python gate '{py_gate.name}' is standard but C++ produced ParameterisedGate")
        assert py_gate.name == cpp_gate.name


# ---------------------------------------------------------------
# Synthetic parity tests
# ---------------------------------------------------------------

def test_ve_analyze_map_parts_parity():
    text = """
[VeAnalyze]
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_lambda_target_tables_parity():
    text = """
[VeAnalyze]
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
lambdaTargetTables = afrTable1, afrTSCustom
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_standard_filter_gates_parity():
    text = """
[VeAnalyze]
filter = std_xAxisMin
filter = std_DeadLambda
filter = std_Custom
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_parameterised_filter_gate_parity():
    text = """
[VeAnalyze]
filter = minCltFilter, "Minimum CLT", coolant, <, 71, true
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_disabled_by_default_gate_parity():
    text = """
[VeAnalyze]
filter = accelFilter, "Accel Flag", engine, &, 16, false
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_equals_operator_parity():
    text = """
[WueAnalyze]
filter = overrunFilter, "Overrun", pulseWidth, =, 0, false
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_wue_analyze_long_map_parity():
    text = """
[WueAnalyze]
wueAnalyzeMap = warmupEnrich, lambdaTable1, lambda, coolant, warmupEnrich, egoCorrection
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_both_sections_parity():
    text = """
[VeAnalyze]
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
filter = std_xAxisMin

[WueAnalyze]
wueAnalyzeMap = warmupEnrich, lambdaTable1, lambda, coolant, warmupEnrich, egoCorrection
filter = std_DeadLambda
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_lines_outside_section_ignored_parity():
    text = """
[Constants]
filter = wrong

[VeAnalyze]
filter = std_Custom
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_preprocessor_if_gating_parity():
    text = """
#set LAMBDA
[VeAnalyze]
#if LAMBDA
veAnalyzeMap = veTable1Tbl, lambdaTable1, lambda, egoCorrection
lambdaTargetTables = lambdaTable1, afrTSCustom
#else
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
lambdaTargetTables = afrTable1, afrTSCustom
#endif
filter = std_Custom
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections_preprocessed(text, set())
    _compare(py, cpp)


def test_active_settings_lambda_branch_parity():
    text = """
[VeAnalyze]
#if LAMBDA
veAnalyzeMap = veTable1Tbl, lambdaTable1, lambda, egoCorrection
#else
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
#endif
"""
    # Without LAMBDA → #else branch.
    py1 = _parse_python(text)
    cpp1 = _tuner_core.parse_autotune_sections_preprocessed(text, set())
    _compare(py1, cpp1)

    # With LAMBDA → #if branch.
    py2 = _parse_python(text, active_settings=frozenset({"LAMBDA"}))
    cpp2 = _tuner_core.parse_autotune_sections_preprocessed(text, {"LAMBDA"})
    _compare(py2, cpp2)


def test_empty_input_parity():
    py = _parse_python("")
    cpp = _tuner_core.parse_autotune_sections("")
    _compare(py, cpp)


def test_empty_section_parity():
    text = "[VeAnalyze]\n"
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


def test_mixed_standard_and_parameterised_parity():
    text = """
[VeAnalyze]
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
lambdaTargetTables = afrTable1, afrTSCustom
filter = std_xAxisMin
filter = std_xAxisMax
filter = std_yAxisMin
filter = std_yAxisMax
filter = std_DeadLambda
filter = minCltFilter, "Minimum CLT", coolant, <, 71, true
filter = accelFilter, "Accel Flag", engine, &, 16, false
filter = aseFilter, "ASE Flag", engine, &, 4, false
filter = overrunFilter, "Overrun", pulseWidth, =, 0, false
filter = std_Custom
"""
    py = _parse_python(text)
    cpp = _tuner_core.parse_autotune_sections(text)
    _compare(py, cpp)


# ---------------------------------------------------------------
# Production INI parity
# ---------------------------------------------------------------

@pytest.mark.skipif(not _PROD_INI.exists(), reason="production INI fixture missing")
def test_production_ini_parity():
    text = _PROD_INI.read_text(encoding="utf-8", errors="ignore")
    parser = IniParser()
    definition = parser.parse(_PROD_INI)
    py_maps = definition.autotune_maps

    cpp = _tuner_core.parse_autotune_sections_preprocessed(text, set())
    _compare(py_maps, cpp)


# ---------------------------------------------------------------
# Compiler aggregator parity
# ---------------------------------------------------------------

@pytest.mark.skipif(not _PROD_INI.exists(), reason="production INI fixture missing")
def test_compiler_autotune_sections_parity():
    """Verify the autotune_sections field lands on NativeEcuDefinition."""
    text = _PROD_INI.read_text(encoding="utf-8", errors="ignore")
    parser = IniParser()
    definition = parser.parse(_PROD_INI)
    py_maps = definition.autotune_maps

    compiled = _tuner_core.compile_ecu_definition_text(text, set())
    _compare(py_maps, compiled.autotune_sections)
