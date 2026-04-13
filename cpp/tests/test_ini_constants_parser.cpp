// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniConstantsParser. Mirrors the
// Python `[Constants]` parser test surface so cross-validation against
// the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_constants_parser.hpp"

#include <string>

namespace {

const tuner_core::IniScalar* find_scalar(
    const tuner_core::IniConstantsSection& section, const std::string& name) {
    for (const auto& s : section.scalars) {
        if (s.name == name) return &s;
    }
    return nullptr;
}

const tuner_core::IniArray* find_array(
    const tuner_core::IniConstantsSection& section, const std::string& name) {
    for (const auto& a : section.arrays) {
        if (a.name == name) return &a;
    }
    return nullptr;
}

}  // namespace

TEST_CASE("parse_constants_section ignores lines outside [Constants]") {
    auto section = tuner_core::parse_constants_section(
        "[Other]\nfoo = scalar, U08, 0, \"unit\"\n");
    CHECK(section.scalars.empty());
    CHECK(section.arrays.empty());
}

TEST_CASE("parses a single scalar U08") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "reqFuel = scalar, U08, 0, \"ms\", 0.1, 0.0, 0.0, 25.5, 1\n");
    REQUIRE(section.scalars.size() == 1);
    const auto& s = section.scalars[0];
    CHECK(s.name == "reqFuel");
    CHECK(s.data_type == "U08");
    CHECK(s.page.value() == 1);
    CHECK(s.offset.value() == 0);
    CHECK(s.units.value() == "ms");
    CHECK(s.scale.value() == doctest::Approx(0.1));
    CHECK(s.min_value.value() == doctest::Approx(0.0));
    CHECK(s.max_value.value() == doctest::Approx(25.5));
    CHECK(s.digits.value() == 1);
}

TEST_CASE("lastOffset auto-advances within a page") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "first = scalar, U16, 0, \"\", 1, 0, 0, 65535, 0\n"
        "second = scalar, U08, lastOffset, \"\", 1, 0, 0, 255, 0\n");
    REQUIRE(section.scalars.size() == 2);
    // First scalar is U16 → 2 bytes → second offset starts at 2
    CHECK(section.scalars[0].offset.value() == 0);
    CHECK(section.scalars[1].offset.value() == 2);
}

TEST_CASE("lastOffset uses U32 width for 4-byte advance") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "first = scalar, U32, 0, \"\", 1, 0, 0, 1000, 0\n"
        "second = scalar, U08, lastOffset, \"\", 1, 0, 0, 255, 0\n");
    REQUIRE(section.scalars.size() == 2);
    CHECK(section.scalars[1].offset.value() == 4);
}

TEST_CASE("lastOffset resets at page boundaries") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "first = scalar, U16, 0, \"\", 1, 0, 0, 65535, 0\n"
        "page = 2\n"
        "second = scalar, U08, lastOffset, \"\", 1, 0, 0, 255, 0\n");
    REQUIRE(section.scalars.size() == 2);
    CHECK(section.scalars[1].page.value() == 2);
    CHECK(section.scalars[1].offset.value() == 0);
}

TEST_CASE("parses 2D array shape [rows x cols]") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "veTable = array, U08, 0, [16x16], \"%\", 1.0, 0.0, 0.0, 255.0, 0\n");
    REQUIRE(section.arrays.size() == 1);
    const auto& a = section.arrays[0];
    CHECK(a.name == "veTable");
    CHECK(a.rows == 16);
    CHECK(a.columns == 16);
    CHECK(a.data_type == "U08");
    CHECK(a.units.value() == "%");
}

TEST_CASE("parses 1D array shape [N]") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "rpmBins = array, U08, 0, [16], \"rpm\", 100.0, 0.0, 0.0, 25500.0, 0\n");
    REQUIRE(section.arrays.size() == 1);
    const auto& a = section.arrays[0];
    CHECK(a.rows == 16);
    CHECK(a.columns == 1);
    CHECK(a.units.value() == "rpm");
}

TEST_CASE("array storage size advances lastOffset by rows*cols*width") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "veTable = array, U08, 0, [16x16], \"%\", 1, 0, 0, 255, 0\n"
        "afterArray = scalar, U08, lastOffset, \"\", 1, 0, 0, 255, 0\n");
    REQUIRE(section.arrays.size() == 1);
    REQUIRE(section.scalars.size() == 1);
    // 16*16*1 byte = 256
    CHECK(section.scalars[0].offset.value() == 256);
}

TEST_CASE("parses bits entry with bit range") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "knock_mode = bits, U08, 100, [0:1], \"Off\", \"Digital\", \"Analog\"\n");
    REQUIRE(section.scalars.size() == 1);
    const auto& s = section.scalars[0];
    CHECK(s.name == "knock_mode");
    CHECK(s.bit_offset.value() == 0);
    CHECK(s.bit_length.value() == 2);  // bits 0..1 inclusive
    REQUIRE(s.options.size() == 3);
    CHECK(s.options[0] == "Off");
    CHECK(s.options[1] == "Digital");
    CHECK(s.options[2] == "Analog");
}

