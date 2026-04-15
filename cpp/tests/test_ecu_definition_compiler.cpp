// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::EcuDefinitionCompiler. Confirms
// the orchestrator dispatches every leaf parser against a single
// preprocessor pass.

#include "doctest.h"

#include "tuner_core/ecu_definition_compiler.hpp"

#include <string>

namespace {

const char* MIXED_INI = R"(
[Constants]
page = 1
nCylinders = scalar, U08, 0, "cyl", 1.0, 0.0, 1, 12, 0
veTable = array, U08, 1, [16x16], "%", 1.0, 0.0, 0, 255, 0

[OutputChannels]
ochBlockSize = 148
rpm = scalar, U16, 0, "rpm", 1.0, 0.0, 0, 8000, 0

[TableEditor]
table = veTable1Tbl, veTable, "VE Table", 1
xBins = rpmBins, rpm
yBins = mapBins, map
zBins = veTable

[CurveEditor]
curve = wueCurve, "Warmup Enrichment"
columnLabel = "Coolant", "Enrichment %"
xAxis = -40, 215, 5
yAxis = 100, 250, 10
xBins = wueBins, coolant
yBins = wueTable

[Menu]
menuDialog = main
menu = "Settings"
subMenu = engineConstants, "Engine Constants"

[GaugeConfigurations]
rpmGauge = rpm, "RPM", "rpm", 0, 8000, 0, 0, 6500, 7500, 0, 0

[FrontPage]
gauge1 = rpmGauge
gauge2 = mapGauge
indicator = { sync }, "NoSync", "Sync", red, white, green, white

[LoggerDefinition]
loggerDef = tooth, "Tooth Log", tooth
dataReadCommand = "T$tsCanId"
dataLength = 16
recordDef = 0, 0, 4

[ControllerCommands]
cmdResetEcu = "E\xAB\xCD"

[SettingGroups]
settingGroup = mcu, "Controller in use"
settingOption = mcu_teensy, "Teensy 3.5/3.6/4.1"
settingOption = mcu_mega2560, "Arduino Mega 2560"
)";

}  // namespace

TEST_CASE("compile_ecu_definition_text dispatches every leaf parser") {
    auto def = tuner_core::compile_ecu_definition_text(MIXED_INI);

    // Constants
    CHECK(!def.constants.scalars.empty());
    CHECK(!def.constants.arrays.empty());

    // Output channels
    CHECK(!def.output_channels.channels.empty());

    // Table editor
    REQUIRE(def.table_editors.editors.size() == 1);
    CHECK(def.table_editors.editors[0].table_id == "veTable1Tbl");

    // Curve editor
    REQUIRE(def.curve_editors.curves.size() == 1);
    CHECK(def.curve_editors.curves[0].name == "wueCurve");

    // Menu
    CHECK(!def.menus.menus.empty());

    // Gauge configurations
    REQUIRE(def.gauge_configurations.gauges.size() == 1);
    CHECK(def.gauge_configurations.gauges[0].name == "rpmGauge");

    // Front page
    CHECK(def.front_page.gauges.size() == 2);
    REQUIRE(def.front_page.indicators.size() == 1);
    CHECK(def.front_page.indicators[0].expression == "sync");

    // Logger definition
    REQUIRE(def.logger_definitions.loggers.size() == 1);
    CHECK(def.logger_definitions.loggers[0].name == "tooth");
    CHECK(def.logger_definitions.loggers[0].record_count == 4);

    // Controller commands
    REQUIRE(def.controller_commands.commands.size() == 1);
    CHECK(def.controller_commands.commands[0].name == "cmdResetEcu");
    CHECK(def.controller_commands.commands[0].payload.size() == 3);

    // Setting groups
    REQUIRE(def.setting_groups.groups.size() == 1);
    CHECK(def.setting_groups.groups[0].symbol == "mcu");
    CHECK(def.setting_groups.groups[0].label == "Controller in use");
    REQUIRE(def.setting_groups.groups[0].options.size() == 2);
    CHECK(def.setting_groups.groups[0].options[0].symbol == "mcu_teensy");
    CHECK(def.setting_groups.groups[0].options[1].symbol == "mcu_mega2560");
}

TEST_CASE("active_settings gates conditional sections") {
    const char* gated =
        "#if FEATURE_X\n"
        "[GaugeConfigurations]\n"
        "rpmGauge = rpm, \"RPM\", \"rpm\", 0, 8000\n"
        "#endif\n";
    auto enabled = tuner_core::compile_ecu_definition_text(gated, {"FEATURE_X"});
    CHECK(enabled.gauge_configurations.gauges.size() == 1);
    auto disabled = tuner_core::compile_ecu_definition_text(gated, {});
    CHECK(disabled.gauge_configurations.gauges.empty());
}

TEST_CASE("empty INI yields empty catalogs without crashing") {
    auto def = tuner_core::compile_ecu_definition_text("");
    CHECK(def.constants.scalars.empty());
    CHECK(def.output_channels.channels.empty());
    CHECK(def.table_editors.editors.empty());
    CHECK(def.curve_editors.curves.empty());
    CHECK(def.menus.menus.empty());
    CHECK(def.gauge_configurations.gauges.empty());
    CHECK(def.front_page.gauges.empty());
    CHECK(def.front_page.indicators.empty());
    CHECK(def.logger_definitions.loggers.empty());
    CHECK(def.controller_commands.commands.empty());
    CHECK(def.setting_groups.groups.empty());
}

TEST_CASE("TN-007: endianness defaults to little when absent") {
    auto def = tuner_core::compile_ecu_definition_text("");
    CHECK(def.byte_order == "little");
    CHECK(def.is_little_endian() == true);
}

TEST_CASE("TN-007: endianness = little parsed and reported") {
    auto def = tuner_core::compile_ecu_definition_text(
        "[Constants]\nendianness = little\n");
    CHECK(def.byte_order == "little");
    CHECK(def.is_little_endian() == true);
}

TEST_CASE("TN-007: endianness = big parsed and reported") {
    auto def = tuner_core::compile_ecu_definition_text(
        "[Constants]\nendianness = big\n");
    CHECK(def.byte_order == "big");
    CHECK(def.is_little_endian() == false);
}

TEST_CASE("TN-007: endianness is case-insensitive") {
    auto def = tuner_core::compile_ecu_definition_text(
        "[Constants]\nEndianness = LITTLE\n");
    CHECK(def.byte_order == "little");
    CHECK(def.is_little_endian() == true);

    auto def2 = tuner_core::compile_ecu_definition_text(
        "[Constants]\nendianness = Big\n");
    CHECK(def2.byte_order == "big");
    CHECK(def2.is_little_endian() == false);
}

TEST_CASE("TN-007: unknown endianness value falls back to little") {
    auto def = tuner_core::compile_ecu_definition_text(
        "[Constants]\nendianness = middle\n");
    CHECK(def.byte_order == "little");
    CHECK(def.is_little_endian() == true);
}

TEST_CASE("TN-007: endianness key in other sections ignored") {
    auto def = tuner_core::compile_ecu_definition_text(
        "[MegaTune]\nendianness = big\n");
    CHECK(def.byte_order == "little");
}

TEST_CASE("TN-007: endianness line with trailing comment is stripped") {
    auto def = tuner_core::compile_ecu_definition_text(
        "[Constants]\nendianness = big  ; firmware switched in Phase 12\n");
    CHECK(def.byte_order == "big");
}
