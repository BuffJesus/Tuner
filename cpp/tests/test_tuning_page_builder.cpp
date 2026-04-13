// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/tuning_page_builder.hpp"

#include <filesystem>
#include <fstream>
#include <string>

namespace tpb = tuner_core::tuning_page_builder;

TEST_SUITE("tuning_page_builder") {

TEST_CASE("empty definition produces no pages") {
    tuner_core::NativeEcuDefinition def;
    auto groups = tpb::build_pages(def);
    CHECK(groups.empty());
}

TEST_CASE("production INI produces grouped pages") {
    // Try to load the real INI for an integration test.
    const char* paths[] = {
        "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
    };
    std::filesystem::path ini_path;
    for (const char* p : paths) {
        if (std::filesystem::exists(p)) { ini_path = p; break; }
    }
    if (ini_path.empty()) {
        MESSAGE("Production INI not found — skipping integration test");
        return;
    }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    auto groups = tpb::build_pages(def);

    // Should have multiple groups.
    CHECK(groups.size() >= 3);

    // Should have table pages.
    int table_count = 0;
    int total_pages = 0;
    for (const auto& g : groups) {
        for (const auto& p : g.pages) {
            ++total_pages;
            if (p.kind == tpb::PageKind::TABLE) ++table_count;
        }
    }
    CHECK(total_pages > 10);
    CHECK(table_count > 5);

    // veTableDialog should be present as a table page.
    bool found_ve = false;
    for (const auto& g : groups) {
        for (const auto& p : g.pages) {
            if (p.page_id.find("veTableDialog") != std::string::npos) {
                found_ve = true;
                CHECK(p.kind == tpb::PageKind::TABLE);
                CHECK(!p.table_id.empty());
            }
        }
    }
    CHECK(found_ve);
}

TEST_CASE("production INI table pages have axis parameters") {
    const char* paths[] = {
        "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
    };
    std::filesystem::path ini_path;
    for (const char* p : paths) {
        if (std::filesystem::exists(p)) { ini_path = p; break; }
    }
    if (ini_path.empty()) {
        MESSAGE("Production INI not found — skipping");
        return;
    }

    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    auto groups = tpb::build_pages(def);

    // Find veTableDialog — it should be a TABLE kind with axis params.
    bool found = false;
    for (const auto& g : groups) {
        for (const auto& p : g.pages) {
            if (p.page_id.find("veTableDialog") != std::string::npos
                && p.kind == tpb::PageKind::TABLE) {
                found = true;
                CHECK(!p.table_id.empty());
                CHECK(!p.table_name.empty());
                CHECK(p.parameters.size() >= 3);  // z + x + y at minimum
            }
        }
    }
    CHECK(found);
}

}  // TEST_SUITE
