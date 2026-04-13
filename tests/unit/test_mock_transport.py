from tuner.transports.mock_transport import MockTransport


def test_mock_transport_round_trip() -> None:
    transport = MockTransport()
    transport.open()

    written = transport.write(b"abc")

    assert written == 3
    assert transport.read(2) == b"ab"
    assert transport.read(10) == b"c"
