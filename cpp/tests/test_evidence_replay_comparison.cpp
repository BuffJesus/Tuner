// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::evidence_replay_comparison.

#include "doctest.h"

#include "tuner_core/evidence_replay_comparison.hpp"

#include <vector>

using namespace tuner_core::evidence_replay_comparison;

namespace {

Channel make_ch(std::string name, double value, std::string units = "") {
    Channel c;
    c.name = std::move(name);
    c.value = value;
    if (!units.empty()) c.units = std::move(units);
    return c;
}

}  // namespace

TEST_CASE("compare: empty inputs return nullopt") {
    auto r = compare_runtime_channels({}, {}, {});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("compare: identical channels return nullopt") {
    std::vector<Channel> baseline{make_ch("rpm", 5500.0)};
    std::vector<Channel> current{make_ch("rpm", 5500.0)};
    auto r = compare_runtime_channels(baseline, current, {});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("compare: single delta produces a result") {
    std::vector<Channel> baseline{make_ch("rpm", 5000.0, "rpm")};
    std::vector<Channel> current{make_ch("rpm", 5500.0, "rpm")};
    auto r = compare_runtime_channels(baseline, current, {});
    REQUIRE(r.has_value());
    REQUIRE(r->changed_channels.size() == 1);
    CHECK(r->changed_channels[0].name == "rpm");
    CHECK(r->changed_channels[0].previous_value == 5000.0);
    CHECK(r->changed_channels[0].current_value == 5500.0);
    CHECK(r->changed_channels[0].delta_value == 500.0);
    CHECK(r->changed_channels[0].units.value() == "rpm");
}

TEST_CASE("compare: top 4 by absolute delta") {
    std::vector<Channel> baseline{
        make_ch("a", 0.0), make_ch("b", 0.0), make_ch("c", 0.0),
        make_ch("d", 0.0), make_ch("e", 0.0), make_ch("f", 0.0),
    };
    std::vector<Channel> current{
        make_ch("a", 1.0),
        make_ch("b", 50.0),
        make_ch("c", -100.0),
        make_ch("d", 25.0),
        make_ch("e", 200.0),
        make_ch("f", 5.0),
    };
    auto r = compare_runtime_channels(baseline, current, {});
    REQUIRE(r.has_value());
    REQUIRE(r->changed_channels.size() == 4);
    CHECK(r->changed_channels[0].name == "e");  // 200
    CHECK(r->changed_channels[1].name == "c");  // -100 → 100
    CHECK(r->changed_channels[2].name == "b");  // 50
    CHECK(r->changed_channels[3].name == "d");  // 25
}

TEST_CASE("compare: case-insensitive name matching") {
    std::vector<Channel> baseline{make_ch("RPM", 5000.0)};
    std::vector<Channel> current{make_ch("rpm", 5500.0)};
    auto r = compare_runtime_channels(baseline, current, {"rpm"});
    REQUIRE(r.has_value());
    CHECK(r->changed_channels.size() == 1);
}

TEST_CASE("compare: missing channels are skipped") {
    std::vector<Channel> baseline{make_ch("rpm", 5000.0)};
    std::vector<Channel> current{make_ch("clt", 90.0)};
    auto r = compare_runtime_channels(baseline, current, {});
    CHECK_FALSE(r.has_value());  // no overlap → no deltas
}

TEST_CASE("compare: tiny deltas below 1e-9 are filtered") {
    std::vector<Channel> baseline{make_ch("rpm", 5000.0)};
    std::vector<Channel> current{make_ch("rpm", 5000.0 + 1e-12)};
    auto r = compare_runtime_channels(baseline, current, {});
    CHECK_FALSE(r.has_value());
}

TEST_CASE("compare: relevant_channel_names filters output") {
    std::vector<Channel> baseline{make_ch("rpm", 5000.0), make_ch("clt", 80.0)};
    std::vector<Channel> current{make_ch("rpm", 5500.0), make_ch("clt", 90.0)};
    auto r = compare_runtime_channels(baseline, current, {"rpm"});
    REQUIRE(r.has_value());
    REQUIRE(r->changed_channels.size() == 1);
    CHECK(r->changed_channels[0].name == "rpm");
}

TEST_CASE("compare: detail text formats with sign and units") {
    std::vector<Channel> baseline{make_ch("rpm", 5000.0, "rpm")};
    std::vector<Channel> current{make_ch("rpm", 5500.0, "rpm")};
    auto r = compare_runtime_channels(baseline, current, {});
    REQUIRE(r.has_value());
    CHECK(r->summary_text ==
          "Comparison vs latest capture highlights runtime drift on this page.");
    CHECK(r->detail_text.find("rpm +500.0 rpm") != std::string::npos);
}

TEST_CASE("compare: units fall back from current to baseline when current is empty") {
    std::vector<Channel> baseline{make_ch("rpm", 5000.0, "rpm")};
    std::vector<Channel> current{make_ch("rpm", 5500.0)};
    auto r = compare_runtime_channels(baseline, current, {});
    REQUIRE(r.has_value());
    CHECK(r->changed_channels[0].units.value() == "rpm");
}
