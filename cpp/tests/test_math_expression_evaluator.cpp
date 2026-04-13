// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::math_expression_evaluator.
// Direct parity with tests/unit/test_math_expression_evaluator.py.

#include "doctest.h"

#include "tuner_core/math_expression_evaluator.hpp"
#include "tuner_core/ecu_definition_compiler.hpp"

#include <cmath>
#include <filesystem>

using tuner_core::math_expression_evaluator::evaluate;
using tuner_core::math_expression_evaluator::compute_all;
using tuner_core::math_expression_evaluator::enrich;
using tuner_core::math_expression_evaluator::ValueMap;
using tuner_core::math_expression_evaluator::ArrayMap;
using tuner_core::IniFormulaOutputChannel;

TEST_CASE("empty expression returns zero") {
    ValueMap v;
    CHECK(evaluate("", v) == 0.0);
    CHECK(evaluate("   ", v) == 0.0);
    CHECK(evaluate("{}", v) == 0.0);
}

TEST_CASE("brace stripping") {
    ValueMap v;
    CHECK(evaluate("{ 1 + 2 }", v) == 3.0);
}

TEST_CASE("parse error returns zero") {
    ValueMap v;
    CHECK(evaluate("((", v) == 0.0);
}

TEST_CASE("unknown identifier defaults to zero") {
    ValueMap v;
    CHECK(evaluate("unknownChannel", v) == 0.0);
    CHECK(evaluate("unknownChannel + 5", v) == 5.0);
}

TEST_CASE("addition and subtraction") {
    ValueMap v{{"coolantRaw", 90.0}};
    CHECK(evaluate("coolantRaw - 40", v) == 50.0);
    ValueMap v2{{"a", 1.0}, {"b", 2.0}, {"c", 3.0}};
    CHECK(evaluate("a + b + c", v2) == 6.0);
}

TEST_CASE("multiplication and division") {
    ValueMap v{{"fuelPressure", 300.0}};
    CHECK(evaluate("fuelPressure * 0.06894757", v) == doctest::Approx(300.0 * 0.06894757));
    ValueMap v2;
    CHECK(evaluate("100 / 4", v2) == 25.0);
}

TEST_CASE("modulo") {
    ValueMap v;
    CHECK(evaluate("10 % 3", v) == 1.0);
}

TEST_CASE("division by zero returns zero") {
    ValueMap v;
    CHECK(evaluate("10 / 0", v) == 0.0);
    CHECK(evaluate("10 % 0", v) == 0.0);
}

TEST_CASE("precedence multiply before add") {
    ValueMap v;
    CHECK(evaluate("2 + 3 * 4", v) == 14.0);
}

TEST_CASE("parentheses override precedence") {
    ValueMap v;
    CHECK(evaluate("(2 + 3) * 4", v) == 20.0);
}

TEST_CASE("unary minus") {
    ValueMap v{{"rpm", 3000.0}};
    CHECK(evaluate("-5", ValueMap{}) == -5.0);
    CHECK(evaluate("-rpm", v) == -3000.0);
    CHECK(evaluate("-(2 + 3)", ValueMap{}) == -5.0);
}

TEST_CASE("unary plus") {
    ValueMap v;
    CHECK(evaluate("+5", v) == 5.0);
}

TEST_CASE("left shift") {
    ValueMap v{{"sync", 1.0}};
    CHECK(evaluate("1 << 3", ValueMap{}) == 8.0);
    CHECK(evaluate("sync << 1", v) == 2.0);
}

TEST_CASE("right shift") {
    ValueMap v;
    CHECK(evaluate("16 >> 2", v) == 4.0);
}

TEST_CASE("shift truncates to int operands") {
    ValueMap v;
    CHECK(evaluate("3.9 << 1", v) == 6.0);
}

TEST_CASE("equality comparisons") {
    ValueMap v1{{"twoStroke", 1.0}};
    ValueMap v0{{"twoStroke", 0.0}};
    CHECK(evaluate("twoStroke == 1", v1) == 1.0);
    CHECK(evaluate("twoStroke == 1", v0) == 0.0);
}

TEST_CASE("logical and/or") {
    ValueMap v{{"boostCutFuel", 1.0}, {"boostCutSpark", 0.0}};
    CHECK(evaluate("boostCutFuel || boostCutSpark", v) == 1.0);
    ValueMap v2{{"a", 1.0}, {"b", 0.0}};
    CHECK(evaluate("a && b", v2) == 0.0);
}

