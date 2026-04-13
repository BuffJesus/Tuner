"""Unit tests for TcpTransport using a loopback socket pair (no network required)."""
from __future__ import annotations

import socket
import threading
import time

import pytest

from tuner.transports.tcp_transport import TcpTransport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loopback_server() -> tuple[socket.socket, int]:
    """Bind a listening socket on a free loopback port and return (server_sock, port)."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    _, port = server.getsockname()
    return server, port


# ---------------------------------------------------------------------------
# Basic open / close
# ---------------------------------------------------------------------------

def test_transport_opens_and_closes() -> None:
    server, port = _loopback_server()
    conn_holder: list[socket.socket] = []
    done = threading.Event()

    def _accept() -> None:
        conn, _ = server.accept()
        conn_holder.append(conn)
        done.wait(timeout=2.0)
        conn.close()

    t = threading.Thread(target=_accept, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        assert not transport.is_open()
        transport.open()
        assert transport.is_open()
        transport.close()
        assert not transport.is_open()
    finally:
        done.set()
        server.close()
        t.join(timeout=2.0)


def test_transport_open_is_idempotent() -> None:
    server, port = _loopback_server()
    conns: list[socket.socket] = []
    accepted = threading.Event()
    done = threading.Event()

    def _accept_all() -> None:
        server.settimeout(1.0)
        for _ in range(5):
            try:
                conn, _ = server.accept()
                conns.append(conn)
                accepted.set()
            except (socket.timeout, OSError):
                break
        done.wait(timeout=2.0)
        for c in conns:
            c.close()

    t = threading.Thread(target=_accept_all, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        accepted.wait(timeout=2.0)
        transport.open()  # should not open a second connection
        assert transport.is_open()
        assert len(conns) == 1
    finally:
        transport.close()
        done.set()
        server.close()
        t.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Write / read round-trip
# ---------------------------------------------------------------------------

def test_write_and_read_round_trip() -> None:
    server, port = _loopback_server()
    server_conn: list[socket.socket] = []
    ready = threading.Event()
    done = threading.Event()

    def _echo_server() -> None:
        conn, _ = server.accept()
        server_conn.append(conn)
        ready.set()
        # Echo all received bytes back
        while not done.is_set():
            try:
                conn.settimeout(0.2)
                data = conn.recv(256)
                if data:
                    conn.sendall(data)
            except (socket.timeout, OSError):
                break
        conn.close()

    t = threading.Thread(target=_echo_server, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        ready.wait(timeout=2.0)

        n = transport.write(b"hello")
        assert n == 5

        # Give the echo server time to bounce it back
        time.sleep(0.05)
        data = transport.read(5, timeout=1.0)
        assert data == b"hello"
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)


def test_write_returns_full_length() -> None:
    server, port = _loopback_server()
    done = threading.Event()

    def _accept_drain() -> None:
        conn, _ = server.accept()
        done.wait(timeout=2.0)
        conn.close()

    t = threading.Thread(target=_accept_drain, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        payload = b"x" * 64
        n = transport.write(payload)
        assert n == len(payload)
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Read timeout
# ---------------------------------------------------------------------------

def test_read_returns_empty_on_timeout() -> None:
    server, port = _loopback_server()
    done = threading.Event()

    def _accept_idle() -> None:
        conn, _ = server.accept()
        done.wait(timeout=3.0)  # send nothing
        conn.close()

    t = threading.Thread(target=_accept_idle, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        # 50 ms timeout → nothing arrives → empty bytes
        data = transport.read(16, timeout=0.05)
        assert data == b""
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)


# ---------------------------------------------------------------------------
# clear_buffers
# ---------------------------------------------------------------------------

def test_clear_buffers_drains_pending_data() -> None:
    server, port = _loopback_server()
    ready = threading.Event()
    done = threading.Event()

    def _send_junk() -> None:
        conn, _ = server.accept()
        conn.sendall(b"\xff" * 32)  # pre-send junk
        ready.set()
        done.wait(timeout=2.0)
        conn.close()

    t = threading.Thread(target=_send_junk, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        ready.wait(timeout=2.0)
        time.sleep(0.05)  # let the junk arrive in the socket buffer
        transport.clear_buffers()
        # After clearing, a short read should return nothing
        data = transport.read(32, timeout=0.05)
        assert data == b""
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)


def test_clear_buffers_noop_when_not_open() -> None:
    transport = TcpTransport("127.0.0.1", 9999)
    transport.clear_buffers()  # must not raise


# ---------------------------------------------------------------------------
# Error on read/write when closed
# ---------------------------------------------------------------------------

def test_read_raises_when_closed() -> None:
    transport = TcpTransport("127.0.0.1", 9999)
    with pytest.raises(RuntimeError, match="not open"):
        transport.read(1)


def test_write_raises_when_closed() -> None:
    transport = TcpTransport("127.0.0.1", 9999)
    with pytest.raises(RuntimeError, match="not open"):
        transport.write(b"x")


# ---------------------------------------------------------------------------
# mDNS suffix detection
# ---------------------------------------------------------------------------

def test_mdns_host_is_recognised() -> None:
    """TcpTransport stores the host unchanged; .local suffix is handled at open() time."""
    transport = TcpTransport("speeduino.local", 2000)
    assert transport.host == "speeduino.local"
    assert transport.port == 2000


def test_non_mdns_host_uses_normal_timeout() -> None:
    transport = TcpTransport("192.168.1.100", 2000, connect_timeout=3.0)
    assert transport._connect_timeout == 3.0


# ---------------------------------------------------------------------------
# Speeduino new-protocol framing (write_framed / read_framed_response)
# ---------------------------------------------------------------------------

def _framed(payload: bytes) -> bytes:
    """Build a Speeduino new-protocol frame for *payload*."""
    import struct, zlib
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return struct.pack("<H", len(payload)) + payload + struct.pack("<I", crc)


def test_write_framed_sends_length_payload_crc() -> None:
    server, port = _loopback_server()
    received: list[bytes] = []
    ready = threading.Event()
    done = threading.Event()

    def _capture() -> None:
        conn, _ = server.accept()
        ready.set()
        buf = bytearray()
        conn.settimeout(1.0)
        try:
            while not done.is_set():
                try:
                    chunk = conn.recv(256)
                    if chunk:
                        buf.extend(chunk)
                except (socket.timeout, OSError):
                    break
        finally:
            received.append(bytes(buf))
            conn.close()

    t = threading.Thread(target=_capture, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        ready.wait(timeout=2.0)
        payload = b"r\x00\x30\x00\x00\x00\x94"
        transport.write_framed(payload)
        time.sleep(0.05)
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)

    assert len(received) == 1
    data = received[0]
    assert data == _framed(payload)


def test_write_framed_length_field_is_little_endian() -> None:
    import struct
    server, port = _loopback_server()
    received: list[bytes] = []
    done = threading.Event()

    def _capture() -> None:
        conn, _ = server.accept()
        buf = bytearray()
        conn.settimeout(0.5)
        try:
            while True:
                chunk = conn.recv(256)
                if not chunk:
                    break
                buf.extend(chunk)
        except (socket.timeout, OSError):
            pass
        received.append(bytes(buf))
        conn.close()

    t = threading.Thread(target=_capture, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        payload = b"x" * 300  # length > 255 so we can verify LE encoding
        transport.write_framed(payload)
        time.sleep(0.1)
    finally:
        transport.close()
        server.close()
        t.join(timeout=2.0)

    data = received[0]
    length_field = struct.unpack("<H", data[:2])[0]
    assert length_field == 300


def test_write_framed_crc32_is_correct() -> None:
    import struct, zlib
    server, port = _loopback_server()
    received: list[bytes] = []
    done = threading.Event()

    def _capture() -> None:
        conn, _ = server.accept()
        buf = bytearray()
        conn.settimeout(0.5)
        try:
            while True:
                chunk = conn.recv(256)
                if not chunk:
                    break
                buf.extend(chunk)
        except (socket.timeout, OSError):
            pass
        received.append(bytes(buf))
        conn.close()

    t = threading.Thread(target=_capture, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        payload = b"hello speeduino"
        transport.write_framed(payload)
        time.sleep(0.05)
    finally:
        transport.close()
        server.close()
        t.join(timeout=2.0)

    data = received[0]
    payload_len = struct.unpack("<H", data[:2])[0]
    received_payload = data[2 : 2 + payload_len]
    received_crc = struct.unpack("<I", data[2 + payload_len :])[0]
    expected_crc = zlib.crc32(received_payload) & 0xFFFFFFFF
    assert received_crc == expected_crc


def test_read_framed_response_strips_header_and_crc() -> None:
    server, port = _loopback_server()
    done = threading.Event()
    payload = b"\x01\x02\x03\x04\x05"

    def _send_frame() -> None:
        conn, _ = server.accept()
        conn.sendall(_framed(payload))
        done.wait(timeout=2.0)
        conn.close()

    t = threading.Thread(target=_send_frame, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        result = transport.read_framed_response(timeout=1.0)
        assert result == payload
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)


def test_read_framed_response_multi_byte_payload() -> None:
    server, port = _loopback_server()
    done = threading.Event()
    payload = bytes(range(148))  # typical Speeduino OCH block size

    def _send_frame() -> None:
        conn, _ = server.accept()
        conn.sendall(_framed(payload))
        done.wait(timeout=2.0)
        conn.close()

    t = threading.Thread(target=_send_frame, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        result = transport.read_framed_response(timeout=1.0)
        assert result == payload
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)


def test_read_framed_response_timeout_raises() -> None:
    server, port = _loopback_server()
    done = threading.Event()

    def _accept_idle() -> None:
        conn, _ = server.accept()
        done.wait(timeout=3.0)  # send nothing
        conn.close()

    t = threading.Thread(target=_accept_idle, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        with pytest.raises(RuntimeError, match="timeout"):
            transport.read_framed_response(timeout=0.1)
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)


def test_framed_round_trip() -> None:
    """write_framed then read_framed_response via echo server."""
    server, port = _loopback_server()
    ready = threading.Event()
    done = threading.Event()

    def _echo_frames() -> None:
        conn, _ = server.accept()
        ready.set()
        buf = bytearray()
        conn.settimeout(1.0)
        try:
            while not done.is_set():
                try:
                    chunk = conn.recv(256)
                    if chunk:
                        buf.extend(chunk)
                        # Echo once we have a full frame (2+len+4)
                        if len(buf) >= 2:
                            import struct
                            plen = struct.unpack("<H", bytes(buf[:2]))[0]
                            if len(buf) >= 2 + plen + 4:
                                conn.sendall(bytes(buf[:2 + plen + 4]))
                                buf = buf[2 + plen + 4:]
                except (socket.timeout, OSError):
                    break
        finally:
            conn.close()

    t = threading.Thread(target=_echo_frames, daemon=True)
    t.start()
    try:
        transport = TcpTransport("127.0.0.1", port)
        transport.open()
        ready.wait(timeout=2.0)
        payload = b"r\x00\x30\x00\x00\x00\x94"  # typical runtime request
        transport.write_framed(payload)
        result = transport.read_framed_response(timeout=1.0)
        assert result == payload
    finally:
        done.set()
        transport.close()
        server.close()
        t.join(timeout=2.0)
