// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::staged_change.

#include "doctest.h"

#include "tuner_core/staged_change.hpp"

#include <set>
#include <string>
#include <vector>

using namespace tuner_core::staged_change;

namespace {

ScalarOrList scalar(double v) { return ScalarOrList{v}; }
ScalarOrList list(std::vector<double> v) { return ScalarOrList{std::move(v)}; }

}  // namespace

TEST_CASE("summarize: empty input produces empty output") {
    auto entries = summarize({}, {}, {}, {});
    CHECK(entries.empty());
}

TEST_CASE("summarize: single scalar entry") {
    auto entries = summarize(
        {{"reqFuel", scalar(12.5)}},
        {{"reqFuel", scalar(10.0)}},
        {{"reqFuel", "Engine Constants"}},
        {});
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].name == "reqFuel");
    CHECK(entries[0].preview == "12.5");
    CHECK(entries[0].before_preview == "10.0");
    CHECK(entries[0].page_title == "Engine Constants");
    CHECK_FALSE(entries[0].is_written);
}

TEST_CASE("summarize: missing base value falls back to 'n/a'") {
    auto entries = summarize(
        {{"newParam", scalar(5.0)}},
        {},
        {},
        {});
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].before_preview == "n/a");
}

TEST_CASE("summarize: missing page title falls back to 'Other'") {
    auto entries = summarize(
        {{"x", scalar(1.0)}},
        {{"x", scalar(0.0)}},
        {},
        {});
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].page_title == "Other");
}

TEST_CASE("summarize: is_written reflects written_names membership") {
    std::set<std::string> written{"a", "c"};
    auto entries = summarize(
        {{"a", scalar(1.0)}, {"b", scalar(2.0)}, {"c", scalar(3.0)}},
        {},
        {},
        written);
    REQUIRE(entries.size() == 3);
    CHECK(entries[0].name == "a");
    CHECK(entries[0].is_written);
    CHECK(entries[1].name == "b");
    CHECK_FALSE(entries[1].is_written);
    CHECK(entries[2].name == "c");
    CHECK(entries[2].is_written);
}

TEST_CASE("summarize: entries are sorted by name lexicographically") {
    auto entries = summarize(
        {{"zeta", scalar(1.0)}, {"alpha", scalar(2.0)}, {"mu", scalar(3.0)}},
        {},
        {},
        {});
    REQUIRE(entries.size() == 3);
    CHECK(entries[0].name == "alpha");
    CHECK(entries[1].name == "mu");
    CHECK(entries[2].name == "zeta");
}

TEST_CASE("summarize: list-valued staged entry gets list preview") {
    auto entries = summarize(
        {{"veRow", list({75.0, 80.0, 85.0, 90.0, 95.0})}},
        {{"veRow", list({70.0, 75.0, 80.0, 85.0, 90.0})}},
        {},
        {});
    REQUIRE(entries.size() == 1);
    CHECK(entries[0].preview == "75.0, 80.0, 85.0, 90.0 ... (5 values)");
    CHECK(entries[0].before_preview == "70.0, 75.0, 80.0, 85.0 ... (5 values)");
}
