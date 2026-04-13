from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class DataLogRecord:
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    values: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class DataLog:
    name: str
    records: list[DataLogRecord] = field(default_factory=list)
