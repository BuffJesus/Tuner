// SPDX-License-Identifier: MIT
//
// doctest cases for `ini_setting_context_help_parser.hpp`.

#include "doctest.h"

#include "tuner_core/ini_setting_context_help_parser.hpp"

using namespace tuner_core;

TEST_CASE("setting_context_help: parses simple key=value pairs") {
    const char* text = R"(
[SettingContextHelp]
dwellLim = "Coil dwell time limit"
nCylinders = "Number of cylinders"
reqFuel = "Required fuel pulse width"
)";
    auto section = parse_setting_context_help_section(text);
    REQUIRE(section.help_by_name.size() == 3);
    CHECK(section.help_by_name["dwellLim"] == "Coil dwell time limit");
    CHECK(section.help_by_name["nCylinders"] == "Number of cylinders");
    CHECK(section.help_by_name["reqFuel"] == "Required fuel pulse width");
}

TEST_CASE("setting_context_help: strips quotes and semicolon comments") {
    const char* text = R"(
[SettingContextHelp]
paramA = "Quoted help"
paramB = "Help ends here"; trailing comment
paramC = Bare help text without quotes
)";
    auto section = parse_setting_context_help_section(text);
    REQUIRE(section.help_by_name.size() == 3);
    CHECK(section.help_by_name["paramA"] == "Quoted help");
    CHECK(section.help_by_name["paramB"] == "Help ends here");
    CHECK(section.help_by_name["paramC"] == "Bare help text without quotes");
}

TEST_CASE("setting_context_help: lines outside section ignored") {
    const char* text = R"(
[Constants]
scalar = foo, U08, 0
skipped = "Should be ignored"

[SettingContextHelp]
wanted = "Kept"
)";
    auto section = parse_setting_context_help_section(text);
    REQUIRE(section.help_by_name.size() == 1);
    CHECK(section.help_by_name["wanted"] == "Kept");
}

TEST_CASE("setting_context_help: missing equals lines skipped") {
    const char* text = R"(
[SettingContextHelp]
valid = "Has value"
no_equals_line
another = "Also valid"
)";
    auto section = parse_setting_context_help_section(text);
    REQUIRE(section.help_by_name.size() == 2);
    CHECK(section.help_by_name.count("valid") == 1);
    CHECK(section.help_by_name.count("another") == 1);
    CHECK(section.help_by_name.count("no_equals_line") == 0);
}

TEST_CASE("setting_context_help: comments and blank lines skipped") {
    const char* text = R"(
[SettingContextHelp]
; comment line
paramA = "help A"

# also a comment
paramB = "help B"
)";
    auto section = parse_setting_context_help_section(text);
    REQUIRE(section.help_by_name.size() == 2);
}

TEST_CASE("setting_context_help: case-insensitive section header match") {
    const char* text = R"(
[settingcontexthelp]
p = "lowercase section"
)";
    auto section = parse_setting_context_help_section(text);
    REQUIRE(section.help_by_name.size() == 1);
    CHECK(section.help_by_name["p"] == "lowercase section");
}

TEST_CASE("setting_context_help: preprocessor #if gating") {
    const char* text = R"(
#set FEATURE_X
[SettingContextHelp]
#if FEATURE_X
paramX = "X enabled"
#else
paramX = "X disabled"
#endif
)";
    auto section = parse_setting_context_help_section_preprocessed(text);
    REQUIRE(section.help_by_name.size() == 1);
    CHECK(section.help_by_name["paramX"] == "X enabled");
}

TEST_CASE("setting_context_help: active_settings override gates branches") {
    const char* text = R"(
#set DEFAULT_FEATURE
[SettingContextHelp]
#if USER_FEATURE
wanted = "user mode"
#else
wanted = "default mode"
#endif
)";
    auto section = parse_setting_context_help_section_preprocessed(text, {"USER_FEATURE"});
    CHECK(section.help_by_name["wanted"] == "user mode");
}

TEST_CASE("setting_context_help: empty input") {
    auto section = parse_setting_context_help_section("");
    CHECK(section.help_by_name.empty());
}

TEST_CASE("setting_context_help: section present but empty") {
    auto section = parse_setting_context_help_section("[SettingContextHelp]\n");
    CHECK(section.help_by_name.empty());
}

TEST_CASE("setting_context_help: empty key skipped") {
    const char* text = R"(
[SettingContextHelp]
= "dangling value"
valid = "present"
)";
    auto section = parse_setting_context_help_section(text);
    REQUIRE(section.help_by_name.size() == 1);
    CHECK(section.help_by_name.count("valid") == 1);
}
