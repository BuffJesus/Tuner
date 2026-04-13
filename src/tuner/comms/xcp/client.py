from __future__ import annotations

from dataclasses import dataclass, field

from tuner.comms.xcp.packets import (
    XcpConnectResponse,
    XcpGetIdResponse,
    XcpStatusResponse,
    build_connect_command,
    build_get_id_command,
    build_get_status_command,
    build_set_mta_command,
    build_upload_command,
    parse_command_ack,
    parse_connect_response,
    parse_get_id_response,
    parse_status_response,
    parse_upload_response,
)
from tuner.transports.base import Transport


@dataclass(slots=True)
class XcpClient:
    transport: Transport
    connect_response: XcpConnectResponse | None = field(default=None, init=False)
    status_response: XcpStatusResponse | None = field(default=None, init=False)
    id_response: XcpGetIdResponse | None = field(default=None, init=False)

    def connect(self, mode: int = 0x00, timeout: float = 1.0) -> XcpConnectResponse:
        self.transport.open()
        self.transport.write(build_connect_command(mode))
        packet = self._read_exact(8, timeout)
        self.connect_response = parse_connect_response(packet)
        return self.connect_response

    def disconnect(self) -> None:
        if self.transport.is_open():
            self.transport.close()

    def get_status(self, timeout: float = 1.0) -> XcpStatusResponse:
        self.transport.write(build_get_status_command())
        packet = self._read_exact(6, timeout)
        self.status_response = parse_status_response(packet)
        return self.status_response

    def get_id(self, identifier_type: int = 0x00, timeout: float = 1.0) -> XcpGetIdResponse:
        self.transport.write(build_get_id_command(identifier_type))
        header = self._read_exact(8, timeout)
        identifier_length = int.from_bytes(header[4:8], byteorder="big", signed=False)
        remainder = self._read_exact(identifier_length, timeout)
        packet = header + remainder
        self.id_response = parse_get_id_response(packet)
        return self.id_response

    def set_mta(self, address: int, address_extension: int = 0x00, timeout: float = 1.0) -> None:
        self.transport.write(build_set_mta_command(address=address, address_extension=address_extension))
        packet = self._read_exact(1, timeout)
        parse_command_ack(packet)

    def upload(self, size: int, timeout: float = 1.0) -> bytes:
        self.transport.write(build_upload_command(size))
        packet = self._read_exact(size + 1, timeout)
        return parse_upload_response(packet, size)

    def read_memory(self, address: int, size: int, address_extension: int = 0x00, timeout: float = 1.0) -> bytes:
        self.set_mta(address=address, address_extension=address_extension, timeout=timeout)
        return self.upload(size=size, timeout=timeout)

    def _read_exact(self, size: int, timeout: float) -> bytes:
        buffer = bytearray()
        while len(buffer) < size:
            chunk = self.transport.read(size - len(buffer), timeout=timeout)
            if not chunk:
                raise RuntimeError(f"Expected {size} bytes from XCP transport, got {len(buffer)}")
            buffer.extend(chunk)
        return bytes(buffer)
