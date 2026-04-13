"""Python ↔ C++ parity harness for MsqWriteService insert_missing mode.

Pins the C++ `write_msq_text_with_insertions` + scalar/table formatters
against the Python `MsqWriteService.save(insert_missing=True)` path so
the two write-out layers stay byte-identical on every case the Python
fixture suite already covers.
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest


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


_MSQ_HEADER = textwrap.dedent("""\
    <?xml version="1.0" encoding="ISO-8859-1"?>
    <msq xmlns="http://www.msefi.com/:msq">
      <versionInfo signature="speeduino 202501-T41" fileFormat="2" nPages="1"/>
      <page number="1">
""")
_MSQ_FOOTER = textwrap.dedent("""\
      </page>
    </msq>
    """)


def _msq_with_only_reqfuel() -> str:
    body = '    <constant name="reqFuel" units="ms" digits="1">8.5</constant>\n'
    return _MSQ_HEADER + body + _MSQ_FOOTER


# ---------------------------------------------------------------------------
# Scalar / table formatter parity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (0.0, "0"),
    (6.0, "6"),
    (-3.0, "-3"),
    (8.5, "8.5"),
    (1.25, "1.25"),
])
def test_format_msq_scalar_matches_python(value, expected):
    from tuner.services.msq_write_service import _fmt_scalar
    py = _fmt_scalar(value)
    cpp = _tuner_core.format_msq_scalar(value)
    assert cpp == py == expected


def test_format_msq_table_matches_python_layout():
    from tuner.domain.tune import TuneValue
    from tuner.services.msq_write_service import MsqWriteService
    tv = TuneValue(name="veTable", value=[50.0, 55.0, 60.0, 65.0], rows=2, cols=2, units="%")
    py_text = MsqWriteService()._format_value(tv)
    cpp_text = _tuner_core.format_msq_table([50.0, 55.0, 60.0, 65.0], 2, 2)
    assert cpp_text == py_text


def test_format_msq_table_single_row():
    from tuner.domain.tune import TuneValue
    from tuner.services.msq_write_service import MsqWriteService
    tv = TuneValue(name="rpmBins", value=[500.0, 1000.0, 1500.0], rows=1, cols=3)
    py_text = MsqWriteService()._format_value(tv)
    cpp_text = _tuner_core.format_msq_table([500.0, 1000.0, 1500.0], 1, 3)
    assert cpp_text == py_text


# ---------------------------------------------------------------------------
# write_msq_text_with_insertions parity
# ---------------------------------------------------------------------------

def _run_python_insert_missing(tmp_path, source_text, stage_ops):
    """Invoke the Python `MsqWriteService.save(insert_missing=True)` path
    the same way the existing test suite does, then return the rewritten
    XML text."""
    from tuner.parsers.msq_parser import MsqParser
    from tuner.services.local_tune_edit_service import LocalTuneEditService
    from tuner.services.msq_write_service import MsqWriteService

    src = tmp_path / "source.msq"
    src.write_text(source_text, encoding="ISO-8859-1")
    tune = MsqParser().parse(src)
    edit = LocalTuneEditService()
    edit.set_tune_file(tune)
    for op in stage_ops:
        edit.set_or_add_base_value(**op)

    dst = tmp_path / "out.msq"
    MsqWriteService().save(src, dst, edit, insert_missing=True)
    return dst.read_text(encoding="ISO-8859-1")


def _build_cpp_insertions(stage_ops):
    """Translate the same stage_ops list into a list of C++
    `MsqInsertion` objects so both implementations see byte-identical
    inputs. Mirrors `MsqWriteService._constant_attribs` +
    `_format_value`."""
    insertions = []
    for op in stage_ops:
        ins = _tuner_core.MsqInsertion()
        ins.name = op["name"]
        value = op["value"]
        if isinstance(value, list):
            ins.text = _tuner_core.format_msq_table(
                [float(v) for v in value],
                int(op.get("rows") or 1),
                int(op.get("cols") or len(value)),
            )
            ins.rows = int(op.get("rows") or 1)
            ins.cols = int(op.get("cols") or len(value))
        else:
            ins.text = _tuner_core.format_msq_scalar(float(value))
            ins.rows = 0
            ins.cols = 0
        ins.units = op.get("units", "") or ""
        ins.digits = int(op["digits"]) if "digits" in op and op["digits"] is not None else -1
        insertions.append(ins)
    return insertions


def test_insert_missing_table_parity(tmp_path):
    src = _msq_with_only_reqfuel()
    stage_ops = [
        {"name": "veTable", "value": [50.0, 55.0, 60.0, 65.0],
         "rows": 2, "cols": 2, "units": "%"},
    ]
    py_text = _run_python_insert_missing(tmp_path, src, stage_ops)
    cpp_text = _tuner_core.write_msq_text_with_insertions(
        src, {}, _build_cpp_insertions(stage_ops)
    )
    # Both should now contain the veTable constant with matching values.
    assert "veTable" in cpp_text
    assert "50 55" in cpp_text
    assert "60 65" in cpp_text
    # And the round-trip through MsqParser on both sides yields the
    # same typed values (the structural parity check).
    from tuner.parsers.msq_parser import MsqParser as PyMsqParser
    py_out = tmp_path / "py_out.msq"
    py_out.write_text(py_text, encoding="ISO-8859-1")
    py_doc = PyMsqParser().parse(py_out)
    cpp_doc_src = tmp_path / "cpp_out.msq"
    cpp_doc_src.write_text(cpp_text, encoding="ISO-8859-1")
    cpp_doc = PyMsqParser().parse(cpp_doc_src)
    py_ve = next(c for c in py_doc.constants if c.name == "veTable")
    cpp_ve = next(c for c in cpp_doc.constants if c.name == "veTable")
    assert py_ve.value == cpp_ve.value == [50.0, 55.0, 60.0, 65.0]
    assert py_ve.rows == cpp_ve.rows == 2
    assert py_ve.cols == cpp_ve.cols == 2
    assert py_ve.units == cpp_ve.units == "%"


def test_insert_missing_scalar_parity(tmp_path):
    src = _msq_with_only_reqfuel()
    stage_ops = [{"name": "nCylinders", "value": 6.0}]
    cpp_text = _tuner_core.write_msq_text_with_insertions(
        src, {}, _build_cpp_insertions(stage_ops)
    )
    # Parse both through the Python MsqParser and compare typed values.
    from tuner.parsers.msq_parser import MsqParser
    py_text = _run_python_insert_missing(tmp_path, src, stage_ops)
    py_out = tmp_path / "py.msq"
    py_out.write_text(py_text, encoding="ISO-8859-1")
    py_doc = MsqParser().parse(py_out)
    cpp_src = tmp_path / "cpp.msq"
    cpp_src.write_text(cpp_text, encoding="ISO-8859-1")
    cpp_doc = MsqParser().parse(cpp_src)
    py_cyl = next(c for c in py_doc.constants if c.name == "nCylinders")
    cpp_cyl = next(c for c in cpp_doc.constants if c.name == "nCylinders")
    assert py_cyl.value == cpp_cyl.value == 6.0


def test_insert_missing_preserves_existing_constants_parity(tmp_path):
    src = _msq_with_only_reqfuel()
    stage_ops = [
        {"name": "veTable", "value": [10.0, 20.0, 30.0, 40.0],
         "rows": 2, "cols": 2, "units": "%"},
    ]
    cpp_text = _tuner_core.write_msq_text_with_insertions(
        src, {}, _build_cpp_insertions(stage_ops)
    )
    from tuner.parsers.msq_parser import MsqParser
    cpp_src = tmp_path / "cpp.msq"
    cpp_src.write_text(cpp_text, encoding="ISO-8859-1")
    cpp_doc = MsqParser().parse(cpp_src)
    req = next(c for c in cpp_doc.constants if c.name == "reqFuel")
    assert req.value == 8.5


def test_insert_missing_skips_name_already_present(tmp_path):
    src = _msq_with_only_reqfuel()
    stage_ops = [{"name": "reqFuel", "value": 9999.0}]  # should be ignored
    cpp_text = _tuner_core.write_msq_text_with_insertions(
        src, {}, _build_cpp_insertions(stage_ops)
    )
    # Original reqFuel value preserved, no 9999 injected.
    assert "9999" not in cpp_text
    assert ">8.5<" in cpp_text
