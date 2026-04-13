// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/ts_dash_file.hpp"

namespace tdf = tuner_core::ts_dash_file;
namespace dl = tuner_core::dashboard_layout;

TEST_SUITE("ts_dash_file") {

TEST_CASE("parse minimal .dash XML") {
    const char* xml =
        "<dsh xmlns=\"http://www.EFIAnalytics.com/:dsh\">\n"
        "  <versionInfo fileFormat=\"3.0\" firmwareSignature=\"speeduino 202501-T41\"/>\n"
        "  <gaugeCluster>\n"
        "    <dashComp type=\"com.efiAnalytics.apps.ts.dashboard.Gauge\">\n"
        "      <Title type=\"String\">RPM</Title>\n"
        "      <Units type=\"String\">rpm</Units>\n"
        "      <Min type=\"double\">0.0</Min>\n"
        "      <Max type=\"double\">8000.0</Max>\n"
        "      <RelativeX type=\"double\">0.02</RelativeX>\n"
        "      <RelativeY type=\"double\">0.02</RelativeY>\n"
        "      <RelativeWidth type=\"double\">0.20</RelativeWidth>\n"
        "      <RelativeHeight type=\"double\">0.15</RelativeHeight>\n"
        "      <HighWarning type=\"double\">6500.0</HighWarning>\n"
        "      <HighCritical type=\"double\">7500.0</HighCritical>\n"
        "      <OutputChannel type=\"String\">rpm</OutputChannel>\n"
        "    </dashComp>\n"
        "  </gaugeCluster>\n"
        "</dsh>\n";
    auto layout = tdf::parse_text(xml);
    CHECK(layout.name == "speeduino 202501-T41");
    REQUIRE(layout.widgets.size() == 1);
    auto& w = layout.widgets[0];
    CHECK(w.kind == "dial");
    CHECK(w.title == "RPM");
    CHECK(w.source == "rpm");
    CHECK(w.units == "rpm");
    CHECK(w.min_value == doctest::Approx(0.0));
    CHECK(w.max_value == doctest::Approx(8000.0));
    CHECK(w.x == doctest::Approx(0.02));
    CHECK(w.width == doctest::Approx(0.20));
    CHECK(w.color_zones.size() == 2);  // warning + danger
}

TEST_CASE("parse multiple widgets") {
    const char* xml =
        "<dsh xmlns=\"http://www.EFIAnalytics.com/:dsh\">\n"
        "  <gaugeCluster>\n"
        "    <dashComp type=\"com.efiAnalytics.apps.ts.dashboard.Gauge\">\n"
        "      <Title type=\"String\">RPM</Title>\n"
        "      <OutputChannel type=\"String\">rpm</OutputChannel>\n"
        "    </dashComp>\n"
        "    <dashComp type=\"com.efiAnalytics.apps.ts.dashboard.Indicator\">\n"
        "      <Title type=\"String\">Sync</Title>\n"
        "      <OutputChannel type=\"String\">syncLoss</OutputChannel>\n"
        "    </dashComp>\n"
        "    <dashComp type=\"com.efiAnalytics.apps.ts.dashboard.DashLabel\">\n"
        "      <Title type=\"String\">Status</Title>\n"
        "    </dashComp>\n"
        "  </gaugeCluster>\n"
        "</dsh>\n";
    auto layout = tdf::parse_text(xml);
    REQUIRE(layout.widgets.size() == 3);
    CHECK(layout.widgets[0].kind == "dial");
    CHECK(layout.widgets[1].kind == "indicator");
    CHECK(layout.widgets[2].kind == "label");
}

TEST_CASE("export and re-parse round-trip") {
    dl::Layout layout;
    layout.name = "Test Layout";
    dl::Widget w;
    w.widget_id = "rpm"; w.kind = "dial"; w.title = "RPM"; w.source = "rpm";
    w.units = "rpm"; w.x = 0.1; w.y = 0.2; w.width = 0.3; w.height = 0.4;
    w.min_value = 0; w.max_value = 8000;
    w.color_zones = {{6500, 7500, "warning"}, {7500, 8000, "danger"}};
    layout.widgets.push_back(w);

    auto xml = tdf::export_text(layout);
    CHECK(xml.find("Test Layout") != std::string::npos);
    CHECK(xml.find("gaugeCluster") != std::string::npos);

    auto restored = tdf::parse_text(xml);
    CHECK(restored.name == "Test Layout");
    REQUIRE(restored.widgets.size() == 1);
    CHECK(restored.widgets[0].title == "RPM");
    CHECK(restored.widgets[0].source == "rpm");
    CHECK(restored.widgets[0].max_value == doctest::Approx(8000.0));
}

TEST_CASE("empty gaugeCluster produces empty widget list") {
    const char* xml =
        "<dsh xmlns=\"http://www.EFIAnalytics.com/:dsh\">\n"
        "  <gaugeCluster/>\n"
        "</dsh>\n";
    auto layout = tdf::parse_text(xml);
    CHECK(layout.widgets.empty());
}

TEST_CASE("default layout name when no firmwareSignature") {
    const char* xml =
        "<dsh xmlns=\"http://www.EFIAnalytics.com/:dsh\">\n"
        "  <gaugeCluster/>\n"
        "</dsh>\n";
    auto layout = tdf::parse_text(xml);
    CHECK(layout.name == "Imported Dashboard");
}

TEST_CASE("widget ID is slugified from title") {
    const char* xml =
        "<dsh xmlns=\"http://www.EFIAnalytics.com/:dsh\">\n"
        "  <gaugeCluster>\n"
        "    <dashComp type=\"com.efiAnalytics.apps.ts.dashboard.Gauge\">\n"
        "      <Title type=\"String\">Coolant Temp (C)</Title>\n"
        "    </dashComp>\n"
        "  </gaugeCluster>\n"
        "</dsh>\n";
    auto layout = tdf::parse_text(xml);
    REQUIRE(layout.widgets.size() == 1);
    CHECK(layout.widgets[0].widget_id == "coolant_temp_c");
}

}  // TEST_SUITE
