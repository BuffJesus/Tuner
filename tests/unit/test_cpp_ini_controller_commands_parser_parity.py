"""Python ↔ C++ parity harness for tuner_core INI [ControllerCommands] parser."""
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
    [ControllerCommands]
    cmdResetEcu = "E\\xAB\\xCD"
    cmdInjector1 = "E\\x02\\x01"
    cmdSparkA = "E\\x03\\x05"
    """)


class TestSyntheticParity:
    def test_command_count_matches_python(self) -> None:
        cpp = _tuner_core.parse_controller_commands_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        assert len(cpp.commands) == len(py.controller_commands)

    def test_command_payloads_match_python(self) -> None:
        cpp = _tuner_core.parse_controller_commands_section(_SYNTHETIC_INI)
        py = _python_parse(_SYNTHETIC_INI)
        py_by_name = {c.name: c for c in py.controller_commands}
        for cc in cpp.commands:
            pc = py_by_name[cc.name]
            assert bytes(cc.payload) == pc.payload


_PRODUCTION_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"


@pytest.mark.skipif(
    not _PRODUCTION_INI.exists(),
    reason="production INI fixture not available",
)
class TestProductionFixtureParity:
    def _parse(self):
        py = IniParser().parse(_PRODUCTION_INI)
        text = _PRODUCTION_INI.read_text(encoding="utf-8", errors="replace")
        cpp = _tuner_core.parse_controller_commands_section_preprocessed(
            text, set()
        )
        return py, cpp

    def test_command_count_matches_python(self) -> None:
        py, cpp = self._parse()
        assert len(cpp.commands) == len(py.controller_commands)

    def test_command_name_set_matches_python(self) -> None:
        py, cpp = self._parse()
        assert {c.name for c in cpp.commands} == {
            c.name for c in py.controller_commands
        }

    def test_command_payloads_match_python(self) -> None:
        py, cpp = self._parse()
        py_by_name = {c.name: c for c in py.controller_commands}
        mismatches = []
        for cc in cpp.commands:
            pc = py_by_name.get(cc.name)
            if pc is None:
                continue
            if bytes(cc.payload) != pc.payload:
                mismatches.append(
                    f"{cc.name}: cpp={bytes(cc.payload)!r} vs py={pc.payload!r}"
                )
        assert not mismatches, "\n".join(mismatches[:20])

    def test_command_count_is_substantial(self) -> None:
        _, cpp = self._parse()
        # Production INI has 70+ commands per CLAUDE.md.
        assert len(cpp.commands) >= 50
