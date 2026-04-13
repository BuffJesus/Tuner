// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::definition_layout — forty-seventh sub-slice.

#include <doctest.h>

#include "tuner_core/definition_layout.hpp"
#include "tuner_core/ecu_definition_compiler.hpp"

#include <fstream>
#include <string>
#include <vector>

namespace dl = tuner_core::definition_layout;
namespace tc = tuner_core;

// -----------------------------------------------------------------------
// Helper: build minimal INI sections for testing.
// -----------------------------------------------------------------------

static tc::IniMenuSection make_menu(
    std::initializer_list<std::pair<const char*, std::vector<tc::IniMenuItem>>> menus) {
    tc::IniMenuSection sec;
    for (auto& [title, items] : menus) {
        tc::IniMenu m;
        m.title = title;
        m.items = items;
        sec.menus.push_back(m);
    }
    return sec;
}

static tc::IniMenuItem item(const char* target, const char* label = nullptr) {
    tc::IniMenuItem i;
    i.target = target;
    if (label) i.label = label;
    return i;
}

// -----------------------------------------------------------------------
// 1. Empty input → empty pages
// -----------------------------------------------------------------------
TEST_CASE("layout: empty input produces empty pages") {
    auto pages = dl::compile_pages({}, {}, {});
    CHECK(pages.empty());
}

// -----------------------------------------------------------------------
// 2. Menu item pointing to table editor → table page
// -----------------------------------------------------------------------
TEST_CASE("layout: menu item to table editor creates table page") {
    auto menus = make_menu({{"&Tuning", {item("veTable1Tbl", "VE Table")}}});
    tc::IniTableEditorSection editors;
    tc::IniTableEditor ed;
    ed.table_id = "veTable1Tbl";
    editors.editors.push_back(ed);

    auto pages = dl::compile_pages(menus, {}, editors);
    REQUIRE(pages.size() == 1);
    CHECK(pages[0].target == "veTable1Tbl");
    CHECK(pages[0].title == "VE Table");
    CHECK(pages[0].table_editor_id == "veTable1Tbl");
    CHECK(pages[0].group_title == "Tuning");
}

// -----------------------------------------------------------------------
// 3. Menu item pointing to dialog with fields → scalar page
// -----------------------------------------------------------------------
TEST_CASE("layout: menu item to dialog creates scalar page") {
    auto menus = make_menu({{"&Settings", {item("fuelDialog", "Fuel Settings")}}});
    tc::IniDialogSection dialogs;
    tc::IniDialog d;
    d.dialog_id = "fuelDialog";
    d.title = "Fuel";
    tc::IniDialogField f;
    f.label = "Required Fuel";
    f.parameter_name = "reqFuel";
    d.fields.push_back(f);
    dialogs.dialogs.push_back(d);

    auto pages = dl::compile_pages(menus, dialogs, {});
    REQUIRE(pages.size() == 1);
    CHECK(pages[0].target == "fuelDialog");
    CHECK(pages[0].title == "Fuel Settings");
    CHECK(pages[0].table_editor_id.empty());
    REQUIRE(pages[0].sections.size() == 1);
    CHECK(pages[0].sections[0].fields.size() == 1);
    CHECK(pages[0].sections[0].fields[0].parameter_name == "reqFuel");
}

// -----------------------------------------------------------------------
// 4. Dialog with nested panel referencing a table editor
// -----------------------------------------------------------------------
TEST_CASE("layout: dialog with table editor panel ref") {
    auto menus = make_menu({{"&Tuning", {item("veTableDialog", "VE Table")}}});
    tc::IniDialogSection dialogs;
    tc::IniDialog d;
    d.dialog_id = "veTableDialog";
    d.title = "VE Table";
    tc::IniDialogPanelRef p;
    p.target = "veTable1Tbl";
    d.panels.push_back(p);
    dialogs.dialogs.push_back(d);

    tc::IniTableEditorSection editors;
    tc::IniTableEditor ed;
    ed.table_id = "veTable1Tbl";
    editors.editors.push_back(ed);

    auto pages = dl::compile_pages(menus, dialogs, editors);
    REQUIRE(pages.size() == 1);
    CHECK(pages[0].table_editor_id == "veTable1Tbl");
}

