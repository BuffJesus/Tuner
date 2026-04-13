// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::replay_sample_gate.

#include "doctest.h"

#include "tuner_core/replay_sample_gate.hpp"

namespace rsg = tuner_core::replay_sample_gate;
using ValueMap = rsg::ValueMap;

TEST_CASE("default_gate_order matches Python priority sequence") {
    const auto& order = rsg::default_gate_order();
    REQUIRE(order.size() == 5);
    CHECK(order[0] == "std_DeadLambda");
    CHECK(order[1] == "accelFilter");
    CHECK(order[2] == "aseFilter");
    CHECK(order[3] == "minCltFilter");
    CHECK(order[4] == "overrunFilter");
}

TEST_CASE("evaluate_record rejects on missing lambda/AFR channel") {
    ValueMap rec = {{"rpm", 3000.0}, {"map", 80.0}};
    rsg::Config cfg;
    auto evals = rsg::evaluate_record(rec, cfg);
    REQUIRE(evals.size() == 1);
    CHECK(evals[0].gate_name == "std_DeadLambda");
    CHECK_FALSE(evals[0].accepted);
    CHECK(evals[0].reason == "no lambda/AFR channel in record");
}

TEST_CASE("evaluate_record accepts a clean record under defaults") {
    ValueMap rec = {
        {"rpm", 3000.0},
        {"afr", 14.7},
        {"coolant", 85.0},
        {"engine", 0.0},
        {"pulsewidth", 4.5},
    };
    rsg::Config cfg;
    auto evals = rsg::evaluate_record(rec, cfg);
    REQUIRE(evals.size() == 5);
    for (const auto& e : evals) CHECK(e.accepted);
    CHECK(rsg::is_accepted(rec, cfg));
    CHECK_FALSE(rsg::primary_rejection(rec, cfg).has_value());
}

TEST_CASE("evaluate_record fail-fast stops at first rejection") {
    // Cold engine: minCltFilter rejects. Order is dead_lambda → accel
    // → ase → minClt → overrun, so we expect 4 evals total with the
    // last one rejecting.
    ValueMap rec = {
        {"afr", 14.7},
        {"engine", 0.0},
        {"coolant", 30.0},   // below 70 °C default
        {"pulsewidth", 4.5},
    };
    rsg::Config cfg;
    auto evals = rsg::evaluate_record(rec, cfg);
    REQUIRE(evals.size() == 4);
    CHECK(evals.back().gate_name == "minCltFilter");
    CHECK_FALSE(evals.back().accepted);
    CHECK(evals.back().reason.find("coolant") != std::string::npos);
}

TEST_CASE("std_DeadLambda rejects when AFR is outside plausible range") {
    ValueMap rec = {{"afr", 5.0}};
    rsg::Config cfg;
    auto rejection = rsg::primary_rejection(rec, cfg);
    REQUIRE(rejection.has_value());
    CHECK(rejection->gate_name == "std_DeadLambda");
    CHECK(rejection->reason.find("AFR 5.00 outside plausible range") != std::string::npos);
}

TEST_CASE("accelFilter rejects when engine status bit 0x10 is set") {
    ValueMap rec = {{"afr", 14.7}, {"engine", 16.0}};
    rsg::Config cfg;
    auto rejection = rsg::primary_rejection(rec, cfg);
    REQUIRE(rejection.has_value());
    CHECK(rejection->gate_name == "accelFilter");
    CHECK(rejection->reason == "accel enrichment active (engine & 16)");
}

TEST_CASE("aseFilter rejects when engine status bit 0x04 is set") {
    ValueMap rec = {{"afr", 14.7}, {"engine", 4.0}};
    rsg::Config cfg;
    auto rejection = rsg::primary_rejection(rec, cfg);
    REQUIRE(rejection.has_value());
    CHECK(rejection->gate_name == "aseFilter");
}

TEST_CASE("overrunFilter rejects when pulseWidth is zero") {
    ValueMap rec = {
        {"afr", 14.7},
        {"engine", 0.0},
        {"coolant", 85.0},
        {"pulsewidth", 0.0},
    };
    rsg::Config cfg;
    auto rejection = rsg::primary_rejection(rec, cfg);
    REQUIRE(rejection.has_value());
    CHECK(rejection->gate_name == "overrunFilter");
}

TEST_CASE("custom enabled_gates set runs in alphabetical order") {
    rsg::Config cfg;
    cfg.enabled_gates = {"minRPM", "maxTPS"};
    cfg.rpm_min = 500.0;
    cfg.tps_max_percent = 80.0;
    // maxTPS comes before minRPM alphabetically, so maxTPS rejection
    // wins when both would fire.
    ValueMap rec = {{"rpm", 100.0}, {"tps", 95.0}};
    auto rejection = rsg::primary_rejection(rec, cfg);
    REQUIRE(rejection.has_value());
    CHECK(rejection->gate_name == "maxTPS");
}

