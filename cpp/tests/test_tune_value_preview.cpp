// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::tune_value_preview.

#include "doctest.h"

#include "tuner_core/tune_value_preview.hpp"

#include <vector>

using namespace tuner_core::tune_value_preview;

TEST_CASE("scalar repr matches Python str(float) for whole-number floats") {
    CHECK(format_scalar_python_repr(0.0) == "0.0");
    CHECK(format_scalar_python_repr(1.0) == "1.0");
    CHECK(format_scalar_python_repr(-2.0) == "-2.0");
    CHECK(format_scalar_python_repr(100.0) == "100.0");
}

TEST_CASE("scalar repr matches Python str(float) for fractional values") {
    CHECK(format_scalar_python_repr(0.5) == "0.5");
    CHECK(format_scalar_python_repr(3.14) == "3.14");
    CHECK(format_scalar_python_repr(-1.25) == "-1.25");
}

TEST_CASE("scalar repr handles small values without scientific notation") {
    CHECK(format_scalar_python_repr(0.1) == "0.1");
}

TEST_CASE("list preview joins first 4 items with comma-space") {
    std::vector<double> v{1.0, 2.0, 3.0};
    CHECK(format_list_preview(v) == "1.0, 2.0, 3.0");
}

TEST_CASE("list preview truncates after 4 items with values count suffix") {
    std::vector<double> v{1.0, 2.0, 3.0, 4.0, 5.0, 6.0};
    CHECK(format_list_preview(v) == "1.0, 2.0, 3.0, 4.0 ... (6 values)");
}

TEST_CASE("list preview shows exactly 4 items with no suffix") {
    std::vector<double> v{1.0, 2.0, 3.0, 4.0};
    CHECK(format_list_preview(v) == "1.0, 2.0, 3.0, 4.0");
}

TEST_CASE("list preview empty produces empty string") {
    std::vector<double> v;
    CHECK(format_list_preview(v).empty());
}

TEST_CASE("format_value_preview dispatches scalar arm") {
    CHECK(format_value_preview(ScalarOrList{2.5}) == "2.5");
}

TEST_CASE("format_value_preview dispatches list arm") {
    std::vector<double> v{1.0, 2.0};
    CHECK(format_value_preview(ScalarOrList{v}) == "1.0, 2.0");
}