TEST_CASE("logical not") {
    ValueMap v0{{"x", 0.0}};
    ValueMap v5{{"x", 5.0}};
    CHECK(evaluate("!x", v0) == 1.0);
    CHECK(evaluate("!x", v5) == 0.0);
}

TEST_CASE("simple ternary") {
    ValueMap v1{{"twoStroke", 1.0}};
    ValueMap v0{{"twoStroke", 0.0}};
    CHECK(evaluate("twoStroke == 1 ? 1 : 2", v1) == 1.0);
    CHECK(evaluate("twoStroke == 1 ? 1 : 2", v0) == 2.0);
}

TEST_CASE("ternary with rpm guard — revolutionTime") {
    ValueMap v{{"rpm", 6000.0}};
    ValueMap vz{{"rpm", 0.0}};
    CHECK(evaluate("rpm ? ( 60000.0 / rpm) : 0", v) == 10.0);
    CHECK(evaluate("rpm ? ( 60000.0 / rpm) : 0", vz) == 0.0);
}

TEST_CASE("nested ternary right associative — fuelLoad2") {
    ValueMap v{{"fuel2Algorithm", 1.0}, {"map", 90.0}, {"tps", 42.0}};
    CHECK(evaluate("fuel2Algorithm == 0 ? map : fuel2Algorithm == 1 ? tps : 0", v) == 42.0);
}

TEST_CASE("ternary inside parentheses — load max") {
    ValueMap v0{{"ignAlgorithm", 0.0}};
    ValueMap v1{{"ignAlgorithm", 1.0}};
    CHECK(evaluate("(ignAlgorithm == 0 || ignAlgorithm == 2) ? 511 : 100.0", v0) == 511.0);
    CHECK(evaluate("(ignAlgorithm == 0 || ignAlgorithm == 2) ? 511 : 100.0", v1) == 100.0);
}

TEST_CASE("arrayValue with prefix") {
    ArrayMap arr{{"boardFuelOutputs", {4.0, 8.0, 8.0}}};
    ValueMap v;
    CHECK(evaluate("arrayValue(array.boardFuelOutputs, 0)", v, &arr) == 4.0);
    CHECK(evaluate("arrayValue(array.boardFuelOutputs, 2)", v, &arr) == 8.0);
}

TEST_CASE("arrayValue index from channel") {
    ArrayMap arr{{"boardFuelOutputs", {4.0, 8.0, 16.0}}};
    ValueMap v{{"pinLayout", 2.0}};
    CHECK(evaluate("arrayValue( array.boardFuelOutputs, pinLayout )", v, &arr) == 16.0);
}

TEST_CASE("arrayValue out of range is zero") {
    ArrayMap arr{{"boardFuelOutputs", {4.0, 8.0}}};
    ValueMap v;
    CHECK(evaluate("arrayValue(array.boardFuelOutputs, 99)", v, &arr) == 0.0);
}

TEST_CASE("arrayValue missing array is zero") {
    ArrayMap arr;
    ValueMap v;
    CHECK(evaluate("arrayValue(array.unknown, 0)", v, &arr) == 0.0);
}

TEST_CASE("unknown function returns zero") {
    ValueMap v;
    CHECK(evaluate("mysteryFn(1, 2)", v) == 0.0);
}

TEST_CASE("compute_all respects declaration order") {
    std::vector<IniFormulaOutputChannel> formulas{
        IniFormulaOutputChannel{"revolutionTime", "rpm ? ( 60000.0 / rpm) : 0", {}, {}},
        IniFormulaOutputChannel{"strokeMultipler", "twoStroke == 1 ? 1 : 2", {}, {}},
        IniFormulaOutputChannel{"cycleTime", "revolutionTime * strokeMultipler", {}, {}},
    };
    ValueMap values{{"rpm", 6000.0}, {"twoStroke", 0.0}};
    auto result = compute_all(formulas, values);
    CHECK(result["revolutionTime"] == 10.0);
    CHECK(result["strokeMultipler"] == 2.0);
    CHECK(result["cycleTime"] == 20.0);
}

TEST_CASE("compute_all does not mutate input") {
    std::vector<IniFormulaOutputChannel> formulas{
        IniFormulaOutputChannel{"x2", "x * 2", {}, {}},
    };
    ValueMap values{{"x", 5.0}};
    compute_all(formulas, values);
    CHECK(values.find("x2") == values.end());
}

