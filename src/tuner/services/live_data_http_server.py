"""HTTP live-data server that exposes the latest OutputChannelSnapshot as JSON.

The server runs in a daemon thread and never blocks the Qt event loop.
It is opt-in — callers must call ``start()`` to begin serving.

Endpoints
---------
``GET /api/channels``
    Returns all channel values as a flat JSON object:
    ``{"rpm": 1500.0, "map": 95.0, ...}``

``GET /api/channels/{name}``
    Returns a single channel:
    ``{"name": "rpm", "value": 1500.0, "units": "rpm"}``

``GET /api/status``
    Returns connection / sync state:
    ``{"connected": true, "sync_state": "clean", "port": 8080}``

All responses include CORS headers so browser-based dashboards on the same
LAN (e.g. the Airbear web dash at ``speeduino.local``) can consume the feed
cross-origin without a proxy.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue


_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


class LiveDataHttpServer:
    """Opt-in HTTP server that exposes live channel data as JSON.

    Thread-safety: ``update_snapshot()`` and ``update_status()`` are called
    from the Qt event loop (main thread).  The HTTP handler runs in a separate
    daemon thread and acquires ``_lock`` before reading shared state.
    """

    def __init__(self, port: int = 8080) -> None:
        self._port = port
        self._lock = threading.Lock()
        self._channels: dict[str, float] = {}
        self._channel_units: dict[str, str] = {}
        self._status: dict[str, Any] = {"connected": False, "sync_state": "offline"}
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API (called from Qt thread)
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        """Start the HTTP server on ``self.port`` in a daemon thread."""
        if self._server is not None:
            return
        handler_class = _make_handler(self)
        server = HTTPServer(("0.0.0.0", self._port), handler_class)
        server.allow_reuse_address = True
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="live-data-http",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the HTTP server and release the port."""
        if self._server is None:
            return
        # shutdown() signals serve_forever() to exit; server_close() releases the socket.
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None

    def update_snapshot(self, snapshot: OutputChannelSnapshot | None) -> None:
        """Replace the cached channel snapshot (called from Qt poll tick)."""
        if snapshot is None:
            channels: dict[str, float] = {}
            units: dict[str, str] = {}
        else:
            channels = {v.name: v.value for v in snapshot.values}
            units = {v.name: v.units for v in snapshot.values if v.units}
        with self._lock:
            self._channels = channels
            self._channel_units = units

    def update_status(self, *, connected: bool, sync_state: str) -> None:
        """Update the connection / sync state reported by ``/api/status``."""
        with self._lock:
            self._status = {"connected": connected, "sync_state": sync_state}

    # ------------------------------------------------------------------
    # Internal snapshot accessors (called from HTTP handler thread)
    # ------------------------------------------------------------------

    def _snapshot_channels(self) -> dict[str, float]:
        with self._lock:
            return dict(self._channels)

    def _snapshot_channel(self, name: str) -> tuple[float, str] | None:
        with self._lock:
            if name not in self._channels:
                return None
            return self._channels[name], self._channel_units.get(name, "")

    def _snapshot_status(self) -> dict[str, Any]:
        with self._lock:
            data = dict(self._status)
        data["port"] = self._port
        return data


# ---------------------------------------------------------------------------
# HTTP handler factory
# ---------------------------------------------------------------------------

def _make_handler(server: LiveDataHttpServer) -> type[BaseHTTPRequestHandler]:
    """Return a ``BaseHTTPRequestHandler`` subclass bound to *server*."""

    class _Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:  # pre-flight CORS
            self.send_response(204)
            for k, v in _CORS_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()

        def do_GET(self) -> None:
            path = self.path.split("?")[0].rstrip("/")

            if path == "/api/channels":
                self._send_json(server._snapshot_channels())

            elif path.startswith("/api/channels/"):
                name = path[len("/api/channels/"):]
                result = server._snapshot_channel(name)
                if result is None:
                    self._send_error(404, f"Channel '{name}' not found.")
                else:
                    value, units = result
                    self._send_json({"name": name, "value": value, "units": units})

            elif path == "/api/status":
                self._send_json(server._snapshot_status())

            else:
                self._send_error(404, "Endpoint not found.")

        def _send_json(self, data: Any) -> None:
            body = json.dumps(data, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for k, v in _CORS_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, code: int, message: str) -> None:
            body = json.dumps({"error": message}, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for k, v in _CORS_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
            pass  # suppress per-request stdout noise

    return _Handler
