// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/curve_page_builder.hpp"

#include <map>
#include <optional>
#include <string>

namespace cpb = tuner_core::curve_page_builder;

static std::map<std::string, cpb::ParamInfo> g_params;

static std::optional<cpb::ParamInfo> test_finder(const std::string& name, void*) {
    auto it = g_params.find(name);
    if (it != g_params.end()) return it->second;
    return std::nullopt;
}

TEST_SUITE("curve_page_builder") {

TEST_CASE("empty curves produce no groups") {
    auto result = cpb::build_curve_pages({}, test_finder, nullptr);
    CHECK(result.empty());
}

TEST_CASE("single fuel curve produces one group") {
    g_params.clear();
    g_params["wueBins"] = {"wueBins", "CLT Bins", "\xc2\xb0""C", ""};
    g_params["wueRates"] = {"wueRates", "WUE Rates", "%", ""};

    cpb::CurveDefinition cd;
    cd.name = "wueCurve";
    cd.title = "Warmup Enrichment";
    cd.x_bins_param = "wueBins";
    cd.x_channel = "coolant";
    cd.x_label = "CLT";
    cd.y_label = "Enrichment %";
    cd.y_bins_list = {{"wueRates", ""}};
    cd.gauge = "";
    cd.topic_help = "";

    auto result = cpb::build_curve_pages({cd}, test_finder, nullptr);
    REQUIRE(result.size() == 1);
    CHECK(result[0].group_id.find("enrich") != std::string::npos);
    REQUIRE(result[0].pages.size() == 1);
    auto& page = result[0].pages[0];
    CHECK(page.page_id == "curve:wueCurve");
    CHECK(page.title == "Warmup Enrichment");
    CHECK(page.curve_x_bins_param == "wueBins");
    CHECK(page.curve_x_channel == "coolant");
    CHECK(page.summary.find("1D") != std::string::npos);
    CHECK(page.summary.find("coolant") != std::string::npos);
    // Should have x + y params.
    CHECK(page.parameters.size() == 2);
    CHECK(page.parameters[0].role == "x_axis");
    CHECK(page.parameters[1].role == "y_axis");
}

TEST_CASE("multi-line curve shows N lines in summary") {
    g_params.clear();
    g_params["xBins"] = {"xBins", "RPM", "rpm", ""};
    g_params["yBins1"] = {"yBins1", "Line 1", "%", ""};
    g_params["yBins2"] = {"yBins2", "Line 2", "%", ""};

    cpb::CurveDefinition cd;
    cd.name = "sparkCurve";
    cd.title = "Spark Advance";
    cd.x_bins_param = "xBins";
    cd.x_channel = "";
    cd.x_label = "RPM";
    cd.y_label = "Advance";
    cd.y_bins_list = {{"yBins1", "Line 1"}, {"yBins2", "Line 2"}};

    auto result = cpb::build_curve_pages({cd}, test_finder, nullptr);
    REQUIRE(!result.empty());
    CHECK(result[0].pages[0].summary.find("2 lines") != std::string::npos);
    CHECK(result[0].pages[0].curve_y_bins_params.size() == 2);
    CHECK(result[0].pages[0].curve_line_labels.size() == 2);
}

TEST_CASE("curves from different categories land in separate groups") {
    g_params.clear();
    g_params["x"] = {"x", "X", "", ""};
    g_params["y"] = {"y", "Y", "", ""};

    cpb::CurveDefinition fuel_cd;
    fuel_cd.name = "fuelCurve";
    fuel_cd.title = "Fuel Curve";
    fuel_cd.x_bins_param = "x";
    fuel_cd.y_bins_list = {{"y", ""}};

    cpb::CurveDefinition idle_cd;
    idle_cd.name = "idleCurve";
    idle_cd.title = "Idle RPM Curve";
    idle_cd.x_bins_param = "x";
    idle_cd.y_bins_list = {{"y", ""}};

    auto result = cpb::build_curve_pages({fuel_cd, idle_cd}, test_finder, nullptr);
    CHECK(result.size() == 2);
}

TEST_CASE("pages within a group are sorted alphabetically") {
    g_params.clear();
    g_params["x"] = {"x", "X", "", ""};
    g_params["y"] = {"y", "Y", "", ""};

    cpb::CurveDefinition cd_z;
    cd_z.name = "zFuel"; cd_z.title = "Z Fuel Trim";
    cd_z.x_bins_param = "x"; cd_z.y_bins_list = {{"y", ""}};

    cpb::CurveDefinition cd_a;
    cd_a.name = "aFuel"; cd_a.title = "A Fuel Trim";
    cd_a.x_bins_param = "x"; cd_a.y_bins_list = {{"y", ""}};

    auto result = cpb::build_curve_pages({cd_z, cd_a}, test_finder, nullptr);
    REQUIRE(!result.empty());
    REQUIRE(result[0].pages.size() == 2);
    CHECK(result[0].pages[0].title == "A Fuel Trim");
    CHECK(result[0].pages[1].title == "Z Fuel Trim");
}

TEST_CASE("missing parameter is skipped gracefully") {
    g_params.clear();
    // Don't register any params — the builder should still produce a page.
    cpb::CurveDefinition cd;
    cd.name = "test"; cd.title = "Test Curve";
    cd.x_bins_param = "missing_x";
    cd.y_bins_list = {{"missing_y", ""}};

    auto result = cpb::build_curve_pages({cd}, test_finder, nullptr);
    REQUIRE(!result.empty());
    CHECK(result[0].pages[0].parameters.empty());
}

TEST_CASE("y_label falls back through chain") {
    g_params.clear();
    g_params["x"] = {"x", "X", "", ""};
    g_params["y"] = {"y", "Y Param Label", "%", ""};

    cpb::CurveDefinition cd;
    cd.name = "fuelTest"; cd.title = "Fuel Test";
    cd.x_bins_param = "x";
    cd.y_label = "";  // No curve-level y label.
    cd.y_bins_list = {{"y", ""}};  // No bins-level label.

    auto result = cpb::build_curve_pages({cd}, test_finder, nullptr);
    REQUIRE(!result.empty());
    auto& params = result[0].pages[0].parameters;
    // y param should fall back to param info label.
    bool found_y = false;
    for (const auto& p : params) {
        if (p.role == "y_axis") { found_y = true; CHECK(p.label == "Y Param Label"); }
    }
    CHECK(found_y);
}

}  // TEST_SUITE
