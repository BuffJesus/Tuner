"""Focused unit tests for LiveDataHttpServer.

Tests spin up a real HTTPServer on a free loopback port and exercise
the three JSON endpoints via urllib.request — no mocking required.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from unittest.mock import MagicMock

import pytest

from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.services.live_data_http_server import LiveDataHttpServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Return a free TCP port on loopback."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _snapshot(*pairs: tuple[str, float, str]) -> OutputChannelSnapshot:
    """Build an OutputChannelSnapshot from (name, value, units) tuples."""
    values = [OutputChannelValue(name=n, value=v, units=u) for n, v, u in pairs]
    snap = MagicMock(spec=OutputChannelSnapshot)
    snap.values = values
    return snap


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_server_starts_and_stops() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    assert not server.is_running
    server.start()
    assert server.is_running
    assert server.port == port
    server.stop()
    assert not server.is_running


def test_start_is_idempotent() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    server.start()  # second call must not raise or open a second socket
    assert server.is_running
    server.stop()


def test_stop_when_not_started_is_noop() -> None:
    server = LiveDataHttpServer(port=_free_port())
    server.stop()  # must not raise


# ---------------------------------------------------------------------------
# /api/channels — all channels
# ---------------------------------------------------------------------------

def test_channels_empty_before_snapshot() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    try:
        status, data = _get(f"http://127.0.0.1:{port}/api/channels")
        assert status == 200
        assert data == {}
    finally:
        server.stop()


def test_channels_returns_snapshot_values() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.update_snapshot(_snapshot(("rpm", 1500.0, "rpm"), ("map", 95.0, "kPa")))
    server.start()
    try:
        status, data = _get(f"http://127.0.0.1:{port}/api/channels")
        assert status == 200
        assert data["rpm"] == pytest.approx(1500.0)
        assert data["map"] == pytest.approx(95.0)
    finally:
        server.stop()


def test_channels_updates_on_new_snapshot() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    try:
        server.update_snapshot(_snapshot(("rpm", 1000.0, "rpm")))
        _, data1 = _get(f"http://127.0.0.1:{port}/api/channels")
        assert data1["rpm"] == pytest.approx(1000.0)

        server.update_snapshot(_snapshot(("rpm", 2000.0, "rpm")))
        _, data2 = _get(f"http://127.0.0.1:{port}/api/channels")
        assert data2["rpm"] == pytest.approx(2000.0)
    finally:
        server.stop()


def test_channels_clears_on_none_snapshot() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.update_snapshot(_snapshot(("rpm", 1500.0, "rpm")))
    server.start()
    try:
        server.update_snapshot(None)
        _, data = _get(f"http://127.0.0.1:{port}/api/channels")
        assert data == {}
    finally:
        server.stop()


def test_channels_returns_all_fields() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.update_snapshot(_snapshot(
        ("rpm", 1200.0, "rpm"),
        ("map", 80.0, "kPa"),
        ("clt", 85.0, "°C"),
    ))
    server.start()
    try:
        _, data = _get(f"http://127.0.0.1:{port}/api/channels")
        assert set(data.keys()) == {"rpm", "map", "clt"}
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# /api/channels/{name} — single channel
# ---------------------------------------------------------------------------

def test_single_channel_found() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.update_snapshot(_snapshot(("rpm", 3000.0, "rpm")))
    server.start()
    try:
        status, data = _get(f"http://127.0.0.1:{port}/api/channels/rpm")
        assert status == 200
        assert data["name"] == "rpm"
        assert data["value"] == pytest.approx(3000.0)
        assert data["units"] == "rpm"
    finally:
        server.stop()


def test_single_channel_not_found_returns_404() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    try:
        status, data = _get(f"http://127.0.0.1:{port}/api/channels/nonexistent")
        assert status == 404
        assert "error" in data
    finally:
        server.stop()


def test_single_channel_units_empty_string_when_absent() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    # OutputChannelValue with empty units
    values = [OutputChannelValue(name="tps", value=25.0, units="")]
    snap = MagicMock(spec=OutputChannelSnapshot)
    snap.values = values
    server.update_snapshot(snap)
    server.start()
    try:
        _, data = _get(f"http://127.0.0.1:{port}/api/channels/tps")
        assert data["units"] == ""
    finally:
        server.stop()


def test_single_channel_fractional_value() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.update_snapshot(_snapshot(("lambda1", 0.998, "")))
    server.start()
    try:
        _, data = _get(f"http://127.0.0.1:{port}/api/channels/lambda1")
        assert data["value"] == pytest.approx(0.998)
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# /api/status
# ---------------------------------------------------------------------------

def test_status_default_offline() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    try:
        status, data = _get(f"http://127.0.0.1:{port}/api/status")
        assert status == 200
        assert data["connected"] is False
        assert data["sync_state"] == "offline"
        assert data["port"] == port
    finally:
        server.stop()


def test_status_connected() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.update_status(connected=True, sync_state="clean")
    server.start()
    try:
        _, data = _get(f"http://127.0.0.1:{port}/api/status")
        assert data["connected"] is True
        assert data["sync_state"] == "clean"
        assert data["port"] == port
    finally:
        server.stop()


def test_status_updates_after_disconnect() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.update_status(connected=True, sync_state="clean")
    server.start()
    try:
        server.update_status(connected=False, sync_state="offline")
        _, data = _get(f"http://127.0.0.1:{port}/api/status")
        assert data["connected"] is False
        assert data["sync_state"] == "offline"
    finally:
        server.stop()


def test_status_port_reflects_constructor_arg() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    try:
        _, data = _get(f"http://127.0.0.1:{port}/api/status")
        assert data["port"] == port
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------

def test_cors_header_on_channels() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/channels", timeout=3) as resp:
            assert resp.headers.get("Access-Control-Allow-Origin") == "*"
    finally:
        server.stop()


def test_cors_header_on_status() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=3) as resp:
            assert resp.headers.get("Access-Control-Allow-Origin") == "*"
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# Unknown endpoint
# ---------------------------------------------------------------------------

def test_unknown_endpoint_returns_404() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.start()
    try:
        status, data = _get(f"http://127.0.0.1:{port}/api/unknown")
        assert status == 404
        assert "error" in data
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# Snapshot/status updates before start (pre-warm)
# ---------------------------------------------------------------------------

def test_snapshot_before_start_is_served_after_start() -> None:
    port = _free_port()
    server = LiveDataHttpServer(port=port)
    server.update_snapshot(_snapshot(("rpm", 4000.0, "rpm")))
    server.update_status(connected=True, sync_state="staged")
    server.start()
    try:
        _, ch_data = _get(f"http://127.0.0.1:{port}/api/channels")
        assert ch_data["rpm"] == pytest.approx(4000.0)
        _, st_data = _get(f"http://127.0.0.1:{port}/api/status")
        assert st_data["connected"] is True
        assert st_data["sync_state"] == "staged"
    finally:
        server.stop()
