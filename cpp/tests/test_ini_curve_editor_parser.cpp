// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniCurveEditorParser. Mirrors
// the Python `_parse_curve_editors` test surface so cross-validation
// against the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_curve_editor_parser.hpp"

#include <string>

namespace {

const tuner_core::IniCurveEditor* find_curve(
    const tuner_core::IniCurveEditorSection& section,
    const std::string& name) {
    for (const auto& c : section.curves) {
        if (c.name == name) return &c;
    }
    return nullptr;
}

}  // namespace

TEST_CASE("parse_curve_editor_section ignores lines outside [CurveEditor]") {
    auto section = tuner_core::parse_curve_editor_section(
        "[Other]\ncurve = wueCurve, \"WUE\"\n");
    CHECK(section.curves.empty());
}

TEST_CASE("parses a single curve with all common fields") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = wueCurve, \"Warm-up Enrichment\"\n"
        "columnLabel = \"Coolant\", \"Multiplier %\"\n"
        "xAxis = -40.0, 215.0, 5\n"
        "yAxis = 100.0, 250.0, 5\n"
        "xBins = wueBins, coolant\n"
        "yBins = WUEValues\n"
        "topicHelp = \"WUE help\"\n"
        "gauge = cltGauge\n"
        "size = 360, 200\n");
    REQUIRE(section.curves.size() == 1);
    const auto& c = section.curves[0];
    CHECK(c.name == "wueCurve");
    CHECK(c.title == "Warm-up Enrichment");
    CHECK(c.x_label == "Coolant");
    CHECK(c.y_label == "Multiplier %");
    REQUIRE(c.x_axis.has_value());
    CHECK(c.x_axis->min == doctest::Approx(-40.0));
    CHECK(c.x_axis->max == doctest::Approx(215.0));
    CHECK(c.x_axis->steps == 5);
    REQUIRE(c.y_axis.has_value());
    CHECK(c.y_axis->min == doctest::Approx(100.0));
    CHECK(c.y_axis->max == doctest::Approx(250.0));
    CHECK(c.x_bins_param == "wueBins");
    CHECK(c.x_channel.value() == "coolant");
    REQUIRE(c.y_bins_list.size() == 1);
    CHECK(c.y_bins_list[0].param == "WUEValues");
    CHECK(c.topic_help.value() == "WUE help");
    CHECK(c.gauge.value() == "cltGauge");
    REQUIRE(c.size.has_value());
    CHECK(c.size->at(0) == 360);
    CHECK(c.size->at(1) == 200);
}

TEST_CASE("parses multiple curves and flushes correctly between them") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = first, \"First\"\n"
        "xBins = aBins\n"
        "yBins = aValues\n"
        "curve = second, \"Second\"\n"
        "xBins = bBins\n"
        "yBins = bValues\n");
    REQUIRE(section.curves.size() == 2);
    CHECK(find_curve(section, "first")->y_bins_list[0].param == "aValues");
    CHECK(find_curve(section, "second")->y_bins_list[0].param == "bValues");
}

TEST_CASE("multi-line curves accumulate yBins entries") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = veCmp, \"VE current vs recommended\"\n"
        "xBins = veBins\n"
        "yBins = veCurrent\n"
        "yBins = veRecommended\n");
    REQUIRE(section.curves.size() == 1);
    REQUIRE(section.curves[0].y_bins_list.size() == 2);
    CHECK(section.curves[0].y_bins_list[0].param == "veCurrent");
    CHECK(section.curves[0].y_bins_list[1].param == "veRecommended");
}

TEST_CASE("lineLabel entries are matched onto y_bins positionally") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = veCmp, \"VE Comparison\"\n"
        "xBins = veBins\n"
        "yBins = veCurrent\n"
        "yBins = veRecommended\n"
        "lineLabel = \"Current\"\n"
        "lineLabel = \"Recommended\"\n");
    REQUIRE(section.curves.size() == 1);
    const auto& yb = section.curves[0].y_bins_list;
    REQUIRE(yb.size() == 2);
    CHECK(yb[0].label.value() == "Current");
    CHECK(yb[1].label.value() == "Recommended");
}

