// SPDX-License-Identifier: MIT
//
// tuner_core::spark_table_generator — port of SparkTableGeneratorService.
// Forty-second sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Generates a conservative 16×16 spark advance table shaped by compression
// ratio, forced induction topology, boost target, and calibration intent.
// Pure logic, stage-only output.

#pragma once

#include "generator_types.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::spark_table_generator {

using generator_types::AssumptionSource;
using generator_types::Assumption;
using generator_types::CalibrationIntent;
using generator_types::ForcedInductionTopology;

struct SparkGeneratorContext {
    ForcedInductionTopology forced_induction_topology = ForcedInductionTopology::NA;
    std::optional<double> compression_ratio;
    std::optional<int> cylinder_count;
    std::optional<double> dwell_ms;
    std::optional<double> boost_target_kpa;
    bool intercooler_present = false;
};

constexpr int ROWS = 16;
constexpr int COLS = 16;
constexpr double CRANK_TIMING_FLOOR = 5.0;
constexpr double TIMING_MAX = 45.0;

struct Result {
    std::vector<double> values;  // flat row-major
    int rows = ROWS;
    int columns = COLS;
    ForcedInductionTopology topology = ForcedInductionTopology::NA;
    std::optional<double> compression_ratio;
    CalibrationIntent calibration_intent = CalibrationIntent::FIRST_START;
    std::string summary;
    std::vector<std::string> warnings;
    std::vector<Assumption> assumptions;
};

Result generate(
    const SparkGeneratorContext& ctx,
    CalibrationIntent intent = CalibrationIntent::FIRST_START);

}  // namespace tuner_core::spark_table_generator
