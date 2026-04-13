from __future__ import annotations

from pathlib import Path

from tuner.domain.tune import TuneFile
from tuner.parsers.msq_parser import MsqParser


class TuneFileService:
    def __init__(self, parser: MsqParser | None = None) -> None:
        self.parser = parser or MsqParser()

    def open_tune(self, path: Path) -> TuneFile:
        return self.parser.parse(path)
