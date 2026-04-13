from __future__ import annotations

from typing import Protocol

from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.domain.parameters import ParameterValue


class ControllerClient(Protocol):
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def read_runtime(self) -> OutputChannelSnapshot: ...

    def read_parameter(self, name: str) -> ParameterValue: ...

    def write_parameter(self, name: str, value: ParameterValue) -> None: ...

    def burn(self) -> None: ...

    def verify_crc(self) -> bool: ...

    def write_calibration_table(self, page: int, payload: bytes) -> None:
        """Write a 64-byte calibration table to the given page (0=CLT, 1=IAT).

        Sends the Speeduino ``'t'`` command with the pre-encoded payload.
        Implementations that do not support calibration writes may raise
        ``NotImplementedError``.
        """
        ...
