from __future__ import annotations

import json
import math
import socket
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SimulatorState:
    tick: int = 0
    parameters: dict[str, int | float | str | bool] = field(default_factory=dict)

    def runtime_values(self) -> dict[str, float]:
        self.tick += 1
        return {
            "rpm": round(900.0 + math.sin(self.tick / 4.0) * 120.0, 2),
            "map": round(95.0 + math.cos(self.tick / 5.0) * 4.0, 2),
            "afr": round(14.7 + math.sin(self.tick / 6.0) * 0.4, 2),
        }


class ProtocolSimulatorServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.state = SimulatorState()
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def address(self) -> tuple[str, int]:
        return self._server.getsockname()

    def start(self) -> None:
        self._server.bind((self.host, self.port))
        self._server.listen(1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            with socket.create_connection(self.address, timeout=0.2):
                pass
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server.close()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._server.accept()
            except OSError:
                return
            with conn:
                file = conn.makefile("rwb")
                while not self._stop.is_set():
                    line = file.readline()
                    if not line:
                        break
                    response = self._handle(json.loads(line.decode("utf-8")))
                    file.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
                    file.flush()

    def _handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = payload.get("command")
        if command == "hello":
            return {"status": "ok", "controller": "tuner-py-sim"}
        if command == "runtime":
            return {"status": "ok", "values": self.state.runtime_values()}
        if command == "read_parameter":
            name = str(payload["name"])
            return {"status": "ok", "value": self.state.parameters.get(name, 0.0)}
        if command == "write_parameter":
            self.state.parameters[str(payload["name"])] = payload["value"]
            return {"status": "ok"}
        if command == "burn":
            return {"status": "ok"}
        if command == "verify_crc":
            return {"status": "ok", "match": True}
        return {"status": "error", "message": f"Unknown command: {command}"}
