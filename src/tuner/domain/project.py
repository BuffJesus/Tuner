from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ConnectionProfile:
    name: str
    transport: str
    protocol: str | None = None
    host: str | None = None
    port: int | None = None
    serial_port: str | None = None
    baud_rate: int | None = None


@dataclass(slots=True)
class Project:
    name: str
    project_path: Path | None = None
    ecu_definition_path: Path | None = None
    tune_file_path: Path | None = None
    dashboards: list[str] = field(default_factory=list)
    connection_profiles: list[ConnectionProfile] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    active_settings: frozenset[str] = field(default_factory=frozenset)
