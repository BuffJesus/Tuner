// SPDX-License-Identifier: MIT
//
// End-to-end test: load production INI + MSQ → workspace presenter →
// stage edits → export to native .tuner + .tunerproj + .tunerdef →
// validate all three files.
//
// This is the strongest correctness signal in the C++ test suite —
// it proves the entire pipeline from legacy format ingest through
// the workspace to native format output.

#include <doctest.h>
#include "tuner_core/workspace_presenter.hpp"
#include "tuner_core/native_tune_writer.hpp"
#include "tuner_core/project_file.hpp"
#include "tuner_core/native_definition_writer.hpp"
#include "tuner_core/msq_parser.hpp"

#include <filesystem>
#include <sstream>

namespace {

std::filesystem::path find_fixture(const char* name) {
    std::string candidates[] = {
        std::string("tests/fixtures/") + name,
        std::string("../tests/fixtures/") + name,
        std::string("../../tests/fixtures/") + name,
        std::string("../../../tests/fixtures/") + name,
        std::string("D:/Documents/JetBrains/Python/Tuner/tests/fixtures/") + name,
    };
    for (const auto& p : candidates)
        if (std::filesystem::exists(p)) return p;
    return {};
}

}  // namespace

TEST_SUITE("end_to_end") {

TEST_CASE("full pipeline: INI + MSQ → presenter → stage → native export") {
    auto ini_path = find_fixture("speeduino-dropbear-v2.0.1.ini");
    auto msq_path = find_fixture("Ford300_TwinGT28_BaseStartup.msq");
    if (ini_path.empty() || msq_path.empty()) {
        MESSAGE("Production fixtures not found — skipping end-to-end");
        return;
    }

    // Step 1: Load definition.
    auto def = tuner_core::compile_ecu_definition_file(ini_path);

    // Step 2: Parse MSQ into TuneFile.
    auto msq = tuner_core::parse_msq(msq_path);
    tuner_core::local_tune_edit::TuneFile tf;
    tf.signature = msq.signature;
    for (const auto& c : msq.constants) {
        tuner_core::local_tune_edit::TuneValue tv;
        tv.name = c.name; tv.units = c.units; tv.rows = c.rows; tv.cols = c.cols;
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

    // Step 3: Load into presenter.
    namespace wp = tuner_core::workspace_presenter;
    wp::Presenter presenter;
    presenter.load(def, &tf);

    auto snap = presenter.snapshot();
    CHECK(snap.has_definition);
    CHECK(snap.has_tune);
    CHECK(snap.total_pages > 20);

    // Step 4: Navigate and stage an edit.
    auto& groups = presenter.page_groups();
    REQUIRE(!groups.empty());
    REQUIRE(!groups[0].pages.empty());
    presenter.select_page(groups[0].pages[0].page_id);

    // Find reqFuel and stage it.
    auto* rv = presenter.edit_service().get_value("reqFuel");
    if (rv && std::holds_alternative<double>(rv->value)) {
        (void)std::get<double>(rv->value);  // original value exists
        presenter.stage_scalar("reqFuel", "9.5");
        CHECK(presenter.snapshot().staged_count >= 1);

        // Verify the staged value is 9.5.
        auto* sv = presenter.edit_service().get_value("reqFuel");
        REQUIRE(sv);
        CHECK(std::get<double>(sv->value) == doctest::Approx(9.5));
    }

    // Step 5: Export to .tuner (native tune).
    namespace ntw = tuner_core::native_tune_writer;
    auto tune = ntw::from_edit_service(presenter.edit_service(), msq.signature);
    auto tune_json = ntw::export_json(tune);
    CHECK(tune_json.find("tuner-tune-v1") != std::string::npos);
    CHECK(tune_json.find(msq.signature) != std::string::npos);
    CHECK(tune.values.size() > 50);

    // Step 6: Export to .tunerproj (native project).
    namespace pf = tuner_core::project_file;
    pf::Project proj;
    proj.name = "Ford 300 Twin-GT28";
    proj.definition_path = "speeduino-202501-T41.tunerdef";
    proj.tune_path = "Ford300_TwinGT28.tuner";
    proj.firmware_signature = msq.signature;
    proj.active_settings = {"LAMBDA"};
    proj.calibration_intent = "drivable_base";
    auto proj_json = pf::export_json(proj);
    CHECK(proj_json.find("tuner-project-v1") != std::string::npos);

    // Step 7: Export to .tunerdef (native definition).
    namespace ndw = tuner_core::native_definition_writer;
    auto def_json = ndw::export_json(def, "speeduino", "202501-T41");
    CHECK(ndw::validate_json(def_json).empty());
    CHECK(def_json.find("\"scalars\"") != std::string::npos);
    CHECK(def_json.find("\"tables\"") != std::string::npos);

    // Step 8: Verify all three files reference the same firmware.
    CHECK(tune_json.find("speeduino") != std::string::npos);
    CHECK(proj_json.find("speeduino") != std::string::npos);
    CHECK(def_json.find("speeduino") != std::string::npos);

    // Step 9: Import the .tuner back and verify the staged value persisted.
    auto restored = ntw::import_json(tune_json);
    bool found_reqfuel = false;
    for (const auto& [name, val] : restored.values) {
        if (name == "reqFuel" && std::holds_alternative<double>(val)) {
            found_reqfuel = true;
            CHECK(std::get<double>(val) == doctest::Approx(9.5));
        }
    }
    if (rv) CHECK(found_reqfuel);

    // Step 10: Mark written + burned to verify full lifecycle.
    presenter.mark_written();
    CHECK(presenter.snapshot().active_page_state == wp::PageState::WRITTEN);
    presenter.mark_burned();
    CHECK(presenter.snapshot().active_page_state == wp::PageState::BURNED);
    CHECK(presenter.snapshot().staged_count == 0);
}

}  // TEST_SUITE
