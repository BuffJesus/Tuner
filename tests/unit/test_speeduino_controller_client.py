from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from tuner.comms.speeduino_controller_client import SpeeduinoControllerClient
from tuner.domain.ecu_definition import EcuDefinition, ScalarParameterDefinition, TableDefinition
from tuner.parsers.ini_parser import IniParser


def _make_frame(payload: bytes) -> bytes:
    """Build a Speeduino new-protocol response frame."""
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return struct.pack("<H", len(payload)) + payload + struct.pack("<I", crc)


@dataclass
class FakeSpeeduinoTransport:
    signature: bytes = b"speeduino 202501-T41"
    product: bytes = b"Speeduino DropBear v2.0.1"
    capabilities_payload: bytes = b"\x00\x02\x00\x40\x00\x80"
    pages: dict[int, bytearray] = field(default_factory=dict)
    runtime_payload: bytearray = field(default_factory=bytearray)
    burn_requests: list[int] = field(default_factory=list)
    writes: list[bytes] = field(default_factory=list)
    _read_buffer: bytearray = field(default_factory=bytearray)
    _open: bool = False

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
        self.writes.append(data)
        if data == b"Q":
            self._read_buffer.extend(self.signature)
            return len(data)
        if data == b"S":
            self._read_buffer.extend(self.product)
            return len(data)
        if data == b"f":
            self._read_buffer.extend(self.capabilities_payload)
            return len(data)
        command = chr(data[0])
        if command == "p":
            page = data[2]
            offset = data[3] | (data[4] << 8)
            length = data[5] | (data[6] << 8)
            self._read_buffer.extend(self.pages[page][offset : offset + length])
            return len(data)
        if command == "M":
            page = data[2]
            offset = data[3] | (data[4] << 8)
            length = data[5] | (data[6] << 8)
            payload = data[7 : 7 + length]
            self.pages[page][offset : offset + length] = payload
            return len(data)
        if command == "b":
            self.burn_requests.append(data[2])
            return len(data)
        if command == "r":
            offset = data[3] | (data[4] << 8)
            length = data[5] | (data[6] << 8)
            self._read_buffer.extend(self.runtime_payload[offset : offset + length])
            return len(data)
        raise AssertionError(f"Unexpected command bytes: {data!r}")


@dataclass
class RejectLargePageReadTransport(FakeSpeeduinoTransport):
    rejected_reads: list[tuple[int, int, int]] = field(default_factory=list)

    def write(self, data: bytes) -> int:
        if data and chr(data[0]) == "p":
            page = data[2]
            offset = data[3] | (data[4] << 8)
            length = data[5] | (data[6] << 8)
            if offset == 0 and length >= 544:
                self.rejected_reads.append((page, offset, length))
                return len(data)
        return super().write(data)


