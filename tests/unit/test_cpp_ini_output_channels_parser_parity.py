"""Python ↔ C++ parity harness for the tuner_core INI [OutputChannels] parser.

Phase 14 first parser slice. Drives the same INI source through both
the Python `IniParser._parse_output_channels` (via the public
`IniParser.parse` API) and the C++ `tuner_core.parse_output_channels_*`
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
    """Parse via the public IniParser API. Writes to a temp file because
    the parser is path-driven."""
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
    [OutputChannels]
    rpm = scalar, U16, 14, "RPM", 1.0, 0.0, 0.0, 8000.0, 0
    map = scalar, U16, 4, "kPa", 1.0, 0.0, 0.0, 511.0, 0
    iat = scalar, U08, 6, "C", 1.0, -40.0, -40.0, 215.0, 0
    engine = bits, U08, 2, [0:0], "Off", "On"
    boardHasRTC = array, U08, [4]
    defaultValue = boardHasRTC, 1 0 1 0
    """)


_SYNTHETIC_FORMULA_INI = textwrap.dedent("""\
    [OutputChannels]
    rpm      = scalar, U16, 14, "RPM", 1.0, 0.0, 0.0, 8000.0, 0
    coolant  = { coolantRaw - 40 }
    throttle = { tps }, "%"
    map_psi  = { (map - baro) * 0.145038 }, "PSI", 2
    lambda   = { afr / stoich }
    """)


class TestSyntheticParity:
    def test_scalar_set_matches_python(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        cpp_names = {c.name for c in cpp.channels}
        py_names = {c.name for c in py.output_channel_definitions}
        assert cpp_names == py_names

    def test_scalar_offsets_and_data_types_match_python(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        py_by_name = {c.name: c for c in py.output_channel_definitions}
        for cc in cpp.channels:
            pc = py_by_name[cc.name]
            assert cc.offset == pc.offset, f"offset mismatch on {cc.name}"
            assert cc.data_type == pc.data_type, f"type mismatch on {cc.name}"
            assert cc.units == pc.units, f"units mismatch on {cc.name}"

    def test_array_default_values_match_python(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        # Python stores arrays in `output_channel_arrays`
        assert "boardHasRTC" in cpp.arrays
        assert "boardHasRTC" in py.output_channel_arrays
        assert cpp.arrays["boardHasRTC"] == py.output_channel_arrays["boardHasRTC"]

    def test_bit_field_options_match_python(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_INI, {})
        py = _python_parse(_SYNTHETIC_INI)
        cpp_engine = next(c for c in cpp.channels if c.name == "engine")
        py_engine = next(c for c in py.output_channel_definitions if c.name == "engine")
        assert cpp_engine.bit_offset == py_engine.bit_offset
        assert cpp_engine.bit_length == py_engine.bit_length
        cpp_labels = list(cpp_engine.options)
        py_labels = [opt.label for opt in py_engine.options]
        assert cpp_labels == py_labels


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
        cpp = _tuner_core.parse_output_channels_section_preprocessed(text, set())
        return py, cpp

    def test_output_channel_set_matches_python(self) -> None:
        py, cpp = self._parse()
        cpp_names = {c.name for c in cpp.channels}
        py_names = {c.name for c in py.output_channel_definitions}
        only_in_cpp = cpp_names - py_names
        only_in_python = py_names - cpp_names
        assert not only_in_cpp, f"C++ saw channels Python didn't: {only_in_cpp}"
        assert not only_in_python, (
            f"Python saw channels C++ didn't ({len(only_in_python)} total): "
            f"{sorted(only_in_python)[:20]}"
        )

    def test_every_channel_offset_matches_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.output_channel_definitions}
        mismatches = []
        for cc in cpp.channels:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            if cc.offset != pc.offset:
                mismatches.append(
                    f"{cc.name}: cpp offset={cc.offset} vs py offset={pc.offset}"
                )
        assert not mismatches, "Offset mismatches:\n" + "\n".join(mismatches[:20])

    def test_every_channel_data_type_matches_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.output_channel_definitions}
        mismatches = []
        for cc in cpp.channels:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            if cc.data_type != pc.data_type:
                mismatches.append(
                    f"{cc.name}: cpp={cc.data_type} vs py={pc.data_type}"
                )
        assert not mismatches, "Data-type mismatches:\n" + "\n".join(mismatches[:20])

    def test_array_default_values_match_python(self) -> None:
        """The production INI uses `defaultValue` lines for several
        array-typed output channels (e.g. `boardHasRTC`,
        `pinLayouts` etc.). The C++ parser must populate the same map."""
        py, cpp = self._parse()
        # Every array Python recognized should also be in cpp.arrays
        # with byte-identical values.
        for name, py_values in py.output_channel_arrays.items():
            assert name in cpp.arrays, f"missing array {name}"
            assert cpp.arrays[name] == py_values, (
                f"array {name}: cpp={cpp.arrays[name]} vs py={py_values}"
            )

    def test_total_channel_count_is_substantial(self) -> None:
        """Sanity check that we're parsing the bulk of the production
        INI's output channels, not just a handful."""
        _, cpp = self._parse()
        assert len(cpp.channels) > 100, (
            f"only {len(cpp.channels)} channels parsed — production INI "
            "has hundreds"
        )

    # -------------------------------------------------------------------
    # Formula (virtual / computed) output channel parity — Phase 14 G4
    # -------------------------------------------------------------------

    def test_formula_channel_names_match_python(self) -> None:
        py, cpp = self._parse()
        cpp_names = [c.name for c in cpp.formula_channels]
        py_names = [c.name for c in py.formula_output_channels]
        assert cpp_names == py_names, (
            "formula channel name sequence diverged — "
            f"cpp_only={set(cpp_names) - set(py_names)} "
            f"py_only={set(py_names) - set(cpp_names)}"
        )

    def test_formula_channel_expressions_match_python_byte_identical(self) -> None:
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.formula_output_channels}
        mismatches = []
        for cc in cpp.formula_channels:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            if cc.formula_expression != pc.formula_expression:
                mismatches.append(
                    f"{cc.name}: cpp={cc.formula_expression!r} "
                    f"vs py={pc.formula_expression!r}"
                )
        assert not mismatches, (
            "Formula expression mismatches:\n" + "\n".join(mismatches[:20])
        )

    def test_formula_channel_units_match_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.formula_output_channels}
        mismatches = []
        for cc in cpp.formula_channels:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            if cc.units != pc.units:
                mismatches.append(
                    f"{cc.name}: cpp={cc.units!r} vs py={pc.units!r}"
                )
        assert not mismatches, (
            "Formula channel units mismatches:\n" + "\n".join(mismatches[:20])
        )

    def test_formula_channel_count_is_substantial(self) -> None:
        _, cpp = self._parse()
        # Production INI ships dozens of computed channels (temperatures,
        # pressure conversions, timing derivatives, lambda, etc.).
        assert len(cpp.formula_channels) >= 30, (
            f"only {len(cpp.formula_channels)} formula channels parsed"
        )

    def test_formula_channel_core_names_present(self) -> None:
        _, cpp = self._parse()
        names = {c.name for c in cpp.formula_channels}
        expected = {
            "coolant", "iat", "map_psi", "map_bar", "lambda",
            "throttle", "dutyCycle", "boostCutOut",
        }
        missing = expected - names
        assert not missing, f"C++ parser missing core formula channels: {missing}"


