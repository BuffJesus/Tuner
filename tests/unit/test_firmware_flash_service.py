from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from tuner.domain.firmware import BoardFamily, FirmwareFlashRequest, FlashTool
from tuner.services.firmware_flash_service import FirmwareFlashService


@pytest.fixture
def tool_root(tmp_path: Path) -> Path:
    avrdude_dir = tmp_path / "bin" / "avrdude-windows"
    avrdude_dir.mkdir(parents=True)
    (avrdude_dir / "avrdude.exe").write_text("", encoding="utf-8")
    (avrdude_dir / "avrdude.conf").write_text("", encoding="utf-8")

    teensy_dir = tmp_path / "bin" / "teensy_loader_cli-windows"
    teensy_dir.mkdir(parents=True)
    (teensy_dir / "teensy_loader_cli.exe").write_text("", encoding="utf-8")
    (teensy_dir / "teensy_post_compile.exe").write_text("", encoding="utf-8")
    teensy_linux_dir = tmp_path / "bin" / "teensy_loader_cli-linux_x86_64"
    teensy_linux_dir.mkdir(parents=True)
    (teensy_linux_dir / "teensy_loader_cli").write_text("", encoding="utf-8")

    dfu_dir = tmp_path / "bin" / "dfuutil-windows"
    dfu_dir.mkdir(parents=True)
    (dfu_dir / "dfu-util-static.exe").write_text("", encoding="utf-8")
    return tmp_path


@pytest.fixture
def firmware_file(tmp_path: Path) -> Path:
    firmware_path = tmp_path / "speeduino.hex"
    firmware_path.write_text(":00000001FF\n", encoding="utf-8")
    return firmware_path


def test_build_avrdude_command(tool_root: Path, firmware_file: Path) -> None:
    service = FirmwareFlashService(system_name="Windows", machine_name="AMD64")
    request = FirmwareFlashRequest(
        firmware_path=firmware_file,
        board_family=BoardFamily.ATMEGA2560,
        tool_root=tool_root,
        serial_port="COM7",
    )

    command = service.build_command(request)

    assert command.tool == FlashTool.AVRDUDE
    assert command.executable.name == "avrdude.exe"
    assert "-patmega2560" in command.arguments
    assert command.arguments[command.arguments.index("-P") + 1] == "COM7"
    assert any(str(firmware_file) in value for value in command.arguments)


def test_build_teensy_command(tool_root: Path, firmware_file: Path) -> None:
    service = FirmwareFlashService(system_name="Windows", machine_name="AMD64")
    request = FirmwareFlashRequest(
        firmware_path=firmware_file,
        board_family=BoardFamily.TEENSY41,
        tool_root=tool_root,
    )

    command = service.build_command(request)

    assert command.tool == FlashTool.TEENSY
    assert command.internal is True
    assert command.executable.name == "embedded-teensy-loader"
    assert "--mcu=TEENSY41" in command.arguments
    assert str(firmware_file) in command.arguments


def test_build_teensy_command_uses_cli_fallback_off_windows(tool_root: Path, firmware_file: Path) -> None:
    service = FirmwareFlashService(system_name="Linux", machine_name="x86_64")
    request = FirmwareFlashRequest(
        firmware_path=firmware_file,
        board_family=BoardFamily.TEENSY41,
        tool_root=tool_root,
    )

    command = service.build_command(request)

    assert command.tool == FlashTool.TEENSY
    assert command.internal is False
    assert command.executable.name == "teensy_loader_cli"
    assert "--mcu=TEENSY41" in command.arguments


def test_build_dfu_command(tool_root: Path, firmware_file: Path) -> None:
    service = FirmwareFlashService(system_name="Windows", machine_name="AMD64")
    request = FirmwareFlashRequest(
        firmware_path=firmware_file,
        board_family=BoardFamily.STM32F407_DFU,
        tool_root=tool_root,
        usb_vid="0483",
        usb_pid="DF11",
    )

    command = service.build_command(request)

    assert command.tool == FlashTool.DFU_UTIL
    assert command.executable.name == "dfu-util-static.exe"
    assert command.arguments[command.arguments.index("-d") + 1] == "0483:DF11"


def test_build_command_requires_serial_for_avr(tool_root: Path, firmware_file: Path) -> None:
    service = FirmwareFlashService(system_name="Windows", machine_name="AMD64")
    request = FirmwareFlashRequest(
        firmware_path=firmware_file,
        board_family=BoardFamily.ATMEGA2560,
        tool_root=tool_root,
    )

    with pytest.raises(ValueError, match="Serial port"):
        service.build_command(request)


def test_resolve_tool_root_prefers_requested_root(tool_root: Path) -> None:
    service = FirmwareFlashService(system_name="Windows", machine_name="AMD64")

    resolved = service.resolve_tool_root(tool_root)

    assert resolved == tool_root.resolve()


def test_read_teensy_hex_remaps_teensy41_flexspi_addresses(tmp_path: Path) -> None:
    firmware_path = tmp_path / "teensy41.hex"
    firmware_path.write_text(":0200000460009A\n:0400000001020304F2\n:00000001FF\n", encoding="utf-8")
    service = FirmwareFlashService(system_name="Windows", machine_name="AMD64")

    image = service._read_teensy_hex(firmware_path, service._teensy_mcu_spec(BoardFamily.TEENSY41))

    assert image.byte_count == 4
    assert image.bytes_by_address[0] == 0x01
    assert image.bytes_by_address[3] == 0x04


def test_try_teensy_serial_reboot_opens_port_at_134_baud(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []

    class FakeSerial:
        def __init__(self, port: str, baudrate: int, timeout: float, write_timeout: float) -> None:
            calls.append((port, baudrate))

        def __enter__(self) -> "FakeSerial":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(Serial=FakeSerial))

    assert FirmwareFlashService._try_teensy_serial_reboot("COM9") is True
    assert calls == [("COM9", 134)]
