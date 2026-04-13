from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TuneTable:
    name: str
    x_axis: list[float] = field(default_factory=list)
    y_axis: list[float] = field(default_factory=list)
    values: list[list[float]] = field(default_factory=list)
