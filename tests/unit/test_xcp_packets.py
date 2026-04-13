from tuner.comms.xcp.packets import (
    XcpPid,
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


def test_build_connect_command() -> None:
    assert build_connect_command() == bytes([0xFF, 0x00])


def test_parse_connect_response() -> None:
    response = parse_connect_response(bytes([XcpPid.POSITIVE_RESPONSE, 0x01, 0x02, 0x08, 0x01, 0x00, 0x01, 0x01]))

    assert response.resource == 0x01
    assert response.comm_mode_basic == 0x02
    assert response.max_cto == 0x08
    assert response.max_dto == 0x0100
    assert response.protocol_layer_version == 0x01
    assert response.transport_layer_version == 0x01


def test_build_get_status_command() -> None:
    assert build_get_status_command() == bytes([0xFD])


def test_build_get_id_command() -> None:
    assert build_get_id_command() == bytes([0xFA, 0x00])


def test_build_set_mta_command() -> None:
    assert build_set_mta_command(0x12345678) == bytes([0xF6, 0x00, 0x00, 0x00, 0x12, 0x34, 0x56, 0x78])


def test_build_upload_command() -> None:
    assert build_upload_command(4) == bytes([0xF5, 0x04])


def test_parse_status_response() -> None:
    response = parse_status_response(bytes([XcpPid.POSITIVE_RESPONSE, 0x05, 0x00, 0x00, 0x01, 0x00]))

    assert response.session_status == 0x05
    assert response.protection_status == 0x00
    assert response.configuration_status == 0x0001


def test_parse_get_id_response() -> None:
    response = parse_get_id_response(
        bytes([XcpPid.POSITIVE_RESPONSE, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03]) + b"SIM"
    )

    assert response.mode == 1
    assert response.identifier_length == 3
    assert response.identifier_text() == "SIM"


def test_parse_command_ack() -> None:
    parse_command_ack(bytes([0xFF]))


def test_parse_upload_response() -> None:
    payload = parse_upload_response(bytes([0xFF, 0x12, 0x34]), 2)

    assert payload == b"\x12\x34"
