// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::sample_gate_helpers.

#include "doctest.h"

#include "tuner_core/sample_gate_helpers.hpp"

using namespace tuner_core::sample_gate_helpers;

TEST_CASE("normalise_operator rewrites = to ==") {
    CHECK(normalise_operator("=") == "==");
    CHECK(normalise_operator("==") == "==");
    CHECK(normalise_operator(" < ") == "<");
}

TEST_CASE("apply_operator dispatches every supported operator") {
    CHECK(apply_operator(5.0, "<", 10.0));
    CHECK(apply_operator(10.0, ">", 5.0));
    CHECK(apply_operator(5.0, "<=", 5.0));
    CHECK(apply_operator(5.0, ">=", 5.0));
    CHECK(apply_operator(5.0, "==", 5.0));
    CHECK(apply_operator(5.0, "!=", 6.0));
    CHECK(apply_operator(0x12, "&", 0x10));
    CHECK_FALSE(apply_operator(0x10, "&", 0x01));
}

TEST_CASE("apply_operator returns false for unknown operator") {
    CHECK_FALSE(apply_operator(1.0, "??", 2.0));
}

TEST_CASE("apply_operator accepts = as alias for ==") {
    CHECK(apply_operator(5.0, "=", 5.0));
}

TEST_CASE("resolve_channel finds an alias substring match") {
    ValueMap v{{"rpm", 5500.0}, {"clt", 90.0}};
    auto rpm = resolve_channel("rpm", v);
    REQUIRE(rpm.has_value());
    CHECK(*rpm == 5500.0);
    auto clt = resolve_channel("coolant", v);
    REQUIRE(clt.has_value());
    CHECK(*clt == 90.0);
}

TEST_CASE("resolve_channel returns nullopt when nothing matches") {
    ValueMap v{{"rpm", 5500.0}};
    CHECK_FALSE(resolve_channel("coolant", v).has_value());
}

TEST_CASE("resolve_channel falls back through multi-alias entries") {
    ValueMap v{{"egoCorrection", 1.0}};
    // 'ego' aliases to (ego, afr, lambda) — first 'ego' substring wins.
    auto v_ego = resolve_channel("ego", v);
    REQUIRE(v_ego.has_value());
    CHECK(*v_ego == 1.0);
}

TEST_CASE("resolve_channel returns the first matching record key") {
    ValueMap v{
        {"map1", 100.0},
        {"map2", 200.0},
    };
    auto m = resolve_channel("map", v);
    REQUIRE(m.has_value());
    CHECK(*m == 100.0);  // insertion order preserved
}

TEST_CASE("lambda_value prefers an explicit lambda channel") {
    ValueMap v{{"afr", 14.7}, {"lambda", 1.05}};
    auto l = lambda_value(v);
    REQUIRE(l.has_value());
    CHECK(*l == 1.05);
}

TEST_CASE("lambda_value falls back to AFR / 14.7") {
    ValueMap v{{"egoAfr", 12.5}};
    auto l = lambda_value(v);
    REQUIRE(l.has_value());
    CHECK(*l == doctest::Approx(12.5 / 14.7));
}

TEST_CASE("afr_value prefers an explicit AFR channel") {
    ValueMap v{{"lambda", 1.0}, {"afr", 14.7}};
    auto a = afr_value(v);
    REQUIRE(a.has_value());
    // Insertion order: lambda is first, gets multiplied by 14.7
    CHECK(*a == doctest::Approx(1.0 * 14.7));
}

TEST_CASE("afr_value with only lambda derives via × 14.7") {
    ValueMap v{{"lambda", 0.95}};
    auto a = afr_value(v);
    REQUIRE(a.has_value());
    CHECK(*a == doctest::Approx(0.95 * 14.7));
}

TEST_CASE("lambda/afr_value return nullopt on empty input") {
    ValueMap v;
    CHECK_FALSE(lambda_value(v).has_value());
    CHECK_FALSE(afr_value(v).has_value());
}
