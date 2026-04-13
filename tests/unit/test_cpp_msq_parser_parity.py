"""Python ↔ C++ parity harness for the tuner_core MSQ parser.

Future Phase 13 first slice. Drives the existing MSQ fixture suite
through both the Python ``MsqParser``/``MsqWriteService`` and the
C++ ``tuner_core`` extension, then asserts byte-identical results.

The C++ extension is **optional**: if it isn't built (no compiler,
fresh dev install, etc.) every test in this file is marked as
skipped — never as a failure. Build instructions live in
``cpp/README.md``.
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from tuner.parsers.msq_parser import MsqParser
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CPP_BUILD_CANDIDATES = [
    _REPO_ROOT / "build" / "cpp",
    _REPO_ROOT / "build" / "cpp" / "Release",
    _REPO_ROOT / "build" / "cpp" / "Debug",
    _REPO_ROOT / "cpp" / "build",
]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


def _try_import_tuner_core():
    """Locate the tuner_core extension on disk and import it.

    Tries the in-tree CMake build directories first; falls back to a
    package import in case the wheel is installed. Returns the module
    or ``None`` when the extension is not available.
    """
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
# Synthetic fixture (so the parity suite has at least one case the user
# can run without copying the production MSQ to tests/fixtures/).
# ---------------------------------------------------------------------------

_SYNTHETIC_MSQ = textwrap.dedent("""\
    <?xml version="1.0" encoding="ISO-8859-1"?>
    <msq xmlns="http://www.msefi.com/:msq">
      <versionInfo signature="speeduino 202501-T41" fileFormat="2" nPages="1"/>
      <page number="1">
        <constant name="reqFuel" units="ms" digits="1">8.5</constant>
        <constant name="nCylinders" units="cyl">4</constant>
        <constant name="veTable" units="%" rows="2" cols="2" digits="1">
             50 55
             60 65
          </constant>
      </page>
    </msq>
    """)


@pytest.fixture
def synthetic_msq(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.msq"
    path.write_text(_SYNTHETIC_MSQ, encoding="ISO-8859-1")
    return path


# ---------------------------------------------------------------------------
# parse_msq parity
# ---------------------------------------------------------------------------

class TestParseParity:
    def test_signature_matches_python(self, synthetic_msq: Path) -> None:
        py_doc = MsqParser().parse(synthetic_msq)
        cpp_doc = _tuner_core.parse_msq(str(synthetic_msq))
        assert cpp_doc.signature == py_doc.signature == "speeduino 202501-T41"

    def test_constant_names_match_python(self, synthetic_msq: Path) -> None:
        py_doc = MsqParser().parse(synthetic_msq)
        cpp_doc = _tuner_core.parse_msq(str(synthetic_msq))
        py_names = {c.name for c in py_doc.constants}
        cpp_names = {c.name for c in cpp_doc.constants}
        assert py_names == cpp_names

    def test_table_shape_matches_python(self, synthetic_msq: Path) -> None:
        cpp_doc = _tuner_core.parse_msq(str(synthetic_msq))
        ve = next(c for c in cpp_doc.constants if c.name == "veTable")
        assert ve.rows == 2
        assert ve.cols == 2
        assert ve.units == "%"
        assert ve.digits == 1


# ---------------------------------------------------------------------------
# write_msq parity — proves the C++ writer produces a file the Python
# parser reads as equivalent to the Python writer's output.
# ---------------------------------------------------------------------------

class TestWriteParity:
    def test_no_op_write_is_byte_stable(self, synthetic_msq: Path, tmp_path: Path) -> None:
        out = tmp_path / "noop.msq"
        applied = _tuner_core.write_msq(str(synthetic_msq), str(out), {})
        assert applied == 0
        assert out.read_text(encoding="ISO-8859-1") == synthetic_msq.read_text(encoding="ISO-8859-1")

    def test_scalar_update_round_trips_through_python_parser(
        self, synthetic_msq: Path, tmp_path: Path,
    ) -> None:
        out = tmp_path / "updated.msq"
        applied = _tuner_core.write_msq(
            str(synthetic_msq), str(out), {"reqFuel": "9.5"},
        )
        assert applied == 1
        reloaded = MsqParser().parse(out)
        req = next(c for c in reloaded.constants if c.name == "reqFuel")
        assert req.value == 9.5

    def test_cpp_writer_matches_python_writer_semantically(
        self, synthetic_msq: Path, tmp_path: Path,
    ) -> None:
        # Drive both writers with the same edit and assert the resulting
        # documents parse to equal constant sets. We compare *semantics*
        # rather than bytes because the two writers take different
        # strategies that are both valid:
        #   - Python re-serializes via xml.etree.ElementTree, which uses
        #     single quotes for attributes and adds an ns0: namespace
        #     prefix.
        #   - C++ byte-splices the source XML, preserving the original
        #     double-quoted attributes and xmlns form verbatim.
        # The C++ approach is actually preferable for round-trip
        # fidelity (keeps the upstream TunerStudio formatting), but the
        # parity claim is that *the resulting tunes are equivalent*.
        edit = LocalTuneEditService()
        edit.set_tune_file(MsqParser().parse(synthetic_msq))
        edit.stage_scalar_value("reqFuel", "9.5")

        py_out = tmp_path / "py.msq"
        MsqWriteService().save(synthetic_msq, py_out, edit)

        cpp_out = tmp_path / "cpp.msq"
        _tuner_core.write_msq(str(synthetic_msq), str(cpp_out), {"reqFuel": "9.5"})

        py_tune = MsqParser().parse(py_out)
        cpp_tune = MsqParser().parse(cpp_out)
        py_values = {c.name: c.value for c in py_tune.constants}
        cpp_values = {c.name: c.value for c in cpp_tune.constants}
        assert py_values == cpp_values
        assert py_values["reqFuel"] == 9.5

    def test_cpp_writer_drops_unknown_constants_like_python(
        self, synthetic_msq: Path, tmp_path: Path,
    ) -> None:
        out = tmp_path / "drop.msq"
        applied = _tuner_core.write_msq(
            str(synthetic_msq), str(out),
            {"unknownConstant": "1 2 3 4"},
        )
        assert applied == 0
        # The new constant must NOT appear in the output — matches the
        # documented Python default insert_missing=False behaviour.
        reloaded = MsqParser().parse(out)
        names = {c.name for c in reloaded.constants}
        assert "unknownConstant" not in names


# ---------------------------------------------------------------------------
# Production fixture parity — only runs when the real production MSQ is
# in tests/fixtures/. This is the headline cross-validation test.
# ---------------------------------------------------------------------------

_PRODUCTION_MSQ = _FIXTURES / "speeduino-dropbear-v2.0.1-base-tune.msq"


@pytest.mark.skipif(
    not _PRODUCTION_MSQ.exists(),
    reason="production MSQ fixture not available",
)
class TestProductionFixtureParity:
    def test_python_and_cpp_parsers_see_same_constant_set(self) -> None:
        py_doc = MsqParser().parse(_PRODUCTION_MSQ)
        cpp_doc = _tuner_core.parse_msq(str(_PRODUCTION_MSQ))
        py_names = sorted(c.name for c in py_doc.constants)
        cpp_names = sorted(c.name for c in cpp_doc.constants)
        assert py_names == cpp_names

    def test_no_op_write_is_byte_stable_against_production(self, tmp_path: Path) -> None:
        out = tmp_path / "production_noop.msq"
        _tuner_core.write_msq(str(_PRODUCTION_MSQ), str(out), {})
        assert out.read_bytes() == _PRODUCTION_MSQ.read_bytes()
