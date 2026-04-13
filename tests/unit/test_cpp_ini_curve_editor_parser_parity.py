"""Python ↔ C++ parity harness for the tuner_core INI [CurveEditor] parser.

Phase 14 third parser slice. Drives the same INI source through both
the Python `IniParser._parse_curve_editors` (via the public
`IniParser.parse` API) and the C++ `tuner_core.parse_curve_editor_*`
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
    [CurveEditor]
    curve = wueCurve, "Warm-up Enrichment"
    columnLabel = "Coolant", "Multiplier %"
    xAxis = -40.0, 215.0, 5
    yAxis = 100.0, 250.0, 5
    xBins = wueBins, coolant
    yBins = WUEValues
    topicHelp = "WUE help"
    gauge = cltGauge

    curve = veCmp, "VE current vs recommended"
    xBins = veBins
    yBins = veCurrent
    yBins = veRecommended
    lineLabel = "Current"
    lineLabel = "Recommended"
    """)


class TestSyntheticParity:
    def test_curve_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_curve_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        assert len(cpp.curves) == len(py.curve_definitions)

    def test_curve_names_match_python(self) -> None:
        cpp = _tuner_core.parse_curve_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        assert {c.name for c in cpp.curves} == {c.name for c in py.curve_definitions}

    def test_curve_fields_match_python(self) -> None:
        cpp = _tuner_core.parse_curve_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        py_by_name = {c.name: c for c in py.curve_definitions}
        for cc in cpp.curves:
            pc = py_by_name[cc.name]
            assert cc.title == pc.title, f"title on {cc.name}"
            assert cc.x_bins_param == pc.x_bins_param, f"x_bins_param on {cc.name}"
            assert cc.x_channel == pc.x_channel, f"x_channel on {cc.name}"
            assert cc.x_label == pc.x_label, f"x_label on {cc.name}"
            assert cc.y_label == pc.y_label, f"y_label on {cc.name}"
            assert cc.topic_help == pc.topic_help, f"topic_help on {cc.name}"
            assert cc.gauge == pc.gauge, f"gauge on {cc.name}"

    def test_y_bins_lists_match_python(self) -> None:
        cpp = _tuner_core.parse_curve_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        py_by_name = {c.name: c for c in py.curve_definitions}
        for cc in cpp.curves:
            pc = py_by_name[cc.name]
            cpp_params = [yb.param for yb in cc.y_bins_list]
            py_params = [yb.param for yb in pc.y_bins_list]
            assert cpp_params == py_params, f"y_bins params on {cc.name}"
            cpp_labels = [yb.label for yb in cc.y_bins_list]
            py_labels = [yb.label for yb in pc.y_bins_list]
            assert cpp_labels == py_labels, f"y_bins labels on {cc.name}"

    def test_axis_ranges_match_python(self) -> None:
        cpp = _tuner_core.parse_curve_editor_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        cc = next(c for c in cpp.curves if c.name == "wueCurve")
        pc = next(c for c in py.curve_definitions if c.name == "wueCurve")
        assert cc.x_axis.min == pc.x_axis.min
        assert cc.x_axis.max == pc.x_axis.max
        assert cc.x_axis.steps == pc.x_axis.steps
        assert cc.y_axis.min == pc.y_axis.min
        assert cc.y_axis.max == pc.y_axis.max
        assert cc.y_axis.steps == pc.y_axis.steps


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
        cpp = _tuner_core.parse_curve_editor_section_preprocessed(text, set())
        return py, cpp

    def test_curve_set_matches_python(self) -> None:
        py, cpp = self._parse()
        cpp_names = {c.name for c in cpp.curves}
        py_names = {c.name for c in py.curve_definitions}
        only_in_cpp = cpp_names - py_names
        only_in_python = py_names - cpp_names
        assert not only_in_cpp, f"C++ saw curves Python didn't: {only_in_cpp}"
        assert not only_in_python, (
            f"Python saw curves C++ didn't ({len(only_in_python)} total): "
            f"{sorted(only_in_python)[:20]}"
        )

    def test_every_curve_x_bins_param_matches_python(self) -> None:
        """For every overlapping curve, the x_bins_param (the
        constant array name backing the X axis) must match
        byte-for-byte. This is what generators and runtime consumers
        reference."""
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.curve_definitions}
        mismatches = []
        for cc in cpp.curves:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            if cc.x_bins_param != pc.x_bins_param:
                mismatches.append(
                    f"{cc.name}: cpp x_bins_param={cc.x_bins_param} "
                    f"vs py x_bins_param={pc.x_bins_param}"
                )
        assert not mismatches, "x_bins_param mismatches:\n" + "\n".join(mismatches[:20])

    def test_every_curve_y_bins_list_matches_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.curve_definitions}
        mismatches = []
        for cc in cpp.curves:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            cpp_params = [yb.param for yb in cc.y_bins_list]
            py_params = [yb.param for yb in pc.y_bins_list]
            if cpp_params != py_params:
                mismatches.append(
                    f"{cc.name}: cpp={cpp_params} vs py={py_params}"
                )
        assert not mismatches, "y_bins_list mismatches:\n" + "\n".join(mismatches[:20])

    def test_every_curve_y_bins_labels_match_python(self) -> None:
        """Multi-line curves have line labels — these need to match
        byte-for-byte too because the curve editor widget reads them
        for the legend."""
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.curve_definitions}
        mismatches = []
        for cc in cpp.curves:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            cpp_labels = [yb.label for yb in cc.y_bins_list]
            py_labels = [yb.label for yb in pc.y_bins_list]
            if cpp_labels != py_labels:
                mismatches.append(
                    f"{cc.name}: cpp={cpp_labels} vs py={py_labels}"
                )
        assert not mismatches, "y_bins label mismatches:\n" + "\n".join(mismatches[:20])

    def test_every_curve_x_channel_matches_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.curve_definitions}
        mismatches = []
        for cc in cpp.curves:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            if cc.x_channel != pc.x_channel:
                mismatches.append(
                    f"{cc.name}: cpp x_channel={cc.x_channel} "
                    f"vs py x_channel={pc.x_channel}"
                )
        assert not mismatches, "x_channel mismatches:\n" + "\n".join(mismatches[:20])

    def test_every_curve_titles_match_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.curve_definitions}
        mismatches = []
        for cc in cpp.curves:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            if cc.title != pc.title:
                mismatches.append(
                    f"{cc.name}: cpp title={cc.title!r} vs py title={pc.title!r}"
                )
        assert not mismatches, "title mismatches:\n" + "\n".join(mismatches[:20])

    def test_total_curve_count_is_substantial(self) -> None:
        """The production INI has 34+ curves per CLAUDE.md."""
        _, cpp = self._parse()
        assert len(cpp.curves) >= 30, (
            f"only {len(cpp.curves)} curves parsed — production INI "
            "should have at least 30"
        )
