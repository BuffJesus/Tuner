from __future__ import annotations

import ctypes
import platform
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tuner.app.paths import bundled_tools_root
from tuner.domain.firmware import (
    BoardFamily,
    FirmwareFlashRequest,
    FirmwareFlashResult,
    FlashProgress,
    FlashTool,
    ResolvedFlashCommand,
)


_MAX_TEENSY_MEMORY_SIZE = 0x1000000


@dataclass(slots=True, frozen=True)
class _TeensyMcuSpec:
    name: str
    code_size: int
    block_size: int


@dataclass(slots=True)
class _TeensyHexImage:
    bytes_by_address: dict[int, int]
    byte_count: int


@dataclass(slots=True, frozen=True)
class _UsbWriteResult:
    ok: bool
    detail: str | None = None


class FirmwareFlashService:
    def __init__(self, system_name: str | None = None, machine_name: str | None = None) -> None:
        self.system_name = (system_name or platform.system()).lower()
        self.machine_name = (machine_name or platform.machine()).lower()

    def build_command(self, request: FirmwareFlashRequest) -> ResolvedFlashCommand:
        firmware_path = request.firmware_path.expanduser().resolve()
        if not firmware_path.is_file():
            raise FileNotFoundError(f"Firmware file not found: {firmware_path}")
        if request.board_family == BoardFamily.ATMEGA2560:
            tool_root = self.resolve_tool_root(request.tool_root)
            return self._build_avrdude_command(request, tool_root, firmware_path)
        if request.board_family in {BoardFamily.TEENSY35, BoardFamily.TEENSY36, BoardFamily.TEENSY41}:
            return self._build_teensy_command(request, firmware_path)
        if request.board_family == BoardFamily.STM32F407_DFU:
            tool_root = self.resolve_tool_root(request.tool_root)
            return self._build_dfu_command(request, tool_root, firmware_path)
        raise RuntimeError(f"Unsupported board family: {request.board_family.value}")

    def flash(
        self,
        request: FirmwareFlashRequest,
        progress_callback: Callable[[FlashProgress], None] | None = None,
    ) -> FirmwareFlashResult:
        command = self.build_command(request)
        if progress_callback is not None:
            progress_callback(FlashProgress(message=f"Executing {command.tool.value}", percent=0))
            progress_callback(FlashProgress(message=command.display_command()))

        if command.internal:
            return self._flash_internal(request, command, progress_callback)

        process = subprocess.Popen(
            [str(command.executable), *command.arguments],
            cwd=command.working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        stream_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        output_parts: list[str] = []
        progress_updates: list[int] = []
        avrdude_buffer = ""
        teensy_buffer = ""
        dfu_buffer = ""
        burn_started = False

        def enqueue_stream(name: str, stream: object) -> None:
            assert stream is not None
            while True:
                chunk = stream.read(1)
                if chunk == "":
                    break
                stream_queue.put((name, chunk))
            stream_queue.put((name, None))

        stdout_thread = threading.Thread(target=enqueue_stream, args=("stdout", process.stdout), daemon=True)
        stderr_thread = threading.Thread(target=enqueue_stream, args=("stderr", process.stderr), daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        closed_streams = 0
        while closed_streams < 2:
            stream_name, chunk = stream_queue.get()
            if chunk is None:
                closed_streams += 1
                continue
            output_parts.append(chunk)

            if command.tool == FlashTool.AVRDUDE and stream_name == "stderr":
                avrdude_buffer += chunk
                if not burn_started and avrdude_buffer.endswith("Writing | "):
                    burn_started = True
                elif burn_started and chunk == "#":
                    progress = min(100, len(progress_updates) + 1)
                    progress_updates.append(progress)
                    if progress_callback is not None:
                        progress_callback(FlashProgress(message="Flashing AVR firmware", percent=progress))

            elif command.tool == FlashTool.TEENSY:
                teensy_buffer += chunk
                if not burn_started and ("Programming" in teensy_buffer or teensy_buffer.endswith("Writing | ")):
                    burn_started = True
                elif burn_started and chunk in {".", "#"}:
                    progress = min(100, len(progress_updates) + 1)
                    progress_updates.append(progress)
                    if progress_callback is not None:
                        progress_callback(FlashProgress(message="Flashing Teensy firmware", percent=progress))

            elif command.tool == FlashTool.DFU_UTIL and stream_name == "stdout":
                dfu_buffer += chunk
                if not burn_started and "Erase    done." in dfu_buffer:
                    burn_started = True
                    if progress_callback is not None:
                        progress_callback(FlashProgress(message="STM32 erase completed", percent=0))
                elif burn_started and chunk == "=":
                    progress = min(100, (len(progress_updates) + 1) * 4)
                    progress_updates.append(progress)
                    if progress_callback is not None:
                        progress_callback(FlashProgress(message="Flashing STM32 firmware", percent=progress))

        exit_code = process.wait()
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        output = "".join(output_parts)
        if progress_callback is not None:
            message = "Flash completed" if exit_code == 0 else f"Flash failed with exit code {exit_code}"
            progress_callback(FlashProgress(message=message, percent=100 if exit_code == 0 else None))
        return FirmwareFlashResult(
            command=command,
            exit_code=exit_code,
            output=output,
            progress_updates=progress_updates,
        )

    def resolve_tool_root(self, requested_root: Path | None) -> Path:
        candidates: list[Path] = []
        if requested_root is not None and str(requested_root).strip():
            candidates.append(requested_root.expanduser().resolve())
        candidates.append(bundled_tools_root().resolve())
        candidates.append(Path(r"C:\Users\Cornelio\Desktop\SpeedyLoader-1.7.0"))
        for candidate in candidates:
            if (candidate / "bin").exists():
                return candidate
        checked = ", ".join(str(candidate) for candidate in candidates)
        raise FileNotFoundError(f"No flashing tools root found. Checked: {checked}")

    def _flash_internal(
        self,
        request: FirmwareFlashRequest,
        command: ResolvedFlashCommand,
        progress_callback: Callable[[FlashProgress], None] | None,
    ) -> FirmwareFlashResult:
        if command.tool == FlashTool.TEENSY and self._supports_internal_teensy():
            return self._flash_teensy_windows(request, command, progress_callback)
        raise RuntimeError(f"Unsupported internal flash command: {command.tool.value}")

    def _flash_teensy_windows(
        self,
        request: FirmwareFlashRequest,
        command: ResolvedFlashCommand,
        progress_callback: Callable[[FlashProgress], None] | None,
    ) -> FirmwareFlashResult:
        spec = self._teensy_mcu_spec(request.board_family)
        firmware_path = request.firmware_path.expanduser().resolve()
        image = self._read_teensy_hex(firmware_path, spec)
        output_lines = [
            "Embedded Teensy loader",
            f'Read "{firmware_path}": {image.byte_count} bytes, {image.byte_count / spec.code_size * 100.0:.1f}% usage',
        ]
        progress_updates: list[int] = []
        handle: int | None = None
        auto_reboot_requested = False
        auto_reboot_succeeded = False

        if request.serial_port:
            auto_reboot_requested = True
            if progress_callback is not None:
                progress_callback(FlashProgress(message=f"Requesting Teensy reboot on {request.serial_port}", percent=0))
            if self._try_teensy_serial_reboot(request.serial_port):
                auto_reboot_succeeded = True
                output_lines.append(f"Requested auto reboot on {request.serial_port}")
            else:
                output_lines.append(f"Auto reboot request on {request.serial_port} was unavailable")

        if progress_callback is not None:
            if auto_reboot_succeeded:
                wait_message = "Waiting for Teensy bootloader after auto reboot."
            elif auto_reboot_requested:
                wait_message = "Waiting for Teensy bootloader. Press the reset button if auto reboot does not trigger."
            else:
                wait_message = "Waiting for Teensy bootloader. Press the reset button."
            progress_callback(FlashProgress(message=wait_message, percent=0))

        try:
            handle = self._open_teensy_bootloader()
            output_lines.append("Found HalfKay Bootloader")
            block_addresses = self._teensy_block_addresses(image, spec)
            total_blocks = max(1, len(block_addresses))

            for index, addr in enumerate(block_addresses, start=1):
                payload = self._teensy_payload(image, spec, addr)
                timeout = 45.0 if index <= 5 else 0.5
                write_result = self._teensy_write(handle, payload, timeout)
                if not write_result.ok:
                    raise RuntimeError(
                        f"Failed to write firmware block {index}/{total_blocks} at 0x{addr:06X}: "
                        f"{write_result.detail or 'unknown USB write error'}"
                    )
                progress = min(99, max(1, int(index * 100 / total_blocks)))
                progress_updates.append(progress)
                if progress_callback is not None:
                    progress_callback(FlashProgress(message="Flashing Teensy firmware", percent=progress))

            self._teensy_boot(handle, spec)
            output_lines.append("Booting")
        finally:
            if handle is not None:
                self._close_handle(handle)

        if progress_callback is not None:
            progress_callback(FlashProgress(message="Flash completed", percent=100))
        return FirmwareFlashResult(
            command=command,
            exit_code=0,
            output="\n".join(output_lines),
            progress_updates=progress_updates,
        )

    def _build_avrdude_command(
        self,
        request: FirmwareFlashRequest,
        tool_root: Path,
        firmware_path: Path,
    ) -> ResolvedFlashCommand:
        if not request.serial_port:
            raise ValueError("Serial port is required for ATMEGA2560 flashing.")
        platform_dir = self._platform_dir(FlashTool.AVRDUDE)
        executable = tool_root / "bin" / platform_dir / self._tool_filename(FlashTool.AVRDUDE)
        config_path = tool_root / "bin" / platform_dir / "avrdude.conf"
        self._require_file(executable)
        self._require_file(config_path)
        return ResolvedFlashCommand(
            tool=FlashTool.AVRDUDE,
            executable=executable,
            arguments=[
                "-v",
                "-patmega2560",
                "-C",
                str(config_path),
                "-cwiring",
                "-b",
                "115200",
                "-P",
                request.serial_port,
                "-D",
                "-U",
                f"flash:w:{firmware_path}:i",
            ],
            working_directory=executable.parent,
        )

    def _build_teensy_command(self, request: FirmwareFlashRequest, firmware_path: Path) -> ResolvedFlashCommand:
        if self._supports_internal_teensy():
            mcu = self._teensy_mcu_spec(request.board_family).name
            return ResolvedFlashCommand(
                tool=FlashTool.TEENSY,
                executable=Path("embedded-teensy-loader"),
                arguments=[f"--mcu={mcu}", "-w", str(firmware_path)],
                working_directory=firmware_path.parent,
                display_override=f'embedded-teensy-loader --mcu={mcu} -w "{firmware_path}"',
                internal=True,
            )

        tool_root = self.resolve_tool_root(request.tool_root)
        platform_dir = self._platform_dir(FlashTool.TEENSY)
        tools_dir = tool_root / "bin" / platform_dir
        cli_executable = tools_dir / self._teensy_cli_filename()
        if cli_executable.exists():
            return ResolvedFlashCommand(
                tool=FlashTool.TEENSY,
                executable=cli_executable,
                arguments=[
                    f"--mcu={self._teensy_mcu_spec(request.board_family).name}",
                    "-w",
                    "-v",
                    str(firmware_path),
                ],
                working_directory=tools_dir,
            )

        executable = tools_dir / self._tool_filename(FlashTool.TEENSY)
        self._require_file(executable)
        return ResolvedFlashCommand(
            tool=FlashTool.TEENSY,
            executable=executable,
            arguments=[
                f"-board={request.board_family.value}",
                "-reboot",
                f"-file={firmware_path.stem}",
                f"-path={firmware_path.parent}",
                f"-tools={tools_dir}",
            ],
            working_directory=tools_dir,
        )

    def _build_dfu_command(
        self,
        request: FirmwareFlashRequest,
        tool_root: Path,
        firmware_path: Path,
    ) -> ResolvedFlashCommand:
        vid = (request.usb_vid or "").strip()
        pid = (request.usb_pid or "").strip()
        if not vid or not pid:
            raise ValueError("USB VID and PID are required for STM32 DFU flashing.")
        platform_dir = self._platform_dir(FlashTool.DFU_UTIL)
        executable = tool_root / "bin" / platform_dir / self._tool_filename(FlashTool.DFU_UTIL)
        self._require_file(executable)
        return ResolvedFlashCommand(
            tool=FlashTool.DFU_UTIL,
            executable=executable,
            arguments=[
                "-d",
                f"{vid}:{pid}",
                "-a",
                "0",
                "-s",
                "0x08000000:leave",
                "-D",
                str(firmware_path),
            ],
            working_directory=executable.parent,
        )

    def _platform_dir(self, tool: FlashTool) -> str:
        if tool == FlashTool.AVRDUDE:
            if self.system_name == "windows":
                return "avrdude-windows"
            if self.system_name == "darwin":
                return "avrdude-darwin-x86_64"
            if self.system_name == "linux":
                return self._linux_platform_dir("avrdude")
        if tool == FlashTool.TEENSY:
            if self.system_name == "windows":
                return "teensy_loader_cli-windows"
            if self.system_name == "darwin":
                return "teensy_loader_cli-darwin-x86_64"
            if self.system_name == "linux":
                return self._linux_platform_dir("teensy_loader_cli")
        if tool == FlashTool.DFU_UTIL:
            if self.system_name == "windows":
                return "dfuutil-windows"
            if self.system_name == "darwin":
                return "dfuutil-darwin-x86_64"
            if self.system_name == "linux":
                return self._linux_platform_dir("dfuutil")
        raise RuntimeError(f"Unsupported platform '{self.system_name}' for {tool.value}.")

    def _tool_filename(self, tool: FlashTool) -> str:
        if tool == FlashTool.AVRDUDE:
            return "avrdude.exe" if self.system_name == "windows" else "avrdude"
        if tool == FlashTool.TEENSY:
            return "teensy_post_compile.exe" if self.system_name == "windows" else "teensy_post_compile"
        if tool == FlashTool.DFU_UTIL:
            if self.system_name == "windows":
                return "dfu-util-static.exe"
            return "dfu-util"
        raise RuntimeError(f"Unsupported tool: {tool.value}")

    def _linux_platform_dir(self, prefix: str) -> str:
        if self.machine_name in {"x86_64", "amd64"}:
            suffix = "linux_x86_64" if prefix != "dfuutil" else "linux-x86_64"
        elif self.machine_name in {"i386", "i686", "x86"}:
            suffix = "linux_i686" if prefix != "dfuutil" else "linux-i686"
        elif self.machine_name in {"armv7l", "arm"}:
            suffix = "armhf"
        elif self.machine_name in {"aarch64", "arm64"}:
            suffix = "aarch64"
        else:
            raise RuntimeError(f"Unsupported machine architecture: {self.machine_name}")
        return f"{prefix}-{suffix}"

    def _supports_internal_teensy(self) -> bool:
        return self.system_name == "windows"

    @staticmethod
    def _teensy_mcu_spec(board_family: BoardFamily) -> _TeensyMcuSpec:
        mapping = {
            BoardFamily.TEENSY35: _TeensyMcuSpec("TEENSY35", 524288, 1024),
            BoardFamily.TEENSY36: _TeensyMcuSpec("TEENSY36", 1048576, 1024),
            BoardFamily.TEENSY41: _TeensyMcuSpec("TEENSY41", 8126464, 1024),
        }
        try:
            return mapping[board_family]
        except KeyError as exc:
            raise RuntimeError(f"Unsupported Teensy board family: {board_family.value}") from exc

    def _read_teensy_hex(self, firmware_path: Path, spec: _TeensyMcuSpec) -> _TeensyHexImage:
        bytes_by_address: dict[int, int] = {}
        byte_count = 0
        extended_addr = 0

        for lineno, raw_line in enumerate(firmware_path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if not line.startswith(":") or len(line) < 11:
                raise ValueError(f"Invalid Intel HEX line {lineno}")

            length = int(line[1:3], 16)
            addr = int(line[3:7], 16)
            record_type = int(line[7:9], 16)
            data_text = line[9 : 9 + (length * 2)]
            checksum = int(line[9 + (length * 2) : 11 + (length * 2)], 16)
            values = [length, (addr >> 8) & 0xFF, addr & 0xFF, record_type]
            data_bytes = [int(data_text[index : index + 2], 16) for index in range(0, len(data_text), 2)]
            values.extend(data_bytes)
            if ((sum(values) + checksum) & 0xFF) != 0:
                raise ValueError(f"Invalid Intel HEX checksum on line {lineno}")

            if record_type == 0x01:
                break
            if record_type == 0x02:
                if length != 2:
                    raise ValueError(f"Invalid Intel HEX segment address on line {lineno}")
                extended_addr = int(data_text, 16) << 4
                continue
            if record_type == 0x04:
                if length != 2:
                    raise ValueError(f"Invalid Intel HEX linear address on line {lineno}")
                extended_addr = int(data_text, 16) << 16
                if (
                    spec.code_size > 1048576
                    and spec.block_size >= 1024
                    and 0x60000000 <= extended_addr < 0x60000000 + spec.code_size
                ):
                    extended_addr -= 0x60000000
                continue
            if record_type != 0x00:
                continue

            base_address = addr + extended_addr
            if base_address < 0 or base_address + length > min(_MAX_TEENSY_MEMORY_SIZE, spec.code_size):
                raise ValueError(f"HEX data on line {lineno} is outside supported memory range")

            for offset, value in enumerate(data_bytes):
                bytes_by_address[base_address + offset] = value
            byte_count += length

        return _TeensyHexImage(bytes_by_address=bytes_by_address, byte_count=byte_count)

    def _teensy_block_addresses(self, image: _TeensyHexImage, spec: _TeensyMcuSpec) -> list[int]:
        block_addresses: list[int] = []
        for addr in range(0, spec.code_size, spec.block_size):
            if block_addresses:
                if not any((addr + offset) in image.bytes_by_address for offset in range(spec.block_size)):
                    continue
                if self._teensy_block_is_blank(image, addr, spec.block_size):
                    continue
            block_addresses.append(addr)
        return block_addresses

    @staticmethod
    def _teensy_block_is_blank(image: _TeensyHexImage, addr: int, block_size: int) -> bool:
        for offset in range(block_size):
            value = image.bytes_by_address.get(addr + offset)
            if value is not None and value != 0xFF:
                return False
        return True

    @staticmethod
    def _teensy_payload(image: _TeensyHexImage, spec: _TeensyMcuSpec, addr: int) -> bytes:
        if spec.block_size in {512, 1024}:
            payload = bytearray(spec.block_size + 64)
            payload[0] = addr & 0xFF
            payload[1] = (addr >> 8) & 0xFF
            payload[2] = (addr >> 16) & 0xFF
            for offset in range(spec.block_size):
                payload[64 + offset] = image.bytes_by_address.get(addr + offset, 0xFF)
            return bytes(payload)

        payload = bytearray(spec.block_size + 2)
        if spec.code_size < 0x10000:
            payload[0] = addr & 0xFF
            payload[1] = (addr >> 8) & 0xFF
        else:
            payload[0] = (addr >> 8) & 0xFF
            payload[1] = (addr >> 16) & 0xFF
        for offset in range(spec.block_size):
            payload[2 + offset] = image.bytes_by_address.get(addr + offset, 0xFF)
        return bytes(payload)

    def _teensy_boot(self, handle: int, spec: _TeensyMcuSpec) -> None:
        write_size = spec.block_size + (64 if spec.block_size in {512, 1024} else 2)
        payload = bytearray(write_size)
        payload[0] = 0xFF
        payload[1] = 0xFF
        payload[2] = 0xFF
        write_result = self._teensy_write(handle, bytes(payload), 0.5)
        if not write_result.ok:
            raise RuntimeError(f"Failed to reboot Teensy after programming: {write_result.detail}")

    def _open_teensy_bootloader(self) -> int:
        while True:
            handle = self._open_usb_device(0x16C0, 0x0478)
            if handle is not None:
                return handle
            time.sleep(0.25)

    @staticmethod
    def _try_teensy_serial_reboot(port: str) -> bool:
        try:
            import serial  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            return False

        try:
            with serial.Serial(port=port, baudrate=134, timeout=0.25, write_timeout=0.25):
                time.sleep(0.05)
            time.sleep(0.25)
            return True
        except Exception:
            return False

    def _open_usb_device(self, vid: int, pid: int) -> int | None:
        if self.system_name != "windows":
            raise RuntimeError("Embedded Teensy flashing is only implemented for Windows.")

        setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
        hid = ctypes.WinDLL("hid", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        wintypes = ctypes.wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("InterfaceClassGuid", GUID),
                ("Flags", wintypes.DWORD),
                ("Reserved", ctypes.c_void_p),
            ]

        class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("DevicePath", wintypes.WCHAR * 1),
            ]

        class HIDD_ATTRIBUTES(ctypes.Structure):
            _fields_ = [
                ("Size", wintypes.ULONG),
                ("VendorID", wintypes.USHORT),
                ("ProductID", wintypes.USHORT),
                ("VersionNumber", wintypes.USHORT),
            ]

        DIGCF_PRESENT = 0x00000002
        DIGCF_DEVICEINTERFACE = 0x00000010
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        FILE_FLAG_OVERLAPPED = 0x40000000
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
        hid.HidD_GetHidGuid.restype = None
        hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
        hid.HidD_GetAttributes.restype = wintypes.BOOLEAN
        setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
        setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
        setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.POINTER(GUID),
            wintypes.DWORD,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
        ]
        setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOLEAN
        setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOLEAN
        setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
        setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOLEAN
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOLEAN

        guid = GUID()
        hid.HidD_GetHidGuid(ctypes.byref(guid))
        device_info_set = setupapi.SetupDiGetClassDevsW(
            ctypes.byref(guid),
            None,
            None,
            DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
        )
        if device_info_set == INVALID_HANDLE_VALUE:
            return None

        try:
            index = 0
            while True:
                interface_data = SP_DEVICE_INTERFACE_DATA()
                interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
                if not setupapi.SetupDiEnumDeviceInterfaces(
                    device_info_set,
                    None,
                    ctypes.byref(guid),
                    index,
                    ctypes.byref(interface_data),
                ):
                    break

                required_size = wintypes.DWORD()
                setupapi.SetupDiGetDeviceInterfaceDetailW(
                    device_info_set,
                    ctypes.byref(interface_data),
                    None,
                    0,
                    ctypes.byref(required_size),
                    None,
                )
                detail_buffer = ctypes.create_string_buffer(required_size.value)
                detail_data = ctypes.cast(detail_buffer, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
                detail_data.contents.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)

                if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                    device_info_set,
                    ctypes.byref(interface_data),
                    detail_data,
                    required_size,
                    None,
                    None,
                ):
                    index += 1
                    continue

                device_path = ctypes.wstring_at(
                    ctypes.addressof(detail_data.contents) + SP_DEVICE_INTERFACE_DETAIL_DATA_W.DevicePath.offset
                )
                handle = kernel32.CreateFileW(
                    device_path,
                    GENERIC_READ | GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None,
                    OPEN_EXISTING,
                    FILE_FLAG_OVERLAPPED,
                    None,
                )
                if handle == INVALID_HANDLE_VALUE:
                    index += 1
                    continue

                attributes = HIDD_ATTRIBUTES()
                attributes.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
                if not hid.HidD_GetAttributes(handle, ctypes.byref(attributes)):
                    kernel32.CloseHandle(handle)
                    index += 1
                    continue
                if attributes.VendorID == vid and attributes.ProductID == pid:
                    return handle

                kernel32.CloseHandle(handle)
                index += 1
        finally:
            setupapi.SetupDiDestroyDeviceInfoList(device_info_set)

        return None

    def _teensy_write(self, handle: int, payload: bytes, timeout: float) -> _UsbWriteResult:
        deadline = time.monotonic() + timeout
        last_result = _UsbWriteResult(False, "unknown USB write error")

        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            attempt = self._write_usb_device_once(handle, payload, remaining)
            if attempt.ok:
                return attempt
            last_result = attempt
            time.sleep(0.01)

        return last_result

    def _write_usb_device_once(self, handle: int, payload: bytes, timeout: float) -> _UsbWriteResult:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        wintypes = ctypes.wintypes

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [
                ("Internal", wintypes.WPARAM),
                ("InternalHigh", wintypes.WPARAM),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        ERROR_IO_PENDING = 997
        WAIT_OBJECT_0 = 0
        WAIT_TIMEOUT = 258

        kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOLEAN, wintypes.BOOLEAN, wintypes.LPCWSTR]
        kernel32.CreateEventW.restype = wintypes.HANDLE
        kernel32.WriteFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(OVERLAPPED),
        ]
        kernel32.WriteFile.restype = wintypes.BOOLEAN
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
        kernel32.ResetEvent.restype = wintypes.BOOLEAN
        kernel32.CancelIo.argtypes = [wintypes.HANDLE]
        kernel32.CancelIo.restype = wintypes.BOOLEAN
        kernel32.GetOverlappedResult.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(OVERLAPPED),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.BOOLEAN,
        ]
        kernel32.GetOverlappedResult.restype = wintypes.BOOLEAN
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOLEAN

        buffer = (ctypes.c_ubyte * (len(payload) + 1))()
        buffer[0] = 0
        ctypes.memmove(ctypes.byref(buffer, 1), payload, len(payload))

        event = kernel32.CreateEventW(None, True, False, None)
        if not event:
            return _UsbWriteResult(False, f"CreateEventW failed with error {ctypes.get_last_error()}")

        try:
            if not kernel32.ResetEvent(event):
                return _UsbWriteResult(False, f"ResetEvent failed with error {ctypes.get_last_error()}")
            overlapped = OVERLAPPED()
            overlapped.hEvent = event
            bytes_written = wintypes.DWORD()
            if not kernel32.WriteFile(handle, buffer, len(payload) + 1, None, ctypes.byref(overlapped)):
                write_error = ctypes.get_last_error()
                if write_error != ERROR_IO_PENDING:
                    return _UsbWriteResult(False, f"WriteFile failed with error {write_error}")
                result = kernel32.WaitForSingleObject(event, int(timeout * 1000))
                if result == WAIT_TIMEOUT:
                    kernel32.CancelIo(handle)
                    return _UsbWriteResult(False, f"WaitForSingleObject timed out after {timeout:.1f}s")
                if result != WAIT_OBJECT_0:
                    return _UsbWriteResult(False, f"WaitForSingleObject returned {result}")
            if not kernel32.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(bytes_written), False):
                return _UsbWriteResult(False, f"GetOverlappedResult failed with error {ctypes.get_last_error()}")
            if bytes_written.value <= 0:
                return _UsbWriteResult(False, "GetOverlappedResult reported zero bytes written")
            return _UsbWriteResult(True)
        finally:
            kernel32.CloseHandle(event)

    @staticmethod
    def _close_handle(handle: int) -> None:
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)

    def _teensy_cli_filename(self) -> str:
        return "teensy_loader_cli.exe" if self.system_name == "windows" else "teensy_loader_cli"

    @staticmethod
    def _require_file(path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Required flashing tool not found: {path}")
