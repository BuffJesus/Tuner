// SPDX-License-Identifier: MIT
//
// doctest cases for `firmware_flash_builder.hpp`.

#include "doctest.h"

#include "tuner_core/firmware_flash_builder.hpp"

#include <stdexcept>

using namespace tuner_core::firmware_flash_builder;
using BoardFamily = tuner_core::board_detection::BoardFamily;

TEST_CASE("to_string maps tools to Python enum values") {
    CHECK(to_string(FlashTool::AVRDUDE)  == "avrdude");
    CHECK(to_string(FlashTool::TEENSY)   == "teensy");
    CHECK(to_string(FlashTool::DFU_UTIL) == "dfu-util");
}

TEST_CASE("platform_dir Windows / Darwin / Linux paths per tool") {
    CHECK(platform_dir(FlashTool::AVRDUDE,  "windows", "x86_64") == "avrdude-windows");
    CHECK(platform_dir(FlashTool::AVRDUDE,  "darwin",  "x86_64") == "avrdude-darwin-x86_64");
    CHECK(platform_dir(FlashTool::AVRDUDE,  "linux",   "x86_64") == "avrdude-linux_x86_64");
    CHECK(platform_dir(FlashTool::AVRDUDE,  "linux",   "amd64")  == "avrdude-linux_x86_64");

    CHECK(platform_dir(FlashTool::TEENSY,   "windows", "x86_64") == "teensy_loader_cli-windows");
    CHECK(platform_dir(FlashTool::TEENSY,   "darwin",  "x86_64") == "teensy_loader_cli-darwin-x86_64");
    CHECK(platform_dir(FlashTool::TEENSY,   "linux",   "x86_64") == "teensy_loader_cli-linux_x86_64");

    CHECK(platform_dir(FlashTool::DFU_UTIL, "windows", "x86_64") == "dfuutil-windows");
    CHECK(platform_dir(FlashTool::DFU_UTIL, "darwin",  "x86_64") == "dfuutil-darwin-x86_64");
    CHECK(platform_dir(FlashTool::DFU_UTIL, "linux",   "x86_64") == "dfuutil-linux-x86_64");
}

TEST_CASE("platform_dir throws on unknown system") {
    CHECK_THROWS_AS(platform_dir(FlashTool::AVRDUDE, "freebsd", "x86_64"),
                    std::runtime_error);
}

TEST_CASE("linux_platform_dir handles every architecture branch") {
    CHECK(linux_platform_dir("avrdude", "x86_64")  == "avrdude-linux_x86_64");
    CHECK(linux_platform_dir("avrdude", "amd64")   == "avrdude-linux_x86_64");
    CHECK(linux_platform_dir("avrdude", "i386")    == "avrdude-linux_i686");
    CHECK(linux_platform_dir("avrdude", "i686")    == "avrdude-linux_i686");
    CHECK(linux_platform_dir("avrdude", "x86")     == "avrdude-linux_i686");
    CHECK(linux_platform_dir("avrdude", "armv7l")  == "avrdude-armhf");
    CHECK(linux_platform_dir("avrdude", "arm")     == "avrdude-armhf");
    CHECK(linux_platform_dir("avrdude", "aarch64") == "avrdude-aarch64");
    CHECK(linux_platform_dir("avrdude", "arm64")   == "avrdude-aarch64");

    // dfuutil takes the dash-separated linux suffix.
    CHECK(linux_platform_dir("dfuutil", "x86_64") == "dfuutil-linux-x86_64");
    CHECK(linux_platform_dir("dfuutil", "i386")   == "dfuutil-linux-i686");
    // ARM dfuutil still uses the bare arch (no leading "linux-").
    CHECK(linux_platform_dir("dfuutil", "armv7l") == "dfuutil-armhf");
}

TEST_CASE("linux_platform_dir throws on unknown architecture") {
    CHECK_THROWS_AS(linux_platform_dir("avrdude", "riscv64"),
                    std::runtime_error);
}

TEST_CASE("tool_filename per OS") {
    CHECK(tool_filename(FlashTool::AVRDUDE,  "windows") == "avrdude.exe");
    CHECK(tool_filename(FlashTool::AVRDUDE,  "linux")   == "avrdude");
    CHECK(tool_filename(FlashTool::AVRDUDE,  "darwin")  == "avrdude");
    CHECK(tool_filename(FlashTool::TEENSY,   "windows") == "teensy_post_compile.exe");
    CHECK(tool_filename(FlashTool::TEENSY,   "linux")   == "teensy_post_compile");
    CHECK(tool_filename(FlashTool::DFU_UTIL, "windows") == "dfu-util-static.exe");
    CHECK(tool_filename(FlashTool::DFU_UTIL, "linux")   == "dfu-util");
}

TEST_CASE("supports_internal_teensy is Windows-only") {
    CHECK(supports_internal_teensy("windows") == true);
    CHECK(supports_internal_teensy("linux")   == false);
    CHECK(supports_internal_teensy("darwin")  == false);
}

