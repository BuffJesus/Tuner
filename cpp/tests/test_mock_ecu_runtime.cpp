// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/mock_ecu_runtime.hpp"

namespace mer = tuner_core::mock_ecu_runtime;

TEST_SUITE("mock_ecu_runtime") {

TEST_CASE("poll produces expected channels") {
    mer::MockEcu ecu;
    auto snap = ecu.poll();
    CHECK(snap.channels.count("rpm"));
    CHECK(snap.channels.count("map"));
    CHECK(snap.channels.count("afr"));
    CHECK(snap.channels.count("clt"));
    CHECK(snap.channels.count("batt"));
    CHECK(snap.channels.size() == 12);
}

TEST_CASE("rpm is in plausible range") {
    mer::MockEcu ecu;
    for (int i = 0; i < 100; ++i) {
        auto snap = ecu.poll();
        double rpm = snap.get("rpm");
        CHECK(rpm >= 600);
        CHECK(rpm <= 8000);
    }
}

TEST_CASE("afr stays in plausible range") {
    mer::MockEcu ecu;
    for (int i = 0; i < 200; ++i) {
        auto snap = ecu.poll();
        double afr = snap.get("afr");
        CHECK(afr >= 10.0);
        CHECK(afr <= 18.0);
    }
}

TEST_CASE("clt warms up over time") {
    mer::MockEcu ecu;
    auto first = ecu.poll();
    for (int i = 0; i < 400; ++i) ecu.poll();
    auto later = ecu.poll();
    CHECK(later.get("clt") > first.get("clt"));
}

TEST_CASE("deterministic with same seed") {
    mer::MockEcu ecu1(42), ecu2(42);
    for (int i = 0; i < 50; ++i) {
        auto s1 = ecu1.poll(), s2 = ecu2.poll();
        CHECK(s1.get("rpm") == s2.get("rpm"));
        CHECK(s1.get("afr") == s2.get("afr"));
    }
}

TEST_CASE("different seeds produce different values") {
    mer::MockEcu ecu1(1), ecu2(999);
    auto s1 = ecu1.poll(), s2 = ecu2.poll();
    // At least one channel should differ (jitter is seed-dependent).
    bool any_diff = false;
    for (const auto& [k, v] : s1.channels) {
        if (v != s2.get(k)) { any_diff = true; break; }
    }
    CHECK(any_diff);
}

}  // TEST_SUITE
