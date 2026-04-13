"""Future Phase 12 deliverable 4 — versioned ChannelContract.

Models the firmware ``live_data_map.h`` byte table as a project-owned
``ChannelContract``: a versioned, signature-tagged catalog of every byte
position in the live-data packet sent to TunerStudio via the ``'A'``
command. Used by logging, replay, VE Analyze, and dashboard code as the
authoritative source of truth for what each logged byte means — instead
of re-deriving channel positions from INI ``[OutputChannels]`` strings.

The contract is intentionally **firmware-version-tagged**: each
`ChannelContract` is anchored to a `LIVE_DATA_MAP_SIZE` value (currently
148) and a firmware signature range. When the firmware bumps the packet
size, a new contract is loaded; old logs stay readable against their
matching contract version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ChannelEncoding(str, Enum):
    """Wire encoding for one channel field."""

    U08 = "U08"
    U08_BITS = "U08_BITS"
    U16_LE = "U16_LE"
    S16_LE = "S16_LE"
    U32_LE = "U32_LE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_header_text(cls, text: str) -> "ChannelEncoding":
        normalized = text.strip().upper().replace(" ", "_")
        if normalized == "U08":
            return cls.U08
        if normalized == "U08_BITS":
            return cls.U08_BITS
        if normalized == "U16_LE":
            return cls.U16_LE
        if normalized == "S16_LE":
            return cls.S16_LE
        if normalized == "U32_LE":
            return cls.U32_LE
        return cls.UNKNOWN

    @property
    def byte_width(self) -> int:
        return {
            ChannelEncoding.U08: 1,
            ChannelEncoding.U08_BITS: 1,
            ChannelEncoding.U16_LE: 2,
            ChannelEncoding.S16_LE: 2,
            ChannelEncoding.U32_LE: 4,
            ChannelEncoding.UNKNOWN: 0,
        }[self]


@dataclass(slots=True, frozen=True)
class ChannelEntry:
    """One row of the live-data byte table."""

    name: str
    byte_start: int
    byte_end: int            # inclusive
    readable_index: int | None  # None when '-' in the header
    encoding: ChannelEncoding
    field: str               # raw `currentStatus` member or expression
    notes: str               # free-text trailing notes (often the INI channel name)
    locked: bool = False     # True when the row carries a [LOCKED] tag

    @property
    def width(self) -> int:
        return self.byte_end - self.byte_start + 1


@dataclass(slots=True, frozen=True)
class ChannelContract:
    """Project-owned channel contract for one firmware schema version."""

    log_entry_size: int
    firmware_signature: str | None = None
    entries: tuple[ChannelEntry, ...] = ()
    runtime_status_a_offset: int | None = None
    board_capability_flags_offset: int | None = None
    flash_health_status_offset: int | None = None
    # Schema version of the *contract format itself*, not the firmware.
    # Bumped when this dataclass shape changes in a backward-incompatible
    # way (e.g. adding required fields).
    schema_version: str = "1.0"

    def find(self, name: str) -> ChannelEntry | None:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def find_by_byte(self, byte_index: int) -> ChannelEntry | None:
        for entry in self.entries:
            if entry.byte_start <= byte_index <= entry.byte_end:
                return entry
        return None
