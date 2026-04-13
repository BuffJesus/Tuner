// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/native_tune_writer.hpp"
#include <stdexcept>

namespace ntw = tuner_core::native_tune_writer;

TEST_SUITE("native_tune_writer") {

TEST_CASE("export produces valid JSON") {
    ntw::TunerTune tune;
    tune.definition_signature = "speeduino 202501-T41";
    tune.created_iso = "2026-04-10T12:00:00Z";
    tune.modified_iso = "2026-04-10T13:00:00Z";
    tune.values = {{"reqFuel", 6.1}, {"nCylinders", 6.0}};
    auto json = ntw::export_json(tune);
    CHECK(json.find("tuner-tune-v1") != std::string::npos);
    CHECK(json.find("reqFuel") != std::string::npos);
    CHECK(json.find("6.1") != std::string::npos);
    CHECK(json.find("speeduino 202501-T41") != std::string::npos);
}

TEST_CASE("export with table values") {
    ntw::TunerTune tune;
    tune.values = {{"veTable", std::vector<double>{80, 82, 85, 88}}};
    auto json = ntw::export_json(tune);
    CHECK(json.find("[") != std::string::npos);
    CHECK(json.find("80") != std::string::npos);
}

TEST_CASE("export with operator context") {
    ntw::TunerTune tune;
    tuner_core::operator_engine_context::OperatorEngineContext ctx;
    ctx.displacement_cc = 2998;
    ctx.cylinder_count = 6;
    ctx.compression_ratio = 10.5;
    ctx.forced_induction_topology = tuner_core::generator_types::ForcedInductionTopology::SINGLE_TURBO;
    tune.operator_context = ctx;
    auto json = ntw::export_json(tune);
    CHECK(json.find("operator_context") != std::string::npos);
    CHECK(json.find("2998") != std::string::npos);
    CHECK(json.find("single_turbo") != std::string::npos);
}

TEST_CASE("import round-trips export") {
    ntw::TunerTune original;
    original.definition_signature = "speeduino 202501-T41";
    original.created_iso = "2026-04-10T12:00:00Z";
    original.values = {
        {"reqFuel", 6.1},
        {"nCylinders", 6.0},
        {"veTable", std::vector<double>{80, 82, 85}},
    };
    auto json = ntw::export_json(original);
    auto restored = ntw::import_json(json);
    CHECK(restored.definition_signature == "speeduino 202501-T41");
    REQUIRE(restored.values.size() == 3);
    // Find reqFuel regardless of order.
    bool found_reqfuel = false;
    for (const auto& [name, val] : restored.values) {
        if (name == "reqFuel") {
            found_reqfuel = true;
            CHECK(std::get<double>(val) == doctest::Approx(6.1));
        }
    }
    CHECK(found_reqfuel);
}

TEST_CASE("import with operator context") {
    const char* json = R"({
        "format": "tuner-tune-v1",
        "values": {"reqFuel": 8.5},
        "operator_context": {
            "displacement_cc": 5000,
            "cylinder_count": 8
        }
    })";
    auto tune = ntw::import_json(json);
    REQUIRE(tune.operator_context.has_value());
    CHECK(tune.operator_context->displacement_cc.value() == doctest::Approx(5000));
    CHECK(tune.operator_context->cylinder_count.value() == 8);
}

TEST_CASE("import rejects invalid JSON") {
    CHECK_THROWS_AS(ntw::import_json("NOT JSON"), std::invalid_argument);
}

TEST_CASE("import rejects non-object root") {
    CHECK_THROWS_AS(ntw::import_json("[1,2,3]"), std::invalid_argument);
}

TEST_CASE("from_edit_service captures scalar values") {
    tuner_core::local_tune_edit::EditService edit;
    tuner_core::local_tune_edit::TuneFile tf;
    tuner_core::local_tune_edit::TuneValue tv;
    tv.name = "reqFuel"; tv.value = 6.1;
    tf.constants.push_back(tv);
    edit.set_tune_file(&tf);
    edit.stage_scalar_value("reqFuel", "8.5");
    auto tune = ntw::from_edit_service(edit, "speeduino 202501-T41");
    CHECK(tune.definition_signature == "speeduino 202501-T41");
    // Should have at least reqFuel.
    bool found = false;
    for (const auto& [name, val] : tune.values)
        if (name == "reqFuel") found = true;
    CHECK(found);
}

}  // TEST_SUITE
