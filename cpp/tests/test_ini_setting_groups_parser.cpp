// SPDX-License-Identifier: MIT
//
// doctest cases for `ini_setting_groups_parser.hpp`.

#include "doctest.h"

#include "tuner_core/ini_setting_groups_parser.hpp"

#include <string>

using namespace tuner_core;

namespace {

const char* kSimpleSection = R"(
[SettingGroups]
settingGroup = mcu, "Controller in use"
settingOption = mcu_mega2560, "Arduino Mega 2560"
settingOption = mcu_teensy, "Teensy 3.5/3.6/4.1"
settingOption = mcu_stm32, "STM32F4"

settingGroup = LAMBDA, "Wideband lambda support"
settingOption = DEFAULT, "Off"
settingOption = LAMBDA, "On"
)";

}  // namespace

TEST_CASE("setting_groups: parses two blocks with options") {
    auto section = parse_setting_groups_section(kSimpleSection);
    REQUIRE(section.groups.size() == 2);

    const auto& mcu = section.groups[0];
    CHECK(mcu.symbol == "mcu");
    CHECK(mcu.label == "Controller in use");
    REQUIRE(mcu.options.size() == 3);
    CHECK(mcu.options[0].symbol == "mcu_mega2560");
    CHECK(mcu.options[0].label == "Arduino Mega 2560");
    CHECK(mcu.options[1].symbol == "mcu_teensy");
    CHECK(mcu.options[1].label == "Teensy 3.5/3.6/4.1");
    CHECK(mcu.options[2].symbol == "mcu_stm32");
    CHECK(mcu.options[2].label == "STM32F4");

    const auto& lambda = section.groups[1];
    CHECK(lambda.symbol == "LAMBDA");
    CHECK(lambda.label == "Wideband lambda support");
    REQUIRE(lambda.options.size() == 2);
    CHECK(lambda.options[0].symbol == "DEFAULT");
    CHECK(lambda.options[1].symbol == "LAMBDA");
}

TEST_CASE("setting_groups: boolean flag (no options) survives") {
    const char* text = R"(
[SettingGroups]
settingGroup = enablehardware_test, "Enable hardware test"
)";
    auto section = parse_setting_groups_section(text);
    REQUIRE(section.groups.size() == 1);
    CHECK(section.groups[0].symbol == "enablehardware_test");
    CHECK(section.groups[0].label == "Enable hardware test");
    CHECK(section.groups[0].options.empty());
}

TEST_CASE("setting_groups: section-change flush preserves in-flight block") {
    const char* text = R"(
[SettingGroups]
settingGroup = mcu, "Controller in use"
settingOption = mcu_teensy, "Teensy"

[OtherSection]
irrelevant = value
)";
    auto section = parse_setting_groups_section(text);
    REQUIRE(section.groups.size() == 1);
    CHECK(section.groups[0].symbol == "mcu");
    CHECK(section.groups[0].options.size() == 1);
}

TEST_CASE("setting_groups: settingOption outside a block is ignored") {
    const char* text = R"(
[SettingGroups]
settingOption = orphan, "No block open"
settingGroup = real, "Real block"
settingOption = child, "Real child"
)";
    auto section = parse_setting_groups_section(text);
    REQUIRE(section.groups.size() == 1);
    CHECK(section.groups[0].symbol == "real");
    CHECK(section.groups[0].options.size() == 1);
    CHECK(section.groups[0].options[0].symbol == "child");
}

TEST_CASE("setting_groups: lines outside [SettingGroups] are ignored") {
    const char* text = R"(
[Constants]
scalar = foo, U08, 0
settingGroup = bad, "Should be skipped"

[SettingGroups]
settingGroup = good, "In section"
)";
    auto section = parse_setting_groups_section(text);
    REQUIRE(section.groups.size() == 1);
    CHECK(section.groups[0].symbol == "good");
}

TEST_CASE("setting_groups: missing label defaults to symbol") {
    const char* text = R"(
[SettingGroups]
settingGroup = onlySymbol
settingOption = optOnly
)";
    auto section = parse_setting_groups_section(text);
    REQUIRE(section.groups.size() == 1);
    CHECK(section.groups[0].symbol == "onlySymbol");
    CHECK(section.groups[0].label == "onlySymbol");
    REQUIRE(section.groups[0].options.size() == 1);
    CHECK(section.groups[0].options[0].symbol == "optOnly");
    CHECK(section.groups[0].options[0].label == "optOnly");
}

TEST_CASE("setting_groups: comments + blank lines are skipped") {
    const char* text = R"(
[SettingGroups]
; this is a comment
settingGroup = mcu, "Controller in use"
# also a comment
settingOption = mcu_teensy, "Teensy"

settingOption = mcu_stm32, "STM32"
)";
    auto section = parse_setting_groups_section(text);
    REQUIRE(section.groups.size() == 1);
    CHECK(section.groups[0].options.size() == 2);
}

TEST_CASE("setting_groups: case-insensitive section header match") {
    const char* text = R"(
[settinggroups]
settingGroup = x, "lowercase section"
)";
    auto section = parse_setting_groups_section(text);
    REQUIRE(section.groups.size() == 1);
    CHECK(section.groups[0].symbol == "x");
}

TEST_CASE("setting_groups: preprocessor #if gating") {
    const char* text = R"(
#set FEATURE_X
[SettingGroups]
#if FEATURE_X
settingGroup = x_on, "X enabled"
#else
settingGroup = x_off, "X disabled"
#endif
)";
    auto section = parse_setting_groups_section_preprocessed(text);
    REQUIRE(section.groups.size() == 1);
    CHECK(section.groups[0].symbol == "x_on");
}

TEST_CASE("setting_groups: empty input") {
    auto section = parse_setting_groups_section("");
    CHECK(section.groups.empty());
}

TEST_CASE("setting_groups: section present but empty") {
    const char* text = R"(
[SettingGroups]
)";
    auto section = parse_setting_groups_section(text);
    CHECK(section.groups.empty());
}
