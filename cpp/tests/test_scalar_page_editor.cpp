// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::scalar_page_editor.

#include "doctest.h"

#include "tuner_core/scalar_page_editor.hpp"

#include <map>
#include <string>

using namespace tuner_core::scalar_page_editor;

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

DirtyCheck dirty_set(std::vector<std::string> names) {
    return [names](std::string_view name) {
        for (const auto& n : names) if (n == name) return true;
        return false;
    };
}

Parameter scalar_param(std::string name, std::string label) {
    Parameter p;
    p.name = std::move(name);
    p.label = std::move(label);
    p.kind = "scalar";
    return p;
}

}  // namespace

TEST_CASE("build_sections: empty page yields a single fallback section") {
    Page page;
    page.title = "Empty";
    auto sections = build_sections(page, from_map({}), from_map({}), dirty_set({}), {});
    REQUIRE(sections.size() == 1);
    CHECK(sections[0].title == "Empty");
    CHECK(sections[0].fields.empty());
}

TEST_CASE("build_sections: fallback path emits scalar fields when no sections defined") {
    Page page;
    page.title = "Engine";
    page.parameters.push_back(scalar_param("reqFuel", "Required Fuel"));
    page.parameters.push_back(scalar_param("nCylinders", "Cylinders"));
    auto sections = build_sections(
        page,
        from_map({{"reqFuel", scalar(12.5)}, {"nCylinders", scalar(4.0)}}),
        from_map({{"reqFuel", scalar(10.0)}, {"nCylinders", scalar(4.0)}}),
        dirty_set({"reqFuel"}),
        {});
    REQUIRE(sections.size() == 1);
    CHECK(sections[0].title == "Engine");
    REQUIRE(sections[0].fields.size() == 2);
    CHECK(sections[0].fields[0].name == "reqFuel");
    CHECK(sections[0].fields[0].value_text == "12.5");
    CHECK(sections[0].fields[0].base_value_text == "10.0");
    CHECK(sections[0].fields[0].is_dirty);
    CHECK(sections[0].fields[1].name == "nCylinders");
    CHECK_FALSE(sections[0].fields[1].is_dirty);
}

TEST_CASE("build_sections: explicit sections take precedence over fallback") {
    Page page;
    page.title = "Engine";
    page.parameters.push_back(scalar_param("reqFuel", "Required Fuel"));
    Section section;
    section.title = "Fueling";
    section.parameter_names = {"reqFuel"};
    page.sections.push_back(section);

    auto sections = build_sections(
        page,
        from_map({{"reqFuel", scalar(12.5)}}),
        from_map({}),
        dirty_set({}),
        {});
    REQUIRE(sections.size() == 1);
    CHECK(sections[0].title == "Fueling");
    REQUIRE(sections[0].fields.size() == 1);
    CHECK(sections[0].fields[0].name == "reqFuel");
}

TEST_CASE("build_sections: per-field visibility hides fields") {
    Page page;
    page.title = "Engine";
    auto p1 = scalar_param("a", "A");
    auto p2 = scalar_param("b", "B");
    p2.visibility_expression = "{ enabled == 1 }";
    page.parameters.push_back(p1);
    page.parameters.push_back(p2);
    Section section;
    section.title = "Group";
    section.parameter_names = {"a", "b"};
    page.sections.push_back(section);

    auto sections = build_sections(
        page,
        from_map({{"a", scalar(1.0)}, {"b", scalar(2.0)}}),
        from_map({}),
        dirty_set({}),
        {{"enabled", 0.0}});
    REQUIRE(sections.size() == 1);
    REQUIRE(sections[0].fields.size() == 1);
    CHECK(sections[0].fields[0].name == "a");
}

TEST_CASE("build_sections: section visibility hides the whole section") {
    Page page;
    page.title = "Engine";
    page.parameters.push_back(scalar_param("a", "A"));
    Section section;
    section.title = "GatedSection";
    section.parameter_names = {"a"};
    section.visibility_expression = "{ enabled == 1 }";
    page.sections.push_back(section);

    auto sections = build_sections(
        page, from_map({{"a", scalar(1.0)}}), from_map({}), dirty_set({}),
        {{"enabled", 0.0}});
    // Section is gated off; no other sections defined → fallback path
    REQUIRE(sections.size() == 1);
    CHECK(sections[0].title == "Engine");  // fallback uses page title
}

TEST_CASE("build_sections: empty section with notes is still emitted") {
    Page page;
    page.title = "Engine";
    page.parameters.push_back(scalar_param("a", "A"));
    Section noteOnly;
    noteOnly.title = "Just notes";
    noteOnly.notes = {"Read this carefully."};
    Section withFields;
    withFields.title = "Fields";
    withFields.parameter_names = {"a"};
    page.sections.push_back(noteOnly);
    page.sections.push_back(withFields);

    auto sections = build_sections(
        page, from_map({{"a", scalar(1.0)}}), from_map({}), dirty_set({}), {});
    REQUIRE(sections.size() == 2);
    CHECK(sections[0].title == "Just notes");
    CHECK(sections[0].fields.empty());
    CHECK(sections[0].notes.size() == 1);
    CHECK(sections[1].title == "Fields");
}

TEST_CASE("build_sections: non-scalar parameters are filtered out") {
    Page page;
    page.title = "Engine";
    Parameter table_param;
    table_param.name = "veTable";
    table_param.kind = "table";
    page.parameters.push_back(table_param);
    page.parameters.push_back(scalar_param("reqFuel", "Required Fuel"));

    Section section;
    section.title = "Mixed";
    section.parameter_names = {"veTable", "reqFuel"};
    page.sections.push_back(section);

    auto sections = build_sections(
        page,
        from_map({{"veTable", list_value({1, 2, 3})}, {"reqFuel", scalar(12.5)}}),
        from_map({}),
        dirty_set({}),
        {});
    REQUIRE(sections.size() == 1);
    REQUIRE(sections[0].fields.size() == 1);
    CHECK(sections[0].fields[0].name == "reqFuel");
}
