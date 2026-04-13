// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::visibility_expression.

#include "doctest.h"

#include "tuner_core/visibility_expression.hpp"

using tuner_core::visibility_expression::evaluate;
using tuner_core::visibility_expression::ValueMap;
using tuner_core::visibility_expression::ArrayMap;

TEST_CASE("empty expression is true") {
    ValueMap v;
    CHECK(evaluate("", v) == true);
    CHECK(evaluate("{}", v) == true);
    CHECK(evaluate("   ", v) == true);
}

TEST_CASE("brace stripping leaves the inner expression") {
    ValueMap v{{"x", 1.0}};
    CHECK(evaluate("{x}", v) == true);
    CHECK(evaluate("{ x == 1 }", v) == true);
}

TEST_CASE("simple equality comparisons") {
    ValueMap v{{"fuelAlgorithm", 1.0}};
    CHECK(evaluate("fuelAlgorithm == 1", v) == true);
    CHECK(evaluate("fuelAlgorithm == 2", v) == false);
    CHECK(evaluate("fuelAlgorithm != 1", v) == false);
}

TEST_CASE("greater/less comparisons") {
    ValueMap v{{"rpm", 5500.0}};
    CHECK(evaluate("rpm > 5000", v) == true);
    CHECK(evaluate("rpm < 5000", v) == false);
    CHECK(evaluate("rpm >= 5500", v) == true);
    CHECK(evaluate("rpm <= 5499", v) == false);
}

TEST_CASE("logical and/or") {
    ValueMap v{{"a", 1.0}, {"b", 0.0}, {"c", 1.0}};
    CHECK(evaluate("a && b", v) == false);
    CHECK(evaluate("a || b", v) == true);
    CHECK(evaluate("a && c", v) == true);
    CHECK(evaluate("b || (a && c)", v) == true);
}

TEST_CASE("logical not") {
    ValueMap v{{"x", 0.0}};
    CHECK(evaluate("!x", v) == true);
    CHECK(evaluate("!!x", v) == false);
}

TEST_CASE("unknown identifier defaults to 0") {
    ValueMap v;
    CHECK(evaluate("missing > 0", v) == false);
    CHECK(evaluate("missing == 0", v) == true);
}

TEST_CASE("dotted identifiers are tokenized as one") {
    ValueMap v{{"foo.bar.baz", 5.0}};
    CHECK(evaluate("foo.bar.baz > 4", v) == true);
}

TEST_CASE("parenthesized expressions") {
    ValueMap v{{"a", 1.0}, {"b", 1.0}, {"c", 0.0}};
    CHECK(evaluate("(a || c) && b", v) == true);
    CHECK(evaluate("a && (b || c) && (b)", v) == true);
}

TEST_CASE("arrayValue with array. prefix") {
    ValueMap v;
    ArrayMap arrays{{"someArr", {10.0, 20.0, 30.0}}};
    CHECK(evaluate("arrayValue(array.someArr, 1) == 20", v, &arrays) == true);
    CHECK(evaluate("arrayValue(someArr, 2) > 25", v, &arrays) == true);
    CHECK(evaluate("arrayValue(someArr, 99)", v, &arrays) == false);
}

TEST_CASE("arrayValue with no arrays map returns 0") {
    ValueMap v;
    CHECK(evaluate("arrayValue(array.x, 0)", v) == false);
    CHECK(evaluate("arrayValue(array.x, 0) == 0", v) == true);
}

TEST_CASE("unknown function fails safe to 0") {
    ValueMap v;
    CHECK(evaluate("unknownFn(1, 2, 3) > 0", v) == false);
    CHECK(evaluate("unknownFn(nested(1)) == 0", v) == true);
}

TEST_CASE("number literals decimal") {
    ValueMap v;
    CHECK(evaluate("3.14 > 3", v) == true);
    CHECK(evaluate("0.5 < 1", v) == true);
}

TEST_CASE("malformed expression fails open to true") {
    ValueMap v;
    // Missing operand after operator — fail-open returns true so the
    // field stays visible.
    CHECK(evaluate("x ==", v) == true);
}
