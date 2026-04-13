"""Python ↔ C++ parity harness for the tuner_core INI [Constants] parser.

Future Phase 13 fourth slice. Drives the same INI source fixtures
through both the Python `IniParser._parse_constant_definitions` (via
the public `IniParser.parse(path)` API) and the C++
`tuner_core.parse_constants_section` and asserts the resulting
scalar/array catalogs match.

Like the prior parity harnesses, the C++ extension is **optional**:
every test in this file is marked as skipped when the extension isn't
built. Build instructions live in `cpp/README.md`.
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CPP_BUILD_CANDIDATES = [
    _REPO_ROOT / "build" / "cpp",
    _REPO_ROOT / "build" / "cpp" / "Release",
    _REPO_ROOT / "build" / "cpp" / "Debug",
    _REPO_ROOT / "cpp" / "build",
]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


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
# Synthetic fixture parity
# ---------------------------------------------------------------------------

def _parse_python_constants(text: str):
    """Parse [Constants] via the public IniParser API. Writes to a
    temp file because the parser is path-driven."""
    import tempfile
    with tempfile.NamedTemporaryFile(
        suffix=".ini", delete=False, mode="w", encoding="utf-8",
    ) as f:
        f.write(text)
        path = Path(f.name)
    try:
        return IniParser().parse(path)
    finally:
        path.unlink(missing_ok=True)


_SYNTHETIC_INI = textwrap.dedent("""\
    [Constants]
    page = 1
    reqFuel = scalar, U16, 0, "ms", 0.1, 0.0, 0.0, 25.5, 1
    nCylinders = scalar, U08, 2, "cyl", 1.0, 0.0, 1.0, 16.0, 0
    veTable = array, U08, 16, [16x16], "%", 1.0, 0.0, 0.0, 255.0, 0
    afterTable = scalar, U08, lastOffset, "", 1, 0, 0, 255, 0

    page = 2
    p2first = scalar, U32, 0, "ms", 1.0, 0.0, 0.0, 1000.0, 0
    rpmBins = array, U08, lastOffset, [16], "rpm", 100.0, 0.0, 0.0, 25500.0, 0
    """)


class TestSyntheticParity:
    def test_scalar_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_constants_section(_SYNTHETIC_INI)
        py = _parse_python_constants(_SYNTHETIC_INI)
        # Match by name set — ordering is consistent across both but
        # comparing sets makes the failure message more useful.
        py_names = {s.name for s in py.scalars}
        cpp_names = {s.name for s in cpp.scalars}
        assert py_names == cpp_names

    def test_array_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_constants_section(_SYNTHETIC_INI)
        py = _parse_python_constants(_SYNTHETIC_INI)
        py_names = {a.name for a in py.tables}
        cpp_names = {a.name for a in cpp.arrays}
        assert py_names == cpp_names

    def test_scalar_offsets_and_pages_match_python(self) -> None:
        cpp = _tuner_core.parse_constants_section(_SYNTHETIC_INI)
        py = _parse_python_constants(_SYNTHETIC_INI)
        py_by_name = {s.name: s for s in py.scalars}
        for cs in cpp.scalars:
            ps = py_by_name[cs.name]
            assert cs.page == ps.page, f"page mismatch on {cs.name}"
            assert cs.offset == ps.offset, f"offset mismatch on {cs.name}"

    def test_lastOffset_resolution_matches_python(self) -> None:
        """`afterTable` should land at offset 16+256=272 in both
        implementations because veTable is a 16x16 U08 array."""
        cpp = _tuner_core.parse_constants_section(_SYNTHETIC_INI)
        py = _parse_python_constants(_SYNTHETIC_INI)
        cpp_after = next(s for s in cpp.scalars if s.name == "afterTable")
        py_after = next(s for s in py.scalars if s.name == "afterTable")
        assert cpp_after.offset == py_after.offset == 272

    def test_array_dimensions_match_python(self) -> None:
        cpp = _tuner_core.parse_constants_section(_SYNTHETIC_INI)
        py = _parse_python_constants(_SYNTHETIC_INI)
        cpp_ve = next(a for a in cpp.arrays if a.name == "veTable")
        py_ve = next(a for a in py.tables if a.name == "veTable")
        assert (cpp_ve.rows, cpp_ve.columns) == (py_ve.rows, py_ve.columns)
        # Also the 1D rpmBins variant
        cpp_rpm = next(a for a in cpp.arrays if a.name == "rpmBins")
        py_rpm = next(a for a in py.tables if a.name == "rpmBins")
        assert (cpp_rpm.rows, cpp_rpm.columns) == (py_rpm.rows, py_rpm.columns)

    def test_units_and_data_types_match_python(self) -> None:
        cpp = _tuner_core.parse_constants_section(_SYNTHETIC_INI)
        py = _parse_python_constants(_SYNTHETIC_INI)
        py_by_name = {s.name: s for s in py.scalars}
        for cs in cpp.scalars:
            ps = py_by_name[cs.name]
            assert cs.data_type == ps.data_type
            assert cs.units == ps.units

    def test_lastOffset_resets_at_page_boundary(self) -> None:
        cpp = _tuner_core.parse_constants_section(_SYNTHETIC_INI)
        py = _parse_python_constants(_SYNTHETIC_INI)
        cpp_p2 = next(s for s in cpp.scalars if s.name == "p2first")
        py_p2 = next(s for s in py.scalars if s.name == "p2first")
        assert cpp_p2.page == py_p2.page == 2
        assert cpp_p2.offset == py_p2.offset == 0
        # rpmBins on page 2 lastOffset = 4 (after U32 p2first)
        cpp_rpm = next(a for a in cpp.arrays if a.name == "rpmBins")
        py_rpm = next(a for a in py.tables if a.name == "rpmBins")
        assert cpp_rpm.offset == py_rpm.offset == 4


# ---------------------------------------------------------------------------
# Real production INI parity — the headline cross-validation
# ---------------------------------------------------------------------------

_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


@pytest.mark.skipif(
    not _PRODUCTION_INI.exists(),
    reason="production INI fixture not available",
)
class TestProductionFixtureParity:
    """Composed-pipeline parity against the real production INI.

    With slice 3 (preprocessor) wired into slice 4 (constants parser)
    via `parse_constants_section_preprocessed`, the C++ catalog is the
    **exact** set of scalars/arrays the Python parser collects from
    `[Constants]`. The Python `EcuDefinition` carries additional
    scalars from non-`[Constants]` sections (`[Menu]`, `[Tuning]`,
    `[SettingGroups]`, etc.) — these have ``page=None offset=None``
    and are correctly absent from the C++ catalog because the v1 C++
    parser only handles `[Constants]`.

    The headline parity claim is therefore:

      1. Every scalar/array C++ finds is in Python with byte-identical
         page+offset (or rows×columns for arrays).
      2. The C++ catalog == Python catalog **after filtering Python to
         entries that have a page+offset** (i.e. entries that came
         from `[Constants]`).
    """

    def _parse(self):
        py = IniParser().parse(_PRODUCTION_INI)
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.parse_constants_section_preprocessed(text, set())
        return py, cpp

    def _python_constants_section_scalars(self, py) -> set[str]:
        """Filter the Python EcuDefinition.scalars to entries that
        came from `[Constants]` (those have a page+offset; entries
        from `[Menu]`/`[Tuning]`/`[SettingGroups]` don't)."""
        return {s.name for s in py.scalars if s.page is not None and s.offset is not None}

    def _python_constants_section_arrays(self, py) -> set[str]:
        return {a.name for a in py.tables if a.page is not None and a.offset is not None}

    def test_cpp_scalar_set_equals_python_constants_section(self) -> None:
        py, cpp = self._parse()
        py_constants_scalars = self._python_constants_section_scalars(py)
        cpp_names = {s.name for s in cpp.scalars}
        only_in_cpp = cpp_names - py_constants_scalars
        only_in_python_constants = py_constants_scalars - cpp_names
        assert not only_in_cpp, f"C++ saw scalars not in Python [Constants]: {only_in_cpp}"
        assert not only_in_python_constants, (
            f"Python [Constants] has scalars C++ didn't: "
            f"{sorted(only_in_python_constants)[:20]}"
        )

    def test_cpp_array_set_equals_python_constants_section(self) -> None:
        py, cpp = self._parse()
        py_constants_arrays = self._python_constants_section_arrays(py)
        cpp_names = {a.name for a in cpp.arrays}
        only_in_cpp = cpp_names - py_constants_arrays
        only_in_python_constants = py_constants_arrays - cpp_names
        assert not only_in_cpp, f"C++ saw arrays not in Python [Constants]: {only_in_cpp}"
        assert not only_in_python_constants, (
            f"Python [Constants] has arrays C++ didn't: "
            f"{sorted(only_in_python_constants)[:20]}"
        )

    def test_every_scalar_byte_position_matches_python(self) -> None:
        """For every scalar both implementations parsed, page+offset
        must match byte-for-byte. This is the headline correctness
        claim of the composed pipeline."""
        py, cpp = self._parse()
        py_by_name = {s.name: s for s in py.scalars}
        mismatches = []
        for cs in cpp.scalars:
            ps = py_by_name.get(cs.name)
            if ps is None:
                continue
            if cs.page != ps.page or cs.offset != ps.offset:
                mismatches.append(
                    f"{cs.name}: cpp page={cs.page} offset={cs.offset} "
                    f"vs py page={ps.page} offset={ps.offset}"
                )
        assert not mismatches, "Page/offset mismatches:\n" + "\n".join(mismatches[:20])

    def test_every_array_dimension_matches_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {a.name: a for a in py.tables}
        mismatches = []
        for ca in cpp.arrays:
            pa = py_by_name.get(ca.name)
            if pa is None:
                continue
            if ca.rows != pa.rows or ca.columns != pa.columns:
                mismatches.append(
                    f"{ca.name}: cpp {ca.rows}x{ca.columns} "
                    f"vs py {pa.rows}x{pa.columns}"
                )
        assert not mismatches, "Dimension mismatches:\n" + "\n".join(mismatches[:20])

    def test_total_constants_section_counts_match(self) -> None:
        """The C++ count must equal the Python count *after filtering
        Python to `[Constants]`-sourced entries*. This proves the C++
        parser is exact for the section it claims, even though Python
        carries additional scalars from `[Menu]`/`[Tuning]`/etc."""
        py, cpp = self._parse()
        assert len(cpp.scalars) > 100, (
            f"C++ found only {len(cpp.scalars)} scalars — sanity check"
        )
        assert len(cpp.arrays) > 20, (
            f"C++ found only {len(cpp.arrays)} arrays — sanity check"
        )
        py_constants_scalars = self._python_constants_section_scalars(py)
        py_constants_arrays = self._python_constants_section_arrays(py)
        assert len(cpp.scalars) == len(py_constants_scalars), (
            f"C++ {len(cpp.scalars)} vs Python [Constants] {len(py_constants_scalars)}"
        )
        assert len(cpp.arrays) == len(py_constants_arrays)
