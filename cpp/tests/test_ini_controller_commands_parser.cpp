// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniControllerCommandsParser.

#include "doctest.h"

#include "tuner_core/ini_controller_commands_parser.hpp"

#include <string>

TEST_CASE("parse_controller_commands_section ignores other sections") {
    auto section = tuner_core::parse_controller_commands_section(
        "[Other]\nfoo = \"E\\x01\\x02\"\n");
    CHECK(section.commands.empty());
}

TEST_CASE("parses a single 3-byte command") {
    auto section = tuner_core::parse_controller_commands_section(
        "[ControllerCommands]\n"
        "resetEcu = \"E\\xAB\\xCD\"\n");
    REQUIRE(section.commands.size() == 1);
    const auto& cmd = section.commands[0];
    CHECK(cmd.name == "resetEcu");
    REQUIRE(cmd.payload.size() == 3);
    CHECK(cmd.payload[0] == 'E');
    CHECK(cmd.payload[1] == 0xAB);
    CHECK(cmd.payload[2] == 0xCD);
}

TEST_CASE("parses multiple commands") {
    auto section = tuner_core::parse_controller_commands_section(
        "[ControllerCommands]\n"
        "a = \"E\\x01\\x02\"\n"
        "b = \"E\\x03\\x04\"\n"
        "c = \"E\\x05\\x06\"\n");
    REQUIRE(section.commands.size() == 3);
    CHECK(section.commands[0].name == "a");
    CHECK(section.commands[1].name == "b");
    CHECK(section.commands[2].name == "c");
    CHECK(section.commands[2].payload[2] == 0x06);
}

TEST_CASE("comma-separated parts are concatenated") {
    auto section = tuner_core::parse_controller_commands_section(
        "[ControllerCommands]\n"
        "combined = \"E\\x01\", \"\\x02\\x03\"\n");
    REQUIRE(section.commands.size() == 1);
    REQUIRE(section.commands[0].payload.size() == 4);
    CHECK(section.commands[0].payload[0] == 'E');
    CHECK(section.commands[0].payload[1] == 0x01);
    CHECK(section.commands[0].payload[2] == 0x02);
    CHECK(section.commands[0].payload[3] == 0x03);
}

TEST_CASE("inline comments are stripped") {
    auto section = tuner_core::parse_controller_commands_section(
        "[ControllerCommands]\n"
        "withComment = \"E\\x01\\x02\" ; some note\n");
    REQUIRE(section.commands.size() == 1);
    CHECK(section.commands[0].payload.size() == 3);
}

TEST_CASE("empty value lines are dropped") {
    auto section = tuner_core::parse_controller_commands_section(
        "[ControllerCommands]\n"
        "empty =\n"
        "good = \"E\\x01\\x02\"\n");
    REQUIRE(section.commands.size() == 1);
    CHECK(section.commands[0].name == "good");
}

TEST_CASE("comment-only and blank lines are skipped") {
    auto section = tuner_core::parse_controller_commands_section(
        "[ControllerCommands]\n"
        "; comment\n"
        "\n"
        "good = \"E\\x07\\x08\"\n");
    REQUIRE(section.commands.size() == 1);
}

TEST_CASE("preprocessor pipeline gates the section") {
    std::string text =
        "#if FEATURE_X\n"
        "[ControllerCommands]\n"
        "a = \"E\\x01\\x02\"\n"
        "#endif\n";
    auto enabled = tuner_core::parse_controller_commands_section_preprocessed(
        text, {"FEATURE_X"});
    CHECK(enabled.commands.size() == 1);
    auto disabled = tuner_core::parse_controller_commands_section_preprocessed(text, {});
    CHECK(disabled.commands.empty());
}
