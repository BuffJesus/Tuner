// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniOutputChannelsParser. Mirrors
// the Python `_parse_output_channels` test surface so cross-validation
// against the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_output_channels_parser.hpp"

#include <string>

namespace {

const tuner_core::IniOutputChannel* find_channel(
    const tuner_core::IniOutputChannelsSection& section,
    const std::string& name) {
    for (const auto& c : section.channels) {
        if (c.name == name) return &c;
    }
    return nullptr;
}

}  // namespace

TEST_CASE("parse_output_channels_section ignores lines outside [OutputChannels]") {
    auto section = tuner_core::parse_output_channels_section(
        "[Other]\nfoo = scalar, U08, 0, \"unit\"\n");
    CHECK(section.channels.empty());
    CHECK(section.arrays.empty());
}

TEST_CASE("parses a single scalar U08 output channel") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "rpm = scalar, U16, 14, \"RPM\", 1.0, 0.0, 0.0, 8000.0, 0\n");
    REQUIRE(section.channels.size() == 1);
    const auto& ch = section.channels[0];
    CHECK(ch.name == "rpm");
    CHECK(ch.data_type == "U16");
    CHECK(ch.offset == 14);
    CHECK(ch.units.value() == "RPM");
    CHECK(ch.scale.value() == doctest::Approx(1.0));
    CHECK(ch.min_value.value() == doctest::Approx(0.0));
    CHECK(ch.max_value.value() == doctest::Approx(8000.0));
    CHECK(ch.digits.value() == 0);
}

TEST_CASE("parses scalar with translate offset") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "iat = scalar, U08, 6, \"C\", 1.0, -40.0, -40.0, 215.0, 0\n");
    REQUIRE(section.channels.size() == 1);
    const auto& ch = section.channels[0];
    CHECK(ch.translate.value() == doctest::Approx(-40.0));
}

TEST_CASE("parses bits entry with bit range and option labels") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "engine = bits, U08, 2, [0:0], \"Off\", \"On\"\n");
    REQUIRE(section.channels.size() == 1);
    const auto& ch = section.channels[0];
    CHECK(ch.name == "engine");
    CHECK(ch.bit_offset.value() == 0);
    CHECK(ch.bit_length.value() == 1);
    REQUIRE(ch.options.size() == 2);
    CHECK(ch.options[0] == "Off");
    CHECK(ch.options[1] == "On");
}

TEST_CASE("array entries are NOT promoted into channels") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "boardHasRTC = array, U08, [4]\n"
        "rpm = scalar, U16, 14, \"RPM\", 1, 0, 0, 8000, 0\n");
    // Only `rpm` lands in `channels`; the array entry only registers its name.
    REQUIRE(section.channels.size() == 1);
    CHECK(section.channels[0].name == "rpm");
}

TEST_CASE("defaultValue lines populate the array map") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "boardHasRTC = array, U08, [4]\n"
        "defaultValue = boardHasRTC, 0 1 1 0\n");
    REQUIRE(section.arrays.count("boardHasRTC") == 1);
    auto& values = section.arrays["boardHasRTC"];
    REQUIRE(values.size() == 4);
    CHECK(values[0] == doctest::Approx(0.0));
    CHECK(values[1] == doctest::Approx(1.0));
    CHECK(values[2] == doctest::Approx(1.0));
    CHECK(values[3] == doctest::Approx(0.0));
}

TEST_CASE("defaultValue for unknown array is silently dropped") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "defaultValue = neverDeclared, 1 2 3\n");
    CHECK(section.arrays.empty());
}

TEST_CASE("comments and blank lines are ignored") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "; this is a comment\n"
        "\n"
        "rpm = scalar, U16, 14, \"RPM\", 1, 0, 0, 8000, 0\n");
    REQUIRE(section.channels.size() == 1);
    CHECK(section.channels[0].name == "rpm");
}

TEST_CASE("multiple scalars and arrays in the same section") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "rpm = scalar, U16, 14, \"RPM\", 1, 0, 0, 8000, 0\n"
        "map = scalar, U16, 4, \"kPa\", 1, 0, 0, 511, 0\n"
        "iat = scalar, U08, 6, \"C\", 1, -40, -40, 215, 0\n"
        "boardHasRTC = array, U08, [4]\n"
        "defaultValue = boardHasRTC, 1 0 1 0\n");
    REQUIRE(section.channels.size() == 3);
    CHECK(find_channel(section, "rpm") != nullptr);
    CHECK(find_channel(section, "map") != nullptr);
    CHECK(find_channel(section, "iat") != nullptr);
    CHECK(section.arrays.count("boardHasRTC") == 1);
}

TEST_CASE("preprocessed pipeline gates entries inside #if blocks") {
    auto section = tuner_core::parse_output_channels_section_preprocessed(
        "[OutputChannels]\n"
        "always = scalar, U08, 0, \"\", 1, 0, 0, 255, 0\n"
        "#if FEATURE_X\n"
        "feature = scalar, U08, 1, \"\", 1, 0, 0, 255, 0\n"
        "#endif\n",
        {});
    REQUIRE(section.channels.size() == 1);
    CHECK(section.channels[0].name == "always");

    auto enabled = tuner_core::parse_output_channels_section_preprocessed(
        "[OutputChannels]\n"
        "always = scalar, U08, 0, \"\", 1, 0, 0, 255, 0\n"
        "#if FEATURE_X\n"
        "feature = scalar, U08, 1, \"\", 1, 0, 0, 255, 0\n"
        "#endif\n",
        {"FEATURE_X"});
    CHECK(enabled.channels.size() == 2);
}

