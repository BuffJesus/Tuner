from __future__ import annotations

from dataclasses import dataclass, field

from tuner.comms.xcp.client import XcpClient
from tuner.domain.ecu_definition import EcuDefinition, XcpMemoryMapping
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.parameters import ParameterValue
from tuner.transports.base import Transport


@dataclass(slots=True)
class XcpControllerClient:
    transport: Transport
    definition: EcuDefinition | None = None
    client: XcpClient = field(init=False)
    controller_name: str | None = None
    memory_preview: bytes = b""

    def __post_init__(self) -> None:
        self.client = XcpClient(self.transport)

    def connect(self) -> None:
        self.client.connect()
        self.client.get_status()
        self.controller_name = self.client.get_id().identifier_text()
        self.memory_preview = self.client.read_memory(0x00000000, 4)

    def disconnect(self) -> None:
        self.client.disconnect()

    def read_runtime(self) -> OutputChannelSnapshot:
        if self.client.status_response is None:
            self.client.get_status()
        values = [
            OutputChannelValue(name="xcp_session_status", value=float(self.client.status_response.session_status)),
            OutputChannelValue(name="xcp_protection_status", value=float(self.client.status_response.protection_status)),
            OutputChannelValue(name="xcp_config_status", value=float(self.client.status_response.configuration_status)),
        ]
        if self.definition is not None:
            values.append(OutputChannelValue(name="definition_loaded", value=1.0))
        if self.client.id_response is not None:
            values.append(OutputChannelValue(name="xcp_id_length", value=float(self.client.id_response.identifier_length)))
        if self.memory_preview:
            values.append(
                OutputChannelValue(
                    name="xcp_memory_preview_u32",
                    value=float(int.from_bytes(self.memory_preview, byteorder="big", signed=False)),
                )
            )
        if self.definition is not None:
            for mapping in self.definition.xcp_mappings[:8]:
                values.append(self._read_mapping(mapping))
        return OutputChannelSnapshot(values=values)

    def read_parameter(self, name: str) -> ParameterValue:
        del name
        raise NotImplementedError("XCP parameter reads are not implemented yet.")

    def write_parameter(self, name: str, value: ParameterValue) -> None:
        del name, value
        raise NotImplementedError("XCP parameter writes are not implemented yet.")

    def burn(self) -> None:
        raise NotImplementedError("XCP burn is not implemented yet.")

    def verify_crc(self) -> bool:
        return self.client.connect_response is not None

    def _read_mapping(self, mapping: XcpMemoryMapping) -> OutputChannelValue:
        raw = self.client.read_memory(mapping.address, mapping.size)
        value = self._decode_mapping_value(raw, mapping.data_type)
        return OutputChannelValue(name=mapping.name, value=value, units=mapping.units)

    @staticmethod
    def _decode_mapping_value(raw: bytes, data_type: str) -> float:
        if data_type == "u8":
            return float(raw[0])
        if data_type == "u16":
            return float(int.from_bytes(raw[:2], byteorder="big", signed=False))
        if data_type == "u32":
            return float(int.from_bytes(raw[:4], byteorder="big", signed=False))
        if data_type == "s16":
            return float(int.from_bytes(raw[:2], byteorder="big", signed=True))
        if data_type == "s32":
            return float(int.from_bytes(raw[:4], byteorder="big", signed=True))
        if data_type == "f32":
            import struct

            return float(struct.unpack(">f", raw[:4])[0])
        if data_type == "ascii":
            return float(len(raw.rstrip(b"\x00")))
        return float(int.from_bytes(raw, byteorder="big", signed=False))
