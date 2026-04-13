from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AppSettings:
    app_name: str = "tuner-py"
    organization_name: str = "Cornelio"
    data_dir: Path = field(default_factory=lambda: Path.cwd() / ".tuner-data")
    log_level: str = "INFO"