def test_speeduino_controller_client_handles_handshake_pages_writes_and_runtime() -> None:
    page = bytearray(16)
    page[0:2] = (20).to_bytes(2, byteorder="little", signed=True)
    page[2:4] = (40).to_bytes(2, byteorder="little", signed=True)
    page[4:6] = (60).to_bytes(2, byteorder="little", signed=True)
    page[6:8] = (80).to_bytes(2, byteorder="little", signed=True)
    page[12] = 91
    page[13] = 0b10100101
    runtime = bytearray(4)
    runtime[0:2] = (1500).to_bytes(2, byteorder="little", signed=False)
    runtime[2:4] = (87).to_bytes(2, byteorder="little", signed=False)
    transport = FakeSpeeduinoTransport(pages={1: page}, runtime_payload=runtime)
    definition = EcuDefinition(
        name="Speeduino",
        query_command="Q",
        version_info_command="S",
        page_read_command="p%2i%2o%2c",
        page_value_write_command="M%2i%2o%2c%v",
        burn_command="b%2i",
        page_sizes=[16],
        scalars=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, scale=0.1, translate=0.0),
            ScalarParameterDefinition(name="sparkMode", data_type="U08", page=1, offset=13, bit_offset=0, bit_length=3),
        ],
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, data_type="S16", scale=0.5, translate=0.0),
        ],
        output_channels=["rpm", "map"],
        output_channel_definitions=[
            ScalarParameterDefinition(name="rpm", data_type="U16", offset=0, scale=1.0, translate=0.0, units="rpm"),
            ScalarParameterDefinition(name="map", data_type="U16", offset=2, scale=1.0, translate=0.0, units="kPa"),
        ],
    )
    client = SpeeduinoControllerClient(transport=transport, definition=definition)

    client.connect()

    assert client.firmware_signature == "speeduino 202501-T41"
    assert client.product_string == "Speeduino DropBear v2.0.1"
    assert client.controller_name == "Speeduino DropBear v2.0.1"
    assert client.capabilities is not None
    assert client.capabilities.serial_protocol_version == 2
    assert client.capabilities.blocking_factor == 64
    assert client.capabilities.table_blocking_factor == 128
    assert client.capabilities.live_data_size == 4
    assert client.read_parameter("reqFuel") == 9.1
    assert client.read_parameter("sparkMode") == 5
    assert client.read_parameter("veTable") == [10.0, 20.0, 30.0, 40.0]

    client.write_parameter("reqFuel", 8.5)
    client.write_parameter("sparkMode", 2)
    client.write_parameter("veTable", [11.0, 22.0, 33.0, 44.0])
    client.burn()
    runtime_snapshot = client.read_runtime()

    assert transport.pages[1][12] == 85
    assert transport.pages[1][13] == 0b10100010
    assert transport.pages[1][0:8] == (
        (22).to_bytes(2, byteorder="little", signed=True)
        + (44).to_bytes(2, byteorder="little", signed=True)
        + (66).to_bytes(2, byteorder="little", signed=True)
        + (88).to_bytes(2, byteorder="little", signed=True)
    )
    assert transport.burn_requests == [1]
    assert runtime_snapshot.as_dict() == {"rpm": 1500.0, "map": 87.0}


def test_speeduino_controller_client_marks_supported_runtime_channels_in_capabilities() -> None:
    definition = IniParser().parse(
        Path(r"C:\Users\Cornelio\Desktop\speeduino-202501.6\release\speeduino-dropbear-v2.0.1-u16p2-experimental.ini")
    )
    transport = FakeSpeeduinoTransport(signature=b"speeduino 202501-T41-U16P2")
    client = SpeeduinoControllerClient(transport=transport, definition=definition)

    client.connect()

    assert client.capabilities is not None
    assert client.capabilities.supports_board_capabilities_channel is True
    assert client.capabilities.supports_spi_flash_health_channel is True
    assert client.capabilities.supports_runtime_status_a is True
    assert client.capabilities.experimental_u16p2 is True


def test_speeduino_controller_client_reads_real_u16_page2_tables_from_ini() -> None:
    definition = IniParser().parse(
        Path(r"C:\Users\Cornelio\Desktop\speeduino-202501.6\release\speeduino-dropbear-v2.0.1-u16p2-experimental.ini")
    )
    page1 = bytearray(definition.page_sizes[0])
    page1[37] = 0
    page2 = bytearray(definition.page_sizes[1])
    for index in range(16 * 16):
        raw_value = 340 + index
        start = index * 2
        page2[start : start + 2] = raw_value.to_bytes(2, byteorder="little", signed=False)
    rpm_bins = [5, 8, 11, 14, 18, 22, 26, 30, 35, 40, 45, 50, 55, 60, 65, 70]
    fuel_load_bins = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 175]
    for index, raw_value in enumerate(rpm_bins):
        page2[512 + index] = raw_value
    for index, raw_value in enumerate(fuel_load_bins):
        page2[528 + index] = raw_value
    transport = FakeSpeeduinoTransport(
        signature=b"speeduino 202501-T41-U16P2",
        product=b"Speeduino DropBear v2.0.1",
        pages={1: page1, 2: page2},
    )
    client = SpeeduinoControllerClient(transport=transport, definition=definition)

    client.connect()

    assert client.read_parameter("veTable")[:4] == [34.0, 34.1, 34.2, 34.300000000000004]
    assert client.read_parameter("rpmBins")[:4] == [500.0, 800.0, 1100.0, 1400.0]
    assert client.read_parameter("fuelLoadBins")[:4] == [10.0, 20.0, 30.0, 40.0]


