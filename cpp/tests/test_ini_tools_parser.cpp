// SPDX-License-Identifier: MIT
//
// doctest cases for `ini_tools_parser.hpp`.

#include "doctest.h"

#include "tuner_core/ini_tools_parser.hpp"

using namespace tuner_core;

TEST_CASE("tools: parses full addTool line") {
    const char* text = R"(
[Tools]
addTool = veAnalyze, "VE Analyze", veTable1Tbl
)";
    auto section = parse_tools_section(text);
    REQUIRE(section.declarations.size() == 1);
    CHECK(section.declarations[0].tool_id == "veAnalyze");
    CHECK(section.declarations[0].label == "VE Analyze");
    REQUIRE(section.declarations[0].target_table_id.has_value());
    CHECK(*section.declarations[0].target_table_id == "veTable1Tbl");
}

TEST_CASE("tools: missing target_table_id is nullopt") {
    const char* text = R"(
[Tools]
addTool = globalHelper, "Global Helper"
)";
    auto section = parse_tools_section(text);
    REQUIRE(section.declarations.size() == 1);
    CHECK(section.declarations[0].tool_id == "globalHelper");
    CHECK(section.declarations[0].label == "Global Helper");
    CHECK_FALSE(section.declarations[0].target_table_id.has_value());
}

TEST_CASE("tools: missing label defaults to tool_id") {
    const char* text = R"(
[Tools]
addTool = onlyId
)";
    auto section = parse_tools_section(text);
    REQUIRE(section.declarations.size() == 1);
    CHECK(section.declarations[0].tool_id == "onlyId");
    CHECK(section.declarations[0].label == "onlyId");
    CHECK_FALSE(section.declarations[0].target_table_id.has_value());
}

TEST_CASE("tools: multiple declarations accumulate in order") {
    const char* text = R"(
[Tools]
addTool = veAnalyze, "VE Analyze", veTable1Tbl
addTool = wueAnalyze, "WUE Analyze", wueTbl
addTool = globalReset, "Global Reset"
)";
    auto section = parse_tools_section(text);
    REQUIRE(section.declarations.size() == 3);
    CHECK(section.declarations[0].tool_id == "veAnalyze");
    CHECK(section.declarations[1].tool_id == "wueAnalyze");
    CHECK(section.declarations[2].tool_id == "globalReset");
    CHECK_FALSE(section.declarations[2].target_table_id.has_value());
}

TEST_CASE("tools: unknown keys silently ignored") {
    const char* text = R"(
[Tools]
unknownKey = foo
addTool = realTool, "Real", realTbl
otherKey = ignored
)";
    auto section = parse_tools_section(text);
    REQUIRE(section.declarations.size() == 1);
    CHECK(section.declarations[0].tool_id == "realTool");
}

TEST_CASE("tools: lines outside section ignored") {
    const char* text = R"(
[Constants]
addTool = wrong, "Wrong section", x

[Tools]
addTool = correct, "Right section", y
)";
    auto section = parse_tools_section(text);
    REQUIRE(section.declarations.size() == 1);
    CHECK(section.declarations[0].tool_id == "correct");
}

TEST_CASE("tools: case-insensitive section header") {
    const char* text = R"(
[tools]
addTool = x, "X", xTbl
)";
    auto section = parse_tools_section(text);
    REQUIRE(section.declarations.size() == 1);
    CHECK(section.declarations[0].tool_id == "x");
}

TEST_CASE("tools: comments and blank lines skipped") {
    const char* text = R"(
[Tools]
; comment line
addTool = a, "A", aTbl

# another comment
addTool = b, "B"
)";
    auto section = parse_tools_section(text);
    CHECK(section.declarations.size() == 2);
}

TEST_CASE("tools: preprocessor #if gating") {
    // Custom raw-string delimiter `INI(...)INI` — the default
    // `R"(...)"` collides with the `)"` sequence inside the quoted
    // "VE Analyze disabled" label.
    const char* text = R"INI(
#set FEATURE_VE
[Tools]
#if FEATURE_VE
addTool = veAnalyze, "VE Analyze", veTbl
#else
addTool = veAnalyzeDisabled, "VE Analyze disabled"
#endif
)INI";
    auto section = parse_tools_section_preprocessed(text);
    REQUIRE(section.declarations.size() == 1);
    CHECK(section.declarations[0].tool_id == "veAnalyze");
}

TEST_CASE("tools: empty input") {
    auto section = parse_tools_section("");
    CHECK(section.declarations.empty());
}

TEST_CASE("tools: section present but empty") {
    auto section = parse_tools_section("[Tools]\n");
    CHECK(section.declarations.empty());
}

TEST_CASE("tools: addTool with empty value is skipped") {
    const char* text = R"(
[Tools]
addTool =
addTool = valid, "Valid"
)";
    auto section = parse_tools_section(text);
    REQUIRE(section.declarations.size() == 1);
    CHECK(section.declarations[0].tool_id == "valid");
}
