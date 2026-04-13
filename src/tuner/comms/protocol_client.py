from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tuner.comms.crc import crc32_bytes
from tuner.comms.packet_codec import JsonLinePacketCodec
from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.parameters import ParameterValue
from tuner.transports.base import Transport


@dataclass(slots=True)
class ProtocolControllerClient:
    transport: Transport
    definition: EcuDefinition | None = None
    codec: JsonLinePacketCodec = field(default_factory=JsonLinePacketCodec)

    def connect(self) -> None:
        self.transport.open()
        response = self._request({"command": "hello"})
        if response.get("status") != "ok":
            raise RuntimeError(f"Controller hello failed: {response}")

    def disconnect(self) -> None:
        if self.transport.is_open():
            self.transport.close()

    def read_runtime(self) -> OutputChannelSnapshot:
        response = self._request({"command": "runtime"})
        values = response.get("values", {})
        return OutputChannelSnapshot(
            values=[
                OutputChannelValue(name=name, value=float(value))
                for name, value in values.items()
            ]
        )

    def read_parameter(self, name: str) -> ParameterValue:
        response = self._request({"command": "read_parameter", "name": name})
        return response["value"]

    def write_parameter(self, name: str, value: ParameterValue) -> None:
        response = self._request({"command": "write_parameter", "name": name, "value": value})
        if response.get("status") != "ok":
            raise RuntimeError(f"Parameter write failed for {name}: {response}")

    def burn(self) -> None:
        response = self._request({"command": "burn"})
        if response.get("status") != "ok":
            raise RuntimeError(f"Burn failed: {response}")

    def verify_crc(self) -> bool:
        definition_name = self.definition.name if self.definition else ""
        payload_crc = crc32_bytes(definition_name.encode("utf-8"))
        response = self._request({"command": "verify_crc", "crc": payload_crc})
        return bool(response.get("match", False))

    def write_calibration_table(self, page: int, payload: bytes) -> None:
        """Not supported over the JSON-line protocol — raises NotImplementedError."""
        raise NotImplementedError(
            "Calibration table writes are not supported over the JSON simulator protocol."
        )

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.codec.send(self.transport, payload)
        response = self.codec.receive(self.transport)
        if response.get("status") == "error":
            raise RuntimeError(response.get("message", "Controller request failed."))
        return response