def test_speeduino_controller_client_writes_large_table_without_forcing_full_page_readback() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        query_command="Q",
        version_info_command="S",
        page_read_command="p%2i%2o%2c",
        page_value_write_command="M%2i%2o%2c%v",
        burn_command="b%2i",
        page_sizes=[544],
        tables=[
            TableDefinition(name="veTable", rows=16, columns=16, page=1, offset=0, data_type="U16", scale=0.1, translate=0.0),
        ],
    )
    page = bytearray(544)
    transport = RejectLargePageReadTransport(pages={1: page})
    client = SpeeduinoControllerClient(transport=transport, definition=definition)

    client.connect()
    client.write_parameter("veTable", [100.0] * 256)
    client.burn()

    assert transport.rejected_reads == []
    assert transport.burn_requests == [1]
    assert transport.pages[1][0:4] == (1000).to_bytes(2, byteorder="little", signed=False) * 2


def test_write_chunked_by_blocking_factor() -> None:
    """Large writes must be split into chunks ≤ blocking_factor bytes.

    AVR boards have a 121-byte blocking_factor.  A 200-byte scalar write must
    produce two M-command packets, not one oversized packet.
    """
    definition = EcuDefinition(
        name="Speeduino",
        query_command="Q",
        version_info_command="S",
        page_read_command="p%2i%2o%2c",
        page_value_write_command="M%2i%2o%2c%v",
        burn_command="b%2i",
        page_sizes=[256],
        blocking_factor=64,  # small factor for test clarity
        scalars=[
            ScalarParameterDefinition(name="bigParam", page=1, offset=0, data_type="U08"),
        ],
    )
    page_data = bytearray(256)
    transport = FakeSpeeduinoTransport(pages={1: page_data})
    client = SpeeduinoControllerClient(transport=transport, definition=definition)
    client.connect()

    # Write 200 bytes of data via a direct _write_page_chunk call
    payload = bytes(range(200))
    client._write_page_chunk(1, 0, payload)

    # With blocking_factor=64, 200 bytes → 4 chunks (64+64+64+8)
    m_writes = [w for w in transport.writes if w and chr(w[0]) == "M"]
    assert len(m_writes) == 4
    # First chunk: offset=0, length=64
    assert m_writes[0][3] == 0   # offset_lo
    assert m_writes[0][4] == 0   # offset_hi
    assert m_writes[0][5] == 64  # length_lo
    assert m_writes[0][6] == 0   # length_hi
    # Second chunk: offset=64
    assert m_writes[1][3] == 64  # offset_lo
    assert m_writes[1][5] == 64  # length_lo
    # Last chunk: offset=192, length=8
    assert m_writes[3][3] == 192  # offset_lo
    assert m_writes[3][5] == 8    # length_lo


def test_write_chunking_uses_capability_over_definition() -> None:
    """Firmware-advertised blocking_factor must take precedence over INI value."""
    definition = EcuDefinition(
        name="Speeduino",
        query_command="Q",
        version_info_command="S",
        page_read_command="p%2i%2o%2c",
        page_value_write_command="M%2i%2o%2c%v",
        burn_command="b%2i",
        page_sizes=[256],
        blocking_factor=64,   # INI says 64
        scalars=[ScalarParameterDefinition(name="x", page=1, offset=0, data_type="U08")],
    )
    page_data = bytearray(256)
    # capabilities_payload: [0x00][version=2][bf_hi=0x00][bf_lo=0x80][tbf_hi=0x00][tbf_lo=0x80]
    # blocking_factor = 128, table_blocking_factor = 128
    transport = FakeSpeeduinoTransport(
        pages={1: page_data},
        capabilities_payload=b"\x00\x02\x00\x80\x00\x80",  # bf=128
    )
    client = SpeeduinoControllerClient(transport=transport, definition=definition)
    client.connect()

    # blocking_factor from capabilities = 128 (overrides INI 64)
    assert client._effective_blocking_factor() == 128

    # Writing 200 bytes → ceil(200/128) = 2 chunks
    client._write_page_chunk(1, 0, bytes(200))
    m_writes = [w for w in transport.writes if w and chr(w[0]) == "M"]
    assert len(m_writes) == 2


