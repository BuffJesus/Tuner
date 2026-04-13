// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::IniDefinesParser. Mirrors the
// Python suite for `_collect_defines` and `_expand_options`
// case-for-case so cross-validation against the Python oracle is direct.

#include "doctest.h"

#include "tuner_core/ini_defines_parser.hpp"

#include <string>

TEST_CASE("collect_defines parses a single string-list define") {
    auto defines = tuner_core::collect_defines(
        "#define injectorTypes = \"Off\",\"Throttle Body\",\"Multi-port\"\n");
    REQUIRE(defines.size() == 1);
    auto it = defines.find("injectorTypes");
    REQUIRE(it != defines.end());
    REQUIRE(it->second.size() == 3);
    CHECK(it->second[0] == "Off");
    CHECK(it->second[1] == "Throttle Body");
    CHECK(it->second[2] == "Multi-port");
}

TEST_CASE("collect_defines parses multiple defines") {
    auto defines = tuner_core::collect_defines(
        "#define a = \"x\",\"y\"\n"
        "#define b = \"p\",\"q\",\"r\"\n");
    CHECK(defines.size() == 2);
    CHECK(defines["a"].size() == 2);
    CHECK(defines["b"].size() == 3);
}

TEST_CASE("collect_defines ignores lines that are not #define") {
    auto defines = tuner_core::collect_defines(
        "; comment\n"
        "[Constants]\n"
        "page = 1\n"
        "scalar1 = scalar, U08, 0, \"\", 1, 0, 0, 255, 0\n"
        "#define real = \"a\",\"b\"\n");
    REQUIRE(defines.size() == 1);
    CHECK(defines.count("real") == 1);
}

TEST_CASE("collect_defines ignores #define lines without an equals sign") {
    auto defines = tuner_core::collect_defines(
        "#define noEquals\n"
        "#define withEquals = \"x\"\n");
    REQUIRE(defines.size() == 1);
    CHECK(defines.count("withEquals") == 1);
}

TEST_CASE("collect_defines stores single-value defines as a one-element list") {
    auto defines = tuner_core::collect_defines("#define version = \"1.0\"\n");
    REQUIRE(defines["version"].size() == 1);
    CHECK(defines["version"][0] == "1.0");
}

TEST_CASE("expand_options resolves a single $macro reference") {
    tuner_core::IniDefines defines{
        {"injectorTypes", {"Off", "Throttle Body", "Multi-port"}},
    };
    auto out = tuner_core::expand_options({"$injectorTypes"}, defines);
    REQUIRE(out.size() == 3);
    CHECK(out[0] == "Off");
    CHECK(out[2] == "Multi-port");
}

TEST_CASE("expand_options drops unresolved $macro references") {
    tuner_core::IniDefines defines{};
    auto out = tuner_core::expand_options({"$missing", "real"}, defines);
    REQUIRE(out.size() == 1);
    CHECK(out[0] == "real");
}

TEST_CASE("expand_options preserves literal labels alongside macros") {
    tuner_core::IniDefines defines{
        {"x", {"a", "b"}},
    };
    auto out = tuner_core::expand_options({"first", "$x", "last"}, defines);
    REQUIRE(out.size() == 4);
    CHECK(out[0] == "first");
    CHECK(out[1] == "a");
    CHECK(out[2] == "b");
    CHECK(out[3] == "last");
}

TEST_CASE("expand_options drops {expression} placeholders") {
    tuner_core::IniDefines defines{};
    auto out = tuner_core::expand_options(
        {"real", "{some_expr}", "another"}, defines);
    REQUIRE(out.size() == 2);
    CHECK(out[0] == "real");
    CHECK(out[1] == "another");
}

TEST_CASE("expand_options recursively expands nested macros") {
    tuner_core::IniDefines defines{
        {"outer", {"$inner", "tail"}},
        {"inner", {"deep1", "deep2"}},
    };
    auto out = tuner_core::expand_options({"$outer"}, defines);
    REQUIRE(out.size() == 3);
    CHECK(out[0] == "deep1");
    CHECK(out[1] == "deep2");
    CHECK(out[2] == "tail");
}

TEST_CASE("expand_options caps recursion at 10 levels") {
    // Build a circular define chain that would loop forever without
    // the depth guard.
    tuner_core::IniDefines defines{
        {"a", {"$b"}},
        {"b", {"$a"}},
    };
    auto out = tuner_core::expand_options({"$a"}, defines);
    // The result is whatever the recursion produces before bailing —
    // the important property is that it terminates.
    CHECK(out.size() <= 12);  // generous upper bound; actual is 0
}

TEST_CASE("expand_options skips empty tokens") {
    tuner_core::IniDefines defines{};
    auto out = tuner_core::expand_options({"", "real", ""}, defines);
    REQUIRE(out.size() == 1);
    CHECK(out[0] == "real");
}
