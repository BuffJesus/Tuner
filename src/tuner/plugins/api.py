from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from PySide6.QtWidgets import QWidget


@dataclass(slots=True)
class AppContext:
    app_name: str
    capabilities: set[str] = field(default_factory=set)


class AppPlugin(Protocol):
    id: str
    display_name: str
    version: str

    def initialize(self, app_context: AppContext) -> None: ...

    def create_panel(self) -> QWidget | None: ...

    def shutdown(self) -> None: ...