TEST_CASE("firmwareLearnGate is prepended when enabled and rejects on bad RSA") {
    rsg::Config cfg;
    cfg.firmware_learn_gate_enabled = true;
    // RSA with fullSync clear → reject regardless of other gates.
    ValueMap rec = {{"afr", 14.7}, {"runtimeStatusA", 0.0}};
    auto evals = rsg::evaluate_record(rec, cfg);
    REQUIRE(evals.size() == 1);
    CHECK(evals[0].gate_name == "firmwareLearnGate");
    CHECK_FALSE(evals[0].accepted);
    CHECK(evals[0].reason.find("!fullSync") != std::string::npos);
}

TEST_CASE("firmwareLearnGate accepts when all four bits are correct") {
    rsg::Config cfg;
    cfg.firmware_learn_gate_enabled = true;
    // tuneLearnValid (0x80) | fullSync (0x10) = 0x90
    ValueMap rec = {
        {"afr", 14.7},
        {"engine", 0.0},
        {"coolant", 85.0},
        {"pulsewidth", 4.5},
        {"runtimeStatusA", static_cast<double>(0x90)},
    };
    CHECK(rsg::is_accepted(rec, cfg));
}

TEST_CASE("firmwareLearnGate rejects on transientActive bit") {
    rsg::Config cfg;
    cfg.firmware_learn_gate_enabled = true;
    ValueMap rec = {{"runtimeStatusA", static_cast<double>(0x90 | 0x20)}};
    auto rej = rsg::primary_rejection(rec, cfg);
    REQUIRE(rej.has_value());
    CHECK(rej->reason.find("transientActive") != std::string::npos);
}

TEST_CASE("firmwareLearnGate accepts when channel is missing (legacy log)") {
    rsg::Config cfg;
    cfg.enabled_gates = {"firmwareLearnGate"};
    ValueMap rec = {{"rpm", 3000.0}};
    auto evals = rsg::evaluate_record(rec, cfg);
    REQUIRE(evals.size() == 1);
    CHECK(evals[0].accepted);
}

TEST_CASE("std_xAxisMin rejects when axis value is below the configured minimum") {
    rsg::Config cfg;
    cfg.enabled_gates = {"std_xAxisMin"};
    cfg.axis_x_min = 1000.0;
    cfg.axis_x_value = 500.0;
    ValueMap rec;
    auto rej = rsg::primary_rejection(rec, cfg);
    REQUIRE(rej.has_value());
    CHECK(rej->gate_name == "std_xAxisMin");
}

TEST_CASE("std_xAxisMin passes through when bounds or values are missing") {
    rsg::Config cfg;
    cfg.enabled_gates = {"std_xAxisMin"};
    ValueMap rec;
    CHECK(rsg::is_accepted(rec, cfg));
}

TEST_CASE("gate_records aggregates accepted and rejected counts") {
    rsg::Config cfg;
    std::vector<ValueMap> records = {
        {{"afr", 14.7}, {"engine", 0.0}, {"coolant", 85.0}, {"pulsewidth", 4.5}},  // accept
        {{"rpm", 1000.0}},  // reject: std_DeadLambda (no AFR)
        {{"afr", 14.7}, {"engine", 16.0}},  // reject: accelFilter
    };
    auto summary = rsg::gate_records(records, cfg);
    CHECK(summary.total_count == 3);
    CHECK(summary.accepted_count == 1);
    CHECK(summary.rejected_count == 2);
    REQUIRE(summary.rejection_counts_by_gate.size() == 2);
    // Sorted alphabetically: accelFilter < std_DeadLambda
    CHECK(summary.rejection_counts_by_gate[0].first == "accelFilter");
    CHECK(summary.rejection_counts_by_gate[0].second == 1);
    CHECK(summary.rejection_counts_by_gate[1].first == "std_DeadLambda");
    CHECK(summary.rejection_counts_by_gate[1].second == 1);
    CHECK(summary.summary_text == "Sample gating: 1 accepted, 2 rejected of 3 total.");
    REQUIRE(summary.detail_lines.size() == 2);
    CHECK(summary.detail_lines[0] == summary.summary_text);
    CHECK(summary.detail_lines[1] == "Rejections by gate: accelFilter=1, std_DeadLambda=1.");
}

TEST_CASE("gate_records reports no rejections when every record is accepted") {
    rsg::Config cfg;
    std::vector<ValueMap> records = {
        {{"afr", 14.7}, {"engine", 0.0}, {"coolant", 85.0}, {"pulsewidth", 4.5}},
    };
    auto summary = rsg::gate_records(records, cfg);
    CHECK(summary.accepted_count == 1);
    CHECK(summary.rejected_count == 0);
    CHECK(summary.rejection_counts_by_gate.empty());
    REQUIRE(summary.detail_lines.size() == 2);
    CHECK(summary.detail_lines[1] == "No rejections.");
}
