// SPDX-License-Identifier: MIT
//
// doctest cases for `ini_pc_variables_parser.hpp`.

#include "doctest.h"

#include "tuner_core/ini_pc_variables_parser.hpp"

using namespace tuner_core;

TEST_CASE("pc_variables: parses a scalar entry with all fields") {
    const char* text = R"INI(
[PcVariables]
myVar = scalar, F32, "%", 1.0, 0.0, 0.0, 100.0, 2
)INI";
    auto section = parse_pc_variables_section(text);
    REQUIRE(section.scalars.size() == 1);
    const auto& s = section.scalars[0];
    CHECK(s.name == "myVar");
    CHECK(s.data_type == "F32");
    REQUIRE(s.units.has_value());
    CHECK(*s.units == "%");
    REQUIRE(s.scale.has_value());
    CHECK(*s.scale == 1.0);
    REQUIRE(s.translate.has_value());
    CHECK(*s.translate == 0.0);
    REQUIRE(s.min_value.has_value());
    CHECK(*s.min_value == 0.0);
    REQUIRE(s.max_value.has_value());
    CHECK(*s.max_value == 100.0);
    REQUIRE(s.digits.has_value());
    CHECK(*s.digits == 2);
    // PC variables never have page/offset set.
    CHECK_FALSE(s.page.has_value());
    CHECK_FALSE(s.offset.has_value());
}

TEST_CASE("pc_variables: parses a bits entry") {
    const char* text = R"INI(
[PcVariables]
myFlag = bits, U08, [0:0], "Off", "On"
)INI";
    auto section = parse_pc_variables_section(text);
    REQUIRE(section.scalars.size() == 1);
    const auto& s = section.scalars[0];
    CHECK(s.name == "myFlag");
    CHECK(s.data_type == "U08");
    REQUIRE(s.bit_offset.has_value());
    CHECK(*s.bit_offset == 0);
    REQUIRE(s.bit_length.has_value());
    CHECK(*s.bit_length == 1);
    REQUIRE(s.options.size() == 2);
    CHECK(s.options[0] == "Off");
    CHECK(s.options[1] == "On");
    CHECK_FALSE(s.page.has_value());
    CHECK_FALSE(s.offset.has_value());
}

TEST_CASE("pc_variables: parses an array entry") {
    const char* text = R"INI(
[PcVariables]
myTable = array, F32, [4x8], "ms", 1.0, 0.0, 0.0, 50.0, 3
)INI";
    auto section = parse_pc_variables_section(text);
    REQUIRE(section.arrays.size() == 1);
    const auto& a = section.arrays[0];
    CHECK(a.name == "myTable");
    CHECK(a.data_type == "F32");
    CHECK(a.rows == 4);
    CHECK(a.columns == 8);
    REQUIRE(a.units.has_value());
    CHECK(*a.units == "ms");
    CHECK_FALSE(a.page.has_value());
    CHECK_FALSE(a.offset.has_value());
}

TEST_CASE("pc_variables: 1D array with [N] shape") {
    const char* text = R"INI(
[PcVariables]
oneD = array, U08, [10], "count"
)INI";
    auto section = parse_pc_variables_section(text);
    REQUIRE(section.arrays.size() == 1);
    CHECK(section.arrays[0].rows == 10);
    CHECK(section.arrays[0].columns == 1);
}

TEST_CASE("pc_variables: multiple entries accumulate in order") {
    const char* text = R"INI(
[PcVariables]
first = scalar, U08, "a"
second = scalar, F32, "b"
third = array, U16, [2x2], "c"
)INI";
    auto section = parse_pc_variables_section(text);
    REQUIRE(section.scalars.size() == 2);
    REQUIRE(section.arrays.size() == 1);
    CHECK(section.scalars[0].name == "first");
    CHECK(section.scalars[1].name == "second");
    CHECK(section.arrays[0].name == "third");
}

TEST_CASE("pc_variables: lines outside section ignored") {
    const char* text = R"INI(
[Constants]
wrongSection = scalar, U08, 0, "should be ignored"

[PcVariables]
correct = scalar, U08, "kept"
)INI";
    auto section = parse_pc_variables_section(text);
    REQUIRE(section.scalars.size() == 1);
    CHECK(section.scalars[0].name == "correct");
}

TEST_CASE("pc_variables: `string` kind not recognised") {
    // [Constants] supports a `string` kind; [PcVariables] does not.
    const char* text = R"INI(
[PcVariables]
strVar = string, ASCII, 16, "bytes"
)INI";
    auto section = parse_pc_variables_section(text);
    CHECK(section.scalars.empty());
    CHECK(section.arrays.empty());
}

TEST_CASE("pc_variables: case-insensitive section header") {
    const char* text = R"INI(
[pcvariables]
x = scalar, U08, "x"
)INI";
    auto section = parse_pc_variables_section(text);
    REQUIRE(section.scalars.size() == 1);
}

TEST_CASE("pc_variables: comments + blank lines skipped") {
    const char* text = R"INI(
[PcVariables]
; comment
first = scalar, U08, "a"

# another
second = scalar, F32, "b"
)INI";
    auto section = parse_pc_variables_section(text);
    CHECK(section.scalars.size() == 2);
}

TEST_CASE("pc_variables: preprocessor #if gating") {
    const char* text = R"INI(
#set FEATURE_EXTRA
[PcVariables]
#if FEATURE_EXTRA
enabled = scalar, U08, "enabled"
#else
disabled = scalar, U08, "disabled"
#endif
)INI";
    auto section = parse_pc_variables_section_preprocessed(text);
    REQUIRE(section.scalars.size() == 1);
    CHECK(section.scalars[0].name == "enabled");
}

TEST_CASE("pc_variables: empty input") {
    auto section = parse_pc_variables_section("");
    CHECK(section.scalars.empty());
    CHECK(section.arrays.empty());
}

TEST_CASE("pc_variables: empty section") {
    auto section = parse_pc_variables_section("[PcVariables]\n");
    CHECK(section.scalars.empty());
    CHECK(section.arrays.empty());
}
