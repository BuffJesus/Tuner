from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DatalogChannelEntry:
    """A single channel slot in a logging profile."""

    name: str
    """Output channel name — must match a key in the runtime snapshot."""

    label: str | None = None
    """Human-readable label; populated from the definition, editable by the operator."""

    units: str | None = None
    """Units string for CSV header and display."""

    enabled: bool = True
    """Whether this channel is included in live capture."""

    format_digits: int | None = None
    """Decimal places for CSV export. None = use raw float representation."""


@dataclass
class DatalogProfile:
    """Named ordered collection of channels to capture during a live logging session."""

    name: str
    channels: list[DatalogChannelEntry] = field(default_factory=list)

    @property
    def enabled_channels(self) -> list[DatalogChannelEntry]:
        return [ch for ch in self.channels if ch.enabled]
