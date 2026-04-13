// SPDX-License-Identifier: MIT
//
// tuner_core::startup_enrichment_generator — port of
// StartupEnrichmentGeneratorService (WUE + cranking + ASE).
// Forty-fourth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Three sub-generators producing conservative startup enrichment curves:
//   - WUE: 10-point CLT → enrichment % (tapers to 100% at warm)
//   - Cranking: 4-point CLT → enrichment % (CR-adjusted)
//   - ASE: 4-point CLT → added % + duration seconds
//
// Pure logic, stage-only output.

#pragma once

#include "generator_types.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::startup_enrichment_generator {

using generator_types::AssumptionSource;
using generator_types::Assumption;
using generator_types::CalibrationIntent;
using generator_types::ForcedInductionTopology;

struct StartupContext {
    std::optional<double> stoich_ratio;
    std::optional<double> compression_ratio;
    ForcedInductionTopology forced_induction_topology = ForcedInductionTopology::NA;
    std::string injector_characterization;  // empty = not set
    std::string intake_manifold_style;      // empty = not set
    std::string head_flow_class;            // empty = not set
};

struct WueResult {
    std::vector<double> clt_bins;        // 10
    std::vector<double> enrichment_pct;  // 10
    std::string summary;
    std::vector<std::string> warnings;
    std::vector<Assumption> assumptions;
};

struct CrankingResult {
    std::vector<double> clt_bins;        // 4
    std::vector<double> enrichment_pct;  // 4
    std::string summary;
    std::vector<std::string> warnings;
    std::vector<Assumption> assumptions;
};

struct AseResult {
    std::vector<double> clt_bins;           // 4
    std::vector<double> enrichment_pct;     // 4
    std::vector<double> duration_seconds;   // 4
    std::string summary;
    std::vector<std::string> warnings;
    std::vector<Assumption> assumptions;
};

WueResult generate_wue(
    const StartupContext& ctx,
    CalibrationIntent intent = CalibrationIntent::FIRST_START);

CrankingResult generate_cranking(
    const StartupContext& ctx,
    CalibrationIntent intent = CalibrationIntent::FIRST_START);

AseResult generate_ase(
    const StartupContext& ctx,
    CalibrationIntent intent = CalibrationIntent::FIRST_START);

}  // namespace tuner_core::startup_enrichment_generator
