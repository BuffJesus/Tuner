// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/datalog_profile.hpp"

namespace dp = tuner_core::datalog_profile;

TEST_SUITE("datalog_profile") {

TEST_CASE("default_profile with no defs returns empty Default") {
    auto p = dp::default_profile({});
    CHECK(p.name == "Default");
    CHECK(p.channels.empty());
}

TEST_CASE("default_profile orders by priority") {
    std::vector<dp::ChannelDef> defs = {
        {"advance", "Timing Advance", "deg", 1},
        {"rpm", "RPM", "RPM", 0},
        {"zzOther", "Other", "", std::nullopt},
        {"map", "MAP", "kPa", 0},
    };
    auto p = dp::default_profile(defs);
    REQUIRE(p.channels.size() == 4);
    CHECK(p.channels[0].name == "rpm");
    CHECK(p.channels[1].name == "map");
    CHECK(p.channels[2].name == "advance");
    CHECK(p.channels[3].name == "zzOther");
}

TEST_CASE("priority_rank for known prefixes") {
    CHECK(dp::priority_rank("rpm") == 0);
    CHECK(dp::priority_rank("RPM") == 0);  // case-insensitive
    CHECK(dp::priority_rank("map") == 1);
    CHECK(dp::priority_rank("tps") == 2);
    CHECK(dp::priority_rank("unknownChannel") > 10);
}

TEST_CASE("serialize and deserialize round-trip") {
    dp::Profile p;
    p.name = "Test";
    p.channels = {
        {"rpm", "RPM", "RPM", true, 0},
        {"map", "MAP", "kPa", false, 1},
    };
    std::string json = dp::serialize_profile(p);
    auto p2 = dp::deserialize_profile(json);
    CHECK(p2.name == "Test");
    REQUIRE(p2.channels.size() == 2);
    CHECK(p2.channels[0].name == "rpm");
    CHECK(p2.channels[0].enabled == true);
    CHECK(p2.channels[1].name == "map");
    CHECK(p2.channels[1].enabled == false);
    CHECK(p2.channels[1].format_digits.value() == 1);
}

TEST_CASE("collection serialize and deserialize") {
    dp::Profile p1; p1.name = "Default"; p1.channels = {{"rpm", "RPM", "", true, std::nullopt}};
    dp::Profile p2; p2.name = "Detail"; p2.channels = {{"afr", "AFR", "", true, 2}};
    std::string json = dp::serialize_collection({p1, p2}, "Detail");
    auto [profiles, active] = dp::deserialize_collection(json);
    CHECK(active == "Detail");
    REQUIRE(profiles.size() == 2);
    CHECK(profiles[0].name == "Default");
    CHECK(profiles[1].name == "Detail");
}

TEST_CASE("deserialize invalid JSON returns default") {
    auto p = dp::deserialize_profile("NOT JSON!");
    CHECK(p.name == "Default");
    CHECK(p.channels.empty());
}

TEST_CASE("unavailable_channels finds missing") {
    dp::Profile p;
    p.channels = {
        {"rpm", "", "", true, std::nullopt},
        {"map", "", "", true, std::nullopt},
        {"ghost", "", "", true, std::nullopt},
        {"disabled", "", "", false, std::nullopt},
    };
    auto missing = dp::unavailable_channels(p, {"rpm", "map"});
    REQUIRE(missing.size() == 1);
    CHECK(missing[0] == "ghost");
}

TEST_CASE("enabled_channels filters correctly") {
    dp::Profile p;
    p.channels = {
        {"rpm", "", "", true, std::nullopt},
        {"map", "", "", false, std::nullopt},
        {"tps", "", "", true, std::nullopt},
    };
    auto enabled = p.enabled_channels();
    CHECK(enabled.size() == 2);
    CHECK(enabled[0].name == "rpm");
    CHECK(enabled[1].name == "tps");
}

}  // TEST_SUITE
