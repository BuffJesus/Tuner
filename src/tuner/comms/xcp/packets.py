from __future__ import annotations

from dataclasses import dataclass


class XcpPid:
    POSITIVE_RESPONSE = 0xFF
    ERROR = 0xFE


class XcpCommand:
    CONNECT = 0xFF
    DISCONNECT = 0xFE
    GET_STATUS = 0xFD
    SYNCH = 0xFC
    GET_COMM_MODE_INFO = 0xFB
    GET_ID = 0xFA
    SET_MTA = 0xF6
    UPLOAD = 0xF5


@dataclass(slots=True)
class XcpConnectResponse:
    resource: int
    comm_mode_basic: int
    max_cto: int
    max_dto: int
    protocol_layer_version: int
    transport_layer_version: int


@dataclass(slots=True)
class XcpStatusResponse:
    session_status: int
    protection_status: int
    configuration_status: int


@dataclass(slots=True)
class XcpGetIdResponse:
    mode: int
    identifier_length: int
    identifier: bytes

    def identifier_text(self) -> str:
        return self.identifier.decode("ascii", errors="replace")


def build_connect_command(mode: int = 0x00) -> bytes:
    return bytes([XcpCommand.CONNECT, mode])


def build_get_status_command() -> bytes:
    return bytes([XcpCommand.GET_STATUS])


def build_get_id_command(identifier_type: int = 0x00) -> bytes:
    return bytes([XcpCommand.GET_ID, identifier_type])


def build_set_mta_command(address: int, address_extension: int = 0x00) -> bytes:
    return bytes(
        [
            XcpCommand.SET_MTA,
            0x00,
            0x00,
            address_extension & 0xFF,
            (address >> 24) & 0xFF,
            (address >> 16) & 0xFF,
            (address >> 8) & 0xFF,
            address & 0xFF,
        ]
    )


def build_upload_command(size: int) -> bytes:
    if size <= 0 or size > 255:
        raise ValueError("XCP UPLOAD size must be between 1 and 255 bytes")
    return bytes([XcpCommand.UPLOAD, size & 0xFF])


def parse_connect_response(packet: bytes) -> XcpConnectResponse:
    if len(packet) != 8:
        raise ValueError(f"XCP CONNECT response must be 8 bytes, got {len(packet)}")
    if packet[0] != XcpPid.POSITIVE_RESPONSE:
        raise ValueError(f"XCP CONNECT response must start with 0xFF, got 0x{packet[0]:02X}")
    return XcpConnectResponse(
        resource=packet[1],
        comm_mode_basic=packet[2],
        max_cto=packet[3],
        max_dto=int.from_bytes(packet[4:6], byteorder="big", signed=False),
        protocol_layer_version=packet[6],
        transport_layer_version=packet[7],
    )


def parse_status_response(packet: bytes) -> XcpStatusResponse:
    if len(packet) != 6:
        raise ValueError(f"XCP GET_STATUS response must be 6 bytes, got {len(packet)}")
    if packet[0] != XcpPid.POSITIVE_RESPONSE:
        raise ValueError(f"XCP GET_STATUS response must start with 0xFF, got 0x{packet[0]:02X}")
    return XcpStatusResponse(
        session_status=packet[1],
        protection_status=packet[2],
        configuration_status=int.from_bytes(packet[3:5], byteorder="big", signed=False),
    )


def parse_get_id_response(packet: bytes) -> XcpGetIdResponse:
    if len(packet) < 8:
        raise ValueError(f"XCP GET_ID response must be at least 8 bytes, got {len(packet)}")
    if packet[0] != XcpPid.POSITIVE_RESPONSE:
        raise ValueError(f"XCP GET_ID response must start with 0xFF, got 0x{packet[0]:02X}")
    payload = packet[1:]
    mode = payload[0]
    identifier_length = int.from_bytes(payload[3:7], byteorder="big", signed=False)
    if identifier_length <= 0:
        raise ValueError("XCP GET_ID length must be greater than zero")
    if mode != 1:
        raise ValueError(f"XCP GET_ID mode {mode} is not supported yet")
    identifier = payload[7 : 7 + identifier_length]
    if len(identifier) != identifier_length:
        raise ValueError("XCP GET_ID response did not include the full identifier payload")
    return XcpGetIdResponse(
        mode=mode,
        identifier_length=identifier_length,
        identifier=identifier,
    )


def parse_command_ack(packet: bytes) -> None:
    if packet != bytes([XcpPid.POSITIVE_RESPONSE]):
        raise ValueError(f"XCP command acknowledgement must be 0xFF, got {packet!r}")


def parse_upload_response(packet: bytes, expected_size: int) -> bytes:
    if len(packet) != expected_size + 1:
        raise ValueError(
            f"XCP UPLOAD response must be {expected_size + 1} bytes, got {len(packet)}"
        )
    if packet[0] != XcpPid.POSITIVE_RESPONSE:
        raise ValueError(f"XCP UPLOAD response must start with 0xFF, got 0x{packet[0]:02X}")
    return packet[1:]
