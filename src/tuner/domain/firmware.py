from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class BoardFamily(str, Enum):
    ATMEGA2560 = "ATMEGA2560"
    TEENSY35 = "TEENSY35"
    TEENSY36 = "TEENSY36"
    TEENSY41 = "TEENSY41"
    STM32F407_DFU = "STM32F407_DFU"


class FlashTool(str, Enum):
    AVRDUDE = "avrdude"
    TEENSY = "teensy"
    DFU_UTIL = "dfu-util"


class FirmwareArtifactKind(str, Enum):
    STANDARD = "standard"
    DIAGNOSTIC = "diagnostic"


@dataclass(slots=True)
class FirmwareFlashRequest:
    firmware_path: Path
    board_family: BoardFamily
    tool_root: Path
    serial_port: str | None = None
    usb_vid: str | None = None
    usb_pid: str | None = None


@dataclass(slots=True)
class ResolvedFlashCommand:
    tool: FlashTool
    executable: Path
    arguments: list[str]
    working_directory: Path
    display_override: str | None = None
    internal: bool = False

    def display_command(self) -> str:
        if self.display_override is not None:
            return self.display_override
        argv = [str(self.executable), *self.arguments]
        return " ".join(f'"{value}"' if " " in value else value for value in argv)


@dataclass(slots=True)
class FlashProgress:
    message: str
    percent: int | None = None


@dataclass(slots=True)
class FirmwareFlashResult:
    command: ResolvedFlashCommand
    exit_code: int
    output: str
    progress_updates: list[int] = field(default_factory=list)


@dataclass(slots=True)
class DetectedFlashTarget:
    board_family: BoardFamily
    source: str
    description: str
    serial_port: str | None = None
    usb_vid: str | None = None
    usb_pid: str | None = None


@dataclass(slots=True)
class FlashPreflightReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
