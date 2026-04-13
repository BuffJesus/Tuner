"""Python <-> C++ parity harness for XCP packet builders + parsers.

Pins the C++ `xcp_*` helpers (port of `tuner.comms.xcp.packets`)
against the Python originals across:

  - build_connect_command (default + custom mode)
  - build_get_status_command
  - build_get_id_command (default + custom identifier_type)
  - build_set_mta_command (address packing + address_extension)
  - build_upload_command (boundary + out-of-range)
  - parse_connect_response (success + length / PID error paths)
  - parse_status_response  (success + length / PID error paths)
  - parse_get_id_response  (success + truncation + zero-length + bad mode)
  - parse_command_ack      (success + every error path)
  - parse_upload_response  (success + length / PID mismatch)
  - identifier_text repr-replacement on non-ASCII bytes

I/O — sending/receiving the bytes over a CAN-USB transport — is out
of scope. The Python parity targets are the pure functions under
`tuner.comms.xcp.packets`, not `XcpControllerClient`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

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


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CPP_BUILD_CANDIDATES = [
    _REPO_ROOT / "build" / "cpp",
    _REPO_ROOT / "build" / "cpp" / "Release",
    _REPO_ROOT / "build" / "cpp" / "Debug",
    _REPO_ROOT / "cpp" / "build",
]


def _try_import_tuner_core():
    try:
        return importlib.import_module("tuner._native.tuner_core")
    except ImportError:
        pass
    for candidate in _CPP_BUILD_CANDIDATES:
        if not candidate.exists():
            continue
        added = str(candidate)
        if added not in sys.path:
            sys.path.insert(0, added)
        try:
            return importlib.import_module("tuner_core")
        except ImportError:
            sys.path.remove(added)
            continue
    return None


_tuner_core = _try_import_tuner_core()

pytestmark = pytest.mark.skipif(
    _tuner_core is None,
    reason="tuner_core C++ extension not built — see cpp/README.md.",
)


# ---------------------------------------------------------------------------
# Builder parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [0x00, 0x01, 0x42, 0xFF])
def test_build_connect_command_parity(mode):
    py = build_connect_command(mode)
    cpp = bytes(_tuner_core.xcp_build_connect_command(mode))
    assert py == cpp


def test_build_get_status_command_parity():
    py = build_get_status_command()
    cpp = bytes(_tuner_core.xcp_build_get_status_command())
    assert py == cpp


@pytest.mark.parametrize("identifier_type", [0x00, 0x01, 0x05, 0xFF])
def test_build_get_id_command_parity(identifier_type):
    py = build_get_id_command(identifier_type)
    cpp = bytes(_tuner_core.xcp_build_get_id_command(identifier_type))
    assert py == cpp


@pytest.mark.parametrize("address,address_extension", [
    (0x00000000, 0x00),
    (0x12345678, 0x00),
    (0xDEADBEEF, 0x42),
    (0xFFFFFFFF, 0xFF),
    (0x00000001, 0x01),
])
def test_build_set_mta_command_parity(address, address_extension):
    py = build_set_mta_command(address, address_extension)
    cpp = bytes(_tuner_core.xcp_build_set_mta_command(address, address_extension))
    assert py == cpp


@pytest.mark.parametrize("size", [1, 2, 4, 8, 16, 64, 127, 128, 254, 255])
def test_build_upload_command_parity(size):
    py = build_upload_command(size)
    cpp = bytes(_tuner_core.xcp_build_upload_command(size))
    assert py == cpp


@pytest.mark.parametrize("size", [0, -1, -100, 256, 257, 1024])
def test_build_upload_command_throws_on_both_sides(size):
    with pytest.raises(ValueError):
        build_upload_command(size)
    with pytest.raises(Exception):
        _tuner_core.xcp_build_upload_command(size)


# ---------------------------------------------------------------------------
# Parser parity — happy paths
# ---------------------------------------------------------------------------


def test_parse_connect_response_parity():
    packet = bytes([XcpPid.POSITIVE_RESPONSE, 0x01, 0x02, 0x08, 0x01, 0x00, 0x01, 0x01])
    py = parse_connect_response(packet)
    cpp = _tuner_core.xcp_parse_connect_response(packet)
    assert py.resource == cpp.resource
    assert py.comm_mode_basic == cpp.comm_mode_basic
    assert py.max_cto == cpp.max_cto
    assert py.max_dto == cpp.max_dto
    assert py.protocol_layer_version == cpp.protocol_layer_version
    assert py.transport_layer_version == cpp.transport_layer_version


def test_parse_connect_response_max_dto_big_endian_parity():
    # max_dto bytes 0xAB 0xCD -> big-endian 0xABCD
    packet = bytes([0xFF, 0x00, 0x00, 0x08, 0xAB, 0xCD, 0x01, 0x01])
    py = parse_connect_response(packet)
    cpp = _tuner_core.xcp_parse_connect_response(packet)
    assert py.max_dto == 0xABCD == cpp.max_dto


def test_parse_status_response_parity():
    packet = bytes([XcpPid.POSITIVE_RESPONSE, 0x05, 0x00, 0x00, 0x01, 0x00])
    py = parse_status_response(packet)
    cpp = _tuner_core.xcp_parse_status_response(packet)
    assert py.session_status == cpp.session_status
    assert py.protection_status == cpp.protection_status
    assert py.configuration_status == cpp.configuration_status


def test_parse_status_response_configuration_status_big_endian_parity():
    packet = bytes([0xFF, 0x00, 0x00, 0xCA, 0xFE, 0x00])
    py = parse_status_response(packet)
    cpp = _tuner_core.xcp_parse_status_response(packet)
    assert py.configuration_status == 0xCAFE == cpp.configuration_status


def test_parse_get_id_response_parity():
    packet = bytes([
        0xFF,
        0x01,
        0x00, 0x00,
        0x00, 0x00, 0x00, 0x05,
    ]) + b"HELLO"
    py = parse_get_id_response(packet)
    cpp = _tuner_core.xcp_parse_get_id_response(packet)
    assert py.mode == cpp.mode
    assert py.identifier_length == cpp.identifier_length
    assert py.identifier == bytes(cpp.identifier)
    assert py.identifier_text() == cpp.identifier_text()


def test_parse_get_id_response_non_ascii_replacement_parity():
    packet = bytes([
        0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03,
        ord('A'), 0xFF, ord('Z'),
    ])
    py = parse_get_id_response(packet)
    cpp = _tuner_core.xcp_parse_get_id_response(packet)
    assert py.identifier_text() == cpp.identifier_text()
    # Both sides should produce the U+FFFD replacement.
    assert "\ufffd" in py.identifier_text()


def test_parse_command_ack_accepts_single_0xff():
    parse_command_ack(bytes([0xFF]))
    _tuner_core.xcp_parse_command_ack(bytes([0xFF]))


def test_parse_upload_response_parity():
    packet = bytes([0xFF, 0xDE, 0xAD, 0xBE, 0xEF])
    py = parse_upload_response(packet, 4)
    cpp = bytes(_tuner_core.xcp_parse_upload_response(packet, 4))
    assert py == cpp == bytes([0xDE, 0xAD, 0xBE, 0xEF])


def test_parse_upload_response_random_payload_parity():
    import random
    rng = random.Random(0xBEEF)
    for _ in range(20):
        n = rng.randint(1, 200)
        payload = bytes(rng.randint(0, 255) for _ in range(n))
        packet = bytes([0xFF]) + payload
        py = parse_upload_response(packet, n)
        cpp = bytes(_tuner_core.xcp_parse_upload_response(packet, n))
        assert py == cpp == payload


# ---------------------------------------------------------------------------
# Parser parity — error paths (both sides must reject)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("packet", [
    bytes([0xFF, 0x01, 0x02, 0x08, 0x01, 0x00, 0x01]),         # too short
    bytes([0xFF, 0x01, 0x02, 0x08, 0x01, 0x00, 0x01, 0x01, 0x00]),  # too long
    bytes([0xFE, 0x01, 0x02, 0x08, 0x01, 0x00, 0x01, 0x01]),   # bad PID
])
def test_parse_connect_response_throws_parity(packet):
    with pytest.raises(ValueError):
        parse_connect_response(packet)
    with pytest.raises(Exception):
        _tuner_core.xcp_parse_connect_response(packet)


@pytest.mark.parametrize("packet", [
    bytes([0xFF, 0x05, 0x00, 0x00, 0x01]),                    # too short
    bytes([0xFF, 0x05, 0x00, 0x00, 0x01, 0x00, 0x00]),        # too long
    bytes([0xFE, 0x05, 0x00, 0x00, 0x01, 0x00]),              # bad PID
])
def test_parse_status_response_throws_parity(packet):
    with pytest.raises(ValueError):
        parse_status_response(packet)
    with pytest.raises(Exception):
        _tuner_core.xcp_parse_status_response(packet)


@pytest.mark.parametrize("packet", [
    bytes([0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]),                       # < 8 bytes
    bytes([0xFE, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05, 0,0,0,0,0]),      # bad PID
    bytes([0xFF, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05, 0,0,0,0,0]),      # bad mode
    bytes([0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05, ord('A'), ord('B'), ord('C')]),  # truncated
    bytes([0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),                 # zero length
])
def test_parse_get_id_response_throws_parity(packet):
    with pytest.raises(ValueError):
        parse_get_id_response(packet)
    with pytest.raises(Exception):
        _tuner_core.xcp_parse_get_id_response(packet)


@pytest.mark.parametrize("packet", [
    b"",
    bytes([0xFE]),
    bytes([0xFF, 0x00]),
    bytes([0xFF, 0xFF]),
])
def test_parse_command_ack_throws_parity(packet):
    with pytest.raises(ValueError):
        parse_command_ack(packet)
    with pytest.raises(Exception):
        _tuner_core.xcp_parse_command_ack(packet)


@pytest.mark.parametrize("packet,expected_size", [
    (bytes([0xFF, 0xAA, 0xBB]), 4),                  # too short
    (bytes([0xFF, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE]), 4),# too long
    (bytes([0xFE, 0xAA, 0xBB, 0xCC, 0xDD]), 4),      # bad PID
])
def test_parse_upload_response_throws_parity(packet, expected_size):
    with pytest.raises(ValueError):
        parse_upload_response(packet, expected_size)
    with pytest.raises(Exception):
        _tuner_core.xcp_parse_upload_response(packet, expected_size)
