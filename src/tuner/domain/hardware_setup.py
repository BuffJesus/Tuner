from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HardwareIssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True, frozen=True)
class HardwareSetupIssue:
    severity: HardwareIssueSeverity
    message: str
    parameter_name: str | None = None  # None = cross-field / page-level issue
    detail: str | None = None
