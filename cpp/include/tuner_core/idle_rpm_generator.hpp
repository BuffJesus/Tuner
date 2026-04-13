// SPDX-License-Identifier: MIT
//
// tuner_core::idle_rpm_generator — port of IdleRpmTargetGeneratorService.
// Fortieth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Generates a conservative 10-point idle RPM target curve (iacBins +
// iacCLValues) shaped by forced induction topology, cam duration, head
// flow class, intake manifold style, and calibration intent. Pure logic.
//
// Also introduces the shared generator domain types (GeneratorInputContext,
// CalibrationIntent, ForcedInductionTopology, etc.) that all future
// generator service ports will compose against.

#pragma once

#include "generator_types.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::idle_rpm_generator {

// Import shared generator domain types.
using generator_types::AssumptionSource;
using generator_types::Assumption;
using generator_types::CalibrationIntent;
using generator_types::ForcedInductionTopology;

// Minimal generator input context — only the fields the idle RPM
// generator reads. Other generators will extend this as they're ported.
struct GeneratorContext {
    ForcedInductionTopology forced_induction_topology = ForcedInductionTopology::NA;
    std::optional<double> cam_duration_deg;
    std::string head_flow_class;      // "mild_ported", "race_ported", or empty
    std::string intake_manifold_style; // "long_runner_plenum", "short_runner_plenum", "itb", "log_compact", or empty
};

// -----------------------------------------------------------------------
// Result
// -----------------------------------------------------------------------

struct Result {
    std::vector<double> clt_bins;      // 10 CLT breakpoints in °C
    std::vector<double> rpm_targets;   // 10 RPM targets
    std::string summary;
    std::vector<std::string> warnings;
    std::vector<Assumption> assumptions;
};

// -----------------------------------------------------------------------
// Constants (exposed for testing)
// -----------------------------------------------------------------------

constexpr int BIN_COUNT = 10;
constexpr double RPM_MIN = 500.0;
constexpr double RPM_MAX = 2550.0;
constexpr double WARM_RPM_NA = 800.0;
constexpr double WARM_RPM_BOOSTED = 850.0;
constexpr double COLD_BUMP_DRIVABLE = 400.0;
constexpr double COLD_BUMP_FIRST_START = 500.0;
constexpr double HIGH_CAM_THRESHOLD_DEG = 270.0;

// -----------------------------------------------------------------------
// Generator
// -----------------------------------------------------------------------

Result generate(
    const GeneratorContext& ctx,
    CalibrationIntent intent = CalibrationIntent::FIRST_START);

}  // namespace tuner_core::idle_rpm_generator
