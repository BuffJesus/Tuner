from __future__ import annotations

from tuner.comms.interfaces import ControllerClient
from tuner.domain.output_channels import OutputChannelSnapshot


class EcuService:
    def __init__(self, client: ControllerClient) -> None:
        self.client = client

    def connect(self) -> None:
        self.client.connect()

    def disconnect(self) -> None:
        self.client.disconnect()

    def poll_runtime(self) -> OutputChannelSnapshot:
        return self.client.read_runtime()
