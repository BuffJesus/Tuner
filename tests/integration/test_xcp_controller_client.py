from tuner.comms.xcp_controller_client import XcpControllerClient
from tuner.domain.ecu_definition import EcuDefinition, XcpMemoryMapping
from tuner.simulator.xcp_simulator import XcpSimulatorServer
from tuner.transports.tcp_transport import TcpTransport


def test_xcp_controller_client_reads_definition_mappings() -> None:
    server = XcpSimulatorServer()
    server.start()
    host, port = server.address
    client = None

    try:
        definition = EcuDefinition(
            name="sim",
            xcp_mappings=[
                XcpMemoryMapping(name="rpm", address=0x4, size=4, data_type="u32", units="rpm"),
                XcpMemoryMapping(name="afr", address=0xA, size=4, data_type="f32", units="afr"),
            ],
        )
        client = XcpControllerClient(transport=TcpTransport(host, port), definition=definition)
        client.connect()

        snapshot = client.read_runtime()
        by_name = {item.name: item for item in snapshot.values}

        assert by_name["rpm"].value == 3210.0
        assert round(by_name["afr"].value, 1) == 14.7
        assert by_name["rpm"].units == "rpm"
    finally:
        if client is not None:
            client.disconnect()
        server.stop()
