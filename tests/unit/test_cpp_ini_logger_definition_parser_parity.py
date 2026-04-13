"""Python ↔ C++ parity harness for tuner_core INI [LoggerDefinition] parser."""
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
    reason="tuner_core C++ extension not built — see cpp/README.md.",
)


def _python_parse(text: str):
    import tempfile
    with tempfile.NamedTemporaryFile(
        suffix=".ini", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(text)
        path = Path(f.name)
    try:
        return IniParser().parse(path)
    finally:
        path.unlink(missing_ok=True)


_SYNTHETIC_INI = textwrap.dedent("""\
    [LoggerDefinition]
    loggerDef = tooth, "Tooth Logger", tooth
    startCommand = "H"
    stopCommand = "h"
    dataReadCommand = "T$tsCanId"
    dataReadTimeout = 5000
    continuousRead = false
    dataLength = 1024
    recordDef = 0, 0, 4
    recordField = toothTime, "Tooth Time", 0, 32, 1.0, "us"
    loggerDef = comp, "Composite Logger", composite
    dataReadCommand = "C$tsCanId"
    dataLength = 256
    recordDef = 0, 0, 5
    recordField = refTime, "Ref Time", 8, 32, 1.0, "us"
    calcField = derived, "Derived", "expr"
    """)


class TestSyntheticParity:
    def test_logger_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_logger_definition_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        assert len(cpp.loggers) == len(py.logger_definitions)

    def test_logger_top_level_fields_match_python(self) -> None:
        cpp = _tuner_core.parse_logger_definition_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        py_by_name = {l.name: l for l in py.logger_definitions}
        for cl in cpp.loggers:
            pl = py_by_name[cl.name]
            assert cl.display_name == pl.display_name
            assert cl.kind == pl.kind
            assert cl.start_command == pl.start_command
            assert cl.stop_command == pl.stop_command
            assert bytes(cl.data_read_command) == pl.data_read_command
            assert cl.data_read_timeout_ms == pl.data_read_timeout_ms
            assert cl.continuous_read == pl.continuous_read
            assert cl.record_header_len == pl.record_header_len
            assert cl.record_footer_len == pl.record_footer_len
            assert cl.record_len == pl.record_len
            assert cl.record_count == pl.record_count

    def test_record_fields_match_python(self) -> None:
        cpp = _tuner_core.parse_logger_definition_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        py_by_name = {l.name: l for l in py.logger_definitions}
        for cl in cpp.loggers:
            pl = py_by_name[cl.name]
            assert len(cl.record_fields) == len(pl.record_fields)
            for cf, pf in zip(cl.record_fields, pl.record_fields):
                assert cf.name == pf.name
                assert cf.header == pf.header
                assert cf.start_bit == pf.start_bit
                assert cf.bit_count == pf.bit_count
                assert cf.scale == pytest.approx(pf.scale)
                assert cf.units == pf.units


_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


@pytest.mark.skipif(
    not _PRODUCTION_INI.exists(),
    reason="production INI fixture not available",
)
class TestProductionFixtureParity:
    def _parse(self):
        py = IniParser().parse(_PRODUCTION_INI)
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.parse_logger_definition_section_preprocessed(text, set())
        return py, cpp

    def test_logger_count_matches_python(self) -> None:
        py, cpp = self._parse()
        assert len(cpp.loggers) == len(py.logger_definitions)

    def test_logger_name_set_matches_python(self) -> None:
        py, cpp = self._parse()
        assert {l.name for l in cpp.loggers} == {
            l.name for l in py.logger_definitions
        }

    def test_logger_fields_match_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {l.name: l for l in py.logger_definitions}
        mismatches = []
        for cl in cpp.loggers:
            pl = py_by_name.get(cl.name)
            if pl is None:
                continue
            for field in (
                "display_name",
                "kind",
                "start_command",
                "stop_command",
                "data_read_timeout_ms",
                "continuous_read",
                "record_header_len",
                "record_footer_len",
                "record_len",
                "record_count",
            ):
                cv = getattr(cl, field)
                pv = getattr(pl, field)
                if cv != pv:
                    mismatches.append(f"{cl.name}.{field}: cpp={cv!r} vs py={pv!r}")
            if bytes(cl.data_read_command) != pl.data_read_command:
                mismatches.append(
                    f"{cl.name}.data_read_command: cpp={bytes(cl.data_read_command)!r} "
                    f"vs py={pl.data_read_command!r}"
                )
        assert not mismatches, "\n".join(mismatches[:20])

    def test_record_fields_match_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {l.name: l for l in py.logger_definitions}
        mismatches = []
        for cl in cpp.loggers:
            pl = py_by_name.get(cl.name)
            if pl is None:
                continue
            if len(cl.record_fields) != len(pl.record_fields):
                mismatches.append(
                    f"{cl.name}: cpp has {len(cl.record_fields)} fields, "
                    f"py has {len(pl.record_fields)}"
                )
                continue
            for i, (cf, pf) in enumerate(zip(cl.record_fields, pl.record_fields)):
                for fld in ("name", "header", "start_bit", "bit_count", "units"):
                    cv = getattr(cf, fld)
                    pv = getattr(pf, fld)
                    if cv != pv:
                        mismatches.append(
                            f"{cl.name}.fields[{i}].{fld}: cpp={cv!r} vs py={pv!r}"
                        )
                if cf.scale != pytest.approx(pf.scale):
                    mismatches.append(
                        f"{cl.name}.fields[{i}].scale: cpp={cf.scale} vs py={pf.scale}"
                    )
        assert not mismatches, "\n".join(mismatches[:20])
