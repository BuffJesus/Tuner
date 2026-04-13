from __future__ import annotations

import socket
import struct
import zlib


_MDNS_SUFFIX = ".local"
_MDNS_RESOLVE_TIMEOUT = 5.0  # seconds — mDNS resolution can be slow on first query


class TcpTransport:
    """TCP transport that speaks identical framing to SerialTransport.

    Suitable for the Airbear ESP32-C3 TunerStudio TCP bridge (port 2000) or any
    other socket endpoint that relays the Speeduino raw command protocol.

    mDNS hostnames (e.g. ``speeduino.local``) are resolved by the OS resolver
    transparently — no additional dependency is required on platforms with Bonjour
    or Avahi (Windows with Bonjour, macOS natively, Linux with avahi-daemon).
    """

    def __init__(self, host: str, port: int, connect_timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self._connect_timeout = connect_timeout
        self._socket: socket.socket | None = None

    def open(self) -> None:
        if self._socket is not None:
            return
        # For .local mDNS addresses, allow a longer timeout on the first lookup.
        timeout = (
            _MDNS_RESOLVE_TIMEOUT
            if self.host.lower().endswith(_MDNS_SUFFIX)
            else self._connect_timeout
        )
        self._socket = socket.create_connection((self.host, self.port), timeout=timeout)
        # Switch to blocking mode with no timeout so that downstream callers can
        # control read timeouts per-call via the timeout parameter.
        self._socket.settimeout(None)

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        except Exception:
            pass
        self._socket = None

    def read(self, size: int, timeout: float | None = None) -> bytes:
        """Read up to *size* bytes.

        Returns fewer bytes than requested when the timeout expires (same
        semantics as SerialTransport / pyserial).  A zero-length response
        indicates the timeout elapsed with no data — callers should loop via
        ``_read_exact`` in SpeeduinoControllerClient.
        """
        if self._socket is None:
            raise RuntimeError("TCP transport is not open.")
        self._socket.settimeout(timeout)
        try:
            data = self._socket.recv(size)
        except (TimeoutError, socket.timeout):
            data = b""
        finally:
            self._socket.settimeout(None)
        return data

    def write(self, data: bytes) -> int:
        if self._socket is None:
            raise RuntimeError("TCP transport is not open.")
        self._socket.sendall(data)
        return len(data)

    def is_open(self) -> bool:
        return self._socket is not None

    # ------------------------------------------------------------------
    # Speeduino new-protocol framing (required for Airbear TCP bridge)
    # ------------------------------------------------------------------
    #
    # The Airbear ESP32-C3 TunerStudio TCP bridge (tcp-uart.cpp) expects every
    # non-handshake command (anything other than 'F'/'Q'/'S') to arrive wrapped
    # in Speeduino new-protocol framing:
    #
    #   [u16 LE payload_length] [payload bytes] [u32 LE CRC32(payload)]
    #
    # The ECU (Teensy Serial2, new protocol handler) responds in the same format.
    # The bridge transparently proxies both directions, so Python must speak
    # the same framing as TunerStudio.
    #
    # SpeeduinoControllerClient detects these methods via getattr and switches
    # to the framed path automatically when the transport is a TcpTransport.

    def write_framed(self, payload: bytes) -> None:
        """Send *payload* wrapped in Speeduino new-protocol framing.

        Frame layout::

            [u16 LE length=len(payload)] [payload] [u32 LE CRC32(payload)]
        """
        if self._socket is None:
            raise RuntimeError("TCP transport is not open.")
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        frame = struct.pack("<H", len(payload)) + payload + struct.pack("<I", crc)
        self._socket.sendall(frame)

    def read_framed_response(self, timeout: float = 1.0) -> bytes:
        """Read one Speeduino new-protocol response frame and return the payload.

        Frame layout::

            [u16 LE payload_length] [payload bytes] [u32 LE CRC32(payload)]

        CRC is read but not validated — the Airbear bridge itself does not
        validate CRC before forwarding, so a mismatch would only indicate a
        transport-layer corruption that would be caught at the protocol level.

        Raises ``RuntimeError`` if the header or payload cannot be read within
        *timeout* seconds.
        """
        header = self._recv_exactly(2, timeout)
        payload_length = struct.unpack("<H", header)[0]
        body = self._recv_exactly(payload_length + 4, timeout)  # payload + CRC
        return body[:payload_length]

    def _recv_exactly(self, size: int, timeout: float) -> bytes:
        """Read exactly *size* bytes, raising RuntimeError on timeout."""
        import time
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while len(buf) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"TCP framing timeout: expected {size} bytes, got {len(buf)}."
                )
            self._socket.settimeout(min(remaining, 0.1))  # type: ignore[union-attr]
            try:
                chunk = self._socket.recv(size - len(buf))  # type: ignore[union-attr]
            except (TimeoutError, socket.timeout):
                chunk = b""
            finally:
                self._socket.settimeout(None)  # type: ignore[union-attr]
            if not chunk:
                continue
            buf.extend(chunk)
        return bytes(buf)

    def clear_buffers(self) -> None:
        """Drain any pending input data from the socket receive buffer.

        Called by SpeeduinoControllerClient._clear_buffers() after open and
        before each command to flush stale bytes (same role as serial port
        reset_input_buffer).
        """
        if self._socket is None:
            return
        self._socket.settimeout(0.0)
        try:
            while True:
                chunk = self._socket.recv(256)
                if not chunk:
                    break
        except (BlockingIOError, socket.timeout, TimeoutError, OSError):
            pass
        finally:
            self._socket.settimeout(None)