TEST_CASE("lineLabel can appear before all yBins (tail-positioned)") {
    // The Python implementation collects pending labels and assigns
    // them at flush time, regardless of where they appear relative
    // to the yBins lines. Verify the same.
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = c, \"C\"\n"
        "lineLabel = \"Label A\"\n"
        "lineLabel = \"Label B\"\n"
        "xBins = cBins\n"
        "yBins = cA\n"
        "yBins = cB\n");
    REQUIRE(section.curves.size() == 1);
    const auto& yb = section.curves[0].y_bins_list;
    REQUIRE(yb.size() == 2);
    CHECK(yb[0].label.value() == "Label A");
    CHECK(yb[1].label.value() == "Label B");
}

TEST_CASE("title defaults to name when missing") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = lonelyCurve\n"
        "xBins = bins\n"
        "yBins = values\n");
    REQUIRE(section.curves.size() == 1);
    CHECK(section.curves[0].name == "lonelyCurve");
    CHECK(section.curves[0].title == "lonelyCurve");
}

TEST_CASE("section change flushes the active curve") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = c, \"C\"\n"
        "xBins = cBins\n"
        "yBins = cValues\n"
        "[OtherSection]\n"
        "yBins = leaked\n");
    REQUIRE(section.curves.size() == 1);
    // Only the original yBins should be present — the leaked one
    // came after the section ended.
    CHECK(section.curves[0].y_bins_list.size() == 1);
}

TEST_CASE("inline comments after key=value are stripped") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = c, \"C\"\n"
        "xBins = cBins ; trailing comment\n"
        "yBins = cValues ; another\n");
    REQUIRE(section.curves.size() == 1);
    CHECK(section.curves[0].x_bins_param == "cBins");
    CHECK(section.curves[0].y_bins_list[0].param == "cValues");
}

TEST_CASE("xAxis with fewer than 3 values is dropped") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = c, \"C\"\n"
        "xAxis = -40.0, 215.0\n");
    REQUIRE(section.curves.size() == 1);
    CHECK_FALSE(section.curves[0].x_axis.has_value());
}

TEST_CASE("size with non-numeric values is dropped") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = c, \"C\"\n"
        "size = wide, tall\n");
    REQUIRE(section.curves.size() == 1);
    CHECK_FALSE(section.curves[0].size.has_value());
}

TEST_CASE("comments and blank lines are ignored") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "; comment\n"
        "\n"
        "curve = c, \"C\"\n"
        "; mid-curve comment\n"
        "xBins = cBins\n"
        "yBins = cValues\n");
    REQUIRE(section.curves.size() == 1);
    CHECK(section.curves[0].x_bins_param == "cBins");
}

TEST_CASE("preprocessed pipeline gates curves inside #if blocks") {
    auto section = tuner_core::parse_curve_editor_section_preprocessed(
        "[CurveEditor]\n"
        "curve = always, \"Always\"\n"
        "xBins = aBins\n"
        "yBins = aValues\n"
        "#if FEATURE_X\n"
        "curve = feature, \"Feature\"\n"
        "xBins = fBins\n"
        "yBins = fValues\n"
        "#endif\n",
        {});
    REQUIRE(section.curves.size() == 1);
    CHECK(section.curves[0].name == "always");

    auto enabled = tuner_core::parse_curve_editor_section_preprocessed(
        "[CurveEditor]\n"
        "curve = always, \"Always\"\n"
        "xBins = aBins\n"
        "yBins = aValues\n"
        "#if FEATURE_X\n"
        "curve = feature, \"Feature\"\n"
        "xBins = fBins\n"
        "yBins = fValues\n"
        "#endif\n",
        {"FEATURE_X"});
    REQUIRE(enabled.curves.size() == 2);
    CHECK(enabled.curves[1].name == "feature");
}

TEST_CASE("final curve at end of section is flushed") {
    auto section = tuner_core::parse_curve_editor_section(
        "[CurveEditor]\n"
        "curve = first, \"First\"\n"
        "yBins = firstValues\n"
        "curve = last, \"Last\"\n"
        "yBins = lastValues\n");
    // Second curve must land in the section even without an explicit
    // section terminator — the implementation flushes on EOF.
    REQUIRE(section.curves.size() == 2);
    CHECK(find_curve(section, "last")->y_bins_list[0].param == "lastValues");
}