// ---------------------------------------------------------------------------
// Production-flavored checks — same scenarios as the Python parity tests
// but expressed as synthetic formulas (the production INI parser test
// already covers verbatim expression preservation).
// ---------------------------------------------------------------------------

TEST_CASE("production coolant fahrenheit conversion") {
    // coolant = (coolantRaw - 40) * 1.8 + 32 → 90 raw → 122 F
    ValueMap v{{"coolantRaw", 90.0}};
    CHECK(evaluate("(coolantRaw - 40) * 1.8 + 32", v) == 122.0);
}

TEST_CASE("production map_psi") {
    ValueMap v{{"map", 201.0}, {"baro", 101.0}};
    CHECK(evaluate("(map - baro) * 0.145038", v) == doctest::Approx((201.0 - 101.0) * 0.145038));
}

TEST_CASE("production lambda") {
    ValueMap v{{"afr", 14.7}, {"stoich", 14.7}};
    CHECK(evaluate("afr / stoich", v) == 1.0);
}

TEST_CASE("production syncStatus uses bitshift") {
    // syncStatus = halfSync + (sync << 1)
    const char* expr = "halfSync + (sync << 1)";
    CHECK(evaluate(expr, ValueMap{{"halfSync", 0.0}, {"sync", 0.0}}) == 0.0);
    CHECK(evaluate(expr, ValueMap{{"halfSync", 1.0}, {"sync", 0.0}}) == 1.0);
    CHECK(evaluate(expr, ValueMap{{"halfSync", 0.0}, {"sync", 1.0}}) == 2.0);
    CHECK(evaluate(expr, ValueMap{{"halfSync", 1.0}, {"sync", 1.0}}) == 3.0);
}

// ---------------------------------------------------------------------------
// enrich — in-place runtime wiring
// ---------------------------------------------------------------------------

TEST_CASE("enrich is a no-op when formulas is empty") {
    ValueMap snap{{"rpm", 3000.0}, {"map", 95.0}};
    enrich(snap, {});
    CHECK(snap.size() == 2);
    CHECK(snap.at("rpm") == 3000.0);
}

TEST_CASE("enrich appends computed channels in place") {
    std::vector<IniFormulaOutputChannel> formulas{
        IniFormulaOutputChannel{"throttle", "tps", {}, {}},
        IniFormulaOutputChannel{"lambda", "afr / stoich", {}, {}},
    };
    ValueMap snap{{"tps", 42.0}, {"afr", 14.7}, {"stoich", 14.7}};
    enrich(snap, formulas);
    CHECK(snap.size() == 5);
    CHECK(snap.at("throttle") == 42.0);
    CHECK(snap.at("lambda") == 1.0);
}

TEST_CASE("enrich does not clobber existing hardware channels") {
    // If a formula channel collides with a hardware channel name, the
    // hardware reading wins.
    std::vector<IniFormulaOutputChannel> formulas{
        IniFormulaOutputChannel{"rpm", "9999", {}, {}},
    };
    ValueMap snap{{"rpm", 3000.0}};
    enrich(snap, formulas);
    CHECK(snap.at("rpm") == 3000.0);
}

TEST_CASE("enrich chains formulas in declaration order") {
    // Same ordering guarantee as compute_all — later formulas can reference
    // earlier ones through the working map.
    std::vector<IniFormulaOutputChannel> formulas{
        IniFormulaOutputChannel{"revolutionTime", "rpm ? ( 60000.0 / rpm) : 0", {}, {}},
        IniFormulaOutputChannel{"strokeMultipler", "twoStroke == 1 ? 1 : 2", {}, {}},
        IniFormulaOutputChannel{"cycleTime", "revolutionTime * strokeMultipler", {}, {}},
    };
    ValueMap snap{{"rpm", 6000.0}, {"twoStroke", 0.0}};
    enrich(snap, formulas);
    CHECK(snap.at("revolutionTime") == 10.0);
    CHECK(snap.at("strokeMultipler") == 2.0);
    CHECK(snap.at("cycleTime") == 20.0);
}

// ---------------------------------------------------------------------------
// Production INI integration — sub-slice 87 app wiring oracle
// ---------------------------------------------------------------------------

namespace {
std::filesystem::path find_production_ini_for_eval() {
    const char* paths[] = {
        "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
    };
    for (const char* p : paths)
        if (std::filesystem::exists(p)) return p;
    return {};
}
}  // namespace

