// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/msq_value_formatter.hpp"

namespace mvf = tuner_core::msq_value_formatter;

TEST_SUITE("msq_value_formatter") {

TEST_CASE("format_scalar integer") {
    CHECK(mvf::format_scalar(42.0) == "42");
    CHECK(mvf::format_scalar(0.0) == "0");
    CHECK(mvf::format_scalar(-5.0) == "-5");
    CHECK(mvf::format_scalar(255.0) == "255");
}

TEST_CASE("format_scalar decimal") {
    CHECK(mvf::format_scalar(6.1) == "6.1");
    CHECK(mvf::format_scalar(14.7) == "14.7");
    CHECK(mvf::format_scalar(0.001) == "0.001");
}

TEST_CASE("format_value string passthrough") {
    mvf::Value v = std::string("hello");
    CHECK(mvf::format_value(v) == "hello");
}

TEST_CASE("format_value double") {
    mvf::Value v = 6.1;
    CHECK(mvf::format_value(v) == "6.1");
}

TEST_CASE("format_value integer double") {
    mvf::Value v = 42.0;
    CHECK(mvf::format_value(v) == "42");
}

TEST_CASE("format_value table 4x4") {
    std::vector<double> vals;
    for (int i = 0; i < 16; ++i) vals.push_back(static_cast<double>(i * 5));
    mvf::Value v = vals;
    auto text = mvf::format_value(v, 4, 4);
    CHECK(text.find("0 5 10 15") != std::string::npos);
    CHECK(text.find("20 25 30 35") != std::string::npos);
}

TEST_CASE("format_value 1D list") {
    mvf::Value v = std::vector<double>{100, 120, 140, 160};
    auto text = mvf::format_value(v, 4, 1);
    CHECK(text.find("100") != std::string::npos);
    CHECK(text.find("160") != std::string::npos);
}

TEST_CASE("format_value empty list") {
    mvf::Value v = std::vector<double>{};
    CHECK(mvf::format_value(v) == "");
}

TEST_CASE("format_scalar large integer") {
    CHECK(mvf::format_scalar(7200.0) == "7200");
    CHECK(mvf::format_scalar(65535.0) == "65535");
}

TEST_CASE("format_scalar negative decimal") {
    CHECK(mvf::format_scalar(-2.5) == "-2.5");
}

}  // TEST_SUITE
