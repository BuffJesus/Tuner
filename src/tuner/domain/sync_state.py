from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SyncMismatchKind(str, Enum):
    SIGNATURE_MISMATCH = "signature_mismatch"
    PAGE_SIZE_MISMATCH = "page_size_mismatch"
    ECU_VS_TUNE = "ecu_vs_tune"
    STALE_STAGED = "stale_staged"


@dataclass(slots=True, frozen=True)
class SyncMismatch:
    kind: SyncMismatchKind
    detail: str


@dataclass(slots=True, frozen=True)
class SyncState:
    mismatches: tuple[SyncMismatch, ...]
    has_ecu_ram: bool
    connection_state: str  # SessionState value string

    @property
    def is_clean(self) -> bool:
        return not self.mismatches
