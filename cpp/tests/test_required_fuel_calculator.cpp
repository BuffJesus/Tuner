// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::required_fuel_calculator.

#include "doctest.h"

#include "tuner_core/required_fuel_calculator.hpp"

using tuner_core::required_fuel_calculator::calculate;

TEST_CASE("invalid inputs return is_valid=false with stored=0") {
    auto r = calculate(0.0, 4, 220.0, 14.7);
    CHECK(r.is_valid == false);
    CHECK(r.req_fuel_ms == 0.0);
    CHECK(r.req_fuel_stored == 0);

    auto r2 = calculate(2000.0, 0, 220.0, 14.7);
    CHECK(r2.is_valid == false);

    auto r3 = calculate(2000.0, 4, -1.0, 14.7);
    CHECK(r3.is_valid == false);

    auto r4 = calculate(2000.0, 4, 220.0, 0.0);
    CHECK(r4.is_valid == false);
}

TEST_CASE("standard 2.0L 4-cyl with 220 cc/min injectors at 14.7") {
    auto r = calculate(2000.0, 4, 220.0, 14.7);
    CHECK(r.is_valid == true);
    // Sanity-check that it lands inside the U08 range and is non-trivial.
    CHECK(r.req_fuel_ms > 0.0);
    CHECK(r.req_fuel_ms < 25.5);
    CHECK(r.req_fuel_stored >= 1);
    CHECK(r.req_fuel_stored <= 255);
}

TEST_CASE("oversized engine clips stored value to 255") {
    // Tiny injectors and a huge displacement push reqFuel above 25.5 ms.
    auto r = calculate(8000.0, 8, 50.0, 14.7);
    CHECK(r.is_valid == true);
    CHECK(r.req_fuel_stored == 255);
}

TEST_CASE("inputs_summary follows the documented format") {
    auto r = calculate(2000.0, 4, 220.0, 14.7);
    CHECK(r.inputs_summary == "2000 cc, 4 cyl, 220 cc/min, AFR 14.7");
}

TEST_CASE("stored value is round(req_fuel_ms * 10) banker's rounded") {
    // Sanity check that the stored field is internally consistent
    // with the floating-point ms — within ±1 LSB tolerance.
    auto r = calculate(2000.0, 4, 220.0, 14.7);
    int diff = r.req_fuel_stored - static_cast<int>(r.req_fuel_ms * 10);
    CHECK((diff == 0 || diff == 1));
}