def test_invalidate_page_cache_forces_fresh_read() -> None:
    """invalidate_page_cache() must cause the next read_parameter to re-fetch
    from the controller instead of returning stale cached data.

    This covers the "Refresh from ECU" regression: without the cache clear,
    read_parameter() returns the Python-side cache, not the live controller
    state.
    """
    definition = EcuDefinition(
        name="Speeduino",
        query_command="Q",
        version_info_command="S",
        page_read_command="p%2i%2o%2c",
        page_value_write_command="M%2i%2o%2c%v",
        burn_command="b%2i",
        page_sizes=[128],
        scalars=[
            ScalarParameterDefinition(
                name="egoType", page=1, offset=0, data_type="U08",
                bit_offset=2, bit_length=2,
            ),
        ],
    )
    # Start with egoType=0 (disabled, bits [2:3] = 0b00)
    page_data = bytearray(128)
    transport = FakeSpeeduinoTransport(pages={1: page_data})
    client = SpeeduinoControllerClient(transport=transport, definition=definition)
    client.connect()

    # First read — seeds the cache
    val1 = client.read_parameter("egoType")
    assert val1 == 0.0

    # Simulate controller-side change (e.g., written by another tool)
    page_data[0] = 0b00001000  # bits [2:3] = 2 → "Wide Band"

    # Without cache invalidation, cached value is returned
    val_cached = client.read_parameter("egoType")
    assert val_cached == 0.0  # stale cache

    # Invalidate → next read goes to controller
    client.invalidate_page_cache()
    val_fresh = client.read_parameter("egoType")
    assert val_fresh == 2.0  # fresh from controller


# ---------------------------------------------------------------------------
# Framed transport (TCP/Airbear path)
# ---------------------------------------------------------------------------

@dataclass
class FakeFramedTransport(FakeSpeeduinoTransport):
    """Like FakeSpeeduinoTransport but exposes write_framed / read_framed_response.

    This simulates a TcpTransport connected to the Airbear bridge.  The
    handshake commands (Q / S) still go through the unframed write() path
    (Airbear special-cases them).  All data commands go through write_framed()
    and expect a framed response via read_framed_response().
    """

    framed_writes: list[bytes] = field(default_factory=list)
    _framed_response_buffer: bytearray = field(default_factory=bytearray)

    def write_framed(self, payload: bytes) -> None:
        self.framed_writes.append(payload)
        command = chr(payload[0])

        if payload == b"f":
            # capabilities command — respond framed
            self._framed_response_buffer.extend(_make_frame(self.capabilities_payload))
            return
        if command == "p":
            page = payload[2]
            offset = payload[3] | (payload[4] << 8)
            length = payload[5] | (payload[6] << 8)
            data = self.pages[page][offset : offset + length]
            self._framed_response_buffer.extend(_make_frame(bytes(data)))
            return
        if command == "M":
            page = payload[2]
            offset = payload[3] | (payload[4] << 8)
            length = payload[5] | (payload[6] << 8)
            data = payload[7 : 7 + length]
            self.pages[page][offset : offset + length] = data
            return
        if command == "b":
            self.burn_requests.append(payload[2])
            return
        if command == "r":
            offset = payload[3] | (payload[4] << 8)
            length = payload[5] | (payload[6] << 8)
            data = self.runtime_payload[offset : offset + length]
            self._framed_response_buffer.extend(_make_frame(bytes(data)))
            return
        raise AssertionError(f"Unexpected framed command: {payload!r}")

    def read_framed_response(self, timeout: float = 1.0) -> bytes:
        buf = self._framed_response_buffer
        if len(buf) < 2:
            raise RuntimeError("No framed response queued")
        payload_length = struct.unpack("<H", bytes(buf[:2]))[0]
        frame_size = 2 + payload_length + 4
        if len(buf) < frame_size:
            raise RuntimeError("Incomplete framed response in buffer")
        payload = bytes(buf[2 : 2 + payload_length])
        del buf[:frame_size]
        return payload


