// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/chart_axes.hpp"

namespace ca = tuner_core::chart_axes;

TEST_CASE("chart_axes::nice_ceiling — landings on 1/2/5/10 × 10^n") {
    // Exact-match boundaries.
    CHECK(ca::nice_ceiling(1.0) == doctest::Approx(1.0));
    CHECK(ca::nice_ceiling(2.0) == doctest::Approx(2.0));
    CHECK(ca::nice_ceiling(5.0) == doctest::Approx(5.0));
    CHECK(ca::nice_ceiling(10.0) == doctest::Approx(10.0));
    CHECK(ca::nice_ceiling(20.0) == doctest::Approx(20.0));
    CHECK(ca::nice_ceiling(50.0) == doctest::Approx(50.0));

    // Just-above-boundary rounds up to next tier.
    CHECK(ca::nice_ceiling(1.01) == doctest::Approx(2.0));
    CHECK(ca::nice_ceiling(2.01) == doctest::Approx(5.0));
    CHECK(ca::nice_ceiling(5.01) == doctest::Approx(10.0));

    // Between boundaries rounds to containing tier.
    CHECK(ca::nice_ceiling(1.5) == doctest::Approx(2.0));
    CHECK(ca::nice_ceiling(3.0) == doctest::Approx(5.0));
    CHECK(ca::nice_ceiling(7.0) == doctest::Approx(10.0));

    // Large values.
    CHECK(ca::nice_ceiling(87.0)   == doctest::Approx(100.0));
    CHECK(ca::nice_ceiling(1234.0) == doctest::Approx(2000.0));
    CHECK(ca::nice_ceiling(4999.0) == doctest::Approx(5000.0));
    CHECK(ca::nice_ceiling(5001.0) == doctest::Approx(10000.0));

    // Small values.
    CHECK(ca::nice_ceiling(0.3)   == doctest::Approx(0.5));
    CHECK(ca::nice_ceiling(0.03)  == doctest::Approx(0.05));
    CHECK(ca::nice_ceiling(0.001) == doctest::Approx(0.001));
}

TEST_CASE("chart_axes::nice_ceiling — non-positive inputs") {
    // Zero and negatives return 1.0 so downstream division never
    // produces a zero or negative axis span.
    CHECK(ca::nice_ceiling(0.0)   == doctest::Approx(1.0));
    CHECK(ca::nice_ceiling(-1.0)  == doctest::Approx(1.0));
    CHECK(ca::nice_ceiling(-999.0) == doctest::Approx(1.0));
}

TEST_CASE("chart_axes::nice_ceiling — always >= input for positive v") {
    const double samples[] = {
        0.17, 0.5, 1.0, 1.9, 2.5, 4.2, 7.8, 15.0, 42.0,
        99.9, 100.0, 333.0, 1000.0, 1500.0, 9999.0, 12345.0,
    };
    for (double v : samples) {
        CHECK(ca::nice_ceiling(v) >= v);
    }
}

TEST_CASE("chart_axes::rpm_tick_step — three-tier breakpoints") {
    // Sub-3000 spans want finer ticks.
    CHECK(ca::rpm_tick_step(500.0)  == doctest::Approx(500.0));
    CHECK(ca::rpm_tick_step(1500.0) == doctest::Approx(500.0));
    CHECK(ca::rpm_tick_step(2999.0) == doctest::Approx(500.0));

    // Mid-range spans default to 1000.
    CHECK(ca::rpm_tick_step(3000.0) == doctest::Approx(1000.0));
    CHECK(ca::rpm_tick_step(5000.0) == doctest::Approx(1000.0));
    CHECK(ca::rpm_tick_step(8000.0) == doctest::Approx(1000.0));

    // Large spans want coarser ticks to avoid label crowding.
    CHECK(ca::rpm_tick_step(8001.0)  == doctest::Approx(2000.0));
    CHECK(ca::rpm_tick_step(12000.0) == doctest::Approx(2000.0));
}
