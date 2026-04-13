from __future__ import annotations

from tuner.comms.interfaces import ControllerClient
from tuner.domain.parameters import ParameterUpdate, ParameterValue


class TuneService:
    def __init__(self, client: ControllerClient) -> None:
        self.client = client
        self._staged: dict[str, ParameterUpdate] = {}

    def stage_value(self, name: str, value: ParameterValue) -> None:
        self._staged[name] = ParameterUpdate(name=name, value=value, staged=True)

    def staged_values(self) -> list[ParameterUpdate]:
        return list(self._staged.values())

    def commit(self) -> None:
        for update in self._staged.values():
            self.client.write_parameter(update.name, update.value)
        self.client.burn()
        self._staged.clear()

    def discard(self) -> None:
        self._staged.clear()
