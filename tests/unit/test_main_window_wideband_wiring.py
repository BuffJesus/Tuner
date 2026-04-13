"""Tests that the WidebandCalibrationPanel is actually wired into MainWindow.

Closes the "wire the panel into the Runtime tab" follow-up from the
gap-matrix wideband calibration row. Without these tests the panel was
shipping as orphaned UI code that the running app never instantiated.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from tuner.services.wideband_calibration_service import (
    WidebandCalibrationPage,
    WidebandCalibrationService,
)
from tuner.ui.main_window import MainWindow
from tuner.ui.wideband_calibration_panel import WidebandCalibrationPanel


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window():
    """Construct + drain a MainWindow with deterministic teardown.

    Some downstream Qt tests (e.g. test_trigger_capture_worker.py) spin
    a fresh event loop and rely on a clean global state. Closing the
    window inside a fixture and pumping pending events on teardown
    keeps the suite order-independent.
    """
    app = _app()
    win = MainWindow()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


class _RecordingClient:
    """Minimal stand-in for SpeeduinoControllerClient.

    The MainWindow code only touches `write_calibration_table(page, payload)`
    on the active client during a wideband Apply, so the recorder can be
    deliberately tiny.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[int, bytes]] = []

    def write_calibration_table(self, page: int, payload: bytes) -> None:
        self.calls.append((page, payload))


def test_main_window_constructs_wideband_panel(main_window: MainWindow) -> None:
    assert hasattr(main_window, "wideband_calibration_panel")
    assert isinstance(main_window.wideband_calibration_panel, WidebandCalibrationPanel)


def test_panel_starts_disconnected(main_window: MainWindow) -> None:
    assert main_window.wideband_calibration_panel._apply_btn.isEnabled() is False


def test_panel_dispatches_payload_through_client_when_connected(
    main_window: MainWindow,
) -> None:
    recorder = _RecordingClient()
    main_window.session_service.client = recorder  # type: ignore[assignment]
    main_window.wideband_calibration_panel.set_connected(True)

    main_window.wideband_calibration_panel._on_apply()

    assert len(recorder.calls) == 1
    page, payload = recorder.calls[0]
    assert page == int(WidebandCalibrationPage.O2)
    assert page == 2
    assert len(payload) == 64

    # The payload must match exactly what the service generates for the
    # selected preset — proves the host is not corrupting the bytes.
    selected = main_window.wideband_calibration_panel.selected_preset()
    assert selected is not None
    expected = WidebandCalibrationService().generate(selected).encode_payload()
    assert payload == expected


def test_panel_send_no_ops_when_no_active_client(main_window: MainWindow) -> None:
    main_window.wideband_calibration_panel.set_connected(True)
    main_window.session_service.client = None  # type: ignore[assignment]
    # Should not raise even though there's no client.
    main_window._send_wideband_calibration(WidebandCalibrationPage.O2, b"\x00" * 64)


def test_disconnect_disables_panel(main_window: MainWindow) -> None:
    main_window.wideband_calibration_panel.set_connected(True)
    assert main_window.wideband_calibration_panel._apply_btn.isEnabled() is True
    main_window.wideband_calibration_panel.set_connected(False)
    assert main_window.wideband_calibration_panel._apply_btn.isEnabled() is False