# ---------------------------------------------------------------------------
# Synthetic formula-channel parity
# ---------------------------------------------------------------------------

class TestSyntheticFormulaParity:
    def test_formula_channel_names_match_python(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_FORMULA_INI, {})
        py = _python_parse(_SYNTHETIC_FORMULA_INI)
        assert [c.name for c in cpp.formula_channels] == [
            c.name for c in py.formula_output_channels
        ]

    def test_formula_channel_expressions_match_python(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_FORMULA_INI, {})
        py = _python_parse(_SYNTHETIC_FORMULA_INI)
        py_by_name = {c.name: c for c in py.formula_output_channels}
        for cc in cpp.formula_channels:
            assert cc.formula_expression == py_by_name[cc.name].formula_expression

    def test_formula_channel_units_match_python(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_FORMULA_INI, {})
        py = _python_parse(_SYNTHETIC_FORMULA_INI)
        py_by_name = {c.name: c for c in py.formula_output_channels}
        for cc in cpp.formula_channels:
            assert cc.units == py_by_name[cc.name].units

    def test_formula_channel_digits_match_python(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_FORMULA_INI, {})
        py = _python_parse(_SYNTHETIC_FORMULA_INI)
        py_by_name = {c.name: c for c in py.formula_output_channels}
        for cc in cpp.formula_channels:
            assert cc.digits == py_by_name[cc.name].digits

    def test_scalar_and_formula_channels_do_not_cross_contaminate(self) -> None:
        cpp = _tuner_core.parse_output_channels_section(_SYNTHETIC_FORMULA_INI, {})
        scalar_names = {c.name for c in cpp.channels}
        formula_names = {c.name for c in cpp.formula_channels}
        assert scalar_names == {"rpm"}
        assert formula_names == {"coolant", "throttle", "map_psi", "lambda"}
        assert not (scalar_names & formula_names)
