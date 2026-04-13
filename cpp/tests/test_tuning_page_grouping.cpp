// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::tuning_page_grouping — forty-eighth sub-slice.

#include <doctest.h>

#include "tuner_core/tuning_page_grouping.hpp"
#include "tuner_core/ecu_definition_compiler.hpp"

#include <fstream>
#include <string>
#include <vector>

namespace tpg = tuner_core::tuning_page_grouping;
namespace dl = tuner_core::definition_layout;

// -----------------------------------------------------------------------
// 1. Group rules exist
// -----------------------------------------------------------------------
TEST_CASE("grouping: 9 group rules") {
    CHECK(tpg::group_rules().size() == 9);
}

// -----------------------------------------------------------------------
// 2. Classify fuel keywords
// -----------------------------------------------------------------------
TEST_CASE("grouping: fuel keyword classified") {
    auto m = tpg::classify_text("VE Table");
    CHECK(m.group_id == "fuel");
    CHECK(m.order == 10);
}

// -----------------------------------------------------------------------
// 3. Classify ignition keywords
// -----------------------------------------------------------------------
TEST_CASE("grouping: ignition keyword classified") {
    auto m = tpg::classify_text("Spark Advance Table");
    CHECK(m.group_id == "ignition");
}

// -----------------------------------------------------------------------
// 4. Classify idle keywords
// -----------------------------------------------------------------------
TEST_CASE("grouping: idle keyword classified") {
    auto m = tpg::classify_text("IAC Settings");
    CHECK(m.group_id == "idle");
}

// -----------------------------------------------------------------------
// 5. Unknown text → other
// -----------------------------------------------------------------------
TEST_CASE("grouping: unknown text becomes other") {
    auto m = tpg::classify_text("xyzzy foobar");
    CHECK(m.group_id == "other");
    CHECK(m.order == 99);
}

// -----------------------------------------------------------------------
// 6. Group pages produces sorted groups
// -----------------------------------------------------------------------
TEST_CASE("grouping: group_pages sorts by order") {
    std::vector<dl::LayoutPage> pages;

    dl::LayoutPage p1;
    p1.target = "sparkTable";
    p1.title = "Spark Table";
    p1.group_id = "tuning";
    p1.group_title = "Tuning";
    p1.table_editor_id = "sparkTable1Tbl";
    pages.push_back(p1);

    dl::LayoutPage p2;
    p2.target = "veTable";
    p2.title = "VE Table";
    p2.group_id = "tuning";
    p2.group_title = "Tuning";
    p2.table_editor_id = "veTable1Tbl";
    pages.push_back(p2);

    dl::LayoutPage p3;
    p3.target = "idleSettings";
    p3.title = "Idle Control";
    p3.group_id = "idle";
    p3.group_title = "Idle";
    pages.push_back(p3);

    auto groups = tpg::group_pages(pages);
    REQUIRE(groups.size() >= 2);
    // Fuel (10) should come before Ignition (20) and Idle (40).
    CHECK(groups[0].order <= groups[1].order);
}

// -----------------------------------------------------------------------
// 7. Production INI integration
// -----------------------------------------------------------------------
TEST_CASE("grouping: production INI groups pages") {
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

    auto def = tuner_core::compile_ecu_definition_file(path);
    auto compiled = dl::compile_pages(def.menus, def.dialogs, def.table_editors);
    auto groups = tpg::group_pages(compiled);

    // Should have multiple groups.
    CHECK(groups.size() >= 3);

    // Fuel group should exist and have pages.
    bool found_fuel = false;
    for (const auto& g : groups) {
        if (g.group_id == "fuel") {
            found_fuel = true;
            CHECK(g.pages.size() >= 1);
        }
    }
    CHECK(found_fuel);
}
