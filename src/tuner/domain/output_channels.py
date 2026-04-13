from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class OutputChannelValue:
    name: str
    value: float
    units: str | None = None


@dataclass(slots=True)
class OutputChannelSnapshot:
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    values: list[OutputChannelValue] = field(default_factory=list)

    def as_dict(self) -> dict[str, float]:
        return {item.name: item.value for item in self.values}
