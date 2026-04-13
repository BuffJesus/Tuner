// SPDX-License-Identifier: MIT
//
// doctest cases for `ini_reference_tables_parser.hpp`.

#include "doctest.h"

#include "tuner_core/ini_reference_tables_parser.hpp"

using namespace tuner_core;

TEST_CASE("reference_tables: parses a single table with all fields") {
    const char* text = R"INI(
[UserDefined]
referenceTable = leanAtWot, "Lean at WOT"
topicHelp = "Diagnose lean running at wide-open throttle"
tableIdentifier = 4, 8
solutionsLabel = "Recommended Solutions"
solution = "Low fuel pressure", "fuelPress < 3"
solution = "Injector too small", "injFlow < 300"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 1);
    const auto& t = section.tables[0];
    CHECK(t.table_id == "leanAtWot");
    CHECK(t.label == "Lean at WOT");
    REQUIRE(t.topic_help.has_value());
    CHECK(*t.topic_help == "Diagnose lean running at wide-open throttle");
    REQUIRE(t.table_identifier.has_value());
    CHECK(*t.table_identifier == "8");  // parts[1] when len>1
    REQUIRE(t.solutions_label.has_value());
    CHECK(*t.solutions_label == "Recommended Solutions");
    REQUIRE(t.solutions.size() == 2);
    CHECK(t.solutions[0].label == "Low fuel pressure");
    REQUIRE(t.solutions[0].expression.has_value());
    CHECK(*t.solutions[0].expression == "fuelPress < 3");
    CHECK(t.solutions[1].label == "Injector too small");
}

TEST_CASE("reference_tables: label defaults to table_id when missing") {
    const char* text = R"INI(
[UserDefined]
referenceTable = onlyId
solution = "Something", "expr"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 1);
    CHECK(section.tables[0].table_id == "onlyId");
    CHECK(section.tables[0].label == "onlyId");
    CHECK(section.tables[0].solutions.size() == 1);
}

TEST_CASE("reference_tables: multiple tables accumulate independently") {
    const char* text = R"INI(
[UserDefined]
referenceTable = first, "First"
topicHelp = "first help"
solution = "A", "a"

referenceTable = second, "Second"
topicHelp = "second help"
solution = "B", "b"
solution = "C", "c"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 2);
    CHECK(section.tables[0].table_id == "first");
    CHECK(section.tables[0].solutions.size() == 1);
    CHECK(section.tables[1].table_id == "second");
    CHECK(section.tables[1].solutions.size() == 2);
}

TEST_CASE("reference_tables: properties before a referenceTable are ignored") {
    const char* text = R"INI(
[UserDefined]
topicHelp = "Orphan help"
solution = "Orphan", "expr"
referenceTable = real, "Real"
solution = "Owned", "x"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 1);
    CHECK(section.tables[0].table_id == "real");
    CHECK(section.tables[0].solutions.size() == 1);
    CHECK(section.tables[0].solutions[0].label == "Owned");
}

TEST_CASE("reference_tables: solution with only a label survives without expression") {
    const char* text = R"INI(
[UserDefined]
referenceTable = t, "T"
solution = "Check fuel pressure"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 1);
    REQUIRE(section.tables[0].solutions.size() == 1);
    CHECK(section.tables[0].solutions[0].label == "Check fuel pressure");
    CHECK_FALSE(section.tables[0].solutions[0].expression.has_value());
}

TEST_CASE("reference_tables: tableIdentifier single-arg uses parts[0]") {
    const char* text = R"INI(
[UserDefined]
referenceTable = t, "T"
tableIdentifier = only_one
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 1);
    REQUIRE(section.tables[0].table_identifier.has_value());
    CHECK(*section.tables[0].table_identifier == "only_one");
}

TEST_CASE("reference_tables: leaves section -> subsequent lines dont land on in-flight table") {
    const char* text = R"INI(
[UserDefined]
referenceTable = t, "T"
solution = "A", "a"

[OtherSection]
solution = "Should be skipped", "x"

[UserDefined]
solution = "Still skipped because no block open after re-entry"
referenceTable = t2, "T2"
solution = "T2 solution", "y"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 2);
    CHECK(section.tables[0].table_id == "t");
    CHECK(section.tables[0].solutions.size() == 1);
    CHECK(section.tables[1].table_id == "t2");
    CHECK(section.tables[1].solutions.size() == 1);
}

TEST_CASE("reference_tables: unknown keys ignored") {
    const char* text = R"INI(
[UserDefined]
referenceTable = t, "T"
unknownKey = foo
solution = "real", "expr"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 1);
    CHECK(section.tables[0].solutions.size() == 1);
}

TEST_CASE("reference_tables: case-insensitive section header") {
    const char* text = R"INI(
[userdefined]
referenceTable = t, "T"
solution = "s", "e"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 1);
}

TEST_CASE("reference_tables: comments + blank lines skipped") {
    const char* text = R"INI(
[UserDefined]
; comment
referenceTable = t, "T"

# another
solution = "s", "e"
)INI";
    auto section = parse_reference_tables_section(text);
    REQUIRE(section.tables.size() == 1);
    CHECK(section.tables[0].solutions.size() == 1);
}

TEST_CASE("reference_tables: preprocessor #if gating") {
    const char* text = R"INI(
#set FEATURE_DIAG
[UserDefined]
#if FEATURE_DIAG
referenceTable = enabled, "On"
#else
referenceTable = disabled, "Off"
#endif
)INI";
    auto section = parse_reference_tables_section_preprocessed(text);
    REQUIRE(section.tables.size() == 1);
    CHECK(section.tables[0].table_id == "enabled");
}

TEST_CASE("reference_tables: empty input") {
    auto section = parse_reference_tables_section("");
    CHECK(section.tables.empty());
}

TEST_CASE("reference_tables: empty section") {
    auto section = parse_reference_tables_section("[UserDefined]\n");
    CHECK(section.tables.empty());
}
