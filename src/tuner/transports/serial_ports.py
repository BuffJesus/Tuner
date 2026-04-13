from __future__ import annotations

from typing import Iterable

from serial.tools import list_ports


def available_serial_ports() -> list[str]:
    ports: Iterable[object] = list_ports.comports()
    return [port.device for port in ports]
