from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OutputCondition:
    expression: str
    description: str | None = None


@dataclass(slots=True)
class OutputPortConfig:
    name: str
    enabled: bool = True
    power_on_value: int | float | None = None
    active_value: int | float | None = None
    active_delay_ms: int | None = None
    inactive_delay_ms: int | None = None
    conditions: list[OutputCondition] = field(default_factory=list)
