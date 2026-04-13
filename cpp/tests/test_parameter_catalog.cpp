// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::parameter_catalog.

#include "doctest.h"

#include "tuner_core/parameter_catalog.hpp"

#include <vector>

using namespace tuner_core::parameter_catalog;

namespace {

ScalarParameterInput make_scalar(
    std::string name, int page, int offset,
    std::string units, std::string data_type) {
    ScalarParameterInput s;
    s.name = std::move(name);
    s.page = page;
    s.offset = offset;
    s.units = std::move(units);
    s.data_type = std::move(data_type);
    return s;
}

TableParameterInput make_table(
    std::string name, int page, int offset, std::string units,
    std::size_t rows, std::size_t cols) {
    TableParameterInput t;
    t.name = std::move(name);
    t.page = page;
    t.offset = offset;
    t.units = std::move(units);
    t.rows = rows;
    t.columns = cols;
    return t;
}

TuneValueInput make_tv(
    std::string name, ScalarOrList value, std::string units = "") {
    TuneValueInput tv;
    tv.name = std::move(name);
    tv.value = std::move(value);
    if (!units.empty()) tv.units = std::move(units);
    return tv;
}

}  // namespace

TEST_CASE("build_catalog: scalar entry has 1x1 shape and tune preview") {
    std::vector<ScalarParameterInput> scalars{
        make_scalar("reqFuel", 1, 0, "ms", "U08"),
    };
    std::vector<TuneValueInput> tune_values{
        make_tv("reqFuel", ScalarOrList{12.5}),
    };
    auto entries = build_catalog(scalars, {}, tune_values);
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].name == "reqFuel");
    CHECK(entries[0].kind == "scalar");
    CHECK(entries[0].shape == "1x1");
    CHECK(entries[0].tune_present);
    CHECK(entries[0].tune_preview == "12.5");
    CHECK(entries[0].data_type == "U08");
}

TEST_CASE("build_catalog: table entry has rows x cols shape and array data type") {
    std::vector<TableParameterInput> tables{
        make_table("veTable", 4, 0, "%", 16, 16),
    };
    auto entries = build_catalog({}, tables, {});
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].kind == "table");
    CHECK(entries[0].shape == "16x16");
    CHECK(entries[0].data_type == "array");
    CHECK_FALSE(entries[0].tune_present);
    CHECK(entries[0].tune_preview.empty());
}

TEST_CASE("build_catalog: tune-only scalar entry") {
    std::vector<TuneValueInput> tune_values{
        make_tv("customX", ScalarOrList{42.0}),
    };
    auto entries = build_catalog({}, {}, tune_values);
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].kind == "scalar");
    CHECK(entries[0].data_type == "tune-only");
    CHECK(entries[0].shape == "1x1");
}

TEST_CASE("build_catalog: tune-only list value becomes a table entry") {
    std::vector<TuneValueInput> tune_values{
        make_tv("customRow", ScalarOrList{std::vector<double>{1, 2, 3, 4}}),
    };
    auto entries = build_catalog({}, {}, tune_values);
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].kind == "table");
    CHECK(entries[0].shape == "4x1");
}

TEST_CASE("build_catalog: tune-only with explicit rows/cols uses them") {
    TuneValueInput tv;
    tv.name = "veRows";
    tv.value = ScalarOrList{std::vector<double>{1, 2, 3, 4, 5, 6}};
    tv.rows = 2;
    tv.cols = 3;
    auto entries = build_catalog({}, {}, {tv});
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].shape == "2x3");
}

TEST_CASE("build_catalog: definition entry takes precedence over tune-only") {
    std::vector<ScalarParameterInput> scalars{
        make_scalar("reqFuel", 1, 0, "ms", "U08"),
    };
    std::vector<TuneValueInput> tune_values{
        make_tv("reqFuel", ScalarOrList{12.5}),
    };
    auto entries = build_catalog(scalars, {}, tune_values);
    REQUIRE(entries.size() == 1);
    // The reqFuel entry comes from the scalar definition, not the
    // tune-only fallback.
    CHECK(entries[0].data_type == "U08");
}

TEST_CASE("build_catalog: entries sorted by page, offset, then lowercase name") {
    std::vector<ScalarParameterInput> scalars{
        make_scalar("zeta", 2, 0, "", "U08"),
        make_scalar("alpha", 1, 5, "", "U08"),
        make_scalar("beta", 1, 0, "", "U08"),
    };
    auto entries = build_catalog(scalars, {}, {});
    REQUIRE(entries.size() == 3);
    CHECK(entries[0].name == "beta");   // page 1, offset 0
    CHECK(entries[1].name == "alpha");  // page 1, offset 5
    CHECK(entries[2].name == "zeta");   // page 2
}

TEST_CASE("filter_catalog: empty query returns everything") {
    std::vector<Entry> entries{
        Entry{"a", "scalar", 1, 0, std::nullopt, "U08", "1x1", false, ""},
    };
    CHECK(filter_catalog(entries, "").size() == 1);
    CHECK(filter_catalog(entries, "  \t\n  ").size() == 1);
}

TEST_CASE("filter_catalog: substring on name") {
    std::vector<Entry> entries{
        Entry{"reqFuel",   "scalar", 1, 0, std::nullopt, "U08", "1x1", false, ""},
        Entry{"nCylinders", "scalar", 1, 1, std::nullopt, "U08", "1x1", false, ""},
    };
    auto out = filter_catalog(entries, "fuel");
    REQUIRE(out.size() == 1);
    CHECK(out[0].name == "reqFuel");
}

TEST_CASE("filter_catalog: substring on units / kind / data_type") {
    std::vector<Entry> entries{
        Entry{"a", "scalar", 1, 0, std::string("rpm"), "U16", "1x1", false, ""},
        Entry{"b", "table", 1, 1, std::string("%"), "array", "16x16", false, ""},
    };
    CHECK(filter_catalog(entries, "rpm").size() == 1);
    CHECK(filter_catalog(entries, "table").size() == 1);
    CHECK(filter_catalog(entries, "u16").size() == 1);
    CHECK(filter_catalog(entries, "array").size() == 1);
}
