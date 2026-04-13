from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

ParameterValue: TypeAlias = int | float | str | bool | list[float]


@dataclass(slots=True)
class ParameterUpdate:
    name: str
    value: ParameterValue
    staged: bool = True
