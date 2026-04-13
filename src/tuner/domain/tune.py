from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class TuneValue:
    name: str
    value: str | float | list[float]
    units: str | None = None
    digits: int | None = None
    rows: int | None = None
    cols: int | None = None


@dataclass(slots=True)
class TuneFile:
    source_path: Path | None = None
    signature: str | None = None
    firmware_info: str | None = None
    file_format: str | None = None
    page_count: int | None = None
    constants: list[TuneValue] = field(default_factory=list)
    pc_variables: list[TuneValue] = field(default_factory=list)
