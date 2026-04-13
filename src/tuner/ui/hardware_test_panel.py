"""Hardware Test Panel.

Exposes the ``[ControllerCommands]`` bench-test operations defined in the ECU
definition: injector and spark activation (on/off/pulsed), STM32 reboot /
bootloader, SD card format, and VSS calibration.

These commands bypass TunerStudio-style memory synchronisation.  The panel
shows a prominent warning and requires an active ECU connection before any
button is enabled.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tuner.domain.ecu_definition import ControllerCommand, EcuDefinition


class HardwareTestPanel(QWidget):
    """Compact panel for sending ``[ControllerCommands]`` to a connected ECU.

    Parameters
    ----------
    send_command:
        Callable that accepts a ``bytes`` payload and dispatches it to the
        controller.  Called from the Qt thread; should not block.
    parent:
        Optional parent widget.
    """

    def __init__(
        self,
        send_command: Callable[[bytes], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._send = send_command
        self._cmd_map: dict[str, bytes] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # Warning banner
        warn = QLabel(
            "⚠  These commands bypass normal memory synchronisation.  "
            "Use only for bench testing — not during a tuning session."
        )
        warn.setWordWrap(True)
        warn.setProperty("surfacePanelNote", True)
        root.addWidget(warn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(8)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        self._connected = False
        self._build_offline_placeholder()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_definition(self, definition: EcuDefinition | None) -> None:
        """Rebuild the panel from *definition*'s controller command list."""
        self._cmd_map = {}
        if definition is not None:
            self._cmd_map = {c.name: c.payload for c in definition.controller_commands}
        self._rebuild()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._rebuild()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clear_inner(self) -> None:
        while self._inner_layout.count():
            item = self._inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild(self) -> None:
        self._clear_inner()
        if not self._cmd_map:
            self._build_offline_placeholder()
            return
        self._build_test_mode_section()
        self._build_injector_section()
        self._build_spark_section()
        self._build_misc_section()
        self._inner_layout.addStretch(1)

    def _build_offline_placeholder(self) -> None:
        lbl = QLabel("Hardware test commands: load a definition to see available commands.")
        lbl.setProperty("surfacePanelNote", True)
        lbl.setWordWrap(True)
        self._inner_layout.addWidget(lbl)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("surfacePanelTitle", True)
        return lbl

    def _cmd_button(self, label: str, cmd_name: str, *, tooltip: str = "") -> QPushButton:
        btn = QPushButton(label)
        btn.setProperty("surfaceActionRole", "secondary")
        btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        if tooltip:
            btn.setToolTip(tooltip)
        payload = self._cmd_map.get(cmd_name)
        if payload is None or not self._connected:
            btn.setEnabled(False)
        else:
            btn.clicked.connect(lambda _=False, p=payload: self._send(p))
        return btn

    def _build_test_mode_section(self) -> None:
        self._inner_layout.addWidget(self._section_label("Test Mode"))
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self._cmd_button(
            "Enable", "cmdEnableTestMode",
            tooltip="Put the ECU into hardware test mode (E 01 01)."
        ))
        row.addWidget(self._cmd_button(
            "Disable", "cmdStopTestMode",
            tooltip="Exit hardware test mode (E 01 00)."
        ))
        row.addStretch(1)
        self._inner_layout.addLayout(row)

    def _build_injector_section(self) -> None:
        self._inner_layout.addWidget(self._section_label("Injectors"))
        # Determine how many injectors have commands
        max_inj = 0
        for n in range(1, 9):
            if f"cmdtestinj{n}on" in self._cmd_map:
                max_inj = n
        if max_inj == 0:
            return

        combo_label = QLabel("Injector:")
        combo = QComboBox()
        for n in range(1, max_inj + 1):
            combo.addItem(str(n), userData=n)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(combo_label)
        row.addWidget(combo)

        def _make_inj_cb(mode: str) -> Callable[[], None]:
            def _cb() -> None:
                n = combo.currentData()
                key = f"cmdtestinj{n}{mode}"
                payload = self._cmd_map.get(key)
                if payload:
                    self._send(payload)
            return _cb

        for label, mode, tip in [
            ("On",      "on",      "Hold injector open continuously (caution: flooding risk)."),
            ("Off",     "off",     "Stop injector test."),
            ("Pulsed",  "Pulsed",  "Fire injector with a single controlled pulse."),
        ]:
            btn = QPushButton(label)
            btn.setProperty("surfaceActionRole", "secondary")
            btn.setToolTip(tip)
            btn.setEnabled(self._connected)
            btn.clicked.connect(_make_inj_cb(mode))
            row.addWidget(btn)

        row.addStretch(1)
        self._inner_layout.addLayout(row)

    def _build_spark_section(self) -> None:
        self._inner_layout.addWidget(self._section_label("Sparks"))
        max_spk = 0
        for n in range(1, 9):
            if f"cmdtestspk{n}on" in self._cmd_map:
                max_spk = n
        if max_spk == 0:
            return

        combo_label = QLabel("Coil:")
        combo = QComboBox()
        for n in range(1, max_spk + 1):
            combo.addItem(str(n), userData=n)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(combo_label)
        row.addWidget(combo)

        def _make_spk_cb(mode: str) -> Callable[[], None]:
            def _cb() -> None:
                n = combo.currentData()
                key = f"cmdtestspk{n}{mode}"
                payload = self._cmd_map.get(key)
                if payload:
                    self._send(payload)
            return _cb

        for label, mode, tip in [
            ("On",     "on",     "Hold coil charged continuously (caution: heat risk)."),
            ("Off",    "off",    "Stop spark test."),
            ("Pulsed", "Pulsed", "Fire a single controlled spark event."),
        ]:
            btn = QPushButton(label)
            btn.setProperty("surfaceActionRole", "secondary")
            btn.setToolTip(tip)
            btn.setEnabled(self._connected)
            btn.clicked.connect(_make_spk_cb(mode))
            row.addWidget(btn)

        row.addStretch(1)
        self._inner_layout.addLayout(row)

    def _build_misc_section(self) -> None:
        misc: list[tuple[str, str, str]] = [
            ("STM32 Reboot",      "cmdstm32reboot",     "Reboot the STM32 MCU (E 32 00)."),
            ("STM32 Bootloader",  "cmdstm32bootloader", "Enter STM32 DFU bootloader (E 32 01)."),
            ("Format SD",         "cmdFormatSD",        "Format the on-board SD card (E 33 01). Irreversible."),
            ("VSS 60 km/h Cal",   "cmdVSS60kmh",        "Drive at exactly 60 km/h and press to calibrate the VSS (E 99 00)."),
            ("VSS Ratio ×1",      "cmdVSSratio1",       "Set VSS ratio 1 (E 99 01)."),
            ("VSS Ratio ×2",      "cmdVSSratio2",       "Set VSS ratio 2 (E 99 02)."),
            ("VSS Ratio ×3",      "cmdVSSratio3",       "Set VSS ratio 3 (E 99 03)."),
            ("VSS Ratio ×4",      "cmdVSSratio4",       "Set VSS ratio 4 (E 99 04)."),
            ("VSS Ratio ×5",      "cmdVSSratio5",       "Set VSS ratio 5 (E 99 05)."),
            ("VSS Ratio ×6",      "cmdVSSratio6",       "Set VSS ratio 6 (E 99 06)."),
        ]
        visible = [(lbl, key, tip) for lbl, key, tip in misc if key in self._cmd_map]
        if not visible:
            return
        self._inner_layout.addWidget(self._section_label("Utilities"))
        row = QHBoxLayout()
        row.setSpacing(6)
        for label, cmd_name, tip in visible:
            row.addWidget(self._cmd_button(label, cmd_name, tooltip=tip))
        row.addStretch(1)
        self._inner_layout.addLayout(row)
