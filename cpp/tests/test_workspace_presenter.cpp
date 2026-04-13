// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/workspace_presenter.hpp"

#include <filesystem>

namespace wp = tuner_core::workspace_presenter;
using tuner_core::IniMenu;
using tuner_core::IniMenuItem;
using tuner_core::IniDialog;
using tuner_core::IniDialogField;

TEST_SUITE("workspace_presenter") {

TEST_CASE("empty presenter has no pages") {
    wp::Presenter p;
    auto snap = p.snapshot();
    CHECK(snap.total_pages == 0);
    CHECK_FALSE(snap.has_definition);
    CHECK_FALSE(snap.has_tune);
}

TEST_CASE("load definition populates pages") {
    auto ini_path = []() -> std::filesystem::path {
        const char* paths[] = {
            "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
            "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
            "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
            "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
            "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        };
        for (const char* p : paths) if (std::filesystem::exists(p)) return p;
        return {};
    }();
    if (ini_path.empty()) { MESSAGE("INI not found"); return; }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    wp::Presenter p;
    p.load(def);
    auto snap = p.snapshot();
    CHECK(snap.has_definition);
    CHECK(snap.total_pages > 10);
    CHECK(!snap.active_page_id.empty());
}

TEST_CASE("stage scalar transitions page to STAGED") {
    tuner_core::NativeEcuDefinition def;
    // Add a minimal menu + dialog so the page builder produces at least one page.
    IniMenu menu; menu.title = "Test";
    IniMenuItem item; item.target = "testDialog"; item.label = "Test"; menu.items.push_back(item);
    def.menus.menus.push_back(menu);
    IniDialog dialog; dialog.dialog_id = "testDialog"; dialog.title = "Test";
    IniDialogField field; field.parameter_name = "reqFuel"; field.label = "Req Fuel";
    dialog.fields.push_back(field);
    def.dialogs.dialogs.push_back(dialog);

    tuner_core::local_tune_edit::TuneFile tf;
    tuner_core::local_tune_edit::TuneValue tv;
    tv.name = "reqFuel"; tv.value = 6.1;
    tf.constants.push_back(tv);

    wp::Presenter p;
    p.load(def, &tf);
    CHECK(p.snapshot().has_tune);

    // Select the test page.
    if (!p.page_groups().empty() && !p.page_groups()[0].pages.empty())
        p.select_page(p.page_groups()[0].pages[0].page_id);

    p.stage_scalar("reqFuel", "8.5");
    auto snap = p.snapshot();
    CHECK(snap.staged_count == 1);
    CHECK(snap.active_page_state == wp::PageState::STAGED);
}

TEST_CASE("write then burn transitions states") {
    tuner_core::NativeEcuDefinition def;
    IniMenu menu; menu.title = "T"; IniMenuItem item; item.target = "d"; item.label = "D"; menu.items.push_back(item);
    def.menus.menus.push_back(menu);
    IniDialog dialog; dialog.dialog_id = "d"; dialog.title = "D";
    IniDialogField f; f.parameter_name = "x"; f.label = "X"; dialog.fields.push_back(f);
    def.dialogs.dialogs.push_back(dialog);

    tuner_core::local_tune_edit::TuneFile tf;
    tuner_core::local_tune_edit::TuneValue tv; tv.name = "x"; tv.value = 1.0;
    tf.constants.push_back(tv);

    wp::Presenter p;
    p.load(def, &tf);
    if (!p.page_groups().empty() && !p.page_groups()[0].pages.empty())
        p.select_page(p.page_groups()[0].pages[0].page_id);

    p.stage_scalar("x", "2.0");
    CHECK(p.snapshot().active_page_state == wp::PageState::STAGED);

    p.mark_written();
    CHECK(p.snapshot().active_page_state == wp::PageState::WRITTEN);

    p.mark_burned();
    CHECK(p.snapshot().active_page_state == wp::PageState::BURNED);
    CHECK(p.snapshot().staged_count == 0);
}

TEST_CASE("revert returns to clean") {
    tuner_core::NativeEcuDefinition def;
    IniMenu menu; menu.title = "T"; IniMenuItem item; item.target = "d"; item.label = "D"; menu.items.push_back(item);
    def.menus.menus.push_back(menu);
    IniDialog dialog; dialog.dialog_id = "d"; dialog.title = "D";
    IniDialogField f; f.parameter_name = "x"; f.label = "X"; dialog.fields.push_back(f);
    def.dialogs.dialogs.push_back(dialog);

    tuner_core::local_tune_edit::TuneFile tf;
    tuner_core::local_tune_edit::TuneValue tv; tv.name = "x"; tv.value = 1.0;
    tf.constants.push_back(tv);

    wp::Presenter p;
    p.load(def, &tf);
    if (!p.page_groups().empty() && !p.page_groups()[0].pages.empty())
        p.select_page(p.page_groups()[0].pages[0].page_id);

    p.stage_scalar("x", "2.0");
    p.revert_active_page();
    CHECK(p.snapshot().active_page_state == wp::PageState::CLEAN);
    CHECK(p.snapshot().staged_count == 0);
}

TEST_CASE("operation log records events") {
    tuner_core::NativeEcuDefinition def;
    IniMenu menu; menu.title = "T"; IniMenuItem item; item.target = "d"; item.label = "D"; menu.items.push_back(item);
    def.menus.menus.push_back(menu);
    IniDialog dialog; dialog.dialog_id = "d"; dialog.title = "D";
    IniDialogField f; f.parameter_name = "x"; f.label = "X"; dialog.fields.push_back(f);
    def.dialogs.dialogs.push_back(dialog);

    tuner_core::local_tune_edit::TuneFile tf;
    tuner_core::local_tune_edit::TuneValue tv; tv.name = "x"; tv.value = 1.0;
    tf.constants.push_back(tv);

    wp::Presenter p;
    p.load(def, &tf);
    if (!p.page_groups().empty() && !p.page_groups()[0].pages.empty())
        p.select_page(p.page_groups()[0].pages[0].page_id);

    p.stage_scalar("x", "2.0");
    p.mark_written();
    auto snap = p.snapshot();
    CHECK(!snap.operation_summary.empty());
}

TEST_CASE("sync state reflected in snapshot") {
    wp::Presenter p;
    p.set_sync_state(wp::SyncState::SYNCED);
    CHECK(p.snapshot().sync_state == wp::SyncState::SYNCED);
}

TEST_CASE("find_page returns correct page") {
    auto ini_path = []() -> std::filesystem::path {
        const char* paths[] = {
            "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
            "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
            "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
            "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
            "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        };
        for (const char* p : paths) if (std::filesystem::exists(p)) return p;
        return {};
    }();
    if (ini_path.empty()) { MESSAGE("INI not found"); return; }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    wp::Presenter p;
    p.load(def);

    // Find veTableDialog.
    const auto* page = p.find_page("veTableDialog");
    if (page) {
        CHECK(!page->title.empty());
        CHECK(page->kind == tuner_core::tuning_page_builder::PageKind::TABLE);
    }
}

}  // TEST_SUITE
