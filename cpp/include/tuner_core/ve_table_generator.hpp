// SPDX-License-Identifier: MIT
//
// tuner_core::ve_table_generator — port of VeTableGeneratorService.
// Forty-third sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Generates a conservative 16×16 VE table shaped by cam duration, head
// flow class, intake manifold style, injector sizing, forced induction
// topology, and supercharger type. Pure logic, stage-only output.

#pragma once

#include "generator_types.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::ve_table_generator {

using generator_types::AssumptionSource;
using generator_types::Assumption;
using generator_types::ForcedInductionTopology;

enum class SuperchargerType { ROOTS, TWIN_SCREW, CENTRIFUGAL };

struct VeGeneratorContext {
    ForcedInductionTopology forced_induction_topology = ForcedInductionTopology::NA;
    std::optional<double> displacement_cc;
    std::optional<int> cylinder_count;
    std::optional<double> compression_ratio;
    std::optional<double> injector_flow_ccmin;
    std::optional<double> required_fuel_ms;
    std::optional<double> computed_req_fuel_ms;
    std::optional<double> injector_dead_time_ms;
    std::string injector_pressure_model;       // empty = not set
    std::string injector_characterization;     // empty = not set
    std::optional<double> cam_duration_deg;
    std::string head_flow_class;               // empty = not set
    std::string intake_manifold_style;         // empty = not set
    std::optional<double> boost_target_kpa;
    bool intercooler_present = false;
    std::optional<SuperchargerType> supercharger_type;
};

constexpr int ROWS = 16;
constexpr int COLS = 16;
constexpr double VE_MIN = 20.0;
constexpr double VE_MAX = 100.0;

struct Result {
    std::vector<double> values;  // flat row-major
    int rows = ROWS;
    int columns = COLS;
    ForcedInductionTopology topology = ForcedInductionTopology::NA;
    std::string summary;
    std::vector<std::string> warnings;
    std::vector<Assumption> assumptions;
};

Result generate(const VeGeneratorContext& ctx);

}  // namespace tuner_core::ve_table_generator
