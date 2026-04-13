// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/operator_engine_context.hpp"

#include <string>

namespace oec = tuner_core::operator_engine_context;
using tuner_core::generator_types::CalibrationIntent;
using tuner_core::generator_types::ForcedInductionTopology;
using tuner_core::ve_table_generator::SuperchargerType;

TEST_SUITE("operator_engine_context") {

TEST_CASE("default context has all-none fields") {
    oec::ContextService svc;
    const auto& c = svc.get();
    CHECK_FALSE(c.displacement_cc.has_value());
    CHECK_FALSE(c.cylinder_count.has_value());
    CHECK_FALSE(c.compression_ratio.has_value());
    CHECK(c.head_flow_class.empty());
    CHECK(c.calibration_intent == CalibrationIntent::FIRST_START);
    CHECK(c.forced_induction_topology == ForcedInductionTopology::NA);
    CHECK_FALSE(c.supercharger_type.has_value());
    CHECK(c.intercooler_present == false);
}

TEST_CASE("update changes specified fields only") {
    oec::ContextService svc;
    oec::ContextService::UpdateFields f;
    f.displacement_cc = 2998.0;
    f.cylinder_count = 6;
    f.calibration_intent = CalibrationIntent::DRIVABLE_BASE;
    const auto& c = svc.update(f);
    CHECK(c.displacement_cc.value() == doctest::Approx(2998.0));
    CHECK(c.cylinder_count.value() == 6);
    CHECK(c.calibration_intent == CalibrationIntent::DRIVABLE_BASE);
    // Unset fields remain default.
    CHECK_FALSE(c.compression_ratio.has_value());
    CHECK(c.head_flow_class.empty());
}

TEST_CASE("update can set topology and supercharger type") {
    oec::ContextService svc;
    oec::ContextService::UpdateFields f;
    f.forced_induction_topology = ForcedInductionTopology::SINGLE_TURBO;
    f.supercharger_type = std::optional<SuperchargerType>(std::nullopt);
    f.boost_target_kpa = 200.0;
    f.intercooler_present = true;
    const auto& c = svc.update(f);
    CHECK(c.forced_induction_topology == ForcedInductionTopology::SINGLE_TURBO);
    CHECK_FALSE(c.supercharger_type.has_value());
    CHECK(c.boost_target_kpa.value() == doctest::Approx(200.0));
    CHECK(c.intercooler_present == true);
}

TEST_CASE("clear resets to defaults") {
    oec::ContextService svc;
    oec::ContextService::UpdateFields f;
    f.displacement_cc = 5000.0;
    f.intercooler_present = true;
    svc.update(f);
    CHECK(svc.get().displacement_cc.has_value());
    svc.clear();
    CHECK_FALSE(svc.get().displacement_cc.has_value());
    CHECK(svc.get().intercooler_present == false);
}

TEST_CASE("save_json omits default fields") {
    oec::ContextService svc;
    std::string json = svc.save_json();
    // All defaults → empty JSON object "{}".
    CHECK(json.find("displacement_cc") == std::string::npos);
    CHECK(json.find("calibration_intent") == std::string::npos);
}

TEST_CASE("save_json includes non-default fields") {
    oec::ContextService svc;
    oec::ContextService::UpdateFields f;
    f.displacement_cc = 2998.0;
    f.calibration_intent = CalibrationIntent::DRIVABLE_BASE;
    f.forced_induction_topology = ForcedInductionTopology::SINGLE_TURBO;
    f.supercharger_type = SuperchargerType::TWIN_SCREW;
    f.intercooler_present = true;
    svc.update(f);
    std::string json = svc.save_json();
    CHECK(json.find("2998") != std::string::npos);
    CHECK(json.find("drivable_base") != std::string::npos);
    CHECK(json.find("single_turbo") != std::string::npos);
    CHECK(json.find("twin_screw") != std::string::npos);
    CHECK(json.find("intercooler_present") != std::string::npos);
}

TEST_CASE("load_json restores saved state") {
    oec::ContextService svc1;
    oec::ContextService::UpdateFields f;
    f.displacement_cc = 4600.0;
    f.cylinder_count = 8;
    f.compression_ratio = 10.5;
    f.cam_duration_deg = 280.0;
    f.head_flow_class = "race_ported";
    f.calibration_intent = CalibrationIntent::DRIVABLE_BASE;
    f.forced_induction_topology = ForcedInductionTopology::TWIN_TURBO_COMPOUND;
    f.boost_target_kpa = 250.0;
    f.intercooler_present = true;
    f.compressor_ar = 0.82;
    svc1.update(f);

    std::string json = svc1.save_json();

    oec::ContextService svc2;
    svc2.load_json(json);
    const auto& c = svc2.get();
    CHECK(c.displacement_cc.value() == doctest::Approx(4600.0));
    CHECK(c.cylinder_count.value() == 8);
    CHECK(c.compression_ratio.value() == doctest::Approx(10.5));
    CHECK(c.cam_duration_deg.value() == doctest::Approx(280.0));
    CHECK(c.head_flow_class == "race_ported");
    CHECK(c.calibration_intent == CalibrationIntent::DRIVABLE_BASE);
    CHECK(c.forced_induction_topology == ForcedInductionTopology::TWIN_TURBO_COMPOUND);
    CHECK(c.boost_target_kpa.value() == doctest::Approx(250.0));
    CHECK(c.intercooler_present == true);
    CHECK(c.compressor_ar.value() == doctest::Approx(0.82));
}

TEST_CASE("load_json ignores invalid JSON") {
    oec::ContextService svc;
    oec::ContextService::UpdateFields f;
    f.displacement_cc = 1000.0;
    svc.update(f);
    svc.load_json("NOT VALID JSON!!");
    // Should keep existing state.
    CHECK(svc.get().displacement_cc.value() == doctest::Approx(1000.0));
}

TEST_CASE("load_json ignores non-object root") {
    oec::ContextService svc;
    oec::ContextService::UpdateFields f;
    f.displacement_cc = 1000.0;
    svc.update(f);
    svc.load_json("[1, 2, 3]");
    CHECK(svc.get().displacement_cc.value() == doctest::Approx(1000.0));
}

TEST_CASE("load_json handles unknown keys gracefully") {
    oec::ContextService svc;
    svc.load_json(R"({"displacement_cc": 3000, "unknown_field": 42})");
    CHECK(svc.get().displacement_cc.value() == doctest::Approx(3000.0));
}

TEST_CASE("supercharger type round-trips through JSON") {
    for (auto sc : {SuperchargerType::ROOTS, SuperchargerType::TWIN_SCREW, SuperchargerType::CENTRIFUGAL}) {
        oec::ContextService svc;
        oec::ContextService::UpdateFields f;
        f.supercharger_type = sc;
        svc.update(f);
        std::string json = svc.save_json();
        oec::ContextService svc2;
        svc2.load_json(json);
        REQUIRE(svc2.get().supercharger_type.has_value());
        CHECK(svc2.get().supercharger_type.value() == sc);
    }
}

}  // TEST_SUITE
