"""End-to-end test for TriggerCaptureWorker (Phase 9 close-out).

The live trigger capture pipeline (start command → poll → read → stop command
→ decode → CSV) is wired in MainWindow but had no end-to-end test. This test
exercises the worker thread against a fake controller client and a real
LoggerDefinition + LiveTriggerLoggerService, then verifies the decoded
TriggerLogCapture round-trips through the CSV path used by the analysis
pipeline.
"""
from __future__ import annotations

import os
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from tuner.domain.ecu_definition import LoggerDefinition, LoggerRecordField
from tuner.services.live_trigger_logger_service import (
    LiveTriggerLoggerService,
    TriggerLogCapture,
)
from tuner.ui.main_window import TriggerCaptureWorker


def _tooth_logger(record_count: int = 3) -> LoggerDefinition:
    return LoggerDefinition(
        name="tooth",
        display_name="Tooth Logger",
        kind="tooth",
        start_command="H",
        stop_command="h",
        data_read_command=b"T",
        data_read_timeout_ms=1000,
        continuous_read=True,
        record_header_len=0,
        record_footer_len=0,
        record_len=4,
        record_count=record_count,
        record_fields=(
            LoggerRecordField(
                name="toothTime", header="ToothTime",
                start_bit=0, bit_count=32, scale=1.0, units="uS",
            ),
        ),
    )


class _FakeClient:
    """Stand-in for SpeeduinoControllerClient.

    Records the logger it was asked to fetch and returns a deterministic
    pre-built buffer of u32 LE tooth times. This is exactly the contract the
    worker depends on — it does not exercise the firmware-level start/poll/stop
    handshake (that's the controller client's responsibility and is covered by
    test_speeduino_controller_client.py).
    """

    def __init__(self, raw: bytes) -> None:
        self._raw = raw
        self.calls: list[LoggerDefinition] = []

    def fetch_logger_data(self, logger: LoggerDefinition) -> bytes:
        self.calls.append(logger)
        return self._raw


def _spin_until(predicate, *, timeout_ms: int = 2000) -> None:
    app = QApplication.instance() or QApplication([])
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    def _tick() -> None:
        if predicate():
            loop.quit()
    timer.timeout.connect(_tick)
    timer.start()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(timeout_ms)
    loop.exec()
    timer.stop()
    deadline.stop()


def test_trigger_capture_worker_decodes_and_emits_capture(tmp_path) -> None:
    QApplication.instance() or QApplication([])

    raw = b"".join(struct.pack("<I", v) for v in (1500, 1505, 1498))
    client = _FakeClient(raw)
    logger = _tooth_logger(record_count=3)
    service = LiveTriggerLoggerService()

    captures: list[TriggerLogCapture] = []
    failures: list[str] = []
    worker = TriggerCaptureWorker(client, logger, service)
    worker.succeeded.connect(captures.append)
    worker.failed.connect(failures.append)
    worker.start()
    _spin_until(lambda: captures or failures or worker.isFinished())
    worker.wait(2000)

    assert failures == []
    assert len(captures) == 1
    capture = captures[0]
    assert isinstance(capture, TriggerLogCapture)
    assert capture.kind == "tooth"
    assert capture.record_count == 3
    assert [row["ToothTime"] for row in capture.rows] == [1500.0, 1505.0, 1498.0]
    assert client.calls == [logger]

    # CSV hand-off to the analysis pipeline must produce a readable file with
    # the expected column header.
    csv_path = capture.to_csv_path()
    try:
        text = csv_path.read_text(encoding="utf-8")
        assert text.splitlines()[0] == "ToothTime"
        assert "1500" in text
    finally:
        csv_path.unlink(missing_ok=True)


def test_trigger_capture_worker_emits_failed_signal_on_client_error() -> None:
    QApplication.instance() or QApplication([])

    class _BoomClient:
        def fetch_logger_data(self, logger):
            raise RuntimeError("ECU did not respond")

    captures: list[object] = []
    failures: list[str] = []
    worker = TriggerCaptureWorker(_BoomClient(), _tooth_logger(), LiveTriggerLoggerService())
    worker.succeeded.connect(captures.append)
    worker.failed.connect(failures.append)
    worker.start()
    _spin_until(lambda: captures or failures or worker.isFinished())
    worker.wait(2000)

    assert captures == []
    assert failures == ["ECU did not respond"]
