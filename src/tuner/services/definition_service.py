from __future__ import annotations

from pathlib import Path

from tuner.domain.ecu_definition import EcuDefinition
from tuner.parsers.ini_parser import IniParser


class DefinitionService:
    def __init__(self, parser: IniParser | None = None) -> None:
        self.parser = parser or IniParser()

    def open_definition(
        self,
        path: Path,
        active_settings: frozenset[str] = frozenset(),
    ) -> EcuDefinition:
        return self.parser.parse(path, active_settings=active_settings)
