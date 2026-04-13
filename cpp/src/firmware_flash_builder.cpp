// SPDX-License-Identifier: MIT
//
// Implementation of `firmware_flash_builder.hpp`.

#include "tuner_core/firmware_flash_builder.hpp"

#include <stdexcept>
#include <string>

namespace tuner_core::firmware_flash_builder {

std::string_view to_string(FlashTool tool) noexcept {
    switch (tool) {
        case FlashTool::AVRDUDE:  return "avrdude";
        case FlashTool::TEENSY:   return "teensy";
        case FlashTool::DFU_UTIL: return "dfu-util";
    }
    return "unknown";
}

std::string linux_platform_dir(std::string_view prefix,
                               std::string_view machine_name) {
    // Mirrors `_linux_platform_dir`. The dfu-util suffix uses dash
    // separators (`linux-x86_64`), the others use underscores
    // (`linux_x86_64`). ARM variants use plain `armhf` / `aarch64`
    // with no `linux*` prefix on either side.
    const bool dfu = (prefix == "dfuutil");
    std::string suffix;
    if (machine_name == "x86_64" || machine_name == "amd64") {
        suffix = dfu ? "linux-x86_64" : "linux_x86_64";
    } else if (machine_name == "i386" || machine_name == "i686" || machine_name == "x86") {
        suffix = dfu ? "linux-i686" : "linux_i686";
    } else if (machine_name == "armv7l" || machine_name == "arm") {
        suffix = "armhf";
    } else if (machine_name == "aarch64" || machine_name == "arm64") {
        suffix = "aarch64";
    } else {
        throw std::runtime_error(
            std::string("Unsupported machine architecture: ") + std::string(machine_name));
    }
    std::string out;
    out.reserve(prefix.size() + 1 + suffix.size());
    out.append(prefix);
    out.push_back('-');
    out.append(suffix);
    return out;
}

std::string platform_dir(FlashTool tool,
                         std::string_view system_name,
                         std::string_view machine_name) {
    if (tool == FlashTool::AVRDUDE) {
        if (system_name == "windows") return "avrdude-windows";
        if (system_name == "darwin")  return "avrdude-darwin-x86_64";
        if (system_name == "linux")   return linux_platform_dir("avrdude", machine_name);
    }
    if (tool == FlashTool::TEENSY) {
        if (system_name == "windows") return "teensy_loader_cli-windows";
        if (system_name == "darwin")  return "teensy_loader_cli-darwin-x86_64";
        if (system_name == "linux")   return linux_platform_dir("teensy_loader_cli", machine_name);
    }
    if (tool == FlashTool::DFU_UTIL) {
        if (system_name == "windows") return "dfuutil-windows";
        if (system_name == "darwin")  return "dfuutil-darwin-x86_64";
        if (system_name == "linux")   return linux_platform_dir("dfuutil", machine_name);
    }
    throw std::runtime_error(
        std::string("Unsupported platform '") + std::string(system_name) +
        std::string("' for ") + std::string(to_string(tool)) + ".");
}

std::string tool_filename(FlashTool tool, std::string_view system_name) {
    const bool windows = (system_name == "windows");
    switch (tool) {
        case FlashTool::AVRDUDE:
            return windows ? "avrdude.exe" : "avrdude";
        case FlashTool::TEENSY:
            return windows ? "teensy_post_compile.exe" : "teensy_post_compile";
        case FlashTool::DFU_UTIL:
            return windows ? "dfu-util-static.exe" : "dfu-util";
    }
    throw std::runtime_error(
        std::string("Unsupported tool: ") + std::string(to_string(tool)));
}

bool supports_internal_teensy(std::string_view system_name) noexcept {
    return system_name == "windows";
}

std::string teensy_cli_filename(std::string_view system_name) {
    return system_name == "windows"
        ? "teensy_loader_cli.exe"
        : "teensy_loader_cli";
}

TeensyMcuSpec teensy_mcu_spec(board_detection::BoardFamily family) {
    using board_detection::BoardFamily;
    switch (family) {
        case BoardFamily::TEENSY35: return {"TEENSY35",   524288, 1024};
        case BoardFamily::TEENSY36: return {"TEENSY36",  1048576, 1024};
        case BoardFamily::TEENSY41: return {"TEENSY41",  8126464, 1024};
        default: break;
    }
    throw std::runtime_error(
        std::string("Unsupported Teensy board family: ") +
        std::string(board_detection::to_string(family)));
}

std::vector<std::string> build_avrdude_arguments(std::string_view serial_port,
                                                 std::string_view config_path,
                                                 std::string_view firmware_path) {
    if (serial_port.empty()) {
        throw std::runtime_error("Serial port is required for ATMEGA2560 flashing.");
    }
    std::vector<std::string> args;
    args.reserve(13);
    args.emplace_back("-v");
    args.emplace_back("-patmega2560");
    args.emplace_back("-C");
    args.emplace_back(config_path);
    args.emplace_back("-cwiring");
    args.emplace_back("-b");
    args.emplace_back("115200");
    args.emplace_back("-P");
    args.emplace_back(serial_port);
    args.emplace_back("-D");
    args.emplace_back("-U");
    args.emplace_back(std::string("flash:w:") + std::string(firmware_path) + ":i");
    return args;
}

std::vector<std::string> build_teensy_cli_arguments(std::string_view mcu_name,
                                                    std::string_view firmware_path) {
    std::vector<std::string> args;
    args.reserve(4);
    args.emplace_back(std::string("--mcu=") + std::string(mcu_name));
    args.emplace_back("-w");
    args.emplace_back("-v");
    args.emplace_back(firmware_path);
    return args;
}

std::vector<std::string> build_teensy_legacy_arguments(std::string_view board_family_value,
                                                       std::string_view firmware_stem,
                                                       std::string_view firmware_parent,
                                                       std::string_view tools_dir) {
    std::vector<std::string> args;
    args.reserve(5);
    args.emplace_back(std::string("-board=") + std::string(board_family_value));
    args.emplace_back("-reboot");
    args.emplace_back(std::string("-file=") + std::string(firmware_stem));
    args.emplace_back(std::string("-path=") + std::string(firmware_parent));
    args.emplace_back(std::string("-tools=") + std::string(tools_dir));
    return args;
}

std::vector<std::string> build_internal_teensy_arguments(std::string_view mcu_name,
                                                         std::string_view firmware_path) {
    std::vector<std::string> args;
    args.reserve(3);
    args.emplace_back(std::string("--mcu=") + std::string(mcu_name));
    args.emplace_back("-w");
    args.emplace_back(firmware_path);
    return args;
}

std::vector<std::string> build_dfu_arguments(std::string_view vid,
                                             std::string_view pid,
                                             std::string_view firmware_path) {
    if (vid.empty() || pid.empty()) {
        throw std::runtime_error("USB VID and PID are required for STM32 DFU flashing.");
    }
    std::vector<std::string> args;
    args.reserve(8);
    args.emplace_back("-d");
    args.emplace_back(std::string(vid) + ":" + std::string(pid));
    args.emplace_back("-a");
    args.emplace_back("0");
    args.emplace_back("-s");
    args.emplace_back("0x08000000:leave");
    args.emplace_back("-D");
    args.emplace_back(firmware_path);
    return args;
}

}  // namespace tuner_core::firmware_flash_builder
