from tuner.comms.protocol_client import ProtocolControllerClient
from tuner.domain.ecu_definition import EcuDefinition
from tuner.simulator.protocol_simulator import ProtocolSimulatorServer
from tuner.transports.tcp_transport import TcpTransport


def test_protocol_client_round_trip_over_tcp() -> None:
    server = ProtocolSimulatorServer()
    server.start()
    host, port = server.address
    client = None

    try:
        client = ProtocolControllerClient(
            transport=TcpTransport(host, port),
            definition=EcuDefinition(name="sim"),
        )
        client.connect()

        snapshot = client.read_runtime()
        client.write_parameter("reqFuel", 9.2)
        value = client.read_parameter("reqFuel")

        assert [item.name for item in snapshot.values] == ["rpm", "map", "afr"]
        assert value == 9.2
        assert client.verify_crc() is True
    finally:
        if client is not None:
            client.disconnect()
        server.stop()