TEST_CASE("production INI formula channels enrich a mock snapshot cleanly") {
    // This is the C++ counterpart of
    // tests/unit/test_runtime_formula_enrichment.py's SessionService
    // end-to-end test. It proves that loading the production INI, feeding
    // `enrich` a realistic mock snapshot, and reading out a handful of
    // computed channels yields expected values — the same pipeline the
    // Qt `tuner_app.exe` LIVE tab exercises via build_live_tab.
    auto ini_path = find_production_ini_for_eval();
    if (ini_path.empty()) return;  // Skip when fixtures aren't present.

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    REQUIRE(def.output_channels.formula_channels.size() >= 30);

    // Synthetic mock snapshot — matches what the Python parity test seeds.
    ValueMap snap{
        {"coolantRaw", 90.0}, {"iatRaw", 60.0}, {"fuelTempRaw", 45.0},
        {"timeNow", 12345.0}, {"secl", 67.0},
        {"fuelPressure", 300.0}, {"oilPressure", 450.0},
        {"tps", 42.0}, {"rpm", 3000.0}, {"twoStroke", 0.0}, {"nSquirts", 2.0},
        {"pinLayout", 2.0}, {"nCylinders", 6.0}, {"stagingEnabled", 0.0},
        {"pulseWidth", 5000.0}, {"pulseWidth3", 0.0},
        {"boostCutFuel", 0.0}, {"boostCutSpark", 0.0},
        {"afr", 14.7}, {"afrTarget", 14.7}, {"stoich", 14.7},
        {"map", 95.0}, {"baro", 101.0}, {"loopsPerSecond", 4000.0},
        {"reqFuel", 12.3}, {"battVCorMode", 0.0}, {"batCorrection", 100.0},
        {"injOpen", 980.0}, {"ASECurr", 0.0}, {"multiplyMAP", 1.0}, {"vss", 50.0},
        {"algorithm", 0.0}, {"ignAlgorithm", 0.0}, {"fuel2Algorithm", 0.0},
        {"spark2Algorithm", 0.0}, {"spark2Mode", 0.0}, {"vvtLoadSource", 0.0},
        {"wmiMode", 0.0}, {"iacAlgorithm", 0.0}, {"boostType", 0.0},
        {"CLIdleTarget", 900.0}, {"halfSync", 1.0}, {"sync", 1.0},
        {"enable_secondarySerial", 1.0}, {"secondarySerialProtocol", 2.0},
        {"ignLoad", 0.0},
    };
    ArrayMap arrays = def.output_channels.arrays;

    enrich(snap, def.output_channels.formula_channels, &arrays);

    // Spot-check: throttle = tps
    CHECK(snap.at("throttle") == 42.0);
    // lambda = afr / stoich
    CHECK(snap.at("lambda") == 1.0);
    // revolutionTime = rpm ? 60000 / rpm : 0
    CHECK(snap.at("revolutionTime") == doctest::Approx(20.0));  // 60000/3000 = 20 ms
    // map_psi = (map - baro) * 0.145038 = (95 - 101) * 0.145038
    CHECK(snap.at("map_psi") == doctest::Approx((95.0 - 101.0) * 0.145038));
    // coolant = (coolantRaw - 40) * 1.8 + 32 → 90 → 122
    CHECK(snap.at("coolant") == doctest::Approx(122.0));
    // Every formula channel evaluated to a finite double.
    for (const auto& f : def.output_channels.formula_channels) {
        auto it = snap.find(f.name);
        REQUIRE(it != snap.end());
        CHECK(std::isfinite(it->second));
    }
}

TEST_CASE("production map_vacboost unary minus") {
    // map_vacboost = map < baro ? -map_inhg : map_psi
    std::vector<IniFormulaOutputChannel> formulas{
        IniFormulaOutputChannel{"map_inhg", "(baro - map) * 0.2953007", {}, {}},
        IniFormulaOutputChannel{"map_psi",  "(map - baro) * 0.145038",  {}, {}},
        IniFormulaOutputChannel{"map_vacboost", "map < baro ? -map_inhg : map_psi", {}, {}},
    };
    // Boost case
    auto high = compute_all(formulas, ValueMap{{"map", 200.0}, {"baro", 100.0}});
    CHECK(high["map_psi"] > 0.0);
    CHECK(high["map_vacboost"] == high["map_psi"]);
    // Vacuum case — map_inhg is positive, flipped negative by unary minus
    auto low = compute_all(formulas, ValueMap{{"map", 50.0}, {"baro", 100.0}});
    CHECK(low["map_inhg"] > 0.0);
    CHECK(low["map_vacboost"] == -low["map_inhg"]);
}
