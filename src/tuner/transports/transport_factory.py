from __future__ import annotations

from tuner.domain.connection import ConnectionConfig, TransportType
from tuner.transports.base import Transport
from tuner.transports.mock_transport import MockTransport
from tuner.transports.serial_transport import SerialTransport
from tuner.transports.tcp_transport import TcpTransport
from tuner.transports.udp_transport import UdpTransport


class TransportFactory:
    def create(self, config: ConnectionConfig) -> Transport:
        if config.transport == TransportType.MOCK:
            return MockTransport()
        if config.transport == TransportType.SERIAL:
            return SerialTransport(config.serial_port, config.baud_rate)
        if config.transport == TransportType.TCP:
            return TcpTransport(config.host, config.port)
        if config.transport == TransportType.UDP:
            return UdpTransport(config.host, config.port)
        raise ValueError(f"Unsupported transport: {config.transport}")
