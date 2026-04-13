// SPDX-License-Identifier: MIT
//
// doctest cases for `ini_autotune_sections_parser.hpp`.

#include "doctest.h"

#include "tuner_core/ini_autotune_sections_parser.hpp"

using namespace tuner_core;

// ---------------------------------------------------------------
// GateOperator enum
// ---------------------------------------------------------------

TEST_CASE("autotune: parse_gate_operator round-trips all known ops") {
    CHECK(parse_gate_operator("<") == GateOperator::Lt);
    CHECK(parse_gate_operator(">") == GateOperator::Gt);
    CHECK(parse_gate_operator("<=") == GateOperator::Le);
    CHECK(parse_gate_operator(">=") == GateOperator::Ge);
    CHECK(parse_gate_operator("==") == GateOperator::Eq);
    CHECK(parse_gate_operator("=") == GateOperator::Eq);
    CHECK(parse_gate_operator("!=") == GateOperator::Ne);
    CHECK(parse_gate_operator("&") == GateOperator::BitAnd);
    CHECK(parse_gate_operator("???") == GateOperator::Unknown);
    // Whitespace tolerance.
    CHECK(parse_gate_operator("  < ") == GateOperator::Lt);
}

TEST_CASE("autotune: gate_operator_to_string canonical forms") {
    CHECK(std::string(gate_operator_to_string(GateOperator::Lt)) == "<");
    CHECK(std::string(gate_operator_to_string(GateOperator::Eq)) == "==");
    CHECK(std::string(gate_operator_to_string(GateOperator::BitAnd)) == "&");
    CHECK(std::string(gate_operator_to_string(GateOperator::Unknown)) == "?");
}

// ---------------------------------------------------------------
// VeAnalyze section
// ---------------------------------------------------------------

TEST_CASE("autotune: parses VeAnalyze map parts") {
    const char* text = R"(
[VeAnalyze]
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    CHECK(result.maps[0].section_name == "VeAnalyze");
    REQUIRE(result.maps[0].map_parts.size() == 4);
    CHECK(result.maps[0].map_parts[0] == "veTable1Tbl");
    CHECK(result.maps[0].map_parts[1] == "afrTable1");
    CHECK(result.maps[0].map_parts[2] == "afr");
    CHECK(result.maps[0].map_parts[3] == "egoCorrection");
}

TEST_CASE("autotune: parses lambdaTargetTables") {
    const char* text = R"(
[VeAnalyze]
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
lambdaTargetTables = afrTable1, afrTSCustom
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    REQUIRE(result.maps[0].lambda_target_tables.size() == 2);
    CHECK(result.maps[0].lambda_target_tables[0] == "afrTable1");
    CHECK(result.maps[0].lambda_target_tables[1] == "afrTSCustom");
}

TEST_CASE("autotune: standard gate produces StandardGate variant") {
    const char* text = R"(
[VeAnalyze]
filter = std_xAxisMin
filter = std_DeadLambda
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    REQUIRE(result.maps[0].filter_gates.size() == 2);
    CHECK(std::holds_alternative<StandardGate>(result.maps[0].filter_gates[0]));
    CHECK(gate_name(result.maps[0].filter_gates[0]) == "std_xAxisMin");
    CHECK(gate_name(result.maps[0].filter_gates[1]) == "std_DeadLambda");
}

TEST_CASE("autotune: parameterised gate produces ParameterisedGate variant") {
    const char* text = R"(
[VeAnalyze]
filter = minCltFilter, "Minimum CLT", coolant, <, 71, true
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    REQUIRE(result.maps[0].filter_gates.size() == 1);
    auto& gate = result.maps[0].filter_gates[0];
    REQUIRE(std::holds_alternative<ParameterisedGate>(gate));
    auto& pg = std::get<ParameterisedGate>(gate);
    CHECK(pg.name == "minCltFilter");
    CHECK(pg.label == "Minimum CLT");
    CHECK(pg.channel == "coolant");
    CHECK(pg.op == GateOperator::Lt);
    CHECK(pg.threshold == 71.0);
    CHECK(pg.default_enabled == true);
}

TEST_CASE("autotune: disabled-by-default parameterised gate") {
    const char* text = R"(
[VeAnalyze]
filter = accelFilter, "Accel Flag", engine, &, 16, false
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    REQUIRE(result.maps[0].filter_gates.size() == 1);
    auto& pg = std::get<ParameterisedGate>(result.maps[0].filter_gates[0]);
    CHECK(pg.op == GateOperator::BitAnd);
    CHECK(pg.threshold == 16.0);
    CHECK(pg.default_enabled == false);
}

TEST_CASE("autotune: equals-sign operator maps to Eq") {
    const char* text = R"(
[WueAnalyze]
filter = overrunFilter, "Overrun", pulseWidth, =, 0, false
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    auto& pg = std::get<ParameterisedGate>(result.maps[0].filter_gates[0]);
    CHECK(pg.op == GateOperator::Eq);
}

// ---------------------------------------------------------------
// WueAnalyze section
// ---------------------------------------------------------------

TEST_CASE("autotune: parses WueAnalyze with longer map parts") {
    const char* text = R"(
[WueAnalyze]
wueAnalyzeMap = warmupEnrich, lambdaTable1, lambda, coolant, warmupEnrich, egoCorrection
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    CHECK(result.maps[0].section_name == "WueAnalyze");
    CHECK(result.maps[0].map_parts.size() == 6);
}

