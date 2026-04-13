// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniTableEditorParser. Mirrors
// the Python `_parse_table_editors` test surface so cross-validation
// against the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_table_editor_parser.hpp"

#include <string>

namespace {

const tuner_core::IniTableEditor* find_editor(
    const tuner_core::IniTableEditorSection& section,
    const std::string& table_id) {
    for (const auto& e : section.editors) {
        if (e.table_id == table_id) return &e;
    }
    return nullptr;
}

}  // namespace

TEST_CASE("parse_table_editor_section ignores lines outside [TableEditor]") {
    auto section = tuner_core::parse_table_editor_section(
        "[Other]\ntable = veTbl, veMap, \"VE Table\"\n");
    CHECK(section.editors.empty());
}

TEST_CASE("parses a single editor with all common fields") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = veTblTbl, veMap, \"VE Table\", 2\n"
        "topicHelp = \"How to tune VE\"\n"
        "xBins = rpmBins, rpm\n"
        "yBins = mapBins, map\n"
        "zBins = veTable\n"
        "xyLabels = \"RPM\", \"MAP (kPa)\"\n"
        "gridHeight = 50.0\n"
        "gridOrient = 250.0, 0.0, 340.0\n"
        "upDownLabel = \"RICHER\", \"LEANER\"\n");
    REQUIRE(section.editors.size() == 1);
    const auto& e = section.editors[0];
    CHECK(e.table_id == "veTblTbl");
    CHECK(e.map_id == "veMap");
    CHECK(e.title == "VE Table");
    CHECK(e.page.value() == 2);
    CHECK(e.topic_help.value() == "How to tune VE");
    CHECK(e.x_bins.value() == "rpmBins");
    CHECK(e.x_channel.value() == "rpm");
    CHECK(e.y_bins.value() == "mapBins");
    CHECK(e.y_channel.value() == "map");
    CHECK(e.z_bins.value() == "veTable");
    CHECK(e.x_label.value() == "RPM");
    CHECK(e.y_label.value() == "MAP (kPa)");
    CHECK(e.grid_height.value() == doctest::Approx(50.0));
    REQUIRE(e.grid_orient.has_value());
    CHECK(e.grid_orient->at(0) == doctest::Approx(250.0));
    CHECK(e.grid_orient->at(1) == doctest::Approx(0.0));
    CHECK(e.grid_orient->at(2) == doctest::Approx(340.0));
    CHECK(e.up_label.value() == "RICHER");
    CHECK(e.down_label.value() == "LEANER");
}

TEST_CASE("parses multiple editors as separate state machines") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = veTblTbl, veMap, \"VE Table\"\n"
        "xBins = rpmBins, rpm\n"
        "zBins = veTable\n"
        "table = ignTblTbl, ignMap, \"Ignition Table\"\n"
        "xBins = rpmBinsIgn, rpm\n"
        "zBins = ignitionTable\n");
    REQUIRE(section.editors.size() == 2);
    CHECK(find_editor(section, "veTblTbl")->z_bins.value() == "veTable");
    CHECK(find_editor(section, "ignTblTbl")->z_bins.value() == "ignitionTable");
    CHECK(find_editor(section, "ignTblTbl")->x_bins.value() == "rpmBinsIgn");
}

TEST_CASE("xBins without channel keeps x_channel empty") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = t, m, \"Title\"\n"
        "xBins = rpmBins\n");
    REQUIRE(section.editors.size() == 1);
    CHECK(section.editors[0].x_bins.value() == "rpmBins");
    CHECK_FALSE(section.editors[0].x_channel.has_value());
}

TEST_CASE("table line missing required parts is dropped") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = onlyOne\n"
        "table = good, ok, \"Title\"\n");
    REQUIRE(section.editors.size() == 1);
    CHECK(section.editors[0].table_id == "good");
}

TEST_CASE("keys before any table line are ignored") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "xBins = orphan, rpm\n"
        "table = good, ok, \"Title\"\n"
        "xBins = rpmBins, rpm\n");
    REQUIRE(section.editors.size() == 1);
    CHECK(section.editors[0].x_bins.value() == "rpmBins");
}

TEST_CASE("section change clears active editor") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = veTblTbl, veMap, \"VE Table\"\n"
        "[OutputChannels]\n"
        "xBins = leaked, rpm\n");
    REQUIRE(section.editors.size() == 1);
    CHECK_FALSE(section.editors[0].x_bins.has_value());
}

TEST_CASE("comments and blank lines are ignored") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "; comment line\n"
        "\n"
        "table = veTblTbl, veMap, \"VE Table\"\n"
        "; another comment\n"
        "xBins = rpmBins, rpm\n");
    REQUIRE(section.editors.size() == 1);
    CHECK(section.editors[0].x_bins.value() == "rpmBins");
}

TEST_CASE("topicHelp without quotes still parses") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = t, m, \"T\"\n"
        "topicHelp = unquoted_help_topic\n");
    REQUIRE(section.editors.size() == 1);
    CHECK(section.editors[0].topic_help.value() == "unquoted_help_topic");
}

TEST_CASE("topicHelp with trailing comment strips comment") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = t, m, \"T\"\n"
        "topicHelp = \"real_topic\" ; trailing comment\n");
    REQUIRE(section.editors.size() == 1);
    CHECK(section.editors[0].topic_help.value() == "real_topic");
}

TEST_CASE("gridOrient with fewer than 3 values is dropped") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = t, m, \"T\"\n"
        "gridOrient = 250.0, 0.0\n");
    REQUIRE(section.editors.size() == 1);
    CHECK_FALSE(section.editors[0].grid_orient.has_value());
}

TEST_CASE("gridHeight with non-numeric value is dropped") {
    auto section = tuner_core::parse_table_editor_section(
        "[TableEditor]\n"
        "table = t, m, \"T\"\n"
        "gridHeight = notanumber\n");
    REQUIRE(section.editors.size() == 1);
    CHECK_FALSE(section.editors[0].grid_height.has_value());
}

TEST_CASE("preprocessed pipeline gates editors inside #if blocks") {
    auto section = tuner_core::parse_table_editor_section_preprocessed(
        "[TableEditor]\n"
        "table = always, alwaysMap, \"Always\"\n"
        "zBins = alwaysTable\n"
        "#if FEATURE_X\n"
        "table = feature, featureMap, \"Feature\"\n"
        "zBins = featureTable\n"
        "#endif\n",
        {});
    REQUIRE(section.editors.size() == 1);
    CHECK(section.editors[0].table_id == "always");

    auto enabled = tuner_core::parse_table_editor_section_preprocessed(
        "[TableEditor]\n"
        "table = always, alwaysMap, \"Always\"\n"
        "zBins = alwaysTable\n"
        "#if FEATURE_X\n"
        "table = feature, featureMap, \"Feature\"\n"
        "zBins = featureTable\n"
        "#endif\n",
        {"FEATURE_X"});
    REQUIRE(enabled.editors.size() == 2);
    CHECK(enabled.editors[1].table_id == "feature");
}
