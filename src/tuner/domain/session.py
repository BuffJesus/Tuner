from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tuner.domain.firmware_capabilities import FirmwareCapabilities


class SessionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    OFFLINE = "offline"


@dataclass(slots=True)
class SessionInfo:
    project_name: str | None = None
    controller_name: str | None = None
    transport_name: str | None = None
    firmware_capabilities: FirmwareCapabilities | None = None
    firmware_signature: str | None = None
    error_detail: str | None = None
    state: SessionState = SessionState.DISCONNECTED
