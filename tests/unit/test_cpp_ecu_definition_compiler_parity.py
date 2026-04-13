"""Python ↔ C++ parity harness for the tuner_core EcuDefinition compiler.

The compiler is the orchestration seam: it takes an INI file path, runs
the slice-3 preprocessor, and dispatches the surviving lines through
every leaf section parser. This test confirms that orchestration produces
the same per-section catalog sizes as the Python `IniParser.parse()` flow
on the production INI.

Per-section *content* parity is already covered by the existing
`test_cpp_ini_*_parser_parity.py` files; this harness is the
end-to-end glue check.
"""
from __future__ import annotations

import importlib
import sys
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
_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


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

pytestmark = [
    pytest.mark.skipif(
        _tuner_core is None,
        reason="tuner_core C++ extension not built — see cpp/README.md.",
    ),
    pytest.mark.skipif(
        not _PRODUCTION_INI.exists(),
        reason="production INI fixture not available",
    ),
]


@pytest.fixture(scope="module")
def parsed():
    py = IniParser().parse(_PRODUCTION_INI)
    cpp = _tuner_core.compile_ecu_definition_file(_PRODUCTION_INI, set())
    return py, cpp


def test_constants_section_count_matches(parsed) -> None:
    py, cpp = parsed
    # Python `EcuDefinition.scalars` includes entries compiled from
    # other sections (`[Menu]`, `[SettingGroups]`, …), so it's a strict
    # superset of the leaf [Constants] catalog. Filter to entries that
    # actually live in [Constants] (page + offset present).
    #
    # Sub-slice 120: the C++ aggregator merges [PcVariables] into
    # `constants.scalars` / `constants.arrays` to match Python's
    # behaviour of appending into the same `definition.scalars` /
    # `definition.tables` lists. PC variables land with page=None +
    # offset=None, so the filtered count above doesn't include them —
    # compute the PC-variables subset explicitly via the standalone
    # Python leaf and add it to the expected total.
    from tuner.domain.ecu_definition import EcuDefinition
    from tuner.parsers.common import preprocess_ini_lines
    from tuner.parsers.ini_parser import IniParser

    def _pc_vars_counts():
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="ignore")
        parser = IniParser()
        parser._lines = preprocess_ini_lines(text.splitlines())
        defines = parser._collect_defines(_PRODUCTION_INI)
        definition = EcuDefinition(name="test")
        parser._parse_pc_variables(_PRODUCTION_INI, definition, defines)
        return len(definition.scalars), len(definition.tables)

    pc_vars_scalars, pc_vars_arrays = _pc_vars_counts()

    py_constants_scalars = [
        s for s in py.scalars if s.page is not None and s.offset is not None
    ]
    assert len(cpp.constants.scalars) == len(py_constants_scalars) + pc_vars_scalars
    py_constants_arrays = [
        t for t in py.tables if t.page is not None and t.offset is not None
    ]
    assert len(cpp.constants.arrays) == len(py_constants_arrays) + pc_vars_arrays


def test_output_channels_count_matches(parsed) -> None:
    py, cpp = parsed
    assert len(cpp.output_channels.channels) == len(py.output_channels)


def test_table_editors_count_matches(parsed) -> None:
    py, cpp = parsed
    assert len(cpp.table_editors.editors) == len(py.table_editors)


def test_curve_editors_count_matches(parsed) -> None:
    py, cpp = parsed
    assert len(cpp.curve_editors.curves) == len(py.curve_definitions)


def test_menus_present(parsed) -> None:
    _, cpp = parsed
    # Menu coverage is harder to compare to the Python side because the
    # Python parser exposes only the compiled menu structure, not the
    # raw menu list. Settle for a "non-empty" smoke check — the
    # dedicated menu parity test owns the field-level claim.
    assert len(cpp.menus.menus) > 0


def test_gauge_configurations_count_matches(parsed) -> None:
    py, cpp = parsed
    assert len(cpp.gauge_configurations.gauges) == len(py.gauge_configurations)


def test_front_page_gauges_match(parsed) -> None:
    py, cpp = parsed
    assert list(cpp.front_page.gauges) == list(py.front_page_gauges)
    assert len(cpp.front_page.indicators) == len(py.front_page_indicators)


def test_logger_definitions_count_matches(parsed) -> None:
    py, cpp = parsed
    assert len(cpp.logger_definitions.loggers) == len(py.logger_definitions)


def test_controller_commands_count_matches(parsed) -> None:
    py, cpp = parsed
    assert len(cpp.controller_commands.commands) == len(py.controller_commands)


def test_setting_groups_parity(parsed) -> None:
    py, cpp = parsed
    assert len(cpp.setting_groups.groups) == len(py.setting_groups)
    for py_group, cpp_group in zip(py.setting_groups, cpp.setting_groups.groups):
        assert py_group.symbol == cpp_group.symbol
        assert (py_group.label or "") == cpp_group.label
        assert len(py_group.options) == len(cpp_group.options)
        for py_opt, cpp_opt in zip(py_group.options, cpp_group.options):
            assert py_opt.symbol == cpp_opt.symbol
            assert (py_opt.label or "") == cpp_opt.label


def test_setting_context_help_parity(parsed) -> None:
    py, cpp = parsed
    py_items = {k: (v or "") for k, v in py.setting_help.items()}
    cpp_items = dict(cpp.setting_context_help.help_by_name)
    assert py_items == cpp_items


def test_constants_extensions_parity(parsed) -> None:
    py, cpp = parsed
    assert set(py.requires_power_cycle) == set(cpp.constants_extensions.requires_power_cycle)


def test_tools_parity(parsed) -> None:
    py, cpp = parsed
    assert len(py.tool_declarations) == len(cpp.tools.declarations)
    for py_decl, cpp_decl in zip(py.tool_declarations, cpp.tools.declarations):
        assert py_decl.tool_id == cpp_decl.tool_id
        assert (py_decl.label or "") == cpp_decl.label
        assert (py_decl.target_table_id or None) == (
            cpp_decl.target_table_id if cpp_decl.target_table_id is not None else None)


def test_reference_tables_parity(parsed) -> None:
    py, cpp = parsed
    assert len(py.reference_tables) == len(cpp.reference_tables.tables)
    for py_t, cpp_t in zip(py.reference_tables, cpp.reference_tables.tables):
        assert py_t.table_id == cpp_t.table_id
        assert (py_t.label or "") == cpp_t.label
        assert (py_t.topic_help or None) == (cpp_t.topic_help or None)
        assert (py_t.table_identifier or None) == (cpp_t.table_identifier or None)
        assert (py_t.solutions_label or None) == (cpp_t.solutions_label or None)
        assert len(py_t.solutions) == len(cpp_t.solutions)
        for py_sol, cpp_sol in zip(py_t.solutions, cpp_t.solutions):
            assert py_sol.label == cpp_sol.label
            assert (py_sol.expression or None) == (cpp_sol.expression or None)


def test_text_and_file_overloads_agree() -> None:
    text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
    from_text = _tuner_core.compile_ecu_definition_text(text, set())
    from_file = _tuner_core.compile_ecu_definition_file(_PRODUCTION_INI, set())
    assert len(from_text.constants.scalars) == len(from_file.constants.scalars)
    assert len(from_text.output_channels.channels) == len(
        from_file.output_channels.channels
    )
    assert len(from_text.table_editors.editors) == len(
        from_file.table_editors.editors
    )
