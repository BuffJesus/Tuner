from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field
import struct

from tuner.comms.xcp.packets import XcpCommand, XcpPid


@dataclass(slots=True)
class XcpSimulatorState:
    session_status: int = 0x05
    protection_status: int = 0x00
    configuration_status: int = 0x0001
    resource: int = 0x01
    comm_mode_basic: int = 0x02
    max_cto: int = 0x08
    max_dto: int = 0x0100
    protocol_layer_version: int = 0x01
    transport_layer_version: int = 0x01
    identifier: bytes = b"TUNERPY-XCP-SIM"
    memory: bytearray = field(default_factory=lambda: bytearray(256))

    def __post_init__(self) -> None:
        self.memory[0:4] = b"\x12\x34\x56\x78"
        self.memory[4:8] = (3210).to_bytes(4, byteorder="big", signed=False)
        self.memory[8:10] = (875).to_bytes(2, byteorder="big", signed=False)
        self.memory[10:14] = struct.pack(">f", 14.7)


class XcpSimulatorServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.state = XcpSimulatorState()
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._mta_address = 0

    @property
    def address(self) -> tuple[str, int]:
        return self._server.getsockname()

    def start(self) -> None:
        self._server.bind((self.host, self.port))
        self._server.listen(1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            with socket.create_connection(self.address, timeout=0.2):
                pass
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server.close()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._server.accept()
            except OSError:
                return
            with conn:
                while not self._stop.is_set():
                    try:
                        command = self._read_command(conn)
                    except ConnectionResetError:
                        break
                    if not command:
                        break
                    response = self._handle(command)
                    try:
                        conn.sendall(response)
                    except ConnectionResetError:
                        break

    def _read_command(self, conn: socket.socket) -> bytes:
        header = conn.recv(1)
        if not header:
            return b""
        opcode = header[0]
        expected_size = self._expected_command_size(opcode)
        if expected_size == 1:
            return header
        payload = bytearray()
        while len(payload) < expected_size - 1:
            chunk = conn.recv(expected_size - 1 - len(payload))
            if not chunk:
                break
            payload.extend(chunk)
        return header + bytes(payload)

    @staticmethod
    def _expected_command_size(opcode: int) -> int:
        if opcode == XcpCommand.GET_STATUS:
            return 1
        if opcode in {XcpCommand.CONNECT, XcpCommand.GET_ID, XcpCommand.UPLOAD}:
            return 2
        if opcode == XcpCommand.SET_MTA:
            return 8
        return 1

    def _handle(self, packet: bytes) -> bytes:
        command = packet[0]
        if command == XcpCommand.CONNECT:
            return bytes(
                [
                    XcpPid.POSITIVE_RESPONSE,
                    self.state.resource,
                    self.state.comm_mode_basic,
                    self.state.max_cto,
                    (self.state.max_dto >> 8) & 0xFF,
                    self.state.max_dto & 0xFF,
                    self.state.protocol_layer_version,
                    self.state.transport_layer_version,
                ]
            )
        if command == XcpCommand.GET_STATUS:
            return bytes(
                [
                    XcpPid.POSITIVE_RESPONSE,
                    self.state.session_status,
                    self.state.protection_status,
                    (self.state.configuration_status >> 8) & 0xFF,
                    self.state.configuration_status & 0xFF,
                    0x00,
                ]
            )
        if command == XcpCommand.GET_ID:
            length = len(self.state.identifier)
            return (
                bytes(
                    [
                        XcpPid.POSITIVE_RESPONSE,
                        0x01,
                        0x00,
                        0x00,
                        (length >> 24) & 0xFF,
                        (length >> 16) & 0xFF,
                        (length >> 8) & 0xFF,
                        length & 0xFF,
                    ]
                )
                + self.state.identifier
            )
        if command == XcpCommand.SET_MTA:
            if len(packet) < 8:
                return bytes([0xFE, 0x20])
            self._mta_address = int.from_bytes(packet[4:8], byteorder="big", signed=False)
            return bytes([XcpPid.POSITIVE_RESPONSE])
        if command == XcpCommand.UPLOAD:
            if len(packet) < 2:
                return bytes([0xFE, 0x20])
            size = packet[1]
            data = bytes(self.state.memory[self._mta_address : self._mta_address + size])
            if len(data) < size:
                data = data + (b"\x00" * (size - len(data)))
            self._mta_address += size
            return bytes([XcpPid.POSITIVE_RESPONSE]) + data
        return bytes([0xFE, 0x20])
