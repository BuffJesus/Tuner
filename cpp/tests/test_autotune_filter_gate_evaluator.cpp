// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::autotune_filter_gate_evaluator.

#include "doctest.h"

#include "tuner_core/autotune_filter_gate_evaluator.hpp"

#include <vector>

using namespace tuner_core::autotune_filter_gate_evaluator;
using ValueMap = tuner_core::sample_gate_helpers::ValueMap;

namespace {

Gate make_gate(std::string name) {
    Gate g;
    g.name = std::move(name);
    g.default_enabled = true;
    return g;
}

Gate make_parametric(std::string name, std::string channel, std::string op, double thr) {
    Gate g;
    g.name = std::move(name);
    g.channel = std::move(channel);
    g.op = std::move(op);
    g.threshold = thr;
    g.default_enabled = true;
    return g;
}

}  // namespace

TEST_CASE("disabled-by-default gate is a pass-through") {
    Gate g = make_parametric("custom", "rpm", ">", 5000.0);
    g.default_enabled = false;
    ValueMap v{{"rpm", 6000.0}};  // would otherwise reject
    auto r = evaluate(g, v);
    CHECK(r.accepted == true);
}

TEST_CASE("std_Custom is a pass-through even when enabled") {
    auto g = make_gate("std_Custom");
    ValueMap v;
    auto r = evaluate(g, v);
    CHECK(r.accepted == true);
}

TEST_CASE("std_DeadLambda accepts a plausible lambda reading") {
    auto g = make_gate("std_DeadLambda");
    ValueMap v{{"lambda1", 1.05}};
    auto r = evaluate(g, v);
    CHECK(r.accepted == true);
}

TEST_CASE("std_DeadLambda rejects when lambda is missing") {
    auto g = make_gate("std_DeadLambda");
    ValueMap v{{"rpm", 5500.0}};
    auto r = evaluate(g, v);
    CHECK(r.accepted == false);
    CHECK(r.reason == "no lambda/AFR channel present");
}

TEST_CASE("std_DeadLambda rejects when lambda is out of range") {
    auto g = make_gate("std_DeadLambda");
    ValueMap v{{"lambda", 0.3}};
    auto r = evaluate(g, v);
    CHECK(r.accepted == false);
    CHECK(r.reason.find("outside plausible range") != std::string::npos);
}

TEST_CASE("std_DeadLambda derives lambda from AFR") {
    auto g = make_gate("std_DeadLambda");
    ValueMap v{{"afr1", 14.7}};  // → lambda 1.0
    auto r = evaluate(g, v);
    CHECK(r.accepted == true);
}

TEST_CASE("std_xAxisMin rejects below the minimum") {
    auto g = make_gate("std_xAxisMin");
    AxisContext axis;
    axis.x_value = 100.0;
    axis.x_min = 200.0;
    ValueMap v;
    auto r = evaluate(g, v, &axis);
    CHECK(r.accepted == false);
    CHECK(r.reason.find("X value 100.0 below axis min 200.0") != std::string::npos);
}

TEST_CASE("std_xAxisMin passes when no axis context is supplied") {
    auto g = make_gate("std_xAxisMin");
    ValueMap v;
    auto r = evaluate(g, v, nullptr);
    CHECK(r.accepted == true);
}

TEST_CASE("std_yAxisMax rejects above the maximum") {
    auto g = make_gate("std_yAxisMax");
    AxisContext axis;
    axis.y_value = 250.0;
    axis.y_max = 200.0;
    ValueMap v;
    auto r = evaluate(g, v, &axis);
    CHECK(r.accepted == false);
    CHECK(r.reason.find("above axis max") != std::string::npos);
}

TEST_CASE("parametric gate rejects when reject condition fires") {
    auto g = make_parametric("minRPM", "rpm", "<", 300.0);
    ValueMap v{{"rpm", 200.0}};
    auto r = evaluate(g, v);
    CHECK(r.accepted == false);
    CHECK(r.reason.find("rpm=200.0") != std::string::npos);
}

TEST_CASE("parametric gate passes when channel is missing from record") {
    auto g = make_parametric("minRPM", "rpm", "<", 300.0);
    ValueMap v;
    auto r = evaluate(g, v);
    CHECK(r.accepted == true);
}

TEST_CASE("evaluate_all stops at the first rejection when fail_fast=true") {
    std::vector<Gate> gates{
        make_parametric("minRPM", "rpm", "<", 300.0),
        make_parametric("maxRPM", "rpm", ">", 7000.0),
    };
    ValueMap v{{"rpm", 200.0}};
    auto results = evaluate_all(gates, v, nullptr, true);
    REQUIRE(results.size() == 1);
    CHECK(results[0].accepted == false);
}

TEST_CASE("evaluate_all evaluates all gates when fail_fast=false") {
    std::vector<Gate> gates{
        make_parametric("minRPM", "rpm", "<", 300.0),
        make_parametric("maxRPM", "rpm", ">", 7000.0),
    };
    ValueMap v{{"rpm", 200.0}};
    auto results = evaluate_all(gates, v, nullptr, false);
    REQUIRE(results.size() == 2);
    CHECK(results[0].accepted == false);
    CHECK(results[1].accepted == true);
}

TEST_CASE("gate_label returns explicit label when set") {
    Gate g = make_gate("std_DeadLambda");
    g.label = "My Custom Label";
    CHECK(gate_label(g) == "My Custom Label");
}

TEST_CASE("gate_label returns standard-gate label for known names") {
    Gate g = make_gate("std_xAxisMin");
    CHECK(gate_label(g) == "Below X-axis minimum");
}

TEST_CASE("gate_label falls back to gate name") {
    Gate g = make_gate("customGate");
    CHECK(gate_label(g) == "customGate");
}
