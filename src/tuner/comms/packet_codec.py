from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from tuner.transports.base import Transport


@dataclass(slots=True)
class JsonLinePacketCodec:
    max_packet_size: int = 1024 * 1024

    def send(self, transport: Transport, payload: dict[str, Any]) -> None:
        packet = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        transport.write(packet)

    def receive(self, transport: Transport, timeout: float | None = 1.0) -> dict[str, Any]:
        buffer = bytearray()
        while True:
            chunk = transport.read(1, timeout=timeout)
            if not chunk:
                raise RuntimeError("No response received from controller.")
            buffer.extend(chunk)
            if len(buffer) > self.max_packet_size:
                raise RuntimeError("Controller response exceeded maximum packet size.")
            if buffer.endswith(b"\n"):
                return json.loads(buffer[:-1].decode("utf-8"))
