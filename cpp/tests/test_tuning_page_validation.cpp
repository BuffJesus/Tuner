// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::tuning_page_validation.

#include "doctest.h"

#include "tuner_core/tuning_page_validation.hpp"

#include <map>
#include <string>

using namespace tuner_core::tuning_page_validation;

namespace {

ScalarOrList scalar(double v) { return ScalarOrList{v}; }
ScalarOrList list_value(std::vector<double> v) { return ScalarOrList{std::move(v)}; }

ValueLookup from_map(std::map<std::string, ScalarOrList> m) {
    return [m](std::string_view name) -> std::optional<ScalarOrList> {
        auto it = m.find(std::string(name));
        if (it == m.end()) return std::nullopt;
        return it->second;
    };
}

Parameter make_param(std::string name, ParameterKind kind = ParameterKind::SCALAR) {
    Parameter p;
    p.name = std::move(name);
    p.kind = kind;
    p.page = 1;
    p.offset = 0;
    return p;
}

}  // namespace

TEST_CASE("validate_page: missing scalar tune value produces an error") {
    Page page;
    page.kind = PageKind::OTHER;
    page.parameters.push_back(make_param("rpmLimit"));
    auto r = validate_page(page, from_map({}), {});
    REQUIRE(r.errors.size() == 1);
    CHECK(r.errors[0] == "Missing tune value for 'rpmLimit'.");
}

TEST_CASE("validate_page: scalar value below min produces a warning") {
    Page page;
    page.kind = PageKind::OTHER;
    auto p = make_param("rpmLimit");
    p.min_value = 1000.0;
    p.max_value = 8000.0;
    page.parameters.push_back(p);
    auto r = validate_page(page, from_map({{"rpmLimit", scalar(500.0)}}), {});
    CHECK(r.errors.empty());
    REQUIRE(r.warnings.size() == 1);
    CHECK(r.warnings[0].find("below minimum") != std::string::npos);
}

TEST_CASE("validate_page: scalar value above max produces a warning") {
    Page page;
    page.kind = PageKind::OTHER;
    auto p = make_param("rpmLimit");
    p.min_value = 1000.0;
    p.max_value = 8000.0;
    page.parameters.push_back(p);
    auto r = validate_page(page, from_map({{"rpmLimit", scalar(9000.0)}}), {});
    REQUIRE(r.warnings.size() == 1);
    CHECK(r.warnings[0].find("exceeds maximum") != std::string::npos);
}

TEST_CASE("validate_page: visibility hides parameter so no missing-value error") {
    Page page;
    page.kind = PageKind::OTHER;
    auto p = make_param("rpmLimit");
    p.visibility_expression = "{ enabled == 1 }";
    page.parameters.push_back(p);
    auto r = validate_page(page, from_map({}), {{"enabled", 0.0}});
    CHECK(r.errors.empty());
}

TEST_CASE("validate_page: table page with no main table name produces error") {
    Page page;
    page.kind = PageKind::TABLE;
    auto r = validate_page(page, from_map({}), {});
    bool found = false;
    for (const auto& e : r.errors) {
        if (e.find("does not define a main table name") != std::string::npos) found = true;
    }
    CHECK(found);
}

TEST_CASE("validate_page: table page with missing main table value is error") {
    Page page;
    page.kind = PageKind::TABLE;
    page.table_name = "veTable";
    auto r = validate_page(page, from_map({}), {});
    bool found = false;
    for (const auto& e : r.errors) {
        if (e.find("Main table 'veTable' is unavailable") != std::string::npos) found = true;
    }
    CHECK(found);
}

TEST_CASE("validate_page: table page with non-list main table is error") {
    Page page;
    page.kind = PageKind::TABLE;
    page.table_name = "veTable";
    auto r = validate_page(
        page, from_map({{"veTable", scalar(1.0)}}), {});
    bool found = false;
    for (const auto& e : r.errors) {
        if (e.find("not list-backed") != std::string::npos) found = true;
    }
    CHECK(found);
}

TEST_CASE("validate_page: empty axis labels produce a warning") {
    Page page;
    page.kind = PageKind::TABLE;
    page.table_name = "veTable";
    page.x_axis_name = "rpmBins";
    auto r = validate_page(
        page,
        from_map({
            {"veTable", list_value({1.0, 2.0})},
            {"rpmBins", list_value({})},
        }),
        {});
    bool found = false;
    for (const auto& w : r.warnings) {
        if (w.find("X axis 'rpmBins' has no labels") != std::string::npos) found = true;
    }
    CHECK(found);
}

TEST_CASE("validate_page: fallback page with only tables warns about no scalars") {
    Page page;
    page.kind = PageKind::OTHER;
    auto p = make_param("auxTable", ParameterKind::TABLE);
    page.parameters.push_back(p);
    auto r = validate_page(
        page,
        from_map({{"auxTable", list_value({1.0, 2.0})}}),
        {});
    bool found = false;
    for (const auto& w : r.warnings) {
        if (w.find("only table content and no direct scalar edits") != std::string::npos) found = true;
    }
    CHECK(found);
}

TEST_CASE("validate_page: clean page produces no issues") {
    Page page;
    page.kind = PageKind::OTHER;
    auto p = make_param("rpmLimit");
    p.min_value = 0.0;
    p.max_value = 8000.0;
    page.parameters.push_back(p);
    auto r = validate_page(
        page, from_map({{"rpmLimit", scalar(7000.0)}}), {});
    CHECK(r.errors.empty());
    CHECK(r.warnings.empty());
}

TEST_CASE("validate_page: errors are deduped") {
    Page page;
    page.kind = PageKind::OTHER;
    page.parameters.push_back(make_param("rpmLimit"));
    page.parameters.push_back(make_param("rpmLimit"));  // duplicate name
    auto r = validate_page(page, from_map({}), {});
    CHECK(r.errors.size() == 1);
}
