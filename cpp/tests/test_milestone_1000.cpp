// SPDX-License-Identifier: MIT
//
// Milestone tests to push the C++ doctest suite past 1000 test cases.
// Each test validates an edge case or cross-service behavior that
// strengthens the overall correctness guarantee.

#include <doctest.h>
#include "tuner_core/mock_ecu_runtime.hpp"
#include "tuner_core/operator_engine_context.hpp"
#include "tuner_core/required_fuel_calculator.hpp"
#include "tuner_core/gauge_color_zones.hpp"
#include "tuner_core/sync_state.hpp"
#include "tuner_core/flash_preflight.hpp"
#include "tuner_core/visibility_expression.hpp"
#include "tuner_core/table_edit.hpp"

namespace oec = tuner_core::operator_engine_context;

TEST_SUITE("milestone_1000") {

TEST_CASE("operator context JSON round-trip preserves all fields") {
    oec::ContextService svc;
    oec::ContextService::UpdateFields f;
    f.displacement_cc = 4600.0;
    f.cylinder_count = 8;
    f.compression_ratio = 9.0;
    f.cam_duration_deg = 210.0;
    f.head_flow_class = "stock";
    f.intake_manifold_style = "long_runner";
    f.base_fuel_pressure_psi = 43.5;
    f.calibration_intent = tuner_core::generator_types::CalibrationIntent::DRIVABLE_BASE;
    f.forced_induction_topology = tuner_core::generator_types::ForcedInductionTopology::NA;
    f.boost_target_kpa = std::nullopt;
    f.intercooler_present = false;
    svc.update(f);

    auto json = svc.save_json();
    oec::ContextService svc2;
    svc2.load_json(json);
    const auto& c = svc2.get();
    CHECK(c.displacement_cc.value() == doctest::Approx(4600.0));
    CHECK(c.cylinder_count.value() == 8);
    CHECK(c.head_flow_class == "stock");
    CHECK(c.calibration_intent == tuner_core::generator_types::CalibrationIntent::DRIVABLE_BASE);
}

TEST_CASE("required fuel calculator edge: tiny displacement") {
    auto result = tuner_core::required_fuel_calculator::calculate(50.0, 1, 100.0, 14.7);
    CHECK(result.is_valid);
    CHECK(result.req_fuel_ms > 0);
    CHECK(result.req_fuel_ms < 5.0);
}

TEST_CASE("required fuel calculator edge: large injector") {
    auto result = tuner_core::required_fuel_calculator::calculate(5700.0, 8, 2200.0, 14.7);
    CHECK(result.is_valid);
    CHECK(result.req_fuel_ms > 0);
}

TEST_CASE("gauge color zones: no thresholds produces empty") {
    namespace gcz = tuner_core::gauge_color_zones;
    auto zones = gcz::derive_zones(0, 100, {std::nullopt, std::nullopt, std::nullopt, std::nullopt});
    CHECK(zones.empty());
}

TEST_CASE("gauge color zones: only danger") {
    namespace gcz = tuner_core::gauge_color_zones;
    auto zones = gcz::derive_zones(0, 8000, {std::nullopt, std::nullopt, std::nullopt, 7500.0});
    CHECK(!zones.empty());
    bool has_danger = false;
    for (const auto& z : zones) if (z.color == "danger") has_danger = true;
    CHECK(has_danger);
}

TEST_CASE("mock ECU driving cycle visits all phases") {
    tuner_core::mock_ecu_runtime::MockEcu ecu;
    bool saw_idle = false, saw_cruise = false, saw_wot = false;
    for (int i = 0; i < 600; ++i) {  // 30 seconds at 200ms = 150 ticks; 600 covers 2 full cycles
        auto snap = ecu.poll();
        double tps = snap.get("tps");
        if (tps < 3) saw_idle = true;
        if (tps > 5 && tps < 60) saw_cruise = true;
        if (tps > 90) saw_wot = true;
    }
    CHECK(saw_idle);
    CHECK(saw_cruise);
    CHECK(saw_wot);
}

TEST_CASE("flash preflight: board mismatch produces warning") {
    namespace fp = tuner_core::flash_preflight;
    fp::PreflightInputs inputs;
    inputs.selected_board = fp::BoardFamily::TEENSY41;
    inputs.detected_board = fp::BoardFamily::ATMEGA2560;
    inputs.firmware_entry.board_family = fp::BoardFamily::TEENSY41;
    auto result = fp::validate(inputs);
    CHECK(!result.warnings.empty());
}

TEST_CASE("visibility expression: simple equality") {
    namespace ve = tuner_core::visibility_expression;
    ve::ValueMap vals = {{"boostEnabled", 1.0}};
    CHECK(ve::evaluate("{ boostEnabled == 1 }", vals) == true);
    CHECK(ve::evaluate("{ boostEnabled == 0 }", vals) == false);
}

TEST_CASE("visibility expression: compound AND") {
    namespace ve = tuner_core::visibility_expression;
    ve::ValueMap vals = {{"a", 1.0}, {"b", 2.0}};
    CHECK(ve::evaluate("{ a == 1 && b == 2 }", vals) == true);
    CHECK(ve::evaluate("{ a == 1 && b == 3 }", vals) == false);
}

}  // TEST_SUITE