TEST_CASE("teensy_cli_filename per OS") {
    CHECK(teensy_cli_filename("windows") == "teensy_loader_cli.exe");
    CHECK(teensy_cli_filename("linux")   == "teensy_loader_cli");
    CHECK(teensy_cli_filename("darwin")  == "teensy_loader_cli");
}

TEST_CASE("teensy_mcu_spec returns the correct shape per Teensy family") {
    auto t35 = teensy_mcu_spec(BoardFamily::TEENSY35);
    CHECK(t35.name == "TEENSY35");
    CHECK(t35.code_size == 524288);
    CHECK(t35.block_size == 1024);

    auto t36 = teensy_mcu_spec(BoardFamily::TEENSY36);
    CHECK(t36.name == "TEENSY36");
    CHECK(t36.code_size == 1048576);
    CHECK(t36.block_size == 1024);

    auto t41 = teensy_mcu_spec(BoardFamily::TEENSY41);
    CHECK(t41.name == "TEENSY41");
    CHECK(t41.code_size == 8126464);
    CHECK(t41.block_size == 1024);
}

TEST_CASE("teensy_mcu_spec throws for non-Teensy families") {
    CHECK_THROWS_AS(teensy_mcu_spec(BoardFamily::ATMEGA2560),    std::runtime_error);
    CHECK_THROWS_AS(teensy_mcu_spec(BoardFamily::STM32F407_DFU), std::runtime_error);
}

TEST_CASE("build_avrdude_arguments matches Python list shape") {
    auto args = build_avrdude_arguments("COM3", "/tools/avrdude.conf", "/fw/firmware.hex");
    REQUIRE(args.size() == 12);
    CHECK(args[0]  == "-v");
    CHECK(args[1]  == "-patmega2560");
    CHECK(args[2]  == "-C");
    CHECK(args[3]  == "/tools/avrdude.conf");
    CHECK(args[4]  == "-cwiring");
    CHECK(args[5]  == "-b");
    CHECK(args[6]  == "115200");
    CHECK(args[7]  == "-P");
    CHECK(args[8]  == "COM3");
    CHECK(args[9]  == "-D");
    CHECK(args[10] == "-U");
    CHECK(args[11] == "flash:w:/fw/firmware.hex:i");
}

TEST_CASE("build_avrdude_arguments throws on missing serial port") {
    CHECK_THROWS_AS(
        build_avrdude_arguments("", "/tools/avrdude.conf", "/fw/firmware.hex"),
        std::runtime_error);
}

TEST_CASE("build_teensy_cli_arguments preserves CLI argument order") {
    auto args = build_teensy_cli_arguments("TEENSY41", "/fw/firmware.hex");
    REQUIRE(args.size() == 4);
    CHECK(args[0] == "--mcu=TEENSY41");
    CHECK(args[1] == "-w");
    CHECK(args[2] == "-v");
    CHECK(args[3] == "/fw/firmware.hex");
}

TEST_CASE("build_teensy_legacy_arguments preserves -board / -reboot / -file / -path / -tools order") {
    auto args = build_teensy_legacy_arguments(
        "TEENSY35", "speeduino_teensy35", "/fw", "/tools/teensy");
    REQUIRE(args.size() == 5);
    CHECK(args[0] == "-board=TEENSY35");
    CHECK(args[1] == "-reboot");
    CHECK(args[2] == "-file=speeduino_teensy35");
    CHECK(args[3] == "-path=/fw");
    CHECK(args[4] == "-tools=/tools/teensy");
}

TEST_CASE("build_internal_teensy_arguments returns the embedded-loader CLI shape") {
    auto args = build_internal_teensy_arguments("TEENSY41", "/fw/firmware.hex");
    REQUIRE(args.size() == 3);
    CHECK(args[0] == "--mcu=TEENSY41");
    CHECK(args[1] == "-w");
    CHECK(args[2] == "/fw/firmware.hex");
}

TEST_CASE("build_dfu_arguments builds the correct VID:PID device spec") {
    auto args = build_dfu_arguments("0483", "df11", "/fw/firmware.bin");
    REQUIRE(args.size() == 8);
    CHECK(args[0] == "-d");
    CHECK(args[1] == "0483:df11");
    CHECK(args[2] == "-a");
    CHECK(args[3] == "0");
    CHECK(args[4] == "-s");
    CHECK(args[5] == "0x08000000:leave");
    CHECK(args[6] == "-D");
    CHECK(args[7] == "/fw/firmware.bin");
}

TEST_CASE("build_dfu_arguments throws on missing VID or PID") {
    CHECK_THROWS_AS(build_dfu_arguments("",     "df11", "/fw/firmware.bin"), std::runtime_error);
    CHECK_THROWS_AS(build_dfu_arguments("0483", "",     "/fw/firmware.bin"), std::runtime_error);
}
