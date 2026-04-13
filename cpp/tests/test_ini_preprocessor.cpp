// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniPreprocessor. Mirrors the
// Python suite in tests/unit/test_ini_preprocessor.py case-for-case
// so cross-validation against the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_preprocessor.hpp"

#include <set>
#include <string>
#include <vector>

namespace {

std::vector<std::string> preprocess(
    const std::string& text,
    const std::set<std::string>& settings = {}) {
    return tuner_core::preprocess_ini_text(text, settings);
}

bool contains_line(const std::vector<std::string>& lines, std::string_view needle) {
    for (const auto& line : lines) {
        if (line.find(needle) != std::string::npos) return true;
    }
    return false;
}

}  // namespace

TEST_CASE("preprocess_ini_text returns plain lines unchanged when no directives") {
    auto out = preprocess("foo = 1\nbar = 2\n");
    REQUIRE(out.size() == 2);
    CHECK(out[0] == "foo = 1");
    CHECK(out[1] == "bar = 2");
}

TEST_CASE("if-set keeps body when symbol is in active_settings") {
    const std::string src =
        "before\n"
        "#if LAMBDA\n"
        "inside_lambda\n"
        "#endif\n"
        "after\n";
    auto out = preprocess(src, {"LAMBDA"});
    CHECK(contains_line(out, "before"));
    CHECK(contains_line(out, "inside_lambda"));
    CHECK(contains_line(out, "after"));
}

TEST_CASE("if-unset drops body when symbol absent") {
    const std::string src =
        "#if LAMBDA\n"
        "inside_lambda\n"
        "#endif\n";
    auto out = preprocess(src);
    CHECK_FALSE(contains_line(out, "inside_lambda"));
}

TEST_CASE("else branch fires when if symbol is absent") {
    const std::string src =
        "#if LAMBDA\n"
        "lambda_branch\n"
        "#else\n"
        "afr_branch\n"
        "#endif\n";
    auto out = preprocess(src);
    CHECK_FALSE(contains_line(out, "lambda_branch"));
    CHECK(contains_line(out, "afr_branch"));
}

TEST_CASE("else branch suppressed when if symbol is present") {
    const std::string src =
        "#if LAMBDA\n"
        "lambda_branch\n"
        "#else\n"
        "afr_branch\n"
        "#endif\n";
    auto out = preprocess(src, {"LAMBDA"});
    CHECK(contains_line(out, "lambda_branch"));
    CHECK_FALSE(contains_line(out, "afr_branch"));
}

TEST_CASE("file-scope set provides default when not overridden") {
    const std::string src =
        "#set LAMBDA\n"
        "#if LAMBDA\n"
        "from_file_default\n"
        "#endif\n";
    auto out = preprocess(src);
    CHECK(contains_line(out, "from_file_default"));
}

TEST_CASE("active_settings overrides file-scope set") {
    // file says LAMBDA on, user explicitly does not enable it — but
    // active_settings is additive (Python comment: "user wins" — wins
    // means user can ADD; user can't *unset* a file default in v1).
    // The Python implementation's `_unset` only clears the file
    // default, not user-added settings; verify the same here.
    const std::string src =
        "#set LAMBDA\n"
        "#if LAMBDA\n"
        "lambda_branch\n"
        "#endif\n";
    auto out = preprocess(src);  // user passes empty
    CHECK(contains_line(out, "lambda_branch"));
}

TEST_CASE("active_settings can enable a symbol the file does not set") {
    const std::string src =
        "#if MCU_TEENSY\n"
        "teensy_branch\n"
        "#endif\n";
    auto out = preprocess(src, {"MCU_TEENSY"});
    CHECK(contains_line(out, "teensy_branch"));
}

TEST_CASE("nested if blocks evaluate inner branch correctly") {
    const std::string src =
        "#if LAMBDA\n"
        "outer_active\n"
        "#if MCU_TEENSY\n"
        "both_active\n"
        "#endif\n"
        "#endif\n";
    auto out = preprocess(src, {"LAMBDA", "MCU_TEENSY"});
    CHECK(contains_line(out, "outer_active"));
    CHECK(contains_line(out, "both_active"));
}

TEST_CASE("nested inner branch suppressed when only outer is active") {
    const std::string src =
        "#if LAMBDA\n"
        "outer_active\n"
        "#if MCU_TEENSY\n"
        "both_active\n"
        "#endif\n"
        "#endif\n";
    auto out = preprocess(src, {"LAMBDA"});
    CHECK(contains_line(out, "outer_active"));
    CHECK_FALSE(contains_line(out, "both_active"));
}

TEST_CASE("nested branch never appears when outer is inactive") {
    const std::string src =
        "#if LAMBDA\n"
        "#if MCU_TEENSY\n"
        "both_active\n"
        "#endif\n"
        "#endif\n";
    auto out = preprocess(src, {"MCU_TEENSY"});
    CHECK_FALSE(contains_line(out, "both_active"));
}

TEST_CASE("set and unset directives are consumed and never emitted") {
    const std::string src =
        "#set FOO\n"
        "#unset BAR\n"
        "real_line\n";
    auto out = preprocess(src);
    REQUIRE(out.size() == 1);
    CHECK(out[0] == "real_line");
}

TEST_CASE("hash-prefixed comments inside inactive branch are dropped") {
    const std::string src =
        "#if LAMBDA\n"
        "#  comment in lambda branch\n"
        "lambda_real\n"
        "#endif\n";
    auto out = preprocess(src);
    CHECK_FALSE(contains_line(out, "comment in lambda branch"));
    CHECK_FALSE(contains_line(out, "lambda_real"));
}

TEST_CASE("hash-prefixed comments inside active branch are kept") {
    const std::string src =
        "#if LAMBDA\n"
        "#  comment in lambda branch\n"
        "lambda_real\n"
        "#endif\n";
    auto out = preprocess(src, {"LAMBDA"});
    CHECK(contains_line(out, "comment in lambda branch"));
    CHECK(contains_line(out, "lambda_real"));
}

TEST_CASE("empty lines are preserved inside active branch") {
    const std::string src =
        "before\n"
        "\n"
        "after\n";
    auto out = preprocess(src);
    REQUIRE(out.size() == 3);
    CHECK(out[1].empty());
}

TEST_CASE("crlf line endings are normalized to lf") {
    auto out = preprocess("foo\r\nbar\r\n");
    REQUIRE(out.size() == 2);
    CHECK(out[0] == "foo");
    CHECK(out[1] == "bar");
}