TEST_CASE("parses bits entry with single bit") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "flag = bits, U08, 100, [3], \"Off\", \"On\"\n");
    REQUIRE(section.scalars.size() == 1);
    const auto& s = section.scalars[0];
    CHECK(s.bit_offset.value() == 3);
    CHECK(s.bit_length.value() == 1);
}

TEST_CASE("comments and blank lines are ignored") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "; this is a comment\n"
        "\n"
        "page = 1\n"
        "; another comment\n"
        "real = scalar, U08, 0, \"\", 1, 0, 0, 255, 0\n");
    REQUIRE(section.scalars.size() == 1);
    CHECK(section.scalars[0].name == "real");
}

TEST_CASE("hex offset literals are accepted") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "first = scalar, U08, 0x10, \"\", 1, 0, 0, 255, 0\n");
    REQUIRE(section.scalars.size() == 1);
    CHECK(section.scalars[0].offset.value() == 16);
}

TEST_CASE("multiple pages with multiple entries") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "p1a = scalar, U08, 0, \"\", 1, 0, 0, 255, 0\n"
        "p1b = scalar, U08, 1, \"\", 1, 0, 0, 255, 0\n"
        "page = 2\n"
        "p2a = scalar, U16, 0, \"\", 1, 0, 0, 65535, 0\n"
        "p2b = array, U08, lastOffset, [4x4], \"\", 1, 0, 0, 255, 0\n");
    REQUIRE(section.scalars.size() == 3);
    REQUIRE(section.arrays.size() == 1);
    CHECK(find_scalar(section, "p1a")->page.value() == 1);
    CHECK(find_scalar(section, "p2a")->page.value() == 2);
    CHECK(find_array(section, "p2b")->page.value() == 2);
    CHECK(find_array(section, "p2b")->offset.value() == 2);  // U16 width = 2
}

TEST_CASE("F32 storage advances lastOffset by 4 bytes") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "first = scalar, F32, 0, \"\", 1, 0, 0, 1000, 2\n"
        "second = scalar, U08, lastOffset, \"\", 1, 0, 0, 255, 0\n");
    REQUIRE(section.scalars.size() == 2);
    CHECK(section.scalars[1].offset.value() == 4);
}

TEST_CASE("preprocessed pipeline drops scalars inside disabled #if") {
    auto section = tuner_core::parse_constants_section_preprocessed(
        "[Constants]\n"
        "page = 1\n"
        "always = scalar, U08, 0, \"\", 1, 0, 0, 255, 0\n"
        "#if FEATURE_X\n"
        "feature_only = scalar, U08, 1, \"\", 1, 0, 0, 255, 0\n"
        "#endif\n",
        {});
    REQUIRE(section.scalars.size() == 1);
    CHECK(section.scalars[0].name == "always");
}

TEST_CASE("preprocessed pipeline keeps scalars when active_setting is on") {
    auto section = tuner_core::parse_constants_section_preprocessed(
        "[Constants]\n"
        "page = 1\n"
        "always = scalar, U08, 0, \"\", 1, 0, 0, 255, 0\n"
        "#if FEATURE_X\n"
        "feature_only = scalar, U08, 1, \"\", 1, 0, 0, 255, 0\n"
        "#endif\n",
        {"FEATURE_X"});
    REQUIRE(section.scalars.size() == 2);
}

TEST_CASE("preprocessed pipeline honours file-scope #set defaults") {
    auto section = tuner_core::parse_constants_section_preprocessed(
        "#set LAMBDA\n"
        "[Constants]\n"
        "page = 1\n"
        "#if LAMBDA\n"
        "afr_in_lambda = scalar, U08, 0, \"lambda\", 1, 0, 0, 255, 0\n"
        "#else\n"
        "afr_in_afr = scalar, U08, 0, \"afr\", 1, 0, 0, 255, 0\n"
        "#endif\n",
        {});
    REQUIRE(section.scalars.size() == 1);
    CHECK(section.scalars[0].name == "afr_in_lambda");
}

TEST_CASE("brace placeholders for scale do not break parsing") {
    auto section = tuner_core::parse_constants_section(
        "[Constants]\n"
        "page = 1\n"
        "weird = scalar, U08, 0, \"%\", {expression}, 0, 0, 100, 0\n");
    REQUIRE(section.scalars.size() == 1);
    const auto& s = section.scalars[0];
    CHECK(s.name == "weird");
    // Scale is unparseable as a float, so it stays nullopt — matches Python.
    CHECK_FALSE(s.scale.has_value());
}
