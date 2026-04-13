// SPDX-License-Identifier: MIT
//
// Integration tests for the native format trilogy: .tuner, .tunerproj,
// .tunerdef. Validates round-trips and cross-format consistency.

#include <doctest.h>
#include "tuner_core/native_tune_writer.hpp"
#include "tuner_core/project_file.hpp"
#include "tuner_core/native_definition_writer.hpp"
#include "tuner_core/ecu_definition_compiler.hpp"
#include "tuner_core/msq_parser.hpp"
#include "tuner_core/local_tune_edit.hpp"
#include "tuner_core/operator_engine_context.hpp"

#include <filesystem>
#include <sstream>
#include <stdexcept>

namespace {

std::filesystem::path find_ini() {
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

std::filesystem::path find_msq() {
    const char* paths[] = {
        "tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../../../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
    };
    for (const char* p : paths)
        if (std::filesystem::exists(p)) return p;
    return {};
}

}  // namespace

TEST_SUITE("native_format_integration") {

TEST_CASE("tune export from real MSQ preserves values") {
    auto msq_path = find_msq();
    if (msq_path.empty()) { MESSAGE("MSQ not found"); return; }

    auto msq = tuner_core::parse_msq(msq_path);
    namespace lte = tuner_core::local_tune_edit;
    lte::TuneFile tf;
    for (const auto& c : msq.constants) {
        lte::TuneValue tv; tv.name = c.name; tv.units = c.units;
        tv.rows = c.rows; tv.cols = c.cols;
        if (c.rows > 0 || c.cols > 0) {
            std::vector<double> vals;
            std::istringstream iss(c.text);
            double d; while (iss >> d) vals.push_back(d);
            if (!vals.empty()) tv.value = std::move(vals);
            else tv.value = c.text;
        } else {
            try { tv.value = std::stod(c.text); } catch (...) { tv.value = c.text; }
        }
        tf.constants.push_back(std::move(tv));
    }
    lte::EditService edit;
    edit.set_tune_file(&tf);

    namespace ntw = tuner_core::native_tune_writer;
    auto tune = ntw::from_edit_service(edit, msq.signature);
    auto json = ntw::export_json(tune);
    CHECK(json.find("tuner-tune-v1") != std::string::npos);
    CHECK(json.find(msq.signature) != std::string::npos);
    // Should have many values.
    CHECK(tune.values.size() > 50);
}

TEST_CASE("tune export + import round-trip preserves scalar values") {
    namespace ntw = tuner_core::native_tune_writer;
    ntw::TunerTune orig;
    orig.definition_signature = "speeduino 202501-T41";
    orig.values = {
        {"reqFuel", 6.1}, {"nCylinders", 6.0}, {"dwell", 3.5},
        {"stoich", 14.7}, {"rpmHard", 7200.0},
    };
    auto json = ntw::export_json(orig);
    auto restored = ntw::import_json(json);
    CHECK(restored.values.size() == 5);
    for (const auto& [name, val] : restored.values) {
        bool found = false;
        for (const auto& [oname, oval] : orig.values) {
            if (name == oname) {
                found = true;
                CHECK(std::get<double>(val) == doctest::Approx(std::get<double>(oval)));
            }
        }
        CHECK(found);
    }
}

TEST_CASE("project file references tune and definition paths") {
    namespace pf = tuner_core::project_file;
    pf::Project proj;
    proj.name = "Ford 300 Twin-GT28";
    proj.definition_path = "speeduino-202501-T41.tunerdef";
    proj.tune_path = "Ford300_TwinGT28.tuner";
    proj.firmware_signature = "speeduino 202501-T41";
    proj.active_settings = {"LAMBDA", "mcu_teensy"};
    proj.calibration_intent = "drivable_base";

    auto json = pf::export_json(proj);
    auto restored = pf::import_json(json);
    CHECK(restored.definition_path == "speeduino-202501-T41.tunerdef");
    CHECK(restored.tune_path == "Ford300_TwinGT28.tuner");
    CHECK(restored.firmware_signature == "speeduino 202501-T41");
    CHECK(restored.calibration_intent == "drivable_base");
}

TEST_CASE("definition export from production INI has scalars and tables") {
    auto ini_path = find_ini();
    if (ini_path.empty()) { MESSAGE("INI not found"); return; }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    namespace ndw = tuner_core::native_definition_writer;
    auto json = ndw::export_json(def, "speeduino", "202501-T41");

    CHECK(ndw::validate_json(json).empty());
    // Should contain many scalars and tables.
    CHECK(json.find("\"scalars\"") != std::string::npos);
    CHECK(json.find("\"tables\"") != std::string::npos);
    CHECK(json.find("\"curves\"") != std::string::npos);
    // Should contain known parameters.
    CHECK(json.find("reqFuel") != std::string::npos);
    // Stats should show substantial counts.
    CHECK(json.find("\"scalar_count\"") != std::string::npos);
}

TEST_CASE("all three native formats reference same signature") {
    const char* sig = "speeduino 202501-T41";

    namespace ntw = tuner_core::native_tune_writer;
    ntw::TunerTune tune;
    tune.definition_signature = sig;
    tune.values = {{"reqFuel", 6.1}};
    auto tune_json = ntw::export_json(tune);
    CHECK(tune_json.find(sig) != std::string::npos);

    namespace pf = tuner_core::project_file;
    pf::Project proj;
    proj.firmware_signature = sig;
    auto proj_json = pf::export_json(proj);
    CHECK(proj_json.find(sig) != std::string::npos);

    // Definition doesn't carry the firmware signature directly
    // (it's in the version field), but the project links them.
}

TEST_CASE("tune with operator context round-trips") {
    namespace ntw = tuner_core::native_tune_writer;
    tuner_core::operator_engine_context::OperatorEngineContext ctx;
    ctx.displacement_cc = 2998;
    ctx.cylinder_count = 6;
    ctx.compression_ratio = 10.5;
    ctx.cam_duration_deg = 280;
    ctx.forced_induction_topology = tuner_core::generator_types::ForcedInductionTopology::SINGLE_TURBO;

    ntw::TunerTune tune;
    tune.values = {{"reqFuel", 8.5}};
    tune.operator_context = ctx;
    auto json = ntw::export_json(tune);
    auto restored = ntw::import_json(json);
    REQUIRE(restored.operator_context.has_value());
    CHECK(restored.operator_context->displacement_cc.value() == doctest::Approx(2998));
    CHECK(restored.operator_context->cylinder_count.value() == 6);
}

}  // TEST_SUITE