def _framed_client() -> tuple[SpeeduinoControllerClient, FakeFramedTransport]:
    page = bytearray(16)
    page[0:2] = (20).to_bytes(2, byteorder="little", signed=True)
    page[2:4] = (40).to_bytes(2, byteorder="little", signed=True)
    page[12] = 91
    runtime = bytearray(4)
    runtime[0:2] = (3000).to_bytes(2, byteorder="little", signed=False)
    runtime[2:4] = (95).to_bytes(2, byteorder="little", signed=False)
    transport = FakeFramedTransport(pages={1: page}, runtime_payload=runtime)
    definition = EcuDefinition(
        name="Speeduino",
        query_command="Q",
        version_info_command="S",
        page_read_command="p%2i%2o%2c",
        page_value_write_command="M%2i%2o%2c%v",
        burn_command="b%2i",
        page_sizes=[16],
        scalars=[
            ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=12, scale=0.1, translate=0.0),
        ],
        tables=[
            TableDefinition(name="veTable", rows=1, columns=2, page=1, offset=0, data_type="S16", scale=0.5, translate=0.0),
        ],
        output_channel_definitions=[
            ScalarParameterDefinition(name="rpm", data_type="U16", offset=0, scale=1.0, translate=0.0, units="rpm"),
            ScalarParameterDefinition(name="map", data_type="U16", offset=2, scale=1.0, translate=0.0, units="kPa"),
        ],
    )
    client = SpeeduinoControllerClient(transport=transport, definition=definition)
    client.connect()
    return client, transport


def test_framed_transport_handshake_uses_raw_write() -> None:
    """Q and S commands must go through unframed write() — Airbear special-cases them."""
    _, transport = _framed_client()
    # Q and S are in the raw write() log, not framed_writes
    raw_cmds = [bytes(w) for w in transport.writes]
    assert b"Q" in raw_cmds
    assert b"S" in raw_cmds


def test_framed_transport_capabilities_command_is_framed() -> None:
    """'f' capabilities command must use write_framed, not raw write()."""
    _, transport = _framed_client()
    assert b"f" in transport.framed_writes


def test_framed_transport_runtime_read_is_framed() -> None:
    client, transport = _framed_client()
    transport.framed_writes.clear()
    client.read_runtime()
    assert any(w[0] == ord("r") for w in transport.framed_writes)


def test_framed_transport_runtime_read_returns_correct_values() -> None:
    client, _ = _framed_client()
    snapshot = client.read_runtime()
    assert snapshot.as_dict() == {"rpm": 3000.0, "map": 95.0}


def test_framed_transport_page_read_is_framed() -> None:
    client, transport = _framed_client()
    transport.framed_writes.clear()
    client.invalidate_page_cache()
    client.read_parameter("reqFuel")
    assert any(w[0] == ord("p") for w in transport.framed_writes)


def test_framed_transport_page_read_returns_correct_value() -> None:
    client, _ = _framed_client()
    assert client.read_parameter("reqFuel") == 9.1


def test_framed_transport_page_write_is_framed() -> None:
    client, transport = _framed_client()
    transport.framed_writes.clear()
    client.write_parameter("reqFuel", 8.5)
    assert any(w[0] == ord("M") for w in transport.framed_writes)


def test_framed_transport_page_write_persists() -> None:
    client, transport = _framed_client()
    client.write_parameter("reqFuel", 8.5)
    assert transport.pages[1][12] == 85


def test_framed_transport_burn_is_framed() -> None:
    client, transport = _framed_client()
    client.write_parameter("reqFuel", 8.5)
    transport.framed_writes.clear()
    client.burn()
    assert any(w[0] == ord("b") for w in transport.framed_writes)


def test_framed_transport_burn_records_page() -> None:
    client, transport = _framed_client()
    client.write_parameter("reqFuel", 8.5)
    client.burn()
    assert 1 in transport.burn_requests


def test_framed_transport_table_read_is_framed() -> None:
    client, transport = _framed_client()
    transport.framed_writes.clear()
    client.invalidate_page_cache()
    client.read_parameter("veTable")
    assert any(w[0] == ord("p") for w in transport.framed_writes)


def test_framed_transport_table_read_returns_correct_values() -> None:
    client, _ = _framed_client()
    assert client.read_parameter("veTable") == [10.0, 20.0]
