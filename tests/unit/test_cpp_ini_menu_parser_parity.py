"""Python ↔ C++ parity harness for the tuner_core INI [Menu] parser.

Phase 14 fifth parser slice. Drives the same INI source through
both the Python `IniParser._parse_menus` and the C++
`tuner_core.parse_menu_*` and asserts the resulting catalogs match.
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


# ---------------------------------------------------------------------------
# Synthetic-fixture parity
# ---------------------------------------------------------------------------

_SYNTHETIC_INI = textwrap.dedent("""\
    [Menu]
    menu = "Tuning"
    subMenu = veTblTbl, "VE Table"
    subMenu = std_separator
    subMenu = ignTblTbl, "Ignition Table"
    subMenu = lambdaTbl, "Lambda Table", { LAMBDA }

    menu = "Setup"
    subMenu = engineSetup, "Engine Setup"
    subMenu = page2tbl, "Page 2 Table", 2
    """)


class TestSyntheticParity:
    def test_menu_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_menu_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        assert len(cpp.menus) == len(py.menus)

    def test_menu_titles_match_python(self) -> None:
        cpp = _tuner_core.parse_menu_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        assert [m.title for m in cpp.menus] == [m.title for m in py.menus]

    def test_item_targets_match_python(self) -> None:
        cpp = _tuner_core.parse_menu_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        for cm, pm in zip(cpp.menus, py.menus):
            assert [i.target for i in cm.items] == [i.target for i in pm.items]

    def test_item_labels_match_python(self) -> None:
        cpp = _tuner_core.parse_menu_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        for cm, pm in zip(cpp.menus, py.menus):
            assert [i.label for i in cm.items] == [i.label for i in pm.items]

    def test_item_pages_match_python(self) -> None:
        cpp = _tuner_core.parse_menu_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        for cm, pm in zip(cpp.menus, py.menus):
            assert [i.page for i in cm.items] == [i.page for i in pm.items]

    def test_item_visibility_expressions_match_python(self) -> None:
        cpp = _tuner_core.parse_menu_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        for cm, pm in zip(cpp.menus, py.menus):
            assert [i.visibility_expression for i in cm.items] == [
                i.visibility_expression for i in pm.items
            ]

    def test_std_separator_dropped_in_both(self) -> None:
        cpp = _tuner_core.parse_menu_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        for cm, pm in zip(cpp.menus, py.menus):
            assert "std_separator" not in [i.target for i in cm.items]
            assert "std_separator" not in [i.target for i in pm.items]


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
        cpp = _tuner_core.parse_menu_section_preprocessed(text, set())
        return py, cpp

    def test_menu_count_matches_python(self) -> None:
        py, cpp = self._parse()
        assert len(cpp.menus) == len(py.menus)

    def test_menu_titles_match_python(self) -> None:
        py, cpp = self._parse()
        cpp_titles = [m.title for m in cpp.menus]
        py_titles = [m.title for m in py.menus]
        assert cpp_titles == py_titles

    def test_item_targets_match_python_per_menu(self) -> None:
        """For every menu, the item target sequence must match
        byte-for-byte. This locks the navigation tree."""
        py, cpp = self._parse()
        mismatches = []
        for cm, pm in zip(cpp.menus, py.menus):
            cpp_targets = [i.target for i in cm.items]
            py_targets = [i.target for i in pm.items]
            if cpp_targets != py_targets:
                mismatches.append(
                    f"{cm.title}: cpp={cpp_targets[:5]}... vs py={py_targets[:5]}..."
                )
        assert not mismatches, "menu item target mismatches:\n" + "\n".join(mismatches)

    def test_item_labels_match_python_per_menu(self) -> None:
        py, cpp = self._parse()
        mismatches = []
        for cm, pm in zip(cpp.menus, py.menus):
            cpp_labels = [i.label for i in cm.items]
            py_labels = [i.label for i in pm.items]
            if cpp_labels != py_labels:
                mismatches.append(
                    f"{cm.title}: first diff at index {next((i for i, (a, b) in enumerate(zip(cpp_labels, py_labels)) if a != b), '?')}"
                )
        assert not mismatches, "menu item label mismatches:\n" + "\n".join(mismatches[:10])

    def test_item_visibility_expressions_match_python(self) -> None:
        """Visibility expressions are how features like `LAMBDA`-only
        pages are hidden from the navigator. Lock them down."""
        py, cpp = self._parse()
        mismatches = []
        for cm, pm in zip(cpp.menus, py.menus):
            for ci, pi in zip(cm.items, pm.items):
                if ci.visibility_expression != pi.visibility_expression:
                    mismatches.append(
                        f"{cm.title}/{ci.target}: cpp={ci.visibility_expression!r} "
                        f"vs py={pi.visibility_expression!r}"
                    )
        assert not mismatches, "visibility mismatches:\n" + "\n".join(mismatches[:10])

    def test_item_pages_match_python(self) -> None:
        py, cpp = self._parse()
        mismatches = []
        for cm, pm in zip(cpp.menus, py.menus):
            for ci, pi in zip(cm.items, pm.items):
                if ci.page != pi.page:
                    mismatches.append(
                        f"{cm.title}/{ci.target}: cpp page={ci.page} vs py page={pi.page}"
                    )
        assert not mismatches, "page mismatches:\n" + "\n".join(mismatches[:10])

    def test_total_menu_count_is_substantial(self) -> None:
        _, cpp = self._parse()
        assert len(cpp.menus) >= 5, (
            f"only {len(cpp.menus)} menus parsed — production INI should have several"
        )
