"""Python ↔ C++ parity harness for the tuner_core INI defines parser.

Future Phase 13 fifth slice. Drives the same INI source through both
the Python `IniParser._collect_defines` (via the public `IniParser.parse`
which collects defines internally) and the C++ `tuner_core.collect_defines`,
then asserts the resulting macro maps match. Also exercises the bit-option
expansion path on the production INI: with defines wired in, the C++
`bits` scalar option lists must equal the Python ones byte-for-byte.

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


def _python_collect_defines(text: str) -> dict[str, list[str]]:
    """Run the same `_collect_defines` Python helper that `IniParser.parse`
    uses internally. We need to call it directly because it's a private
    method on the parser — wrap a temp file."""
    import tempfile
    with tempfile.NamedTemporaryFile(
        suffix=".ini", delete=False, mode="w", encoding="utf-8",
    ) as f:
        f.write(text)
        path = Path(f.name)
    try:
        parser = IniParser()
        # Force the line cache to populate (matches the production code path).
        parser.parse(path)
        return parser._collect_defines(path)
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Synthetic-fixture parity
# ---------------------------------------------------------------------------

class TestSyntheticDefinesParity:
    def test_single_define_matches_python(self) -> None:
        text = '#define injectorTypes = "Off","Throttle Body","Multi-port"\n'
        cpp = _tuner_core.collect_defines(text)
        py = _python_collect_defines(text)
        assert cpp == py

    def test_multiple_defines_match_python(self) -> None:
        text = textwrap.dedent("""\
            #define a = "x","y","z"
            #define b = "p","q"
            #define c = "single"
            """)
        cpp = _tuner_core.collect_defines(text)
        py = _python_collect_defines(text)
        assert cpp == py

    def test_define_in_mixed_section_matches_python(self) -> None:
        text = textwrap.dedent("""\
            ; comment
            [Constants]
            page = 1
            scalar1 = scalar, U08, 0, "", 1, 0, 0, 255, 0
            #define mid = "a","b"
            scalar2 = scalar, U08, 1, "", 1, 0, 0, 255, 0
            """)
        cpp = _tuner_core.collect_defines(text)
        py = _python_collect_defines(text)
        assert cpp == py

    def test_no_equals_define_dropped_in_both(self) -> None:
        text = '#define noEquals\n#define real = "x"\n'
        cpp = _tuner_core.collect_defines(text)
        py = _python_collect_defines(text)
        assert cpp == py
        assert "noEquals" not in cpp


# ---------------------------------------------------------------------------
# Real production INI parity
# ---------------------------------------------------------------------------

_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


@pytest.mark.skipif(
    not _PRODUCTION_INI.exists(),
    reason="production INI fixture not available",
)
class TestProductionDefinesParity:
    def test_define_set_matches_python(self) -> None:
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.collect_defines(text)
        py = _python_collect_defines(text)
        cpp_names = set(cpp.keys())
        py_names = set(py.keys())
        only_in_cpp = cpp_names - py_names
        only_in_python = py_names - cpp_names
        assert not only_in_cpp, f"C++ saw defines Python didn't: {only_in_cpp}"
        assert not only_in_python, (
            f"Python saw defines C++ didn't ({len(only_in_python)} total): "
            f"{sorted(only_in_python)[:20]}"
        )

    def test_every_define_token_list_matches_python(self) -> None:
        """For every define both implementations agree exists, the
        token list must be byte-identical."""
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.collect_defines(text)
        py = _python_collect_defines(text)
        mismatches = []
        for name in cpp:
            if name in py and cpp[name] != py[name]:
                mismatches.append(
                    f"{name}: cpp={cpp[name]!r} vs py={py[name]!r}"
                )
        assert not mismatches, "Token list mismatches:\n" + "\n".join(mismatches[:10])

    def test_total_define_count_is_substantial(self) -> None:
        """The production INI has a meaningful number of defines.
        Sanity check that we're not silently dropping a whole class."""
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.collect_defines(text)
        assert len(cpp) >= 5, f"only {len(cpp)} defines parsed"


# ---------------------------------------------------------------------------
# expand_options parity
# ---------------------------------------------------------------------------

class TestExpandOptionsParity:
    def test_simple_macro_expansion(self) -> None:
        defines = {"x": ["a", "b", "c"]}
        cpp = _tuner_core.expand_options(["$x"], defines)
        # Python equivalent
        from tuner.parsers.ini_parser import IniParser
        py = IniParser._expand_options(["$x"], defines)
        assert cpp == py
        assert cpp == ["a", "b", "c"]

    def test_unresolved_macro_dropped(self) -> None:
        from tuner.parsers.ini_parser import IniParser
        cpp = _tuner_core.expand_options(["$missing", "real"], {})
        py = IniParser._expand_options(["$missing", "real"], {})
        assert cpp == py == ["real"]

    def test_brace_expression_dropped(self) -> None:
        from tuner.parsers.ini_parser import IniParser
        cpp = _tuner_core.expand_options(["real", "{cond}", "more"], {})
        py = IniParser._expand_options(["real", "{cond}", "more"], {})
        assert cpp == py == ["real", "more"]

    def test_nested_macro_expansion(self) -> None:
        from tuner.parsers.ini_parser import IniParser
        defines = {
            "outer": ["$inner", "tail"],
            "inner": ["a", "b"],
        }
        cpp = _tuner_core.expand_options(["$outer"], defines)
        py = IniParser._expand_options(["$outer"], defines)
        assert cpp == py == ["a", "b", "tail"]


# ---------------------------------------------------------------------------
# Composed pipeline: defines wired into bit-options expansion
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _PRODUCTION_INI.exists(),
    reason="production INI fixture not available",
)
class TestBitOptionExpansionParity:
    """The Phase 13 fifth slice composition: with defines wired into
    parse_constants_section_preprocessed, the C++ bit-option labels
    on the production INI must match the Python labels byte-for-byte.
    Before this slice, the C++ side stored raw `$macroName` strings
    in the options list because there was no expansion path.
    """

    def test_bit_option_labels_match_python(self) -> None:
        py = IniParser().parse(_PRODUCTION_INI)
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.parse_constants_section_preprocessed(text, set())

        py_by_name = {s.name: s for s in py.scalars if s.bit_offset is not None}
        cpp_by_name = {s.name: s for s in cpp.scalars if s.bit_offset is not None}

        # Spot check at least one name overlap so we know we're actually
        # comparing something.
        overlap = set(cpp_by_name) & set(py_by_name)
        assert len(overlap) >= 5, (
            f"only {len(overlap)} bit scalars overlapped between C++ and Python — "
            "expected the production INI to have many"
        )

        mismatches = []
        for name in sorted(overlap):
            cpp_options = list(cpp_by_name[name].options)
            py_options = [opt.label for opt in py_by_name[name].options]
            if cpp_options != py_options:
                mismatches.append(
                    f"{name}:\n  cpp = {cpp_options}\n  py  = {py_options}"
                )
        assert not mismatches, (
            "Bit-option label mismatches after defines expansion:\n" +
            "\n".join(mismatches[:10])
        )
