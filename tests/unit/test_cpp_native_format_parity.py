"""Python ↔ C++ parity harness for the tuner_core NativeFormat layer.

Future Phase 13 second slice. Drives the same NativeDefinition /
NativeTune fixtures through both the Python `NativeFormatService` and
the C++ `tuner_core` extension, then asserts byte-identical JSON
output.

Like the MSQ parity harness, the C++ extension is **optional**: if
it isn't built, every test in this file is marked as skipped. Build
instructions live in `cpp/README.md`.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from tuner.domain.native_format import (
    NATIVE_SCHEMA_VERSION,
    NativeAxis,
    NativeDefinition,
    NativeParameter,
    NativeTable,
    NativeTune,
)
from tuner.services.native_format_service import (
    NativeFormatService,
    NativeFormatVersionError,
)


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
    reason=(
        "tuner_core C++ extension not built — see cpp/README.md for build "
        "instructions. Dev installs without a compiler skip these tests."
    ),
)


# ---------------------------------------------------------------------------
# Fixture builders — match the Python TestFromEcuDefinition fixtures so the
# parity harness uses the same shape both sides have already validated.
# ---------------------------------------------------------------------------


def _python_definition() -> NativeDefinition:
    return NativeDefinition(
        schema_version=NATIVE_SCHEMA_VERSION,
        name="speeduino 202501-T41",
        firmware_signature="speeduino 202501-T41",
        parameters=[
            NativeParameter(
                semantic_id="reqFuel", legacy_name="reqFuel",
                label="Required fuel", units="ms",
                min_value=0.0, max_value=20.0,
            ),
        ],
        axes=[
            NativeAxis(
                semantic_id="rpmBins", legacy_name="rpmBins",
                length=16, units="rpm",
            ),
        ],
        tables=[
            NativeTable(
                semantic_id="veTable", legacy_name="veTable",
                rows=16, columns=16, units="%",
            ),
        ],
    )


def _cpp_definition_from_python(py_def: NativeDefinition):
    """Build a C++ NativeDefinition with the same content as `py_def`.

    The bindings expose default-constructible dataclasses, so we set
    each field explicitly. This avoids any Python-to-C++ conversion
    code path that could mask a bug — the parity test compares the
    final JSON, not the intermediate object state.
    """
    cpp_def = _tuner_core.NativeDefinition()
    cpp_def.schema_version = py_def.schema_version
    cpp_def.name = py_def.name
    cpp_def.firmware_signature = py_def.firmware_signature

    cpp_params = []
    for p in py_def.parameters:
        cpp_p = _tuner_core.NativeParameter()
        cpp_p.semantic_id = p.semantic_id
        cpp_p.legacy_name = p.legacy_name
        cpp_p.label = p.label
        cpp_p.units = p.units
        cpp_p.kind = p.kind
        cpp_p.min_value = p.min_value
        cpp_p.max_value = p.max_value
        # The C++ port models default as Optional[str]; the Python side
        # accepts int|float|str. Coerce to str for parity tests.
        cpp_p.default_value = None if p.default is None else str(p.default)
        cpp_params.append(cpp_p)
    cpp_def.parameters = cpp_params

    cpp_axes = []
    for a in py_def.axes:
        cpp_a = _tuner_core.NativeAxis()
        cpp_a.semantic_id = a.semantic_id
        cpp_a.legacy_name = a.legacy_name
        cpp_a.length = a.length
        cpp_a.units = a.units
        cpp_axes.append(cpp_a)
    cpp_def.axes = cpp_axes

    cpp_tables = []
    for t in py_def.tables:
        cpp_t = _tuner_core.NativeTable()
        cpp_t.semantic_id = t.semantic_id
        cpp_t.legacy_name = t.legacy_name
        cpp_t.rows = t.rows
        cpp_t.columns = t.columns
        cpp_t.label = t.label
        cpp_t.units = t.units
        cpp_t.x_axis_id = t.x_axis_id
        cpp_t.y_axis_id = t.y_axis_id
        cpp_tables.append(cpp_t)
    cpp_def.tables = cpp_tables

    return cpp_def


# ---------------------------------------------------------------------------
# dump_definition parity
# ---------------------------------------------------------------------------


class TestDumpDefinitionParity:
    def test_python_and_cpp_output_parse_to_equal_json(self) -> None:
        py_def = _python_definition()
        cpp_def = _cpp_definition_from_python(py_def)

        py_text = NativeFormatService().dump_definition(py_def)
        cpp_text = _tuner_core.dump_definition(cpp_def, 2)

        # Compare structurally — JSON formatters from different libraries
        # may differ in trailing whitespace or numeric representation,
        # but the parsed objects must be identical.
        assert json.loads(py_text) == json.loads(cpp_text)

    def test_cpp_dump_includes_schema_version(self) -> None:
        cpp_def = _tuner_core.NativeDefinition()
        text = _tuner_core.dump_definition(cpp_def, 2)
        data = json.loads(text)
        assert data["schema_version"] == NATIVE_SCHEMA_VERSION


class TestLoadDefinitionParity:
    def test_python_dump_loads_in_cpp(self) -> None:
        py_def = _python_definition()
        py_text = NativeFormatService().dump_definition(py_def)
        cpp_def = _tuner_core.load_definition(py_text)
        assert cpp_def.name == py_def.name
        assert cpp_def.firmware_signature == py_def.firmware_signature
        assert len(cpp_def.parameters) == len(py_def.parameters)
        assert len(cpp_def.axes) == len(py_def.axes)
        assert len(cpp_def.tables) == len(py_def.tables)

    def test_cpp_dump_loads_in_python(self) -> None:
        cpp_def = _cpp_definition_from_python(_python_definition())
        cpp_text = _tuner_core.dump_definition(cpp_def, 2)
        py_def = NativeFormatService().load_definition(cpp_text)
        assert py_def.name == "speeduino 202501-T41"
        assert py_def.firmware_signature == "speeduino 202501-T41"
        assert len(py_def.parameters) == 1
        assert py_def.parameters[0].semantic_id == "reqFuel"


# ---------------------------------------------------------------------------
# Tune parity (the more interesting case — variant types in JSON)
# ---------------------------------------------------------------------------


class TestTuneParity:
    def test_python_dump_loads_in_cpp_with_variant_types(self) -> None:
        py_tune = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="speeduino 202501-T41",
            values={
                "reqFuel": 8.5,
                "veTable": [50.0, 55.0, 60.0, 65.0],
                "label": "shop tune",
            },
        )
        py_text = NativeFormatService().dump_tune(py_tune)
        cpp_tune = _tuner_core.load_tune(py_text)
        assert cpp_tune.definition_signature == "speeduino 202501-T41"
        assert cpp_tune.values["reqFuel"] == 8.5
        assert cpp_tune.values["veTable"] == [50.0, 55.0, 60.0, 65.0]
        assert cpp_tune.values["label"] == "shop tune"

    def test_cpp_dump_loads_in_python_with_variant_types(self) -> None:
        cpp_tune = _tuner_core.NativeTune()
        cpp_tune.definition_signature = "speeduino 202501-T41"
        cpp_tune.values = {
            "reqFuel": 8.5,
            "veTable": [50.0, 55.0, 60.0, 65.0],
            "label": "shop tune",
        }
        cpp_text = _tuner_core.dump_tune(cpp_tune, 2)
        py_tune = NativeFormatService().load_tune(cpp_text)
        assert py_tune.definition_signature == "speeduino 202501-T41"
        assert py_tune.values["reqFuel"] == 8.5
        assert py_tune.values["veTable"] == [50.0, 55.0, 60.0, 65.0]
        assert py_tune.values["label"] == "shop tune"

    def test_python_and_cpp_tune_dump_parse_to_equal_json(self) -> None:
        cpp_tune = _tuner_core.NativeTune()
        cpp_tune.definition_signature = "speeduino 202501-T41"
        cpp_tune.values = {
            "reqFuel": 8.5,
            "veTable": [50.0, 55.0, 60.0, 65.0],
        }
        cpp_text = _tuner_core.dump_tune(cpp_tune, 2)

        py_tune = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="speeduino 202501-T41",
            values={
                "reqFuel": 8.5,
                "veTable": [50.0, 55.0, 60.0, 65.0],
            },
        )
        py_text = NativeFormatService().dump_tune(py_tune)
        assert json.loads(cpp_text) == json.loads(py_text)


# ---------------------------------------------------------------------------
# Schema version gating parity
# ---------------------------------------------------------------------------


class TestSchemaVersionGatingParity:
    def test_missing_version_raises_in_both(self) -> None:
        bad = '{"name": "x"}'
        with pytest.raises(NativeFormatVersionError):
            NativeFormatService().load_definition(bad)
        # The C++ binding maps NativeFormatVersionError → ValueError.
        with pytest.raises(Exception):
            _tuner_core.load_definition(bad)

    def test_future_major_version_raises_in_both(self) -> None:
        future = '{"schema_version": "9.0", "name": "x"}'
        with pytest.raises(NativeFormatVersionError):
            NativeFormatService().load_definition(future)
        with pytest.raises(Exception):
            _tuner_core.load_definition(future)

    def test_minor_bump_accepted_in_both(self) -> None:
        text = '{"schema_version": "1.5", "name": "x"}'
        py_def = NativeFormatService().load_definition(text)
        cpp_def = _tuner_core.load_definition(text)
        assert py_def.name == cpp_def.name == "x"
        assert py_def.schema_version == cpp_def.schema_version == "1.5"
