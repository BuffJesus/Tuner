// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::tuning_page_diff.

#include "doctest.h"

#include "tuner_core/tuning_page_diff.hpp"

#include <set>
#include <string>
#include <vector>

using namespace tuner_core::tuning_page_diff;

namespace {

ScalarOrList scalar(double v) { return ScalarOrList{v}; }
ScalarOrList list(std::vector<double> v) { return ScalarOrList{std::move(v)}; }

}  // namespace

TEST_CASE("build_page_diff: only dirty parameters appear") {
    auto r = build_page_diff(
        {"a", "b", "c"},
        {"b"},                       // only b is dirty
        {{"a", scalar(1.0)}, {"b", scalar(2.0)}, {"c", scalar(3.0)}},
        {{"a", scalar(0.0)}, {"b", scalar(0.0)}, {"c", scalar(0.0)}});
    REQUIRE(r.entries.size() == 1);
    CHECK(r.entries[0].name == "b");
    CHECK(r.entries[0].before_preview == "0.0");
    CHECK(r.entries[0].after_preview == "2.0");
}

TEST_CASE("build_page_diff: missing staged value is skipped") {
    auto r = build_page_diff(
        {"a"},
        {"a"},
        {},                           // no staged value present
        {{"a", scalar(0.0)}});
    CHECK(r.entries.empty());
}

TEST_CASE("build_page_diff: missing base value falls back to 'n/a'") {
    auto r = build_page_diff(
        {"newParam"},
        {"newParam"},
        {{"newParam", scalar(5.0)}},
        {});
    REQUIRE(r.entries.size() == 1);
    CHECK(r.entries[0].before_preview == "n/a");
    CHECK(r.entries[0].after_preview == "5.0");
}

TEST_CASE("build_page_diff: preserves parameter_names input order") {
    auto r = build_page_diff(
        {"zeta", "alpha", "mu"},
        {"alpha", "mu", "zeta"},
        {{"zeta", scalar(1.0)}, {"alpha", scalar(2.0)}, {"mu", scalar(3.0)}},
        {});
    REQUIRE(r.entries.size() == 3);
    CHECK(r.entries[0].name == "zeta");
    CHECK(r.entries[1].name == "alpha");
    CHECK(r.entries[2].name == "mu");
}

TEST_CASE("build_page_diff: list-valued entry uses list preview") {
    auto r = build_page_diff(
        {"veRow"},
        {"veRow"},
        {{"veRow", list({75.0, 80.0, 85.0, 90.0, 95.0})}},
        {{"veRow", list({70.0, 75.0, 80.0, 85.0, 90.0})}});
    REQUIRE(r.entries.size() == 1);
    CHECK(r.entries[0].before_preview == "70.0, 75.0, 80.0, 85.0 ... (5 values)");
    CHECK(r.entries[0].after_preview == "75.0, 80.0, 85.0, 90.0 ... (5 values)");
}

TEST_CASE("summary: empty result") {
    DiffResult r;
    CHECK(summary(r) == "No staged changes on this page.");
}

TEST_CASE("summary: singular vs plural") {
    DiffResult r;
    r.entries.push_back({"a", "0.0", "1.0"});
    CHECK(summary(r) == "1 staged change on this page.");
    r.entries.push_back({"b", "0.0", "2.0"});
    CHECK(summary(r) == "2 staged changes on this page.");
}

TEST_CASE("detail_text: empty result") {
    DiffResult r;
    CHECK(detail_text(r) == "No staged changes on this page.");
}

TEST_CASE("detail_text: joins entries with newlines") {
    DiffResult r;
    r.entries.push_back({"a", "0.0", "1.0"});
    r.entries.push_back({"b", "n/a", "2.0"});
    CHECK(detail_text(r) == "a: 0.0 -> 1.0\nb: n/a -> 2.0");
}
