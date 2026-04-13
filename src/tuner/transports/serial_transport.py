from __future__ import annotations

import time

from serial import Serial


class SerialTransport:
    def __init__(self, port: str, baud_rate: int) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self._serial: Serial | None = None

    def open(self) -> None:
        if self._serial and self._serial.is_open:
            return
        serial_port = Serial()
        serial_port.port = self.port
        serial_port.baudrate = self.baud_rate
        serial_port.timeout = 0.1
        serial_port.write_timeout = 0.5
        serial_port.inter_byte_timeout = 0.1
        try:
            serial_port.dtr = False
        except Exception:
            pass
        try:
            serial_port.rts = False
        except Exception:
            pass
        serial_port.open()
        self._serial = serial_port
        self.clear_buffers()
        time.sleep(0.05)

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()

    def read(self, size: int, timeout: float | None = None) -> bytes:
        if self._serial is None:
            raise RuntimeError("Serial transport is not open.")
        original_timeout = self._serial.timeout
        if timeout is not None:
            self._serial.timeout = timeout
        try:
            return bytes(self._serial.read(size))
        finally:
            self._serial.timeout = original_timeout

    def write(self, data: bytes) -> int:
        if self._serial is None:
            raise RuntimeError("Serial transport is not open.")
        written = int(self._serial.write(data))
        self._serial.flush()
        return written

    def is_open(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def clear_buffers(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass
        try:
            self._serial.reset_output_buffer()
        except Exception:
            pass
