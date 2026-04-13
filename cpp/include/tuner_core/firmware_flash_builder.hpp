// SPDX-License-Identifier: MIT
//
// tuner_core::firmware_flash_builder — pure-logic port of the
// platform/argument-builder helpers in `FirmwareFlashService`
// (`src/tuner/services/firmware_flash_service.py`).
//
// I/O — subprocess execution, file existence checks, USB device
// open / write / close, hex-image parsing — stays Python. This module
// owns only the pure helpers:
//
//   - platform string lookups (per (tool, system, machine) triple)
//   - tool filename lookups
//   - Teensy MCU spec lookup (board family -> {name, code_size, block_size})
//   - "use internal teensy" check (Windows-only)
//   - command argument list builders for AVRDUDE / Teensy CLI / legacy
//     Teensy / DFU / internal Teensy
//
// Each function is pure: takes plain values, returns plain values.

#pragma once

#include "tuner_core/board_detection.hpp"

#include <string>
#include <vector>

namespace tuner_core::firmware_flash_builder {

// Mirror of the Python `FlashTool` enum from `tuner.domain.firmware`.
// Stringified the same way the Python `Enum.value` does.
enum class FlashTool {
    AVRDUDE,
    TEENSY,
    DFU_UTIL,
};

std::string_view to_string(FlashTool tool) noexcept;

// Pure mirror of the private `_TeensyMcuSpec` dataclass — Teensy
// model name + code-section size + block size in bytes.
struct TeensyMcuSpec {
    std::string name;
    int code_size = 0;
    int block_size = 0;
};

// `_platform_dir` parity: pick the per-(tool, system, machine)
// platform-tools subdirectory under `<tool_root>/bin/`.
//   tool         -> AVRDUDE | TEENSY | DFU_UTIL
//   system_name  -> "windows" / "darwin" / "linux"  (lowercased)
//   machine_name -> "x86_64" / "amd64" / "i386" / "i686" / "x86" /
//                   "armv7l" / "arm" / "aarch64" / "arm64"  (lowercased)
// Throws `std::runtime_error` on unknown platform/architecture.
std::string platform_dir(FlashTool tool,
                         std::string_view system_name,
                         std::string_view machine_name);

// `_tool_filename` parity: the OS-specific binary name for `tool`.
// Throws on unknown tool.
std::string tool_filename(FlashTool tool, std::string_view system_name);

// `_linux_platform_dir` parity: assemble the linux subdirectory name
// for a given Python service tool prefix ("avrdude" / "teensy_loader_cli" /
// "dfuutil"). Throws on unknown architecture.
std::string linux_platform_dir(std::string_view prefix,
                               std::string_view machine_name);

// `_supports_internal_teensy` parity — true on Windows only.
bool supports_internal_teensy(std::string_view system_name) noexcept;

// `_teensy_cli_filename` parity — `"teensy_loader_cli.exe"` on
// Windows, `"teensy_loader_cli"` everywhere else.
std::string teensy_cli_filename(std::string_view system_name);

// `_teensy_mcu_spec` parity — board family -> Teensy MCU spec.
// Throws if `family` is not a Teensy.
TeensyMcuSpec teensy_mcu_spec(board_detection::BoardFamily family);

// ---------------------------------------------------------------------
// Command argument list builders (mirror of the `arguments=[...]`
// blocks in `_build_*_command`). All paths are passed in as strings
// the caller has already resolved on the I/O side. None of these
// builders touch the filesystem.
// ---------------------------------------------------------------------

// `_build_avrdude_command` arguments. Throws if `serial_port` is empty.
std::vector<std::string> build_avrdude_arguments(std::string_view serial_port,
                                                 std::string_view config_path,
                                                 std::string_view firmware_path);

// `_build_teensy_command` (CLI branch) arguments — used when
// `teensy_loader_cli.exe` is present in the bundled tools.
std::vector<std::string> build_teensy_cli_arguments(std::string_view mcu_name,
                                                    std::string_view firmware_path);

// `_build_teensy_command` (legacy `teensy_post_compile.exe` branch)
// arguments — used when only the post-compile helper is bundled.
std::vector<std::string> build_teensy_legacy_arguments(std::string_view board_family_value,
                                                       std::string_view firmware_stem,
                                                       std::string_view firmware_parent,
                                                       std::string_view tools_dir);

// `_build_teensy_command` (internal-loader branch) arguments — used
// when `_supports_internal_teensy()` is true.
std::vector<std::string> build_internal_teensy_arguments(std::string_view mcu_name,
                                                         std::string_view firmware_path);

// `_build_dfu_command` arguments. Throws if `vid` or `pid` is empty
// (mirrors the Python "USB VID and PID are required" guard).
std::vector<std::string> build_dfu_arguments(std::string_view vid,
                                             std::string_view pid,
                                             std::string_view firmware_path);

}  // namespace tuner_core::firmware_flash_builder
