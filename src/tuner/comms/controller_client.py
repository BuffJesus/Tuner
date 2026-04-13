from __future__ import annotations

from tuner.comms.crc import crc32_bytes
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.domain.parameters import ParameterValue
from tuner.transports.base import Transport


class BasicControllerClient:
    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    def connect(self) -> None:
        self.transport.open()

    def disconnect(self) -> None:
        self.transport.close()

    def read_runtime(self) -> OutputChannelSnapshot:
        raise NotImplementedError("Runtime polling is pending protocol implementation.")

    def read_parameter(self, name: str) -> ParameterValue:
        del name
        raise NotImplementedError("Parameter reads are pending protocol implementation.")

    def write_parameter(self, name: str, value: ParameterValue) -> None:
        del name, value
        raise NotImplementedError("Parameter writes are pending protocol implementation.")

    def burn(self) -> None:
        raise NotImplementedError("Burn handling is pending protocol implementation.")

    def verify_crc(self) -> bool:
        _ = crc32_bytes(b"")
        raise NotImplementedError("CRC verification is pending protocol implementation.")
