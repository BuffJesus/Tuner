from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.domain.parameters import ParameterValue
from tuner.services.mock_ecu_service import MockEcuRuntime


class MockControllerClient:
    def __init__(self, definition: EcuDefinition | None = None) -> None:
        self.runtime = MockEcuRuntime(definition=definition)
        self.connected = False
        self._parameters: dict[str, ParameterValue] = {}

    def set_definition(self, definition: EcuDefinition | None) -> None:
        self.runtime.definition = definition

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def read_runtime(self) -> OutputChannelSnapshot:
        if not self.connected:
            raise RuntimeError("Mock controller is not connected.")
        return self.runtime.poll()

    def seed_parameters(self, values: dict[str, ParameterValue]) -> None:
        """Pre-populate ECU RAM with known values — used in tests."""
        self._parameters.update(values)

    def read_parameter(self, name: str) -> ParameterValue:
        return self._parameters.get(name, 0.0)

    def write_parameter(self, name: str, value: ParameterValue) -> None:
        self._parameters[name] = value

    def burn(self) -> None:
        return None

    def verify_crc(self) -> bool:
        return True

    def write_calibration_table(self, page: int, payload: bytes) -> None:
        """Accept a calibration table write without doing anything."""
        if not self.connected:
            raise RuntimeError("Mock controller is not connected.")
        if len(payload) != 64:
            raise ValueError(f"Calibration payload must be exactly 64 bytes, got {len(payload)}.")
        # Store for test inspection
        if not hasattr(self, "_calibration_tables"):
            self._calibration_tables: dict[int, bytes] = {}
        self._calibration_tables[page] = payload
