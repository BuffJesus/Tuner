"""Wideband O2 calibration panel.

Compact operator surface for selecting an aftermarket wideband preset
and writing the resulting Speeduino calibration page 2 payload to a
connected ECU. Mirrors the shape of ``HardwareTestPanel`` so it can be
embedded into the Runtime tab next to the existing thermistor flow.

The panel never speaks to a transport directly — it accepts a
``send_calibration`` callable that takes the 64-byte payload and a
``page`` argument so the host (MainWindow) can route the call through
``SpeeduinoControllerClient.write_calibration_table()``.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tuner.services.wideband_calibration_service import (
    WidebandCalibrationPage,
    WidebandCalibrationService,
    WidebandPreset,
)


class WidebandCalibrationPanel(QWidget):
    """Operator-facing wideband O2 calibration panel.

    Parameters
    ----------
    send_calibration:
        Callable invoked with ``(page, payload)`` when the operator
        clicks Apply. ``page`` is always ``WidebandCalibrationPage.O2``
        (an ``IntEnum`` so the host can pass it straight through to
        ``client.write_calibration_table(int(page), payload)``).
    parent:
        Optional parent widget.
    service:
        Optional injected ``WidebandCalibrationService`` (defaults to a
        fresh instance — useful for tests that want to swap presets).
    """

    def __init__(
        self,
        send_calibration: Callable[[WidebandCalibrationPage, bytes], None],
        parent: QWidget | None = None,
        *,
        service: WidebandCalibrationService | None = None,
    ) -> None:
        super().__init__(parent)
        self._send = send_calibration
        self._service = service or WidebandCalibrationService()
        self._connected = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        title = QLabel("Wideband O2 calibration")
        title.setProperty("surfacePanelTitle", True)
        root.addWidget(title)

        note = QLabel(
            "Select a wideband controller preset and write its 32-point "
            "voltage→AFR curve to Speeduino calibration page 2. Connect "
            "to the ECU before applying."
        )
        note.setWordWrap(True)
        note.setProperty("surfacePanelNote", True)
        root.addWidget(note)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel("Preset:"))
        self._preset_combo = QComboBox()
        for preset in self._service.presets:
            self._preset_combo.addItem(preset.name, userData=preset)
        self._preset_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._preset_combo.currentIndexChanged.connect(self._refresh_summary)
        row.addWidget(self._preset_combo, 1)

        self._apply_btn = QPushButton("Apply to ECU")
        self._apply_btn.setProperty("surfaceActionRole", "primary")
        self._apply_btn.clicked.connect(self._on_apply)
        row.addWidget(self._apply_btn)
        root.addLayout(row)

        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setProperty("surfacePanelNote", True)
        root.addWidget(self._summary_label)

        self._refresh_summary()
        self._refresh_enabled()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._refresh_enabled()

    def selected_preset(self) -> WidebandPreset | None:
        return self._preset_combo.currentData()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_enabled(self) -> None:
        self._apply_btn.setEnabled(self._connected)

    def _refresh_summary(self) -> None:
        preset = self.selected_preset()
        if preset is None:
            self._summary_label.setText("")
            return
        self._summary_label.setText(
            f"{preset.afr_at_voltage_low:.2f} AFR @ {preset.voltage_low:.2f} V → "
            f"{preset.afr_at_voltage_high:.2f} AFR @ {preset.voltage_high:.2f} V. "
            f"{preset.notes}"
        )

    def _on_apply(self) -> None:
        preset = self.selected_preset()
        if preset is None or not self._connected:
            return
        result = self._service.generate(preset)
        self._send(WidebandCalibrationPage.O2, result.encode_payload())
