"""Python ↔ C++ parity harness for the tuner_core INI [FrontPage] parser.

Phase 14 ninth parser slice. Drives the same INI source through both
the Python ``IniParser._parse_front_page`` (via the public ``IniParser.parse``
API) and the C++ ``tuner_core.parse_front_page_*`` functions and asserts
the resulting catalogs match.
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
    [FrontPage]
    gauge1 = rpmGauge
    gauge2 = mapGauge
    gauge3 = afrGauge
    gauge4 = cltGauge
    indicator = { sync }, "NoSync", "Sync", red, white, green, white
    indicator = { warmup }, "Cold", "Warm", blue, white, orange, white
    """)


class TestSyntheticParity:
    def test_gauge_list_matches_python(self) -> None:
        cpp = _tuner_core.parse_front_page_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        assert list(cpp.gauges) == list(py.front_page_gauges)

    def test_indicator_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_front_page_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        assert len(cpp.indicators) == len(py.front_page_indicators)

    def test_indicator_fields_match_python(self) -> None:
        cpp = _tuner_core.parse_front_page_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        for ci, pi in zip(cpp.indicators, py.front_page_indicators):
            assert ci.expression == pi.expression
            assert ci.off_label == pi.off_label
            assert ci.on_label == pi.on_label
            assert ci.off_bg == pi.off_bg
            assert ci.off_fg == pi.off_fg
            assert ci.on_bg == pi.on_bg
            assert ci.on_fg == pi.on_fg


_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


@pytest.mark.skipif(
    not _PRODUCTION_INI.exists(),
    reason="production INI fixture not available",
)
class TestProductionFixtureParity:
    def _parse(self):
        py = IniParser().parse(_PRODUCTION_INI)
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.parse_front_page_section_preprocessed(text, set())
        return py, cpp

    def test_gauge_list_matches_python(self) -> None:
        py, cpp = self._parse()
        assert list(cpp.gauges) == list(py.front_page_gauges)

    def test_indicator_count_matches_python(self) -> None:
        py, cpp = self._parse()
        assert len(cpp.indicators) == len(py.front_page_indicators)

    def test_indicator_fields_match_python(self) -> None:
        py, cpp = self._parse()
        mismatches = []
        for i, (ci, pi) in enumerate(
            zip(cpp.indicators, py.front_page_indicators)
        ):
            for field in (
                "expression",
                "off_label",
                "on_label",
                "off_bg",
                "off_fg",
                "on_bg",
                "on_fg",
            ):
                cv = getattr(ci, field)
                pv = getattr(pi, field)
                if cv != pv:
                    mismatches.append(
                        f"indicator[{i}].{field}: cpp={cv!r} vs py={pv!r}"
                    )
        assert not mismatches, "front-page mismatches:\n" + "\n".join(
            mismatches[:20]
        )

    def test_indicator_count_is_substantial(self) -> None:
        _, cpp = self._parse()
        # Production INI has 40+ indicator expressions per CLAUDE.md.
        assert len(cpp.indicators) >= 30
