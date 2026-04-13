from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TransportType(str, Enum):
    MOCK = "mock"
    SERIAL = "serial"
    TCP = "tcp"
    UDP = "udp"


class ProtocolType(str, Enum):
    SIM_JSON = "sim-json"
    XCP = "xcp"
    SPEEDUINO = "speeduino"


@dataclass(slots=True)
class ConnectionConfig:
    transport: TransportType = TransportType.MOCK
    protocol: ProtocolType = ProtocolType.SIM_JSON
    serial_port: str = ""
    baud_rate: int = 115200
    host: str = "127.0.0.1"
    port: int = 29000

    def display_name(self) -> str:
        if self.transport == TransportType.SERIAL:
            return f"{self.protocol.value}:serial:{self.serial_port or 'unset'}@{self.baud_rate}"
        if self.transport in {TransportType.TCP, TransportType.UDP}:
            return f"{self.protocol.value}:{self.transport.value}:{self.host}:{self.port}"
        return f"{self.protocol.value}:mock"
