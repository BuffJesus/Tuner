"""Python ↔ C++ parity harness for the tuner_core INI [GaugeConfigurations] parser.

Phase 14 sixth parser slice. Drives the same INI source through both
the Python `IniParser._parse_gauge_configurations` (via the public
`IniParser.parse` API) and the C++ `tuner_core.parse_gauge_configurations_*`
and asserts the resulting catalogs match.
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
    [GaugeConfigurations]
    gaugeCategory = "Engine"
    rpmGauge = rpm, "RPM", "rpm", 0, 8000, 0, 0, 6500, 7500, 0, 0
    mapGauge = map, "MAP", "kPa", 0, 250, 0, 0, 220, 240, 0, 0
    gaugeCategory = "Sensors"
    iatGauge = iat, "IAT", "C", -40, 215, -20, -10, 60, 80, 0, 0
    afrGauge = afr, "AFR", "", 8.0, 22.0, 0, 10, 16, 18, 2, 1
    """)


class TestSyntheticParity:
    def test_gauge_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_gauge_configurations_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        assert len(cpp.gauges) == len(py.gauge_configurations)

    def test_gauge_names_match_python(self) -> None:
        cpp = _tuner_core.parse_gauge_configurations_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        assert [g.name for g in cpp.gauges] == [g.name for g in py.gauge_configurations]

    def test_gauge_fields_match_python(self) -> None:
        cpp = _tuner_core.parse_gauge_configurations_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        py_by_name = {g.name: g for g in py.gauge_configurations}
        for cg in cpp.gauges:
            pg = py_by_name[cg.name]
            assert cg.channel == pg.channel
            assert cg.title == pg.title
            assert cg.units == pg.units
            assert cg.lo == pg.lo
            assert cg.hi == pg.hi
            assert cg.lo_danger == pg.lo_danger
            assert cg.lo_warn == pg.lo_warn
            assert cg.hi_warn == pg.hi_warn
            assert cg.hi_danger == pg.hi_danger
            assert cg.value_digits == pg.value_digits
            assert cg.label_digits == pg.label_digits
            assert cg.category == pg.category


_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


@pytest.mark.skipif(
    not _PRODUCTION_INI.exists(),
    reason="production INI fixture not available",
)
class TestProductionFixtureParity:
    def _parse(self):
        py = IniParser().parse(_PRODUCTION_INI)
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.parse_gauge_configurations_section_preprocessed(text, set())
        return py, cpp

    def test_gauge_count_matches_python(self) -> None:
        py, cpp = self._parse()
        assert len(cpp.gauges) == len(py.gauge_configurations)

    def test_gauge_name_set_matches_python(self) -> None:
        py, cpp = self._parse()
        cpp_names = {g.name for g in cpp.gauges}
        py_names = {g.name for g in py.gauge_configurations}
        assert cpp_names == py_names

    def test_gauge_fields_match_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {g.name: g for g in py.gauge_configurations}
        mismatches = []
        for cg in cpp.gauges:
            pg = py_by_name.get(cg.name)
            if pg is None:
                continue
            for field in (
                "channel", "title", "units", "lo", "hi",
                "lo_danger", "lo_warn", "hi_warn", "hi_danger",
                "value_digits", "label_digits", "category",
            ):
                cv = getattr(cg, field)
                pv = getattr(pg, field)
                if cv != pv:
                    mismatches.append(f"{cg.name}.{field}: cpp={cv!r} vs py={pv!r}")
        assert not mismatches, "gauge field mismatches:\n" + "\n".join(mismatches[:20])

    def test_total_gauge_count_is_substantial(self) -> None:
        _, cpp = self._parse()
        assert len(cpp.gauges) >= 50
