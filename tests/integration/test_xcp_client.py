from tuner.comms.xcp.client import XcpClient
from tuner.simulator.xcp_simulator import XcpSimulatorServer
from tuner.transports.tcp_transport import TcpTransport


def test_xcp_client_connect_and_get_status_over_tcp() -> None:
    server = XcpSimulatorServer()
    server.start()
    host, port = server.address
    client = None

    try:
        client = XcpClient(TcpTransport(host, port))
        connect_response = client.connect()
        status = client.get_status()
        identity = client.get_id()
        client.set_mta(0x00000000)
        uploaded = client.upload(4)

        assert connect_response.max_cto == 0x08
        assert connect_response.max_dto == 0x0100
        assert status.session_status == 0x05
        assert status.configuration_status == 0x0001
        assert identity.identifier_text() == "TUNERPY-XCP-SIM"
        assert uploaded == b"\x12\x34\x56\x78"
    finally:
        if client is not None:
            client.disconnect()
        server.stop()
