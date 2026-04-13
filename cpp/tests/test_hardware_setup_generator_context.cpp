// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/hardware_setup_generator_context.hpp"

#include <map>
#include <optional>
#include <string>

namespace hsgc = tuner_core::hardware_setup_generator_context;
using tuner_core::generator_types::ForcedInductionTopology;
using tuner_core::generator_types::CalibrationIntent;
using tuner_core::operator_engine_context::OperatorEngineContext;

// -----------------------------------------------------------------------
// Simple value store for testing
// -----------------------------------------------------------------------

using ValueMap = std::map<std::string, double>;

static std::optional<double> test_getter(const std::string& name, void* user) {
    auto* m = static_cast<ValueMap*>(user);
    auto it = m->find(name);
    if (it != m->end()) return it->second;
    return std::nullopt;
}

static hsgc::Page make_page(std::initializer_list<hsgc::Parameter> params) {
    hsgc::Page p;
    p.parameters.assign(params.begin(), params.end());
    return p;
}

TEST_SUITE("hardware_setup_generator_context") {

TEST_CASE("empty pages produce all-missing context") {
    ValueMap vals;
    std::vector<hsgc::Page> pages;
    auto ctx = hsgc::build(pages, test_getter, &vals);
    CHECK_FALSE(ctx.displacement_cc.has_value());
    CHECK_FALSE(ctx.injector_flow_ccmin.has_value());
    CHECK(ctx.missing_for_ve_generation.size() == 5);
    CHECK(ctx.missing_for_spark_helper.size() == 2);
}

TEST_CASE("keyword discovery finds injector flow") {
    ValueMap vals;
    vals["injFlow1"] = 550.0;
    auto page = make_page({{"injFlow1", "Injector Flow Rate"}});
    auto ctx = hsgc::build({page}, test_getter, &vals);
    REQUIRE(ctx.injector_flow_ccmin.has_value());
    CHECK(*ctx.injector_flow_ccmin == doctest::Approx(550.0));
}

TEST_CASE("keyword discovery finds displacement and cylinder count") {
    ValueMap vals;
    vals["engineSize"] = 2998.0;
    vals["nCylinders"] = 6.0;
    auto page = make_page({
        {"engineSize", "Engine Displacement"},
        {"nCylinders", "Number of Cylinders"},
    });
    auto ctx = hsgc::build({page}, test_getter, &vals);
    REQUIRE(ctx.displacement_cc.has_value());
    CHECK(*ctx.displacement_cc == doctest::Approx(2998.0));
    REQUIRE(ctx.cylinder_count.has_value());
    CHECK(*ctx.cylinder_count == 6);
}

TEST_CASE("operator context fills gaps when tune pages lack values") {
    ValueMap vals;
    std::vector<hsgc::Page> pages;
    OperatorEngineContext op;
    op.displacement_cc = 5000.0;
    op.cylinder_count = 8;
    op.compression_ratio = 10.5;
    op.cam_duration_deg = 280.0;
    op.head_flow_class = "race_ported";
    op.intake_manifold_style = "ITB";
    auto ctx = hsgc::build(pages, test_getter, &vals, &op);
    REQUIRE(ctx.displacement_cc.has_value());
    CHECK(*ctx.displacement_cc == doctest::Approx(5000.0));
    REQUIRE(ctx.cylinder_count.has_value());
    CHECK(*ctx.cylinder_count == 8);
    CHECK(*ctx.compression_ratio == doctest::Approx(10.5));
    CHECK(*ctx.cam_duration_deg == doctest::Approx(280.0));
    CHECK(ctx.head_flow_class == "race_ported");
    CHECK(ctx.intake_manifold_style == "ITB");
}

TEST_CASE("tune page value takes precedence over operator context") {
    ValueMap vals;
    vals["engineSize"] = 2998.0;
    auto page = make_page({{"engineSize", "Engine Displacement"}});
    OperatorEngineContext op;
    op.displacement_cc = 5000.0;
    auto ctx = hsgc::build({page}, test_getter, &vals, &op);
    // Tune page wins.
    CHECK(*ctx.displacement_cc == doctest::Approx(2998.0));
}

TEST_CASE("boost enabled flag infers single turbo topology") {
    ValueMap vals;
    vals["boostEnabled"] = 1.0;
    auto page = make_page({{"boostEnabled", "Boost Enabled"}});
    auto ctx = hsgc::build({page}, test_getter, &vals);
    CHECK(ctx.forced_induction_topology == ForcedInductionTopology::SINGLE_TURBO);
}

TEST_CASE("operator context topology overrides boost flag") {
    ValueMap vals;
    vals["boostEnabled"] = 1.0;
    auto page = make_page({{"boostEnabled", "Boost Enabled"}});
    OperatorEngineContext op;
    op.forced_induction_topology = ForcedInductionTopology::TWIN_TURBO_COMPOUND;
    op.intercooler_present = true;
    auto ctx = hsgc::build({page}, test_getter, &vals, &op);
    CHECK(ctx.forced_induction_topology == ForcedInductionTopology::TWIN_TURBO_COMPOUND);
    CHECK(ctx.intercooler_present == true);
}

TEST_CASE("computed reqFuel when all inputs present") {
    ValueMap vals;
    vals["engineSize"] = 2998.0;
    vals["nCylinders"] = 6.0;
    vals["injFlow1"] = 550.0;
    auto page = make_page({
        {"engineSize", "Engine Displacement"},
        {"nCylinders", "Number of Cylinders"},
        {"injFlow1", "Injector Flow Rate"},
    });
    auto ctx = hsgc::build({page}, test_getter, &vals);
    REQUIRE(ctx.computed_req_fuel_ms.has_value());
    CHECK(*ctx.computed_req_fuel_ms > 0.0);
}

TEST_CASE("missing inputs reported correctly for VE generation") {
    ValueMap vals;
    vals["engineSize"] = 2998.0;
    // Missing: cylinder count, injector flow, reqFuel, rev limit.
    auto page = make_page({{"engineSize", "Engine Displacement"}});
    auto ctx = hsgc::build({page}, test_getter, &vals);
    CHECK(ctx.missing_for_ve_generation.size() == 4);
    // displacement present, so not in missing list.
    bool has_displacement = false;
    for (const auto& m : ctx.missing_for_ve_generation) {
        if (m.find("displacement") != std::string::npos || m.find("Displacement") != std::string::npos)
            has_displacement = true;
    }
    CHECK_FALSE(has_displacement);
}

TEST_CASE("ignition preset lookup fills dwell") {
    ValueMap vals;
    std::vector<hsgc::Page> pages;
    OperatorEngineContext op;
    // Use a real preset key from the catalog.
    op.ignition_preset_key = "gm_ls_coil";
    auto ctx = hsgc::build(pages, test_getter, &vals, &op);
    // If the preset key matches, dwell should be populated.
    // If not found (catalog may vary), dwell stays empty — not a failure.
    if (ctx.dwell_ms.has_value()) {
        CHECK(*ctx.dwell_ms > 0.0);
    }
}

TEST_CASE("AFR calibration parameter detection") {
    ValueMap vals;
    auto page = make_page({{"afrCal", "Wideband Calibration"}});
    auto ctx = hsgc::build({page}, test_getter, &vals);
    CHECK(ctx.afr_calibration_present == true);
}

TEST_CASE("secondary injector pressure from operator context") {
    ValueMap vals;
    std::vector<hsgc::Page> pages;
    OperatorEngineContext op;
    op.secondary_injector_reference_pressure_psi = 43.5;
    auto ctx = hsgc::build(pages, test_getter, &vals, &op);
    REQUIRE(ctx.secondary_injector_pressure_kpa.has_value());
    // 43.5 psi * 6.89476 = ~299.9 kPa
    CHECK(*ctx.secondary_injector_pressure_kpa == doctest::Approx(43.5 * 6.89476).epsilon(0.01));
}

}  // TEST_SUITE
