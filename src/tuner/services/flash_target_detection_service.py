from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from serial.tools import list_ports

from tuner.domain.firmware import BoardFamily, DetectedFlashTarget


@dataclass(slots=True)
class _TeensyUsbIdentity:
    board_family: BoardFamily
    label: str


class FlashTargetDetectionService:
    def detect_targets(self) -> list[DetectedFlashTarget]:
        targets: list[DetectedFlashTarget] = []
        targets.extend(self._detect_serial_targets(list_ports.comports()))
        targets.extend(self._detect_usb_targets())
        return targets

    def detect_preferred_target(self, preferred_board: BoardFamily | None = None) -> DetectedFlashTarget | None:
        targets = self.detect_targets()
        if preferred_board is not None:
            for target in targets:
                if target.board_family == preferred_board:
                    return target
        return targets[0] if targets else None

    def _detect_serial_targets(self, ports: Iterable[Any]) -> list[DetectedFlashTarget]:
        targets: list[DetectedFlashTarget] = []
        for port in ports:
            vid = self._normalize_hex(getattr(port, "vid", None))
            pid = self._normalize_hex(getattr(port, "pid", None))
            device = str(getattr(port, "device", ""))
            description = str(getattr(port, "description", "") or device)
            if vid == "2341" and pid in {"0010", "0042"}:
                targets.append(
                    DetectedFlashTarget(
                        board_family=BoardFamily.ATMEGA2560,
                        source="serial",
                        description=f"{device} (Arduino Mega)",
                        serial_port=device,
                        usb_vid=vid,
                        usb_pid=pid,
                    )
                )
            elif vid == "1A86":
                targets.append(
                    DetectedFlashTarget(
                        board_family=BoardFamily.ATMEGA2560,
                        source="serial",
                        description=f"{device} (Arduino Mega CH340)",
                        serial_port=device,
                        usb_vid=vid,
                        usb_pid=pid,
                    )
                )
            elif vid == "16C0":
                identity = self._teensy_identity_from_pid_or_bcd(pid, None)
                if identity is not None:
                    targets.append(
                        DetectedFlashTarget(
                            board_family=identity.board_family,
                            source="serial",
                            description=f"{device} (Teensy {identity.label})",
                            serial_port=device,
                            usb_vid=vid,
                            usb_pid=pid,
                        )
                    )
                else:
                    targets.append(
                        DetectedFlashTarget(
                            board_family=BoardFamily.TEENSY41,
                            source="serial",
                            description=f"{device} ({description})",
                            serial_port=device,
                            usb_vid=vid,
                            usb_pid=pid,
                        )
                    )
            elif vid == "0483" and pid == "5740":
                targets.append(
                    DetectedFlashTarget(
                        board_family=BoardFamily.STM32F407_DFU,
                        source="serial",
                        description=f"{device} (STM32F407 serial mode; use DFU for flashing)",
                        serial_port=device,
                        usb_vid=vid,
                        usb_pid=pid,
                    )
                )
        return targets

    def _detect_usb_targets(self) -> list[DetectedFlashTarget]:
        try:
            import usb.core  # type: ignore[import-not-found]
            import usb.util  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            return []
        try:
            devices = list(usb.core.find(find_all=True))
        except Exception:
            return []

        targets: list[DetectedFlashTarget] = []
        for device in devices:
            vid = self._normalize_hex(getattr(device, "idVendor", None))
            pid = self._normalize_hex(getattr(device, "idProduct", None))
            bcd = self._normalize_hex(getattr(device, "bcdDevice", None))
            if vid == "16C0" and self._device_has_hid_interface(device, usb.util):
                identity = self._teensy_identity_from_pid_or_bcd(pid, bcd)
                if identity is None:
                    continue
                targets.append(
                    DetectedFlashTarget(
                        board_family=identity.board_family,
                        source="usb",
                        description=f"Uninitialized Teensy {identity.label}",
                        usb_vid=vid,
                        usb_pid=pid,
                    )
                )
            elif vid == "0483" and bcd == "2200":
                targets.append(
                    DetectedFlashTarget(
                        board_family=BoardFamily.STM32F407_DFU,
                        source="usb",
                        description="STM32F407 in DFU mode",
                        usb_vid=vid,
                        usb_pid=pid,
                    )
                )
        return targets

    @staticmethod
    def _normalize_hex(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip().removeprefix("0x").upper()
        if isinstance(value, int):
            return f"{value:04X}"
        return None

    @staticmethod
    def _device_has_hid_interface(device: Any, usb_util: Any) -> bool:
        try:
            for configuration in device:
                for interface in configuration:
                    if getattr(interface, "bInterfaceClass", None) == 3:
                        return True
        except Exception:
            try:
                configuration = device.get_active_configuration()
                for interface in configuration:
                    if getattr(interface, "bInterfaceClass", None) == 3:
                        return True
            except Exception:
                return False
        return False

    @staticmethod
    def _teensy_identity_from_pid_or_bcd(pid: str | None, bcd_device: str | None) -> _TeensyUsbIdentity | None:
        mapping = {
            "0276": _TeensyUsbIdentity(BoardFamily.TEENSY35, "3.5"),
            "0277": _TeensyUsbIdentity(BoardFamily.TEENSY36, "3.6"),
            "0280": _TeensyUsbIdentity(BoardFamily.TEENSY41, "4.1"),
        }
        if bcd_device in mapping:
            return mapping[bcd_device]
        if pid in {"0483", "0484", "0485", "0486"}:
            return _TeensyUsbIdentity(BoardFamily.TEENSY41, "4.1")
        return None
