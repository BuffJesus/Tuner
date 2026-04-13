// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniLoggerDefinitionParser.

#include "doctest.h"

#include "tuner_core/ini_logger_definition_parser.hpp"

#include <string>

TEST_CASE("parse_logger_definition_section ignores text outside the section") {
    auto section = tuner_core::parse_logger_definition_section(
        "[Other]\n"
        "loggerDef = tooth, \"Tooth Log\", tooth\n");
    CHECK(section.loggers.empty());
}

TEST_CASE("parses a single tooth-style logger") {
    auto section = tuner_core::parse_logger_definition_section(
        "[LoggerDefinition]\n"
        "loggerDef = tooth, \"Tooth Log\", tooth\n"
        "startCommand = \"H\"\n"
        "stopCommand = \"h\"\n"
        "dataReadCommand = \"T\\x00\\x00\"\n"
        "dataReadTimeout = 5000\n"
        "continuousRead = false\n"
        "dataLength = 1024\n"
        "recordDef = 0, 0, 4\n"
        "recordField = toothTime, \"Tooth Time\", 0, 32, 1.0, \"us\"\n");
    REQUIRE(section.loggers.size() == 1);
    const auto& l = section.loggers[0];
    CHECK(l.name == "tooth");
    CHECK(l.display_name == "Tooth Log");
    CHECK(l.kind == "tooth");
    CHECK(l.start_command == "H");
    CHECK(l.stop_command == "h");
    REQUIRE(l.data_read_command.size() == 3);
    CHECK(l.data_read_command[0] == 'T');
    CHECK(l.data_read_command[1] == 0x00);
    CHECK(l.data_read_command[2] == 0x00);
    CHECK(l.data_read_timeout_ms == 5000);
    CHECK(l.continuous_read == false);
    CHECK(l.record_len == 4);
    // tooth: dataLength is bytes → 1024 / 4 = 256 records
    CHECK(l.record_count == 256);
    REQUIRE(l.record_fields.size() == 1);
    CHECK(l.record_fields[0].name == "toothTime");
    CHECK(l.record_fields[0].header == "Tooth Time");
    CHECK(l.record_fields[0].start_bit == 0);
    CHECK(l.record_fields[0].bit_count == 32);
    CHECK(l.record_fields[0].scale == doctest::Approx(1.0));
    CHECK(l.record_fields[0].units == "us");
}

TEST_CASE("composite logger uses dataLength as record count, not bytes") {
    auto section = tuner_core::parse_logger_definition_section(
        "[LoggerDefinition]\n"
        "loggerDef = comp, \"Composite\", composite\n"
        "dataLength = 256\n"
        "recordDef = 0, 0, 5\n");
    REQUIRE(section.loggers.size() == 1);
    // composite: record_count = dataLength as-is
    CHECK(section.loggers[0].record_count == 256);
    CHECK(section.loggers[0].record_len == 5);
}

TEST_CASE("$tsCanId is rewritten to two zero bytes in dataReadCommand") {
    auto section = tuner_core::parse_logger_definition_section(
        "[LoggerDefinition]\n"
        "loggerDef = tooth, \"T\", tooth\n"
        "dataReadCommand = \"T$tsCanId\"\n");
    REQUIRE(section.loggers.size() == 1);
    REQUIRE(section.loggers[0].data_read_command.size() == 3);
    CHECK(section.loggers[0].data_read_command[0] == 'T');
    CHECK(section.loggers[0].data_read_command[1] == 0x00);
    CHECK(section.loggers[0].data_read_command[2] == 0x00);
}

TEST_CASE("calcField lines are skipped, not stored as record fields") {
    auto section = tuner_core::parse_logger_definition_section(
        "[LoggerDefinition]\n"
        "loggerDef = comp, \"C\", composite\n"
        "calcField = derived, \"Derived\", \"someExpr\"\n"
        "recordField = real, \"Real\", 0, 8, 1.0, \"\"\n");
    REQUIRE(section.loggers.size() == 1);
    REQUIRE(section.loggers[0].record_fields.size() == 1);
    CHECK(section.loggers[0].record_fields[0].name == "real");
}

TEST_CASE("multiple logger blocks flush correctly") {
    auto section = tuner_core::parse_logger_definition_section(
        "[LoggerDefinition]\n"
        "loggerDef = a, \"A\", tooth\n"
        "dataLength = 16\n"
        "recordDef = 0, 0, 4\n"
        "loggerDef = b, \"B\", composite\n"
        "dataLength = 8\n"
        "recordDef = 0, 0, 5\n");
    REQUIRE(section.loggers.size() == 2);
    CHECK(section.loggers[0].name == "a");
    CHECK(section.loggers[0].record_count == 4);  // tooth: 16/4
    CHECK(section.loggers[1].name == "b");
    CHECK(section.loggers[1].record_count == 8);  // composite: 8 as-is
}

TEST_CASE("section change after a block flushes the active block") {
    auto section = tuner_core::parse_logger_definition_section(
        "[LoggerDefinition]\n"
        "loggerDef = a, \"A\", tooth\n"
        "dataLength = 8\n"
        "recordDef = 0, 0, 4\n"
        "[Other]\n"
        "loggerDef = b, \"B\", tooth\n");
    REQUIRE(section.loggers.size() == 1);
    CHECK(section.loggers[0].name == "a");
}

TEST_CASE("loggerDef with too few fields is skipped") {
    auto section = tuner_core::parse_logger_definition_section(
        "[LoggerDefinition]\n"
        "loggerDef = onlyName\n");
    CHECK(section.loggers.empty());
}

TEST_CASE("continuousRead = true is recognised case-insensitively") {
    auto section = tuner_core::parse_logger_definition_section(
        "[LoggerDefinition]\n"
        "loggerDef = a, \"A\", tooth\n"
        "continuousRead = TRUE\n");
    REQUIRE(section.loggers.size() == 1);
    CHECK(section.loggers[0].continuous_read == true);
}

TEST_CASE("preprocessor pipeline gates the section") {
    std::string text =
        "#if FEATURE_X\n"
        "[LoggerDefinition]\n"
        "loggerDef = a, \"A\", tooth\n"
        "#endif\n";
    auto enabled = tuner_core::parse_logger_definition_section_preprocessed(
        text, {"FEATURE_X"});
    CHECK(enabled.loggers.size() == 1);
    auto disabled = tuner_core::parse_logger_definition_section_preprocessed(text, {});
    CHECK(disabled.loggers.empty());
}
