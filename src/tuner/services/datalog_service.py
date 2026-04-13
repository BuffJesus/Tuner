from __future__ import annotations

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.output_channels import OutputChannelSnapshot


class DataLogService:
    def __init__(self) -> None:
        self.current_log = DataLog(name="session")

    def append_snapshot(self, snapshot: OutputChannelSnapshot) -> None:
        self.current_log.records.append(DataLogRecord(values=snapshot.as_dict()))
