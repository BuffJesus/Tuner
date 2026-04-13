from __future__ import annotations

import socket


class UdpTransport:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._socket: socket.socket | None = None

    def open(self) -> None:
        if self._socket is not None:
            return
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.connect((self.host, self.port))

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def read(self, size: int, timeout: float | None = None) -> bytes:
        if self._socket is None:
            raise RuntimeError("UDP transport is not open.")
        original_timeout = self._socket.gettimeout()
        if timeout is not None:
            self._socket.settimeout(timeout)
        try:
            return self._socket.recv(size)
        finally:
            self._socket.settimeout(original_timeout)

    def write(self, data: bytes) -> int:
        if self._socket is None:
            raise RuntimeError("UDP transport is not open.")
        return self._socket.send(data)

    def is_open(self) -> bool:
        return self._socket is not None
