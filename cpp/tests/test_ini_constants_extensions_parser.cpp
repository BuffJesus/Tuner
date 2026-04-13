// SPDX-License-Identifier: MIT
//
// doctest cases for `ini_constants_extensions_parser.hpp`.

#include "doctest.h"

#include "tuner_core/ini_constants_extensions_parser.hpp"

using namespace tuner_core;

TEST_CASE("constants_extensions: parses requiresPowerCycle list") {
    const char* text = R"(
[ConstantsExtensions]
requiresPowerCycle = canBroadcast, canInput, tsCanId
)";
    auto section = parse_constants_extensions_section(text);
    REQUIRE(section.requires_power_cycle.size() == 3);
    CHECK(section.requires_power_cycle.count("canBroadcast") == 1);
    CHECK(section.requires_power_cycle.count("canInput") == 1);
    CHECK(section.requires_power_cycle.count("tsCanId") == 1);
}

TEST_CASE("constants_extensions: comma-separated with whitespace tolerated") {
    const char* text = R"(
[ConstantsExtensions]
requiresPowerCycle =  foo , bar ,baz  , qux
)";
    auto section = parse_constants_extensions_section(text);
    CHECK(section.requires_power_cycle.size() == 4);
    CHECK(section.requires_power_cycle.count("foo") == 1);
    CHECK(section.requires_power_cycle.count("bar") == 1);
    CHECK(section.requires_power_cycle.count("baz") == 1);
    CHECK(section.requires_power_cycle.count("qux") == 1);
}

TEST_CASE("constants_extensions: trailing ';' comment stripped") {
    const char* text = R"(
[ConstantsExtensions]
requiresPowerCycle = alpha, beta ; comment here
)";
    auto section = parse_constants_extensions_section(text);
    CHECK(section.requires_power_cycle.size() == 2);
    CHECK(section.requires_power_cycle.count("alpha") == 1);
    CHECK(section.requires_power_cycle.count("beta") == 1);
}

TEST_CASE("constants_extensions: unknown keys silently ignored") {
    const char* text = R"(
[ConstantsExtensions]
unknownKey = foo, bar
requiresPowerCycle = kept
someOtherMetadata = ignored
)";
    auto section = parse_constants_extensions_section(text);
    REQUIRE(section.requires_power_cycle.size() == 1);
    CHECK(section.requires_power_cycle.count("kept") == 1);
}

TEST_CASE("constants_extensions: empty entries dropped") {
    const char* text = R"(
[ConstantsExtensions]
requiresPowerCycle = , alpha, , beta,
)";
    auto section = parse_constants_extensions_section(text);
    CHECK(section.requires_power_cycle.size() == 2);
}

TEST_CASE("constants_extensions: multiple requiresPowerCycle lines accumulate") {
    const char* text = R"(
[ConstantsExtensions]
requiresPowerCycle = a, b
requiresPowerCycle = c, d
)";
    auto section = parse_constants_extensions_section(text);
    CHECK(section.requires_power_cycle.size() == 4);
    CHECK(section.requires_power_cycle.count("a") == 1);
    CHECK(section.requires_power_cycle.count("d") == 1);
}

TEST_CASE("constants_extensions: lines outside section ignored") {
    const char* text = R"(
[Constants]
requiresPowerCycle = wrong_section

[ConstantsExtensions]
requiresPowerCycle = correct_section
)";
    auto section = parse_constants_extensions_section(text);
    REQUIRE(section.requires_power_cycle.size() == 1);
    CHECK(section.requires_power_cycle.count("correct_section") == 1);
}

TEST_CASE("constants_extensions: case-insensitive section header") {
    const char* text = R"(
[constantsextensions]
requiresPowerCycle = lowercase_header_works
)";
    auto section = parse_constants_extensions_section(text);
    CHECK(section.requires_power_cycle.count("lowercase_header_works") == 1);
}

TEST_CASE("constants_extensions: comments and blank lines skipped") {
    const char* text = R"(
[ConstantsExtensions]
; comment
requiresPowerCycle = kept

# another comment
)";
    auto section = parse_constants_extensions_section(text);
    CHECK(section.requires_power_cycle.size() == 1);
}

TEST_CASE("constants_extensions: preprocessor #if gating") {
    const char* text = R"(
#set FEATURE_CAN
[ConstantsExtensions]
#if FEATURE_CAN
requiresPowerCycle = canBroadcast, canInput
#else
requiresPowerCycle = noCan
#endif
)";
    auto section = parse_constants_extensions_section_preprocessed(text);
    CHECK(section.requires_power_cycle.size() == 2);
    CHECK(section.requires_power_cycle.count("canBroadcast") == 1);
    CHECK(section.requires_power_cycle.count("canInput") == 1);
    CHECK(section.requires_power_cycle.count("noCan") == 0);
}

TEST_CASE("constants_extensions: empty input") {
    auto section = parse_constants_extensions_section("");
    CHECK(section.requires_power_cycle.empty());
}

TEST_CASE("constants_extensions: section present but empty") {
    auto section = parse_constants_extensions_section("[ConstantsExtensions]\n");
    CHECK(section.requires_power_cycle.empty());
}
