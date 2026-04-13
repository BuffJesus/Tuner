from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class FirmwareCapabilities:
    source: str
    serial_protocol_version: int | None = None
    blocking_factor: int | None = None
    table_blocking_factor: int | None = None
    live_data_size: int | None = None
    supports_board_capabilities_channel: bool = False
    supports_spi_flash_health_channel: bool = False
    supports_runtime_status_a: bool = False
    experimental_u16p2: bool = False

    def runtime_trust_summary(self) -> str:
        """Human-readable summary of which runtime channel groups are trustworthy."""
        parts: list[str] = []
        if self.supports_runtime_status_a:
            parts.append("runtimeStatusA: trusted")
        else:
            parts.append("runtimeStatusA: uncertain (not advertised)")
        if self.supports_board_capabilities_channel:
            parts.append("boardCapabilities: available")
        if self.supports_spi_flash_health_channel:
            parts.append("spiFlashHealth: available")
        if self.experimental_u16p2:
            parts.append("U16P2: experimental")
        if self.live_data_size is not None:
            parts.append(f"live_data_size: {self.live_data_size}")
        return "; ".join(parts) if parts else "no capability detail"

    def uncertain_channel_groups(self) -> frozenset[str]:
        """Channel groups that should be treated as uncertain given these capabilities.

        Callers can use this set to suppress or flag runtime evidence for channels
        that the firmware did not advertise as present/reliable.
        """
        uncertain: set[str] = set()
        if not self.supports_runtime_status_a:
            uncertain.add("runtimeStatusA")
        if not self.supports_board_capabilities_channel:
            uncertain.add("boardCapabilities")
        if not self.supports_spi_flash_health_channel:
            uncertain.add("spiFlashHealth")
        return frozenset(uncertain)
