from __future__ import annotations

import time
from dataclasses import dataclass, field

from tuner.domain.ecu_definition import EcuDefinition, LoggerDefinition, ScalarParameterDefinition, TableDefinition
from tuner.domain.firmware_capabilities import FirmwareCapabilities
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.parameters import ParameterValue
from tuner.transports.base import Transport


SEND_OUTPUT_CHANNELS = 0x30
CONNECT_PROBE_TIMEOUT_SECONDS = 1.5
SIGNATURE_PROBE_WINDOW_SECONDS = 1.5
REOPEN_DELAY_SECONDS = 0.15
FAILED_ATTEMPT_DELAY_SECONDS = 0.2


@dataclass(slots=True)
class SpeeduinoControllerClient:
    transport: Transport
    definition: EcuDefinition | None = None
    controller_name: str | None = None
    product_string: str | None = None
    firmware_signature: str | None = None
    capabilities: FirmwareCapabilities | None = None
    _page_cache: dict[int, bytes] = field(default_factory=dict)
    _dirty_pages: set[int] = field(default_factory=set)
    _connected: bool = False

    def connect(self) -> None:
        if self.definition is None:
            raise RuntimeError("A loaded ECU definition is required for Speeduino connections.")
        self.firmware_signature = self._connect_and_probe_signature()
        if not self.firmware_signature:
            raise RuntimeError(
                "Speeduino controller did not respond to serial signature probes after repeated port-open attempts. "
                "Check the selected COM port, baud rate, and whether the board resets or re-enumerates when the port is opened."
            )
        version_char = self._command_char(self.definition.version_info_command, "S")
        self.product_string = self._query_text(version_char, timeout=1.5)
        self.controller_name = self.product_string or self.firmware_signature or self.definition.name
        self.capabilities = self._read_capabilities()
        self._connected = True

    def disconnect(self) -> None:
        self._page_cache.clear()
        self._dirty_pages.clear()
        self._connected = False
        self.capabilities = None
        if self.transport.is_open():
            self.transport.close()

    def invalidate_page_cache(self) -> None:
        """Clear cached page data so the next read forces a fresh serial fetch."""
        self._page_cache.clear()

    def read_runtime(self) -> OutputChannelSnapshot:
        self._require_connection()
        if self.definition is None or not self.definition.output_channel_definitions:
            return OutputChannelSnapshot(values=[])
        packet_length = max(
            (field.offset or 0) + self._data_size(field.data_type)
            for field in self.definition.output_channel_definitions
        )
        payload = self._runtime_request(offset=0, length=packet_length)
        values = [
            OutputChannelValue(
                name=field.name,
                value=float(self._decode_scalar(field, payload)),
                units=field.units,
            )
            for field in self.definition.output_channel_definitions
            if field.offset is not None
        ]
        return OutputChannelSnapshot(values=values)

    def read_parameter(self, name: str) -> ParameterValue:
        self._require_connection()
        scalar = self._find_scalar(name)
        if scalar is not None:
            if scalar.page is None or scalar.offset is None:
                raise RuntimeError(f"Parameter {name} is not controller-backed.")
            page_data = self._read_page(scalar.page)
            return self._decode_scalar(scalar, page_data)
        table = self._find_table(name)
        if table is None or table.page is None or table.offset is None:
            raise RuntimeError(f"Unknown controller parameter: {name}")
        page_data = self._read_page(table.page)
        return self._decode_table(table, page_data)

    def write_parameter(self, name: str, value: ParameterValue) -> None:
        self._require_connection()
        scalar = self._find_scalar(name)
        if scalar is not None:
            if scalar.page is None or scalar.offset is None:
                raise RuntimeError(f"Parameter {name} is not controller-backed.")
            current_page = self._page_cache.get(scalar.page)
            if current_page is not None:
                current_page = bytearray(current_page)
            elif scalar.bit_offset is not None and scalar.bit_length is not None:
                size = self._data_size(scalar.data_type)
                current_page = bytearray(scalar.offset + size)
                current_page[scalar.offset : scalar.offset + size] = self._read_page_slice(scalar.page, scalar.offset, size)
            else:
                current_page = bytearray()
            encoded = self._encode_scalar(scalar, value, current_page)
            self._write_page_chunk(scalar.page, scalar.offset, encoded)
            self._update_cached_page_slice(scalar.page, scalar.offset, encoded)
            self._dirty_pages.add(scalar.page)
            return
        table = self._find_table(name)
        if table is None or table.page is None or table.offset is None:
            raise RuntimeError(f"Unknown controller parameter: {name}")
        encoded_values = self._encode_table(table, value)
        self._write_page_chunk(table.page, table.offset, encoded_values, is_table=True)
        self._update_cached_page_slice(table.page, table.offset, encoded_values)
        self._dirty_pages.add(table.page)

    def burn(self) -> None:
        self._require_connection()
        burn_char = self._command_char(self.definition.burn_command if self.definition else None, "b")
        for page in sorted(self._dirty_pages):
            self._send_data_command(bytes((ord(burn_char), 0x00, page & 0xFF)))
            time.sleep(0.02)
        self._dirty_pages.clear()

    def verify_crc(self) -> bool:
        return self._connected

    def write_calibration_table(self, page: int, payload: bytes) -> None:
        """Send a 64-byte calibration table to the ECU using the ``'t'`` command.

        Parameters
        ----------
        page:
            Calibration page: 0 = CLT, 1 = IAT, 2 = O2.
        payload:
            Exactly 64 bytes — 32 × big-endian uint16 temperatures in °F × 10,
            as produced by :meth:`ThermistorCalibrationResult.encode_payload`.
        """
        self._require_connection()
        if len(payload) != 64:
            raise ValueError(f"Calibration payload must be exactly 64 bytes, got {len(payload)}.")
        length = 64
        command = bytes([
            ord("t"),
            0x00,
            page & 0xFF,
            0x00, 0x00,                             # offset, big-endian (always 0)
            (length >> 8) & 0xFF, length & 0xFF,    # length, big-endian
        ]) + payload
        self._send_data_command(command)
        time.sleep(0.05)

    def send_controller_command(self, payload: bytes) -> None:
        """Send a raw ``[ControllerCommands]`` payload to the ECU.

        These commands (``E\\xSS\\xPP``) bypass normal page-sync — they are
        intended for bench operations such as injector/spark activation, STM32
        reboot, SD format, and VSS calibration.  No response is expected; a
        short settle delay is applied to avoid confusing subsequent commands.

        Parameters
        ----------
        payload:
            Raw bytes as decoded from the INI command string, e.g.
            ``b"E\\x02\\x01"`` to activate injector 1.
        """
        self._require_connection()
        self.transport.write(payload)
        time.sleep(0.02)

    def fetch_logger_data(self, logger: LoggerDefinition) -> bytes:
        """Capture a tooth or composite log buffer from the firmware.

        Flow
        ----
        1. Send the logger's ``startCommand`` (e.g. ``'H'`` for tooth).
        2. Poll the runtime block until ``toothLog1Ready`` bit is set, or the
           ``dataReadTimeout`` deadline is reached.
        3. Send the ``dataReadCommand`` and read back ``record_count × record_len``
           bytes of raw record data.
        4. Send the ``stopCommand`` (e.g. ``'h'``) to stop the logger.

        Returns the raw record bytes (header/footer already stripped — the
        Speeduino logger has no header or footer bytes, ``recordDef = 0,0,N``).

        Raises
        ------
        RuntimeError
            If the firmware never signals ready within the timeout, or if the
            response is truncated.
        """
        self._require_connection()
        # Step 1 — start
        self.transport.write(logger.start_command.encode("ascii"))
        time.sleep(0.05)
        # Step 2 — poll toothLog1Ready (byte 1, bit 6 of runtime block)
        deadline = time.monotonic() + logger.data_read_timeout_ms / 1000.0
        ready = False
        while time.monotonic() < deadline:
            try:
                raw = self._runtime_request(0, 2)  # bytes 0-1 contain status bits
                # toothLog1Ready = byte 1 bit 6
                if len(raw) >= 2 and (raw[1] & 0x40):
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.1)
        if not ready:
            self.transport.write(logger.stop_command.encode("ascii"))
            raise RuntimeError(
                f"Logger '{logger.name}' did not become ready within "
                f"{logger.data_read_timeout_ms} ms."
            )
        # Step 3 — read data
        expected = logger.record_count * logger.record_len
        self._send_data_command(logger.data_read_command)
        raw_data = self._recv_data_response(expected, logger.data_read_timeout_ms / 1000.0)
        # Step 4 — stop
        self.transport.write(logger.stop_command.encode("ascii"))
        time.sleep(0.02)
        return raw_data

    def _read_page(self, page: int) -> bytes:
        cached = self._page_cache.get(page)
        if cached is not None:
            return cached
        length = self._page_size(page)
        request = self._page_request(
            command=self._command_char(self.definition.page_read_command if self.definition else None, "p"),
            page=page,
            offset=0,
            length=length,
        )
        self._send_data_command(request)
        payload = self._recv_data_response(length, timeout=1.0)
        self._page_cache[page] = payload
        return payload

    def _write_page_chunk(self, page: int, offset: int, payload: bytes, *, is_table: bool = False) -> None:
        command = self._command_char(self.definition.page_value_write_command if self.definition else None, "M")
        max_chunk = self._effective_blocking_factor(is_table=is_table)
        sent = 0
        while sent < len(payload):
            chunk = payload[sent : sent + max_chunk]
            request = self._page_request(command=command, page=page, offset=offset + sent, length=len(chunk)) + chunk
            self._send_data_command(request)
            time.sleep(0.01)
            sent += len(chunk)

    def _effective_blocking_factor(self, *, is_table: bool = False) -> int:
        """Return the write chunk size, preferring firmware-advertised over INI over safe default.

        Table writes use ``table_blocking_factor`` when available; scalar writes
        use ``blocking_factor``.  Both fall back to the INI definition values and
        then to a conservative 128-byte default that is safe for all AVR boards.
        """
        if is_table:
            if self.capabilities is not None and self.capabilities.table_blocking_factor:
                return self.capabilities.table_blocking_factor
            if self.definition is not None and self.definition.table_blocking_factor:
                return self.definition.table_blocking_factor
        if self.capabilities is not None and self.capabilities.blocking_factor:
            return self.capabilities.blocking_factor
        if self.definition is not None and self.definition.blocking_factor:
            return self.definition.blocking_factor
        return 128  # conservative default, safe for all AVR boards

    def _read_page_slice(self, page: int, offset: int, length: int) -> bytes:
        request = self._page_request(
            command=self._command_char(self.definition.page_read_command if self.definition else None, "p"),
            page=page,
            offset=offset,
            length=length,
        )
        self._send_data_command(request)
        return self._recv_data_response(length, timeout=1.0)

    def _update_cached_page_slice(self, page: int, offset: int, payload: bytes) -> None:
        cached = self._page_cache.get(page)
        if cached is None:
            return
        current_page = bytearray(cached)
        current_page[offset : offset + len(payload)] = payload
        self._page_cache[page] = bytes(current_page)

    def _runtime_request(self, offset: int, length: int) -> bytes:
        request = bytes(
            (
                ord("r"),
                0x00,
                SEND_OUTPUT_CHANNELS,
                offset & 0xFF,
                (offset >> 8) & 0xFF,
                length & 0xFF,
                (length >> 8) & 0xFF,
            )
        )
        self._send_data_command(request)
        return self._recv_data_response(length, timeout=0.5)

    @staticmethod
    def _page_request(command: str, page: int, offset: int, length: int) -> bytes:
        return bytes(
            (
                ord(command),
                0x00,
                page & 0xFF,
                offset & 0xFF,
                (offset >> 8) & 0xFF,
                length & 0xFF,
                (length >> 8) & 0xFF,
            )
        )

    @staticmethod
    def _command_char(raw: str | None, fallback: str) -> str:
        if not raw:
            return fallback
        return raw[0]

    def _query_text(self, command: str, timeout: float = CONNECT_PROBE_TIMEOUT_SECONDS) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._clear_buffers()
            self.transport.write(command.encode("ascii"))
            response = self._read_text_response()
            if response:
                return response
            time.sleep(0.05)
        return ""

    def _read_text_response(self) -> str:
        chunks: list[bytes] = []
        idle_deadline = time.monotonic() + 0.5
        while time.monotonic() < idle_deadline:
            chunk = self.transport.read(256, timeout=0.1)
            if chunk:
                chunks.append(chunk)
                idle_deadline = time.monotonic() + 0.1
                continue
            if chunks:
                break
        return b"".join(chunks).replace(b"\x00", b"").decode("utf-8", errors="ignore").strip()

    def _read_capabilities(self) -> FirmwareCapabilities:
        payload = self._query_capability_payload()
        serial_protocol_version: int | None = None
        blocking_factor: int | None = None
        table_blocking_factor: int | None = None
        source = "definition"
        if payload is not None and len(payload) >= 6 and payload[0] == 0x00:
            serial_protocol_version = payload[1]
            blocking_factor = (payload[2] << 8) | payload[3]
            table_blocking_factor = (payload[4] << 8) | payload[5]
            source = "serial+definition"
        return FirmwareCapabilities(
            source=source,
            serial_protocol_version=serial_protocol_version,
            blocking_factor=blocking_factor,
            table_blocking_factor=table_blocking_factor,
            live_data_size=self._live_data_size(),
            supports_board_capabilities_channel=self._has_output_channel("boardCapabilities", "boardCap_rtc"),
            supports_spi_flash_health_channel=self._has_output_channel("spiFlashHealth"),
            supports_runtime_status_a=self._has_output_channel("runtimeStatusA", "rSA_tuneValid"),
            experimental_u16p2="U16P2" in (self.firmware_signature or "").upper(),
        )

    def _query_capability_payload(self) -> bytes | None:
        try:
            self._clear_buffers()
            self._send_data_command(b"f")
            return self._recv_data_response(6, timeout=0.3)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Framing-aware send / receive helpers
    # ------------------------------------------------------------------
    #
    # When the transport is a TcpTransport (WiFi via Airbear bridge) every
    # non-handshake data command must be sent with Speeduino new-protocol
    # framing:  [u16 LE len][payload][u32 LE CRC32].  The ECU responds in
    # the same format and the bridge passes both directions transparently.
    #
    # Handshake commands (Q / S) remain unframed — the Airbear bridge has a
    # special-case path for 'F'/'Q'/'S' that writes the raw byte to the ECU
    # and returns the raw response.  Our _query_text() / _probe_signature()
    # paths already call transport.write() directly, so they are unaffected.

    def _send_data_command(self, payload: bytes) -> None:
        """Send a data command — framed for TCP, raw for serial."""
        write_framed = getattr(self.transport, "write_framed", None)
        if callable(write_framed):
            write_framed(payload)
        else:
            self.transport.write(payload)

    def _recv_data_response(self, size: int, timeout: float) -> bytes:
        """Receive a data response — strips framing for TCP, raw bytes for serial.

        For TCP the expected *size* is used only as a sanity check; the true
        length comes from the frame header.
        """
        read_framed = getattr(self.transport, "read_framed_response", None)
        if callable(read_framed):
            payload = read_framed(timeout)
            if len(payload) < size:
                raise RuntimeError(
                    f"Framed response too short: expected {size} bytes, got {len(payload)}."
                )
            return payload[:size]
        return self._read_exact(size, timeout)

    def _read_exact(self, size: int, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        buffer = bytearray()
        while len(buffer) < size and time.monotonic() < deadline:
            chunk = self.transport.read(size - len(buffer), timeout=0.1)
            if chunk:
                buffer.extend(chunk)
                continue
        if len(buffer) < size:
            raise RuntimeError(f"Timed out waiting for {size} bytes from Speeduino controller.")
        return bytes(buffer)

    def _live_data_size(self) -> int | None:
        if self.definition is None or not self.definition.output_channel_definitions:
            return None
        return max(
            ((field.offset or 0) + self._data_size(field.data_type))
            for field in self.definition.output_channel_definitions
        )

    def _has_output_channel(self, *names: str) -> bool:
        if self.definition is None:
            return False
        defined_names = {field.name for field in self.definition.output_channel_definitions}
        return any(name in defined_names for name in names)

    def _drain_input(self) -> None:
        idle_deadline = time.monotonic() + 0.25
        while time.monotonic() < idle_deadline:
            if not self.transport.read(256, timeout=0.05):
                break

    def _settle_after_open(self) -> None:
        self._clear_buffers()
        time.sleep(self._connect_delay_seconds())
        self._clear_buffers()

    def _clear_buffers(self) -> None:
        clear_buffers = getattr(self.transport, "clear_buffers", None)
        if callable(clear_buffers):
            clear_buffers()
        self._drain_input()

    def _probe_signature(self) -> str:
        deadline = time.monotonic() + SIGNATURE_PROBE_WINDOW_SECONDS
        candidates = self._signature_probe_candidates()
        while time.monotonic() < deadline:
            for command in candidates:
                response = self._query_text(command)
                if not response:
                    continue
                if response == command:
                    continue
                if command == "F":
                    continue
                return response
            time.sleep(0.05)
        return ""

    def _connect_and_probe_signature(self) -> str:
        last_baud_rate = self._get_transport_baud_rate()
        for baud_rate in self._baud_probe_candidates():
            if baud_rate is not None:
                self._set_transport_baud_rate(baud_rate)
            self._reopen_transport()
            self._settle_after_open()
            signature = self._probe_signature()
            if signature:
                return signature
            self.disconnect()
            time.sleep(FAILED_ATTEMPT_DELAY_SECONDS)
        if last_baud_rate is not None:
            self._set_transport_baud_rate(last_baud_rate)
        return ""

    def _signature_probe_candidates(self) -> list[str]:
        seen: set[str] = set()
        candidates: list[str] = []
        for raw in (
            self.definition.query_command if self.definition else None,
            self.definition.version_info_command if self.definition else None,
            "F",
            "Q",
            "S",
        ):
            command = self._command_char(raw, "")
            if not command or command in seen:
                continue
            seen.add(command)
            candidates.append(command)
        return candidates

    def _baud_probe_candidates(self) -> list[int | None]:
        current = self._get_transport_baud_rate()
        candidates: list[int | None] = []
        seen: set[int] = set()
        for value in (current, 115200, 230400, 57600, 9600):
            if value is None or value in seen:
                continue
            seen.add(value)
            candidates.append(value)
        return candidates or [None]

    def _get_transport_baud_rate(self) -> int | None:
        baud_rate = getattr(self.transport, "baud_rate", None)
        if isinstance(baud_rate, int) and baud_rate > 0:
            return baud_rate
        return None

    def _set_transport_baud_rate(self, baud_rate: int) -> None:
        if hasattr(self.transport, "baud_rate"):
            setattr(self.transport, "baud_rate", baud_rate)

    def _reopen_transport(self) -> None:
        if self.transport.is_open():
            self.transport.close()
            time.sleep(REOPEN_DELAY_SECONDS)
        self.transport.open()

    def _connect_delay_seconds(self) -> float:
        if self.definition is not None:
            raw_value = (
                self.definition.metadata.get("controllerConnectDelay")
                or self.definition.metadata.get("connectDelay")
                or self.definition.metadata.get("interWriteDelay")
            )
            if raw_value:
                try:
                    delay_ms = float(str(raw_value).strip().split(",", 1)[0])
                    if delay_ms > 0:
                        return delay_ms / 1000.0
                except ValueError:
                    pass
        return 1.5

    def _page_size(self, page: int) -> int:
        if self.definition and 0 < page <= len(self.definition.page_sizes):
            return self.definition.page_sizes[page - 1]
        max_offset = 0
        if self.definition is None:
            raise RuntimeError("A loaded ECU definition is required for page operations.")
        for scalar in self.definition.scalars:
            if scalar.page == page and scalar.offset is not None:
                max_offset = max(max_offset, scalar.offset + self._data_size(scalar.data_type))
        for table in self.definition.tables:
            if table.page == page and table.offset is not None:
                max_offset = max(max_offset, table.offset + (self._data_size(table.data_type) * table.rows * table.columns))
        if max_offset <= 0:
            raise RuntimeError(f"Unable to determine size for Speeduino page {page}.")
        return max_offset

    def _find_scalar(self, name: str) -> ScalarParameterDefinition | None:
        if self.definition is None:
            return None
        return next((item for item in self.definition.scalars if item.name == name), None)

    def _find_table(self, name: str) -> TableDefinition | None:
        if self.definition is None:
            return None
        return next((item for item in self.definition.tables if item.name == name), None)

    @staticmethod
    def _data_size(data_type: str) -> int:
        normalized = data_type.upper()
        if normalized in {"U08", "S08"}:
            return 1
        if normalized in {"U16", "S16"}:
            return 2
        if normalized in {"U32", "S32", "F32"}:
            return 4
        raise RuntimeError(f"Unsupported Speeduino data type: {data_type}")

    def _decode_scalar(self, definition: ScalarParameterDefinition, payload: bytes) -> int | float:
        if definition.offset is None:
            raise RuntimeError(f"Parameter {definition.name} has no offset.")
        size = self._data_size(definition.data_type)
        raw = payload[definition.offset : definition.offset + size]
        value = self._decode_raw_value(raw, definition.data_type)
        if definition.bit_offset is not None and definition.bit_length is not None:
            mask = (1 << definition.bit_length) - 1
            value = (int(value) >> definition.bit_offset) & mask
            return value
        scale = definition.scale if definition.scale is not None else 1.0
        translate = definition.translate if definition.translate is not None else 0.0
        return (float(value) * scale) + translate

    def _decode_table(self, table: TableDefinition, payload: bytes) -> list[float]:
        if table.offset is None:
            raise RuntimeError(f"Table {table.name} has no offset.")
        item_size = self._data_size(table.data_type)
        values: list[float] = []
        scale = table.scale if table.scale is not None else 1.0
        translate = table.translate if table.translate is not None else 0.0
        total = table.rows * table.columns
        for index in range(total):
            start = table.offset + (index * item_size)
            raw = payload[start : start + item_size]
            values.append((float(self._decode_raw_value(raw, table.data_type)) * scale) + translate)
        return values

    def _encode_scalar(
        self,
        definition: ScalarParameterDefinition,
        value: ParameterValue,
        current_page: bytearray,
    ) -> bytes:
        if definition.offset is None:
            raise RuntimeError(f"Parameter {definition.name} has no offset.")
        size = self._data_size(definition.data_type)
        if definition.bit_offset is not None and definition.bit_length is not None:
            raw = current_page[definition.offset : definition.offset + size]
            current_value = int(self._decode_raw_value(raw, definition.data_type))
            mask = ((1 << definition.bit_length) - 1) << definition.bit_offset
            encoded_value = (current_value & ~mask) | ((int(value) << definition.bit_offset) & mask)
            return self._encode_raw_value(encoded_value, definition.data_type)
        scale = definition.scale if definition.scale not in {None, 0} else 1.0
        translate = definition.translate if definition.translate is not None else 0.0
        raw_value = round((float(value) - translate) / scale)
        return self._encode_raw_value(raw_value, definition.data_type)

    def _encode_table(self, table: TableDefinition, value: ParameterValue) -> bytes:
        if not isinstance(value, list):
            raise RuntimeError(f"Table {table.name} expects a list value.")
        scale = table.scale if table.scale not in {None, 0} else 1.0
        translate = table.translate if table.translate is not None else 0.0
        payload = bytearray()
        for item in value:
            raw_value = round((float(item) - translate) / scale)
            payload.extend(self._encode_raw_value(raw_value, table.data_type))
        return bytes(payload)

    @staticmethod
    def _decode_raw_value(raw: bytes, data_type: str) -> int | float:
        normalized = data_type.upper()
        byteorder = "little"
        if normalized == "U08":
            return raw[0]
        if normalized == "S08":
            return int.from_bytes(raw[:1], byteorder=byteorder, signed=True)
        if normalized == "U16":
            return int.from_bytes(raw[:2], byteorder=byteorder, signed=False)
        if normalized == "S16":
            return int.from_bytes(raw[:2], byteorder=byteorder, signed=True)
        if normalized == "U32":
            return int.from_bytes(raw[:4], byteorder=byteorder, signed=False)
        if normalized == "S32":
            return int.from_bytes(raw[:4], byteorder=byteorder, signed=True)
        if normalized == "F32":
            import struct

            return float(struct.unpack("<f", raw[:4])[0])
        raise RuntimeError(f"Unsupported Speeduino data type: {data_type}")

    @staticmethod
    def _encode_raw_value(value: int | float, data_type: str) -> bytes:
        normalized = data_type.upper()
        if normalized == "U08":
            return int(value).to_bytes(1, byteorder="little", signed=False)
        if normalized == "S08":
            return int(value).to_bytes(1, byteorder="little", signed=True)
        if normalized == "U16":
            return int(value).to_bytes(2, byteorder="little", signed=False)
        if normalized == "S16":
            return int(value).to_bytes(2, byteorder="little", signed=True)
        if normalized == "U32":
            return int(value).to_bytes(4, byteorder="little", signed=False)
        if normalized == "S32":
            return int(value).to_bytes(4, byteorder="little", signed=True)
        if normalized == "F32":
            import struct

            return struct.pack("<f", float(value))
        raise RuntimeError(f"Unsupported Speeduino data type: {data_type}")

    def _require_connection(self) -> None:
        if not self._connected:
            raise RuntimeError("Speeduino controller is not connected.")