// ---------------------------------------------------------------
// Both sections present
// ---------------------------------------------------------------

TEST_CASE("autotune: both VeAnalyze and WueAnalyze parsed") {
    const char* text = R"(
[VeAnalyze]
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
filter = std_xAxisMin

[WueAnalyze]
wueAnalyzeMap = warmupEnrich, lambdaTable1, lambda, coolant, warmupEnrich, egoCorrection
filter = std_DeadLambda
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 2);
    CHECK(result.maps[0].section_name == "VeAnalyze");
    CHECK(result.maps[1].section_name == "WueAnalyze");
}

// ---------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------

TEST_CASE("autotune: lines outside section ignored") {
    const char* text = R"(
[Constants]
filter = wrong

[VeAnalyze]
filter = std_Custom
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    CHECK(result.maps[0].filter_gates.size() == 1);
    CHECK(gate_name(result.maps[0].filter_gates[0]) == "std_Custom");
}

TEST_CASE("autotune: case-insensitive section header") {
    const char* text = R"(
[veanalyze]
filter = std_Custom
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    // Preserve original case from bracket content.
    CHECK(result.maps[0].section_name == "veanalyze");
}

TEST_CASE("autotune: comments and blank lines skipped") {
    const char* text = R"(
[VeAnalyze]
; comment
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection

# another comment
filter = std_Custom
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    CHECK(result.maps[0].map_parts.size() == 4);
    CHECK(result.maps[0].filter_gates.size() == 1);
}

TEST_CASE("autotune: preprocessor #if gating") {
    const char* text = R"INI(
#set LAMBDA
[VeAnalyze]
#if LAMBDA
veAnalyzeMap = veTable1Tbl, lambdaTable1, lambda, egoCorrection
lambdaTargetTables = lambdaTable1, afrTSCustom
#else
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
lambdaTargetTables = afrTable1, afrTSCustom
#endif
filter = std_Custom
)INI";
    auto result = parse_autotune_sections_preprocessed(text);
    REQUIRE(result.maps.size() == 1);
    CHECK(result.maps[0].map_parts[1] == "lambdaTable1");
    CHECK(result.maps[0].lambda_target_tables[0] == "lambdaTable1");
}

TEST_CASE("autotune: active_settings override selects else branch") {
    const char* text = R"INI(
#set LAMBDA
[VeAnalyze]
#if LAMBDA
veAnalyzeMap = veTable1Tbl, lambdaTable1, lambda, egoCorrection
#else
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
#endif
)INI";
    // Without active_settings, #set LAMBDA takes the #if branch.
    auto result1 = parse_autotune_sections_preprocessed(text);
    CHECK(result1.maps[0].map_parts[1] == "lambdaTable1");

    // With empty active_settings and no #set, would take #else.
    // But here the file-level #set LAMBDA fires, so we still get lambda.
    // To force #else, we'd need a file without #set — test the
    // active_settings={"LAMBDA"} path instead.
    const char* text2 = R"INI(
[VeAnalyze]
#if LAMBDA
veAnalyzeMap = veTable1Tbl, lambdaTable1, lambda, egoCorrection
#else
veAnalyzeMap = veTable1Tbl, afrTable1, afr, egoCorrection
#endif
)INI";
    // No #set, no active_settings → #else branch.
    auto result2 = parse_autotune_sections_preprocessed(text2);
    CHECK(result2.maps[0].map_parts[1] == "afrTable1");

    // active_settings={"LAMBDA"} → #if branch.
    auto result3 = parse_autotune_sections_preprocessed(text2, {"LAMBDA"});
    CHECK(result3.maps[0].map_parts[1] == "lambdaTable1");
}

TEST_CASE("autotune: empty input") {
    auto result = parse_autotune_sections("");
    CHECK(result.maps.empty());
}

TEST_CASE("autotune: section present but empty") {
    auto result = parse_autotune_sections("[VeAnalyze]\n");
    REQUIRE(result.maps.size() == 1);
    CHECK(result.maps[0].map_parts.empty());
    CHECK(result.maps[0].filter_gates.empty());
}

TEST_CASE("autotune: partial filter (2-5 parts) treated as standard gate") {
    const char* text = R"(
[VeAnalyze]
filter = partialGate, "Has Label", coolant
)";
    auto result = parse_autotune_sections(text);
    REQUIRE(result.maps.size() == 1);
    REQUIRE(result.maps[0].filter_gates.size() == 1);
    // Only 3 parts < 6 → StandardGate fallback matching Python.
    CHECK(std::holds_alternative<StandardGate>(result.maps[0].filter_gates[0]));
    CHECK(gate_name(result.maps[0].filter_gates[0]) == "partialGate");
}

TEST_CASE("autotune: gate_default_enabled accessor") {
    StandardGate sg{"std_foo"};
    ParameterisedGate pg{"bar", "Bar", "ch", GateOperator::Lt, 10.0, false};
    FilterGate fg_std = sg;
    FilterGate fg_param = pg;
    CHECK(gate_default_enabled(fg_std) == true);
    CHECK(gate_default_enabled(fg_param) == false);
}
