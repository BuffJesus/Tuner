// SPDX-License-Identifier: MIT
//
// tuner_core::afr_target_generator — port of AfrTargetGeneratorService.
// Forty-first sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Generates a conservative 16×16 AFR target table from engine topology
// and calibration intent. Pure logic, stage-only output.

#pragma once

#include "generator_types.hpp"

#include <string>
#include <vector>

namespace tuner_core::afr_target_generator {

using generator_types::AssumptionSource;
using generator_types::Assumption;
using generator_types::CalibrationIntent;
using generator_types::ForcedInductionTopology;

// Extended context with AFR-specific fields.
struct AfrGeneratorContext {
    ForcedInductionTopology forced_induction_topology = ForcedInductionTopology::NA;
    std::optional<double> stoich_ratio;
    std::optional<double> boost_target_kpa;
    bool intercooler_present = false;
    std::string injector_pressure_model;  // empty = not set
};

// -----------------------------------------------------------------------
// Constants (exposed for testing)
// -----------------------------------------------------------------------

constexpr int ROWS = 16;
constexpr int COLS = 16;
constexpr double STOICH_PETROL = 14.7;
constexpr double AFR_MIN = 10.0;
constexpr double AFR_MAX = 18.0;
constexpr double FIRST_START_ENRICHMENT = 0.7;

// -----------------------------------------------------------------------
// Result
// -----------------------------------------------------------------------

struct Result {
    std::vector<double> values;   // flat row-major, rows × cols
    int rows = ROWS;
    int columns = COLS;
    ForcedInductionTopology topology = ForcedInductionTopology::NA;
    double stoich = STOICH_PETROL;
    std::string summary;
    std::vector<std::string> warnings;
    std::vector<Assumption> assumptions;
};

// -----------------------------------------------------------------------
// Generator
// -----------------------------------------------------------------------

Result generate(
    const AfrGeneratorContext& ctx,
    CalibrationIntent intent = CalibrationIntent::FIRST_START);

}  // namespace tuner_core::afr_target_generator
