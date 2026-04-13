// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::curve_page_classifier.

#include "doctest.h"

#include "tuner_core/curve_page_classifier.hpp"

using namespace tuner_core::curve_page_classifier;

// ---------------------------------------------------------------------------
// classify
// ---------------------------------------------------------------------------

// Note on keyword matching: the Python service uses `\bkw\b`
// (word-boundary) regex, so a keyword only matches when it appears as
// a standalone word in `name + " " + title`. `crank_curve` does NOT
// match `\bcrank\b` (the `_` is a word char). Real curve titles use
// space-separated words.

TEST_CASE("classify: fuel keywords land in fuel group") {
    auto g = classify("primingCurve", "Fuel Priming");
    CHECK(g.order == 10);
    CHECK(g.group_id == "fuel");
    CHECK(g.group_title == "Fuel");
}

TEST_CASE("classify: ignition keywords land in ignition group") {
    auto g = classify("dwellCurve", "Dwell vs Battery");
    CHECK(g.group_id == "ignition");
}

TEST_CASE("classify: AFR keywords") {
    auto g = classify("afrCurve", "AFR Target");
    CHECK(g.group_id == "afr");
}

TEST_CASE("classify: idle keyword (without 'advance' which lands in ignition)") {
    auto g = classify("idleCurve", "Idle Curve");
    CHECK(g.group_id == "idle");
}

TEST_CASE("classify: enrich/warmup keywords") {
    auto g1 = classify("wueCurve", "Warmup Enrichment");
    // 'warmup' matches as a standalone word; 'enrichment' does NOT
    // match `\benrich\b` because of the trailing word characters.
    CHECK(g1.group_id == "enrich");
    auto g2 = classify("crankCurve", "Crank Curve");
    CHECK(g2.group_id == "enrich");
}

TEST_CASE("classify: boost / vvt keywords") {
    auto g = classify("boostCurve", "Boost Target");
    CHECK(g.group_id == "boost");
}

TEST_CASE("classify: settings keywords") {
    auto g = classify("oilCurve", "Oil Pressure Protection");
    CHECK(g.group_id == "settings");
}

TEST_CASE("classify: unknown text falls through to 'other'") {
    auto g = classify("xxx", "yyy");
    CHECK(g.order == 99);
    CHECK(g.group_id == "other");
    CHECK(g.group_title == "Other");
}

TEST_CASE("classify: word boundary requires standalone keyword") {
    auto g = classify("rpmlimitCurve", "RPM Limit");
    // 'limit' in the title is preceded by space and followed by end-of-string
    // → both word boundaries fire → matches the settings rule.
    CHECK(g.group_id == "settings");
}

TEST_CASE("classify: fuel takes precedence over later groups") {
    // Both "fuel" and "boost" appear as standalone words; fuel rule
    // comes first (order 10) so it wins.
    auto g = classify("boostCurve", "Boost Fuel Curve");
    CHECK(g.group_id == "fuel");
}

// ---------------------------------------------------------------------------
// summary
// ---------------------------------------------------------------------------

TEST_CASE("summary: 1D curve with no live channel") {
    CHECK(summary(1, "") == "Curve \xc2\xb7 1D");
}

TEST_CASE("summary: multi-line curve count") {
    CHECK(summary(3, "") == "Curve \xc2\xb7 3 lines");
}

TEST_CASE("summary: live channel suffix") {
    CHECK(summary(1, "rpm") == "Curve \xc2\xb7 1D \xc2\xb7 live: rpm");
}

TEST_CASE("summary: multi-line plus live channel") {
    CHECK(summary(2, "coolant") == "Curve \xc2\xb7 2 lines \xc2\xb7 live: coolant");
}
