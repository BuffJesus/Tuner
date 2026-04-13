// SPDX-License-Identifier: MIT
//
// Integration tests for the workspace presenter against the real
// production INI and MSQ fixtures.

#include <doctest.h>
#include "tuner_core/workspace_presenter.hpp"
#include "tuner_core/msq_parser.hpp"

#include <filesystem>
#include <sstream>

namespace wp = tuner_core::workspace_presenter;

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

TEST_SUITE("presenter_integration") {

TEST_CASE("presenter loads production INI and builds pages") {
    auto ini_path = find_ini();
    if (ini_path.empty()) { MESSAGE("INI not found"); return; }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    wp::Presenter p;
    p.load(def);

    auto snap = p.snapshot();
    CHECK(snap.has_definition);
    CHECK(snap.total_pages > 20);
    CHECK(p.page_groups().size() >= 3);
}

TEST_CASE("presenter loads INI + MSQ and reads values") {
    auto ini_path = find_ini();
    auto msq_path = find_msq();
    if (ini_path.empty() || msq_path.empty()) { MESSAGE("Fixtures not found"); return; }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    auto msq = tuner_core::parse_msq(msq_path);

    // Build a TuneFile from the MSQ.
    tuner_core::local_tune_edit::TuneFile tf;
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

    wp::Presenter p;
    p.load(def, &tf);

    auto snap = p.snapshot();
    CHECK(snap.has_definition);
    CHECK(snap.has_tune);

    // Read a known scalar value.
    auto* v = p.edit_service().get_value("reqFuel");
    if (v) CHECK(std::holds_alternative<double>(v->value));
}

TEST_CASE("presenter navigate + stage + write + burn lifecycle") {
    auto ini_path = find_ini();
    auto msq_path = find_msq();
    if (ini_path.empty() || msq_path.empty()) { MESSAGE("Fixtures not found"); return; }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    auto msq = tuner_core::parse_msq(msq_path);
    tuner_core::local_tune_edit::TuneFile tf;
    for (const auto& c : msq.constants) {
        tuner_core::local_tune_edit::TuneValue tv;
        tv.name = c.name; tv.units = c.units; tv.rows = c.rows; tv.cols = c.cols;
        try { tv.value = std::stod(c.text); } catch (...) { tv.value = c.text; }
        tf.constants.push_back(std::move(tv));
    }

    wp::Presenter p;
    p.load(def, &tf);

    // Navigate to the first page.
    auto& groups = p.page_groups();
    REQUIRE(!groups.empty());
    REQUIRE(!groups[0].pages.empty());
    p.select_page(groups[0].pages[0].page_id);

    // Stage an edit.
    p.stage_scalar("reqFuel", "9.0");
    auto s1 = p.snapshot();
    CHECK(s1.staged_count == 1);
    CHECK(s1.active_page_state == wp::PageState::STAGED);

    // Write.
    p.mark_written();
    CHECK(p.snapshot().active_page_state == wp::PageState::WRITTEN);

    // Burn.
    p.mark_burned();
    CHECK(p.snapshot().active_page_state == wp::PageState::BURNED);
    CHECK(p.snapshot().staged_count == 0);

    // Operation log should have entries.
    CHECK(!p.snapshot().operation_summary.empty());
}

TEST_CASE("presenter find_page works for VE table") {
    auto ini_path = find_ini();
    if (ini_path.empty()) { MESSAGE("INI not found"); return; }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    wp::Presenter p;
    p.load(def);

    auto* ve = p.find_page("veTableDialog");
    if (ve) {
        CHECK(!ve->title.empty());
        CHECK(ve->kind == tuner_core::tuning_page_builder::PageKind::TABLE);
        CHECK(!ve->table_name.empty());
    }
}

TEST_CASE("presenter sync state persists") {
    wp::Presenter p;
    p.set_sync_state(wp::SyncState::MISMATCH);
    CHECK(p.snapshot().sync_state == wp::SyncState::MISMATCH);
    CHECK(p.snapshot().status_text.find("mismatch") != std::string::npos);
}

}  // TEST_SUITE
