"""Offscreen Qt tests for the WidebandCalibrationPanel widget."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tuner.services.wideband_calibration_service import (
    PRESETS,
    WidebandCalibrationPage,
)
from tuner.ui.wideband_calibration_panel import WidebandCalibrationPanel


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[WidebandCalibrationPage, bytes]] = []

    def __call__(self, page: WidebandCalibrationPage, payload: bytes) -> None:
        self.calls.append((page, payload))


def test_panel_lists_all_presets() -> None:
    _app()
    panel = WidebandCalibrationPanel(_Recorder())
    assert panel._preset_combo.count() == len(PRESETS)
    for index, preset in enumerate(PRESETS):
        assert panel._preset_combo.itemText(index) == preset.name


def test_apply_disabled_when_disconnected() -> None:
    _app()
    panel = WidebandCalibrationPanel(_Recorder())
    assert panel._apply_btn.isEnabled() is False
    panel._apply_btn.click()  # no-op when disabled
    panel._on_apply()          # explicit guard inside the slot
    assert panel.selected_preset() is not None  # combo populated


def test_apply_enabled_after_set_connected() -> None:
    _app()
    panel = WidebandCalibrationPanel(_Recorder())
    panel.set_connected(True)
    assert panel._apply_btn.isEnabled() is True
    panel.set_connected(False)
    assert panel._apply_btn.isEnabled() is False


def test_apply_dispatches_calibration_packet_with_o2_page() -> None:
    _app()
    recorder = _Recorder()
    panel = WidebandCalibrationPanel(recorder)
    panel.set_connected(True)
    panel._on_apply()
    assert len(recorder.calls) == 1
    page, payload = recorder.calls[0]
    assert page == WidebandCalibrationPage.O2
    assert int(page) == 2
    assert len(payload) == 64


def test_disconnected_apply_does_not_dispatch() -> None:
    _app()
    recorder = _Recorder()
    panel = WidebandCalibrationPanel(recorder)
    # Default state is disconnected
    panel._on_apply()
    assert recorder.calls == []


def test_summary_text_reflects_selected_preset() -> None:
    _app()
    panel = WidebandCalibrationPanel(_Recorder())
    panel._preset_combo.setCurrentIndex(0)
    summary_first = panel._summary_label.text()
    assert summary_first  # non-empty
    if panel._preset_combo.count() > 1:
        panel._preset_combo.setCurrentIndex(1)
        summary_second = panel._summary_label.text()
        assert summary_second != summary_first
