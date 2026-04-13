// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniMenuParser. Mirrors the
// Python `_parse_menus` test surface so cross-validation against
// the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_menu_parser.hpp"

#include <string>

namespace {

const tuner_core::IniMenu* find_menu(
    const tuner_core::IniMenuSection& section, const std::string& title) {
    for (const auto& m : section.menus) {
        if (m.title == title) return &m;
    }
    return nullptr;
}

}  // namespace

TEST_CASE("parse_menu_section ignores lines outside [Menu]") {
    auto section = tuner_core::parse_menu_section(
        "[Other]\nmenu = Title\nsubMenu = veTbl, \"VE Table\"\n");
    CHECK(section.menus.empty());
}

TEST_CASE("parses a single menu with a single item") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = veTblTbl, \"VE Table\"\n");
    REQUIRE(section.menus.size() == 1);
    CHECK(section.menus[0].title == "Tuning");
    REQUIRE(section.menus[0].items.size() == 1);
    CHECK(section.menus[0].items[0].target == "veTblTbl");
    CHECK(section.menus[0].items[0].label.value() == "VE Table");
}

TEST_CASE("subMenu and groupChildMenu both populate items") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = first, \"First\"\n"
        "groupChildMenu = second, \"Second\"\n");
    REQUIRE(section.menus.size() == 1);
    REQUIRE(section.menus[0].items.size() == 2);
    CHECK(section.menus[0].items[0].target == "first");
    CHECK(section.menus[0].items[1].target == "second");
}

TEST_CASE("std_separator items are dropped") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = veTbl, \"VE Table\"\n"
        "subMenu = std_separator\n"
        "subMenu = ignTbl, \"Ignition Table\"\n");
    REQUIRE(section.menus.size() == 1);
    REQUIRE(section.menus[0].items.size() == 2);
    CHECK(section.menus[0].items[0].target == "veTbl");
    CHECK(section.menus[0].items[1].target == "ignTbl");
}

TEST_CASE("label defaults to target when missing") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = onlyTarget\n");
    REQUIRE(section.menus[0].items.size() == 1);
    CHECK(section.menus[0].items[0].label.value() == "onlyTarget");
}

TEST_CASE("page number is parsed when present") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = page2tbl, \"Page 2 Table\", 2\n");
    REQUIRE(section.menus[0].items.size() == 1);
    CHECK(section.menus[0].items[0].page.value() == 2);
}

TEST_CASE("visibility expression is captured verbatim") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = lambdaTbl, \"Lambda Table\", { LAMBDA }\n");
    REQUIRE(section.menus[0].items.size() == 1);
    CHECK(section.menus[0].items[0].visibility_expression.value() == "{ LAMBDA }");
}

TEST_CASE("page and visibility can appear in either order") {
    auto withPageFirst = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"M\"\n"
        "subMenu = t, \"Label\", 3, { LAMBDA }\n");
    auto withVisFirst = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"M\"\n"
        "subMenu = t, \"Label\", { LAMBDA }, 3\n");
    REQUIRE(withPageFirst.menus[0].items.size() == 1);
    REQUIRE(withVisFirst.menus[0].items.size() == 1);
    CHECK(withPageFirst.menus[0].items[0].page.value() == 3);
    CHECK(withPageFirst.menus[0].items[0].visibility_expression.value() == "{ LAMBDA }");
    CHECK(withVisFirst.menus[0].items[0].page.value() == 3);
    CHECK(withVisFirst.menus[0].items[0].visibility_expression.value() == "{ LAMBDA }");
}

TEST_CASE("multiple menus are tracked separately") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = veTbl, \"VE Table\"\n"
        "menu = \"Setup\"\n"
        "subMenu = engineSetup, \"Engine Setup\"\n");
    REQUIRE(section.menus.size() == 2);
    CHECK(find_menu(section, "Tuning")->items[0].target == "veTbl");
    CHECK(find_menu(section, "Setup")->items[0].target == "engineSetup");
}

TEST_CASE("items before any menu line are ignored") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "subMenu = orphan, \"Orphan\"\n"
        "menu = \"Real\"\n"
        "subMenu = real, \"Real Item\"\n");
    REQUIRE(section.menus.size() == 1);
    REQUIRE(section.menus[0].items.size() == 1);
    CHECK(section.menus[0].items[0].target == "real");
}

TEST_CASE("section change clears the active menu") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = veTbl, \"VE Table\"\n"
        "[OtherSection]\n"
        "subMenu = leaked, \"Leaked\"\n");
    REQUIRE(section.menus.size() == 1);
    REQUIRE(section.menus[0].items.size() == 1);
    CHECK(section.menus[0].items[0].target == "veTbl");
}

TEST_CASE("comments and blank lines are ignored") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "; comment\n"
        "\n"
        "menu = \"Tuning\"\n"
        "; mid comment\n"
        "subMenu = veTbl, \"VE Table\"\n");
    REQUIRE(section.menus[0].items.size() == 1);
}

TEST_CASE("preprocessed pipeline gates items inside #if blocks") {
    auto disabled = tuner_core::parse_menu_section_preprocessed(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = always, \"Always\"\n"
        "#if FEATURE_X\n"
        "subMenu = feature, \"Feature\"\n"
        "#endif\n",
        {});
    REQUIRE(disabled.menus[0].items.size() == 1);
    CHECK(disabled.menus[0].items[0].target == "always");

    auto enabled = tuner_core::parse_menu_section_preprocessed(
        "[Menu]\n"
        "menu = \"Tuning\"\n"
        "subMenu = always, \"Always\"\n"
        "#if FEATURE_X\n"
        "subMenu = feature, \"Feature\"\n"
        "#endif\n",
        {"FEATURE_X"});
    REQUIRE(enabled.menus[0].items.size() == 2);
}

TEST_CASE("invalid page number is ignored without dropping the item") {
    auto section = tuner_core::parse_menu_section(
        "[Menu]\n"
        "menu = \"M\"\n"
        "subMenu = t, \"Label\", notapage\n");
    REQUIRE(section.menus[0].items.size() == 1);
    CHECK(section.menus[0].items[0].target == "t");
    CHECK_FALSE(section.menus[0].items[0].page.has_value());
}
