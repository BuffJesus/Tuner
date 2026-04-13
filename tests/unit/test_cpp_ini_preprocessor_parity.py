"""Python ↔ C++ parity harness for the tuner_core INI preprocessor.

Future Phase 13 third slice. Drives the same INI source fixtures
through both `tuner.parsers.common.preprocess_ini_lines` and the C++
`tuner_core.preprocess_ini_lines` and asserts byte-identical output.

Like the MSQ and NativeFormat parity harnesses, the C++ extension is
**optional**: every test in this file is marked as skipped when the
extension isn't built. Build instructions live in `cpp/README.md`.
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from tuner.parsers.common import preprocess_ini_lines


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
# Fixture catalog — parametrize against the same shapes the Python suite
# in test_ini_preprocessor.py uses, plus a few real-world variants.
# ---------------------------------------------------------------------------

_FIXTURES: list[tuple[str, str, frozenset[str]]] = [
    (
        "if_false_skips_block",
        textwrap.dedent("""\
            before
            #if MISSING_SYMBOL
            inside_if
            #endif
            after
            """),
        frozenset(),
    ),
    (
        "if_true_includes_block",
        textwrap.dedent("""\
            #if MY_FLAG
            inside_if
            #endif
            """),
        frozenset({"MY_FLAG"}),
    ),
    (
        "else_taken_when_if_false",
        textwrap.dedent("""\
            #if MISSING
            if_branch
            #else
            else_branch
            #endif
            """),
        frozenset(),
    ),
    (
        "file_set_default",
        textwrap.dedent("""\
            #set LAMBDA
            #if LAMBDA
            lambda_branch
            #endif
            """),
        frozenset(),
    ),
    (
        "user_setting_added_to_file_default",
        textwrap.dedent("""\
            #set LAMBDA
            #if MCU_TEENSY
            teensy_branch
            #endif
            #if LAMBDA
            lambda_branch
            #endif
            """),
        frozenset({"MCU_TEENSY"}),
    ),
    (
        "nested_if_both_active",
        textwrap.dedent("""\
            #if A
            outer
            #if B
            inner
            #endif
            #endif
            """),
        frozenset({"A", "B"}),
    ),
    (
        "nested_inner_dropped_when_only_outer",
        textwrap.dedent("""\
            #if A
            outer
            #if B
            inner
            #endif
            tail
            #endif
            """),
        frozenset({"A"}),
    ),
    (
        "set_unset_consumed_not_emitted",
        textwrap.dedent("""\
            #set FOO
            #unset BAR
            real_line
            """),
        frozenset(),
    ),
    (
        "comment_in_active_branch_kept",
        textwrap.dedent("""\
            #if FLAG
            # this is a comment
            real
            #endif
            """),
        frozenset({"FLAG"}),
    ),
    (
        "comment_in_inactive_branch_dropped",
        textwrap.dedent("""\
            #if FLAG
            # this is a comment
            real
            #endif
            """),
        frozenset(),
    ),
    (
        "empty_lines_preserved_in_active_branch",
        "before\n\nafter\n",
        frozenset(),
    ),
    (
        "crlf_input_normalized",
        "foo\r\nbar\r\n",
        frozenset(),
    ),
    (
        "complex_lambda_afr_real_world_subset",
        textwrap.dedent("""\
            ; INI snippet mirroring real Speeduino fragments
            #set LAMBDA
            [Constants]
            #if LAMBDA
            lambdaUnits = "lambda"
            #else
            lambdaUnits = "AFR"
            #endif
            #if MCU_TEENSY
            blockingFactor = 512
            #else
            blockingFactor = 251
            #endif
            """),
        frozenset({"MCU_TEENSY"}),
    ),
]


@pytest.mark.parametrize(
    "name,source,active_settings",
    _FIXTURES,
    ids=[f[0] for f in _FIXTURES],
)
def test_python_and_cpp_preprocess_to_byte_equal_output(
    name: str, source: str, active_settings: frozenset[str],
) -> None:
    """Core parity claim: every fixture produces byte-identical output
    from both implementations."""
    py_lines = preprocess_ini_lines(source.splitlines(), active_settings=active_settings)
    cpp_lines = _tuner_core.preprocess_ini_text(source, set(active_settings))
    assert cpp_lines == py_lines, (
        f"parity mismatch for fixture {name!r}:\n"
        f"  python: {py_lines}\n"
        f"  cpp:    {cpp_lines}"
    )


def test_lines_overload_matches_text_overload() -> None:
    """preprocess_ini_lines and preprocess_ini_text are equivalent for
    sources with no CR / no trailing newline weirdness."""
    src = "before\n#if FLAG\ninside\n#endif\nafter\n"
    via_text = _tuner_core.preprocess_ini_text(src, {"FLAG"})
    via_lines = _tuner_core.preprocess_ini_lines(src.splitlines(), {"FLAG"})
    assert via_text == via_lines


def test_default_active_settings_is_empty_set() -> None:
    """The default-arg path matches passing an explicit empty set."""
    src = "#if MISSING\ninside\n#endif\nreal\n"
    with_default = _tuner_core.preprocess_ini_text(src)
    with_empty = _tuner_core.preprocess_ini_text(src, set())
    assert with_default == with_empty


# ---------------------------------------------------------------------------
# End-to-end parity against the existing Python preprocessor test suite —
# every fixture from test_ini_preprocessor.py runs through both implementations
# automatically because the harness re-uses the same source strings.
# ---------------------------------------------------------------------------


def test_real_speeduino_ini_subset_round_trips_through_cpp() -> None:
    """Use a real-shaped INI fragment that exercises the most common
    constructs. Both implementations should agree on the output."""
    source = textwrap.dedent("""\
        ; speeduino INI subset
        #set LAMBDA
        #set HEAVYDUTY

        [VersionInfo]
        signature = "speeduino 202501-T41"

        [Constants]
        #if LAMBDA
        afrSource = lambda
        #else
        afrSource = afr
        #endif

        #if HEAVYDUTY
        #if MCU_TEENSY
        chunkSize = 512
        #else
        chunkSize = 256
        #endif
        #endif
        """)
    py = preprocess_ini_lines(source.splitlines(), active_settings=frozenset({"MCU_TEENSY"}))
    cpp = _tuner_core.preprocess_ini_text(source, {"MCU_TEENSY"})
    assert cpp == py