TEST_CASE("preprocessed pipeline expands $macroName option labels") {
    auto section = tuner_core::parse_output_channels_section_preprocessed(
        "#define modes = \"Off\",\"Auto\",\"Manual\"\n"
        "[OutputChannels]\n"
        "selector = bits, U08, 5, [0:1], $modes\n",
        {});
    REQUIRE(section.channels.size() == 1);
    REQUIRE(section.channels[0].options.size() == 3);
    CHECK(section.channels[0].options[0] == "Off");
    CHECK(section.channels[0].options[2] == "Manual");
}

// ---------------------------------------------------------------------------
// Formula / virtual output channels (Phase 14 — G4 parser slice)
// ---------------------------------------------------------------------------

TEST_CASE("parses a single formula output channel with no trailing metadata") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "coolant = { coolantRaw - 40 }\n");
    CHECK(section.channels.empty());
    REQUIRE(section.formula_channels.size() == 1);
    const auto& fc = section.formula_channels[0];
    CHECK(fc.name == "coolant");
    CHECK(fc.formula_expression == "coolantRaw - 40");
    CHECK_FALSE(fc.units.has_value());
    CHECK_FALSE(fc.digits.has_value());
}

TEST_CASE("parses formula channel with units") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "throttle = { tps }, \"%\"\n");
    REQUIRE(section.formula_channels.size() == 1);
    const auto& fc = section.formula_channels[0];
    CHECK(fc.name == "throttle");
    CHECK(fc.formula_expression == "tps");
    REQUIRE(fc.units.has_value());
    CHECK(fc.units.value() == "%");
    CHECK_FALSE(fc.digits.has_value());
}

TEST_CASE("parses formula channel with units and digits") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "map_psi = { (map - baro) * 0.145038 }, \"PSI\", 2\n");
    REQUIRE(section.formula_channels.size() == 1);
    const auto& fc = section.formula_channels[0];
    CHECK(fc.name == "map_psi");
    CHECK(fc.formula_expression == "(map - baro) * 0.145038");
    CHECK(fc.units.value() == "PSI");
    CHECK(fc.digits.value() == 2);
}

TEST_CASE("formula channel strips inline ; comment") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "coolant = { coolantRaw - 40 } ; Temperature readings are offset by 40\n");
    REQUIRE(section.formula_channels.size() == 1);
    CHECK(section.formula_channels[0].formula_expression == "coolantRaw - 40");
}

TEST_CASE("formula channel preserves ternary expression verbatim") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "strokeMultipler = { twoStroke == 1 ? 1 : 2 }\n");
    REQUIRE(section.formula_channels.size() == 1);
    CHECK(section.formula_channels[0].formula_expression
          == "twoStroke == 1 ? 1 : 2");
}

TEST_CASE("formula channel preserves arrayValue() call with nested parens") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "nFuelChannels = { arrayValue( array.boardFuelOutputs, pinLayout ) }\n");
    REQUIRE(section.formula_channels.size() == 1);
    const auto& expr = section.formula_channels[0].formula_expression;
    CHECK(expr.find("arrayValue") != std::string::npos);
    CHECK(expr.find("boardFuelOutputs") != std::string::npos);
    CHECK(expr.find("pinLayout") != std::string::npos);
}

TEST_CASE("scalar entry containing { expression } does NOT become a formula channel") {
    // The scalar keyword appears after the `=`, so the formula regex
    // must not match — the line should land in `channels`, not
    // `formula_channels`.
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "idleLoad = scalar, U08, 38, { bitStringValue( idleUnits , iacAlgorithm ) }, 1.0, 0.0\n"
        "coolant  = { coolantRaw - 40 }\n");
    REQUIRE(section.channels.size() == 1);
    CHECK(section.channels[0].name == "idleLoad");
    REQUIRE(section.formula_channels.size() == 1);
    CHECK(section.formula_channels[0].name == "coolant");
}

TEST_CASE("formula channel order is preserved across multiple entries") {
    auto section = tuner_core::parse_output_channels_section(
        "[OutputChannels]\n"
        "coolant  = { coolantRaw - 40 }\n"
        "iat      = { iatRaw - 40 }\n"
        "fuelTemp = { fuelTempRaw - 40 }\n");
    REQUIRE(section.formula_channels.size() == 3);
    CHECK(section.formula_channels[0].name == "coolant");
    CHECK(section.formula_channels[1].name == "iat");
    CHECK(section.formula_channels[2].name == "fuelTemp");
}

TEST_CASE("formula channel outside [OutputChannels] is ignored") {
    auto section = tuner_core::parse_output_channels_section(
        "[PcVariables]\n"
        "foo = { bar + 1 }\n"
        "[OutputChannels]\n"
        "coolant = { coolantRaw - 40 }\n");
    REQUIRE(section.formula_channels.size() == 1);
    CHECK(section.formula_channels[0].name == "coolant");
}

TEST_CASE("formula channel runs through the preprocessed pipeline") {
    auto section = tuner_core::parse_output_channels_section_preprocessed(
        "[OutputChannels]\n"
        "coolant = { coolantRaw - 40 }\n"
        "#if CELSIUS\n"
        "coolant_c = { coolantRaw - 40 }\n"
        "#endif\n",
        {});
    // Without CELSIUS set, only the unconditional coolant line survives.
    REQUIRE(section.formula_channels.size() == 1);
    CHECK(section.formula_channels[0].name == "coolant");

    auto enabled = tuner_core::parse_output_channels_section_preprocessed(
        "[OutputChannels]\n"
        "coolant = { coolantRaw - 40 }\n"
        "#if CELSIUS\n"
        "coolant_c = { coolantRaw - 40 }\n"
        "#endif\n",
        {"CELSIUS"});
    REQUIRE(enabled.formula_channels.size() == 2);
    CHECK(enabled.formula_channels[1].name == "coolant_c");
}
