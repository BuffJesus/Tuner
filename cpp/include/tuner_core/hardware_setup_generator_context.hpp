// SPDX-License-Identifier: MIT
//
// tuner_core::hardware_setup_generator_context — port of
// HardwareSetupGeneratorContextService.  Fifty-fifth sub-slice of
// Phase 14 Slice 4.
//
// Extracts generator-ready hardware inputs from hardware setup pages
// by keyword-matching parameter names.  Composes LocalTuneEditService,
// HardwarePresetService, and RequiredFuelCalculatorService (all
// already ported).  Pure logic, no Qt.

#pragma once

#include "generator_types.hpp"
#include "operator_engine_context.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::hardware_setup_generator_context {

using generator_types::CalibrationIntent;
using generator_types::ForcedInductionTopology;
using operator_engine_context::SuperchargerType;
using operator_engine_context::OperatorEngineContext;

// -----------------------------------------------------------------------
// Minimal page model — just what the service reads
// -----------------------------------------------------------------------

struct Parameter {
    std::string name;
    std::string label;
};

struct Page {
    std::vector<Parameter> parameters;
};

// -----------------------------------------------------------------------
// Generator input context — mirrors Python GeneratorInputContext
// -----------------------------------------------------------------------

struct GeneratorInputContext {
    std::optional<double> injector_flow_ccmin;
    std::optional<double> injector_flow_secondary_ccmin;
    std::optional<double> injector_dead_time_ms;
    std::optional<double> required_fuel_ms;
    std::optional<int> injector_count;
    std::optional<double> displacement_cc;
    std::optional<int> cylinder_count;
    std::optional<double> compression_ratio;
    std::optional<double> cam_duration_deg;
    std::string head_flow_class;
    std::string intake_manifold_style;
    std::string injector_characterization;
    std::optional<double> rev_limit_rpm;
    ForcedInductionTopology forced_induction_topology = ForcedInductionTopology::NA;
    std::optional<double> boost_target_kpa;
    std::optional<double> map_range_kpa;
    bool intercooler_present = false;
    std::optional<SuperchargerType> supercharger_type;
    std::optional<double> stoich_ratio;
    std::optional<double> fuel_pressure_kpa;
    std::string injector_pressure_model;
    std::optional<double> secondary_injector_pressure_kpa;
    std::optional<double> dwell_ms;
    std::optional<int> ego_type_index;
    bool afr_calibration_present = false;
    std::optional<double> computed_req_fuel_ms;
    std::vector<std::string> missing_for_ve_generation;
    std::vector<std::string> missing_for_injector_helper;
    std::vector<std::string> missing_for_spark_helper;
};

// -----------------------------------------------------------------------
// Callback interface for reading tune values
// -----------------------------------------------------------------------

/// The caller provides a function that returns the numeric value of a
/// parameter by name, or nullopt if the parameter is absent or non-numeric.
/// This mirrors the Python `local_tune_edit_service.get_value(name)` call.
using ValueGetter = std::optional<double>(*)(const std::string& name, void* user);

// -----------------------------------------------------------------------
// Service
// -----------------------------------------------------------------------

/// Build a GeneratorInputContext from pages, a tune-value getter, and an
/// optional operator engine context.
GeneratorInputContext build(
    const std::vector<Page>& pages,
    ValueGetter get_value,
    void* get_value_user,
    const OperatorEngineContext* operator_context = nullptr);

}  // namespace tuner_core::hardware_setup_generator_context
