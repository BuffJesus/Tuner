"""Python ↔ C++ parity harness for the tuner_core INI [TableEditor] parser.

Phase 14 second parser slice. Drives the same INI source through both
the Python `IniParser._parse_table_editors` (via the public
`IniParser.parse` API) and the C++ `tuner_core.parse_table_editor_*`
and asserts the resulting catalogs match.

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


def _python_parse(text: str):
    """Parse via the public IniParser API. Writes to a temp file."""
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


# ---------------------------------------------------------------------------
# Synthetic fixture parity
# ---------------------------------------------------------------------------

_SYNTHETIC_INI = textwrap.dedent("""\
    [TableEditor]
    table = veTblTbl, veMap, "VE Table", 2
    topicHelp = "How to tune VE"
    xBins = rpmBins, rpm
    yBins = mapBins, map
    zBins = veTable
    xyLabels = "RPM", "MAP (kPa)"
    gridHeight = 50.0
    gridOrient = 250.0, 0.0, 340.0
    upDownLabel = "RICHER", "LEANER"

    table = ignTblTbl, ignMap, "Ignition Table"
    xBins = rpmBins, rpm
    yBins = mapBins, map
    zBins = ignitionTable
    """)


class TestSyntheticParity:
    def test_editor_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_table_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        assert len(cpp.editors) == len(py.table_editors)

    def test_editor_table_ids_match_python(self) -> None:
        cpp = _tuner_core.parse_table_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        assert {e.table_id for e in cpp.editors} == {e.table_id for e in py.table_editors}

    def test_editor_fields_match_python(self) -> None:
        cpp = _tuner_core.parse_table_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        py_by_id = {e.table_id: e for e in py.table_editors}
        for ce in cpp.editors:
            pe = py_by_id[ce.table_id]
            assert ce.map_id == pe.map_id, f"map_id on {ce.table_id}"
            assert ce.title == pe.title, f"title on {ce.table_id}"
            assert ce.page == pe.page, f"page on {ce.table_id}"
            assert ce.x_bins == pe.x_bins, f"x_bins on {ce.table_id}"
            assert ce.x_channel == pe.x_channel, f"x_channel on {ce.table_id}"
            assert ce.y_bins == pe.y_bins, f"y_bins on {ce.table_id}"
            assert ce.y_channel == pe.y_channel, f"y_channel on {ce.table_id}"
            assert ce.z_bins == pe.z_bins, f"z_bins on {ce.table_id}"
            assert ce.x_label == pe.x_label, f"x_label on {ce.table_id}"
            assert ce.y_label == pe.y_label, f"y_label on {ce.table_id}"
            assert ce.up_label == pe.up_label, f"up_label on {ce.table_id}"
            assert ce.down_label == pe.down_label, f"down_label on {ce.table_id}"

    def test_grid_height_and_orient_match_python(self) -> None:
        cpp = _tuner_core.parse_table_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        cpp_ve = next(e for e in cpp.editors if e.table_id == "veTblTbl")
        py_ve = next(e for e in py.table_editors if e.table_id == "veTblTbl")
        assert cpp_ve.grid_height == py_ve.grid_height
        # Python stores grid_orient as a tuple; C++ exposes it as a list
        # via nanobind's std::array binding.
        assert tuple(cpp_ve.grid_orient) == py_ve.grid_orient

    def test_topic_help_matches_python(self) -> None:
        cpp = _tuner_core.parse_table_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        cpp_ve = next(e for e in cpp.editors if e.table_id == "veTblTbl")
        py_ve = next(e for e in py.table_editors if e.table_id == "veTblTbl")
        assert cpp_ve.topic_help == py_ve.topic_help


# ---------------------------------------------------------------------------
# Real production INI parity
# ---------------------------------------------------------------------------

_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


@pytest.mark.skipif(
    not _PRODUCTION_INI.exists(),
    reason="production INI fixture not available",
)
class TestProductionFixtureParity:
    def _parse(self):
        py = IniParser().parse(_PRODUCTION_INI)
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.parse_table_editor_section_preprocessed(text, set())
        return py, cpp

    def test_editor_set_matches_python(self) -> None:
        py, cpp = self._parse()
        cpp_ids = {e.table_id for e in cpp.editors}
        py_ids = {e.table_id for e in py.table_editors}
        only_in_cpp = cpp_ids - py_ids
        only_in_python = py_ids - cpp_ids
        assert not only_in_cpp, f"C++ saw editors Python didn't: {only_in_cpp}"
        assert not only_in_python, (
            f"Python saw editors C++ didn't ({len(only_in_python)} total): "
            f"{sorted(only_in_python)[:20]}"
        )

    def test_every_editor_zbins_matches_python(self) -> None:
        """For every overlapping editor, the zBins (data array name)
        must match byte-for-byte. This is the headline correctness
        claim — zBins is what the table generators and the runtime
        consumers care about most."""
        py, cpp = self._parse()
        py_by_id = {e.table_id: e for e in py.table_editors}
        mismatches = []
        for ce in cpp.editors:
            pe = py_by_id.get(ce.table_id)
            if pe is None:
                continue
            if ce.z_bins != pe.z_bins:
                mismatches.append(
                    f"{ce.table_id}: cpp z_bins={ce.z_bins} vs py z_bins={pe.z_bins}"
                )
        assert not mismatches, "z_bins mismatches:\n" + "\n".join(mismatches[:20])

    def test_every_editor_axis_bins_match_python(self) -> None:
        py, cpp = self._parse()
        py_by_id = {e.table_id: e for e in py.table_editors}
        mismatches = []
        for ce in cpp.editors:
            pe = py_by_id.get(ce.table_id)
            if pe is None:
                continue
            if ce.x_bins != pe.x_bins:
                mismatches.append(
                    f"{ce.table_id} x_bins: cpp={ce.x_bins} vs py={pe.x_bins}"
                )
            if ce.y_bins != pe.y_bins:
                mismatches.append(
                    f"{ce.table_id} y_bins: cpp={ce.y_bins} vs py={pe.y_bins}"
                )
        assert not mismatches, "axis bin mismatches:\n" + "\n".join(mismatches[:20])

    def test_every_editor_axis_channels_match_python(self) -> None:
        """The live-tuning operating-point overlay (G3) needs the
        x_channel / y_channel mapping; this test locks it down."""
        py, cpp = self._parse()
        py_by_id = {e.table_id: e for e in py.table_editors}
        mismatches = []
        for ce in cpp.editors:
            pe = py_by_id.get(ce.table_id)
            if pe is None:
                continue
            if ce.x_channel != pe.x_channel:
                mismatches.append(
                    f"{ce.table_id} x_channel: cpp={ce.x_channel} vs py={pe.x_channel}"
                )
            if ce.y_channel != pe.y_channel:
                mismatches.append(
                    f"{ce.table_id} y_channel: cpp={ce.y_channel} vs py={pe.y_channel}"
                )
        assert not mismatches, "axis channel mismatches:\n" + "\n".join(mismatches[:20])

    def test_titles_match_python(self) -> None:
        py, cpp = self._parse()
        py_by_id = {e.table_id: e for e in py.table_editors}
        mismatches = []
        for ce in cpp.editors:
            pe = py_by_id.get(ce.table_id)
            if pe is None:
                continue
            if ce.title != pe.title:
                mismatches.append(
                    f"{ce.table_id}: cpp title={ce.title!r} vs py title={pe.title!r}"
                )
        assert not mismatches, "title mismatches:\n" + "\n".join(mismatches[:20])

    def test_total_editor_count_is_substantial(self) -> None:
        """Sanity that the production INI has a meaningful number of
        table editors and we're parsing the bulk of them."""
        _, cpp = self._parse()
        assert len(cpp.editors) > 10, (
            f"only {len(cpp.editors)} editors parsed — production INI "
            "should have at least a dozen"
        )
