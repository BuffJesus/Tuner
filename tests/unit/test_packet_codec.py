from tuner.comms.packet_codec import JsonLinePacketCodec
from tuner.transports.mock_transport import MockTransport


def test_json_line_packet_codec_round_trip() -> None:
    transport = MockTransport()
    codec = JsonLinePacketCodec()
    transport.open()
    codec.send(transport, {"command": "hello", "value": 1})

    payload = codec.receive(transport)

    assert payload == {"command": "hello", "value": 1}