// -----------------------------------------------------------------------
// 5. Duplicate targets are deduplicated
// -----------------------------------------------------------------------
TEST_CASE("layout: duplicate targets are deduplicated") {
    auto menus = make_menu({
        {"&Tuning", {item("d1", "Page 1"), item("d1", "Page 1 again")}},
    });
    tc::IniDialogSection dialogs;
    tc::IniDialog d;
    d.dialog_id = "d1";
    d.title = "D1";
    tc::IniDialogField f;
    f.label = "F";
    f.parameter_name = "p";
    d.fields.push_back(f);
    dialogs.dialogs.push_back(d);

    auto pages = dl::compile_pages(menus, dialogs, {});
    CHECK(pages.size() == 1);
}

// -----------------------------------------------------------------------
// 6. Menu item with unknown target is skipped
// -----------------------------------------------------------------------
TEST_CASE("layout: unknown target skipped") {
    auto menus = make_menu({{"&Test", {item("nonExistent")}}});
    auto pages = dl::compile_pages(menus, {}, {});
    CHECK(pages.empty());
}

// -----------------------------------------------------------------------
// 7. Nested dialog recursion with cycle detection
// -----------------------------------------------------------------------
TEST_CASE("layout: circular panel reference does not infinite loop") {
    auto menus = make_menu({{"&Test", {item("d1")}}});
    tc::IniDialogSection dialogs;
    tc::IniDialog d1;
    d1.dialog_id = "d1";
    d1.title = "D1";
    tc::IniDialogField f;
    f.label = "F";
    f.parameter_name = "p";
    d1.fields.push_back(f);
    tc::IniDialogPanelRef p;
    p.target = "d1";  // self-reference!
    d1.panels.push_back(p);
    dialogs.dialogs.push_back(d1);

    auto pages = dl::compile_pages(menus, dialogs, {});
    REQUIRE(pages.size() == 1);
    // Should have exactly one section (from the first visit), no infinite recursion.
    CHECK(pages[0].sections.size() == 1);
}

// -----------------------------------------------------------------------
// 8. Group ID normalization
// -----------------------------------------------------------------------
TEST_CASE("layout: group ID normalized") {
    auto menus = make_menu({{"&Engine Setup!", {item("d1")}}});
    tc::IniDialogSection dialogs;
    tc::IniDialog d;
    d.dialog_id = "d1";
    d.title = "D";
    tc::IniDialogField f;
    f.label = "F";
    f.parameter_name = "p";
    d.fields.push_back(f);
    dialogs.dialogs.push_back(d);

    auto pages = dl::compile_pages(menus, dialogs, {});
    REQUIRE(pages.size() == 1);
    CHECK(pages[0].group_id == "engine-setup");
}

// -----------------------------------------------------------------------
// 9. Static text fields become notes
// -----------------------------------------------------------------------
TEST_CASE("layout: static text fields become notes") {
    auto menus = make_menu({{"&Test", {item("d1")}}});
    tc::IniDialogSection dialogs;
    tc::IniDialog d;
    d.dialog_id = "d1";
    d.title = "D";
    tc::IniDialogField text_f;
    text_f.label = "Important note";
    text_f.is_static_text = true;
    d.fields.push_back(text_f);
    tc::IniDialogField param_f;
    param_f.label = "Param";
    param_f.parameter_name = "p1";
    d.fields.push_back(param_f);
    dialogs.dialogs.push_back(d);

    auto pages = dl::compile_pages(menus, dialogs, {});
    REQUIRE(pages.size() == 1);
    REQUIRE(pages[0].sections.size() == 1);
    CHECK(pages[0].sections[0].notes.size() == 1);
    CHECK(pages[0].sections[0].notes[0] == "Important note");
    CHECK(pages[0].sections[0].fields.size() == 1);
}

// -----------------------------------------------------------------------
// 10. Production INI integration
// -----------------------------------------------------------------------
TEST_CASE("layout: production INI compiles pages") {
    const char* candidates[] = {
        "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
    };
    std::string path;
    for (const char* c : candidates) {
        std::ifstream test(c);
        if (test.good()) { path = c; break; }
    }
    if (path.empty()) return;

    auto def = tc::compile_ecu_definition_file(path);
    auto pages = dl::compile_pages(def.menus, def.dialogs, def.table_editors);

    // Should produce a substantial number of pages.
    CHECK(pages.size() > 10);

    // Known pages should exist.
    bool found_ve = false, found_table = false;
    for (const auto& p : pages) {
        if (p.target == "veTableDialog") found_ve = true;
        if (!p.table_editor_id.empty()) found_table = true;
    }
    CHECK(found_ve);
    CHECK(found_table);
}
