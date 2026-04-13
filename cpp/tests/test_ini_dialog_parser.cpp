// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::ini_dialog_parser — forty-sixth sub-slice.

#include <doctest.h>

#include "tuner_core/ini_dialog_parser.hpp"

#include <fstream>
#include <string>
#include <vector>

namespace tc = tuner_core;

static std::vector<std::string> lines(std::initializer_list<const char*> l) {
    return {l.begin(), l.end()};
}

// -----------------------------------------------------------------------
// 1. Empty lines → empty result
// -----------------------------------------------------------------------
TEST_CASE("dialog: empty lines produce empty result") {
    auto result = tc::parse_dialogs({});
    CHECK(result.dialogs.empty());
}

// -----------------------------------------------------------------------
// 2. Lines outside [UserDefined] are ignored
// -----------------------------------------------------------------------
TEST_CASE("dialog: lines outside UserDefined are ignored") {
    auto result = tc::parse_dialogs(lines({
        "[Constants]",
        "dialog = myDialog, \"My Dialog\"",
    }));
    CHECK(result.dialogs.empty());
}

// -----------------------------------------------------------------------
// 3. Basic dialog with title
// -----------------------------------------------------------------------
TEST_CASE("dialog: basic dialog with title") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "dialog = veTableDialog, \"VE Table\"",
    }));
    REQUIRE(result.dialogs.size() == 1);
    CHECK(result.dialogs[0].dialog_id == "veTableDialog");
    CHECK(result.dialogs[0].title == "VE Table");
}

// -----------------------------------------------------------------------
// 4. Dialog with axis hint
// -----------------------------------------------------------------------
TEST_CASE("dialog: dialog with axis hint") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "dialog = myDialog, \"Title\", xAxis",
    }));
    REQUIRE(result.dialogs.size() == 1);
    CHECK(result.dialogs[0].axis_hint == "xAxis");
}

// -----------------------------------------------------------------------
// 5. Dialog with fields
// -----------------------------------------------------------------------
TEST_CASE("dialog: dialog with fields") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "dialog = fuelDialog, \"Fuel\"",
        "field = \"Required Fuel\", reqFuel",
        "field = \"Injector Flow\", injFlow, {someExpr > 0}",
    }));
    REQUIRE(result.dialogs.size() == 1);
    REQUIRE(result.dialogs[0].fields.size() == 2);

    CHECK(result.dialogs[0].fields[0].label == "Required Fuel");
    CHECK(result.dialogs[0].fields[0].parameter_name == "reqFuel");
    CHECK(result.dialogs[0].fields[0].visibility_expression.empty());
    CHECK(!result.dialogs[0].fields[0].is_static_text);

    CHECK(result.dialogs[0].fields[1].label == "Injector Flow");
    CHECK(result.dialogs[0].fields[1].parameter_name == "injFlow");
    CHECK(result.dialogs[0].fields[1].visibility_expression == "{someExpr > 0}");
}

// -----------------------------------------------------------------------
// 6. Static text field (no parameter name)
// -----------------------------------------------------------------------
TEST_CASE("dialog: static text field") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "dialog = infoDialog, \"Info\"",
        "field = \"This is a note\"",
    }));
    REQUIRE(result.dialogs.size() == 1);
    REQUIRE(result.dialogs[0].fields.size() == 1);
    CHECK(result.dialogs[0].fields[0].label == "This is a note");
    CHECK(result.dialogs[0].fields[0].is_static_text);
    CHECK(result.dialogs[0].fields[0].parameter_name.empty());
}

// -----------------------------------------------------------------------
// 7. Dialog with panel references
// -----------------------------------------------------------------------
TEST_CASE("dialog: dialog with panel references") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "dialog = mainDialog, \"Main\"",
        "panel = fuelDialog",
        "panel = sparkDialog, North, {fuelType == 1}",
    }));
    REQUIRE(result.dialogs.size() == 1);
    REQUIRE(result.dialogs[0].panels.size() == 2);

    CHECK(result.dialogs[0].panels[0].target == "fuelDialog");
    CHECK(result.dialogs[0].panels[0].position.empty());

    CHECK(result.dialogs[0].panels[1].target == "sparkDialog");
    CHECK(result.dialogs[0].panels[1].position == "North");
    CHECK(result.dialogs[0].panels[1].visibility_expression == "{fuelType == 1}");
}

// -----------------------------------------------------------------------
// 8. Multiple dialogs
// -----------------------------------------------------------------------
TEST_CASE("dialog: multiple dialogs") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "dialog = d1, \"Dialog 1\"",
        "field = \"Label\", param1",
        "dialog = d2, \"Dialog 2\"",
        "field = \"Label2\", param2",
    }));
    REQUIRE(result.dialogs.size() == 2);
    CHECK(result.dialogs[0].dialog_id == "d1");
    CHECK(result.dialogs[0].fields.size() == 1);
    CHECK(result.dialogs[1].dialog_id == "d2");
    CHECK(result.dialogs[1].fields.size() == 1);
}

// -----------------------------------------------------------------------
// 9. Comments and blank lines are skipped
// -----------------------------------------------------------------------
TEST_CASE("dialog: comments and blanks skipped") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "; this is a comment",
        "",
        "dialog = d1, \"D1\"",
        "# another comment",
        "field = \"F1\", p1",
    }));
    REQUIRE(result.dialogs.size() == 1);
    CHECK(result.dialogs[0].fields.size() == 1);
}

// -----------------------------------------------------------------------
// 10. Field with {} (empty visibility) is not a parameter
// -----------------------------------------------------------------------
TEST_CASE("dialog: field with empty braces") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "dialog = d1, \"D1\"",
        "field = \"Label\", paramName, {}",
    }));
    REQUIRE(result.dialogs.size() == 1);
    REQUIRE(result.dialogs[0].fields.size() == 1);
    CHECK(result.dialogs[0].fields[0].parameter_name == "paramName");
}

// -----------------------------------------------------------------------
// 11. Field before any dialog is ignored
// -----------------------------------------------------------------------
TEST_CASE("dialog: field before dialog is ignored") {
    auto result = tc::parse_dialogs(lines({
        "[UserDefined]",
        "field = \"Orphan\", orphanParam",
        "dialog = d1, \"D1\"",
        "field = \"F1\", p1",
    }));
    REQUIRE(result.dialogs.size() == 1);
    CHECK(result.dialogs[0].fields.size() == 1);
    CHECK(result.dialogs[0].fields[0].parameter_name == "p1");
}

// -----------------------------------------------------------------------
// 12. Production INI integration — parse real INI if available
// -----------------------------------------------------------------------
TEST_CASE("dialog: production INI produces dialogs") {
    // Try to find the production INI fixture.
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
    if (path.empty()) {
        // Skip if fixture not found.
        return;
    }
    // Read all lines.
    std::ifstream file(path);
    std::vector<std::string> all_lines;
    std::string line;
    while (std::getline(file, line)) all_lines.push_back(line);

    auto result = tc::parse_dialogs(all_lines);
    // The production INI has many dialogs.
    CHECK(result.dialogs.size() > 20);

    // Verify a known dialog exists.
    bool found_ve = false;
    for (const auto& d : result.dialogs) {
        if (d.dialog_id == "veTableDialog") found_ve = true;
    }
    CHECK(found_ve);
}
