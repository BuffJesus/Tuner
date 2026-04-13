from __future__ import annotations


class MockTransport:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def read(self, size: int, timeout: float | None = None) -> bytes:
        del timeout
        size = min(size, len(self._buffer))
        data = self._buffer[:size]
        del self._buffer[:size]
        return bytes(data)

    def write(self, data: bytes) -> int:
        self._buffer.extend(data)
        return len(data)

    def is_open(self) -> bool:
        return self._open
