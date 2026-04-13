from __future__ import annotations

import math
from dataclasses import dataclass, field
from random import Random

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue


@dataclass(slots=True)
class MockEcuRuntime:
    definition: EcuDefinition | None = None
    seed: int = 12345
    _tick: int = 0
    _rng: Random = field(default_factory=lambda: Random(12345))

    def poll(self) -> OutputChannelSnapshot:
        self._tick += 1
        channel_names = self._channel_names()
        values: list[OutputChannelValue] = []
        for idx, name in enumerate(channel_names):
            phase = (self._tick / 8.0) + idx
            base = 50.0 + math.sin(phase) * 25.0
            jitter = self._rng.uniform(-1.5, 1.5)
            values.append(OutputChannelValue(name=name, value=round(base + jitter, 2)))
        return OutputChannelSnapshot(values=values)

    def _channel_names(self) -> list[str]:
        if self.definition and self.definition.output_channels:
            return self.definition.output_channels[:12]
        return ["rpm", "map", "afr", "clt", "iat", "tps"]
