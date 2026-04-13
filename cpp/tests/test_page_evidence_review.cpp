// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/page_evidence_review.hpp"

namespace per = tuner_core::page_evidence_review;
namespace er = tuner_core::evidence_replay;

TEST_SUITE("page_evidence_review") {

TEST_CASE("null evidence returns nullopt") {
    per::PageContext ctx; ctx.page_title = "VE Table";
    auto result = per::build(ctx, nullptr);
    CHECK_FALSE(result.has_value());
}

TEST_CASE("no matching channels returns empty-channel snapshot") {
    er::Snapshot snap;
    snap.runtime_channels = {{"unknownSensor", 42.0, "?"}};
    per::PageContext ctx; ctx.page_title = "VE Table";
    auto result = per::build(ctx, &snap);
    REQUIRE(result.has_value());
    CHECK(result->relevant_channels.empty());
    CHECK(result->summary_text.find("no page-relevant") != std::string::npos);
}

TEST_CASE("fuel page selects AFR and lambda channels") {
    er::Snapshot snap;
    snap.runtime_channels = {
        {"rpm", 2500, "RPM"}, {"map", 95, "kPa"}, {"afr1", 14.2, ""},
        {"advance", 22, "deg"}, {"randomSensor", 1, ""},
    };
    per::PageContext ctx;
    ctx.page_title = "VE Table";
    ctx.group_id = "fuel";
    auto result = per::build(ctx, &snap);
    REQUIRE(result.has_value());
    CHECK(result->relevant_channels.size() >= 3);
    // rpm, map, afr1 should all be selected.
    bool has_rpm = false, has_map = false, has_afr = false;
    for (const auto& ch : result->relevant_channels) {
        if (ch.name == "rpm") has_rpm = true;
        if (ch.name == "map") has_map = true;
        if (ch.name == "afr1") has_afr = true;
    }
    CHECK(has_rpm); CHECK(has_map); CHECK(has_afr);
}

TEST_CASE("ignition group selects advance and dwell") {
    er::Snapshot snap;
    snap.runtime_channels = {
        {"rpm", 3000, "RPM"}, {"advance", 28, "deg"}, {"dwell", 3.5, "ms"},
        {"afr1", 14.7, ""}, {"battery", 13.8, "V"},
    };
    per::PageContext ctx;
    ctx.page_title = "Spark Table";
    ctx.group_id = "ignition";
    auto result = per::build(ctx, &snap);
    REQUIRE(result.has_value());
    bool has_advance = false, has_dwell = false;
    for (const auto& ch : result->relevant_channels) {
        if (ch.name == "advance") has_advance = true;
        if (ch.name == "dwell") has_dwell = true;
    }
    CHECK(has_advance); CHECK(has_dwell);
}

TEST_CASE("channel cap at 6") {
    er::Snapshot snap;
    for (int i = 0; i < 20; ++i) {
        snap.runtime_channels.push_back({"rpm" + std::to_string(i), double(i), ""});
    }
    per::PageContext ctx; ctx.page_title = "Everything";
    auto result = per::build(ctx, &snap);
    REQUIRE(result.has_value());
    CHECK(result->relevant_channels.size() <= 6);
}

TEST_CASE("summary text includes page title and count") {
    er::Snapshot snap;
    snap.runtime_channels = {{"rpm", 2500, "RPM"}, {"map", 95, "kPa"}};
    snap.runtime_age_seconds = 2.5;
    per::PageContext ctx; ctx.page_title = "VE Table";
    auto result = per::build(ctx, &snap);
    REQUIRE(result.has_value());
    CHECK(result->summary_text.find("VE Table") != std::string::npos);
    CHECK(result->summary_text.find("2 relevant") != std::string::npos);
    CHECK(result->summary_text.find("ago") != std::string::npos);
}

TEST_CASE("parameter name hints add channels") {
    er::Snapshot snap;
    snap.runtime_channels = {
        {"rpm", 2500, ""}, {"clt", 85, "C"}, {"iat", 30, "C"},
    };
    per::PageContext ctx;
    ctx.page_title = "Settings";
    ctx.parameter_names = {"cltBias"};  // "clt" hint
    auto result = per::build(ctx, &snap);
    REQUIRE(result.has_value());
    bool has_clt = false;
    for (const auto& ch : result->relevant_channels) {
        if (ch.name == "clt") has_clt = true;
    }
    CHECK(has_clt);
}

}  // TEST_SUITE
