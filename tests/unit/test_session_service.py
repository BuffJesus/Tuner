from dataclasses import dataclass, field

import pytest

from tuner.domain.connection import ConnectionConfig, ProtocolType, TransportType
from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.session import SessionState
from tuner.services.session_service import SessionService
from tuner.transports.transport_factory import TransportFactory
from tuner.transports.base import Transport


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

@dataclass
class StubSerialTransport:
    _open: bool = False
    _read_buffer: bytearray = field(default_factory=bytearray)
    _firmware_signature: bytes = b"speeduino 202501-T41"

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def read(self, size: int, timeout: float | None = None) -> bytes:
        del timeout
        size = min(size, len(self._read_buffer))
        data = self._read_buffer[:size]
        del self._read_buffer[:size]
        return bytes(data)

    def write(self, data: bytes) -> int:
        if data in {b"Q", b"S", b"f"}:
            if data == b"Q":
                self._read_buffer.extend(self._firmware_signature)
            elif data == b"S":
                self._read_buffer.extend(b"Speeduino")
            else:
                self._read_buffer.extend(b"\x00\x02\x00\x40\x00\x80")
            return len(data)
        return len(data)


@dataclass
class FailingHelloTransport:
    _open: bool = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def read(self, size: int, timeout: float | None = None) -> bytes:
        del size, timeout
        return b'{"status":"error","message":"boom"}\n'

    def write(self, data: bytes) -> int:
        return len(data)


class StubTransportFactory(TransportFactory):
    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    def create(self, config: ConnectionConfig) -> Transport:
        del config
        return self.transport


_SPEEDUINO_CONFIG = ConnectionConfig(
    transport=TransportType.SERIAL, protocol=ProtocolType.SPEEDUINO,
    serial_port="COM1", baud_rate=115200,
)


def _speeduino_definition(signature: str = "speeduino 202501-T41") -> EcuDefinition:
    return EcuDefinition(name=signature, firmware_signature=signature)


def _speeduino_service(signature: bytes = b"speeduino 202501-T41") -> SessionService:
    transport = StubSerialTransport(_firmware_signature=signature)
    return SessionService(
        transport_factory=StubTransportFactory(transport),
        definition=_speeduino_definition(),
    )


# ---------------------------------------------------------------------------
# Baseline connectivity (existing coverage)
# ---------------------------------------------------------------------------

def test_session_service_connects_mock_runtime() -> None:
    service = SessionService(transport_factory=TransportFactory())
    service.set_definition(EcuDefinition(name="demo", output_channels=["rpm", "map"]))

    info = service.connect(ConnectionConfig(transport=TransportType.MOCK, protocol=ProtocolType.SIM_JSON))
    snapshot = service.poll_runtime()

    assert info.state == SessionState.CONNECTED
    assert [value.name for value in snapshot.values] == ["rpm", "map"]

    service.disconnect()
    assert service.info.state == SessionState.DISCONNECTED


def test_session_service_connects_speeduino_protocol() -> None:
    transport = StubSerialTransport()
    service = SessionService(transport_factory=StubTransportFactory(transport))
    service.set_definition(EcuDefinition(name="demo", query_command="Q", version_info_command="S"))

    info = service.connect(ConnectionConfig(transport=TransportType.SERIAL, protocol=ProtocolType.SPEEDUINO, serial_port="COM7"))

    assert info.state == SessionState.CONNECTED
    assert info.controller_name == "Speeduino"
    assert info.firmware_capabilities is not None
    assert info.firmware_capabilities.serial_protocol_version == 2
    assert info.firmware_capabilities.blocking_factor == 64


def test_session_service_failed_connect_rolls_back_and_preserves_error() -> None:
    transport = FailingHelloTransport()
    service = SessionService(transport_factory=StubTransportFactory(transport))

    with pytest.raises(RuntimeError, match="boom"):
        service.connect(ConnectionConfig(transport=TransportType.TCP, protocol=ProtocolType.SIM_JSON, host="127.0.0.1", port=29001))

    assert service.client is None
    assert service.info.state == SessionState.DISCONNECTED
    assert service.info.error_detail == "boom"
    assert transport.is_open() is False


def test_session_service_stores_firmware_signature_after_connect() -> None:
    service = _speeduino_service()
    service.connect(_SPEEDUINO_CONFIG)
    assert service.info.firmware_signature == "speeduino 202501-T41"


def test_session_service_preserves_prior_signature_after_disconnect() -> None:
    service = _speeduino_service()
    service.connect(_SPEEDUINO_CONFIG)
    service.disconnect()
    # Signature must survive disconnect so a subsequent connect can detect a change.
    assert service.info.firmware_signature == "speeduino 202501-T41"
    assert service.info.state == SessionState.DISCONNECTED


# ---------------------------------------------------------------------------
# reconnect_signature_changed — signature mismatch detection
# ---------------------------------------------------------------------------

def test_reconnect_signature_changed_returns_false_on_first_connect() -> None:
    """First-ever connect: no prior signature, so change detection returns False."""
    service = _speeduino_service()
    service.connect(_SPEEDUINO_CONFIG)

    assert service.reconnect_signature_changed() is False


def test_reconnect_signature_changed_returns_false_when_same_signature() -> None:
    """Second connect with the same signature: no change."""
    service = _speeduino_service(b"speeduino 202501-T41")
    service.connect(_SPEEDUINO_CONFIG)
    service.disconnect()
    service.connect(_SPEEDUINO_CONFIG)

    assert service.reconnect_signature_changed() is False


def test_reconnect_signature_changed_returns_true_when_signature_differs() -> None:
    """Reconnect after a firmware reflash that changes the signature must be flagged."""
    # First connect: T41
    transport_a = StubSerialTransport(_firmware_signature=b"speeduino 202501-T41")
    factory_a = StubTransportFactory(transport_a)
    service = SessionService(transport_factory=factory_a, definition=_speeduino_definition())
    service.connect(_SPEEDUINO_CONFIG)
    service.disconnect()

    # Second connect: different firmware signature (simulating a reflash to U16P2).
    transport_b = StubSerialTransport(_firmware_signature=b"speeduino 202501-T41-U16P2")
    service.transport_factory = StubTransportFactory(transport_b)
    service.connect(_SPEEDUINO_CONFIG)

    assert service.reconnect_signature_changed() is True


def test_prior_firmware_signature_captures_pre_connect_value() -> None:
    """prior_firmware_signature must reflect the signature from before the last connect."""
    service = _speeduino_service(b"speeduino 202501-T41")
    service.connect(_SPEEDUINO_CONFIG)
    # After first connect: prior was None (no previous session).
    assert service.prior_firmware_signature is None

    service.disconnect()
    service.connect(_SPEEDUINO_CONFIG)
    # After second connect: prior was the T41 signature.
    assert service.prior_firmware_signature == "speeduino 202501-T41"


def test_reconnect_signature_changed_false_when_prior_is_none() -> None:
    """If the session never had a firmware signature, change detection must not fire."""
    service = SessionService(transport_factory=TransportFactory())
    service.set_definition(EcuDefinition(name="demo", output_channels=[]))
    # Mock client does not set firmware_signature, so info.firmware_signature stays None.
    service.connect(ConnectionConfig(transport=TransportType.MOCK, protocol=ProtocolType.SIM_JSON))

    assert service.reconnect_signature_changed() is False
