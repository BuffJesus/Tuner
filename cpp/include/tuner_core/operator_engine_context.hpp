// SPDX-License-Identifier: MIT
//
// tuner_core::operator_engine_context — port of OperatorEngineContextService.
// Fifty-fourth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Session-level store for operator-provided engine facts that are not held
// in the ECU (displacement, compression ratio, cam duration, etc.).  The
// service is mutable within a session; nothing is persisted automatically.
// JSON save/load mirrors the Python sidecar file contract.

#pragma once

#include "generator_types.hpp"
#include "ve_table_generator.hpp"  // SuperchargerType

#include <optional>
#include <string>

namespace tuner_core::operator_engine_context {

using generator_types::CalibrationIntent;
using generator_types::ForcedInductionTopology;
using ve_table_generator::SuperchargerType;

// -----------------------------------------------------------------------
// Domain model — mirrors Python OperatorEngineContext dataclass
// -----------------------------------------------------------------------

struct OperatorEngineContext {
    std::optional<double> displacement_cc;
    std::optional<int> cylinder_count;
    std::optional<double> compression_ratio;
    std::optional<double> cam_duration_deg;
    std::string head_flow_class;
    std::string intake_manifold_style;
    std::optional<double> base_fuel_pressure_psi;
    std::string injector_pressure_model;
    std::optional<double> secondary_injector_reference_pressure_psi;
    std::string injector_preset_key;
    std::string ignition_preset_key;
    std::string wideband_preset_key;
    std::string wideband_reference_table_label;
    std::string turbo_preset_key;
    std::string injector_characterization;
    CalibrationIntent calibration_intent = CalibrationIntent::FIRST_START;
    ForcedInductionTopology forced_induction_topology = ForcedInductionTopology::NA;
    std::optional<SuperchargerType> supercharger_type;
    std::optional<double> boost_target_kpa;
    bool intercooler_present = false;
    std::optional<double> compressor_corrected_flow_lbmin;
    std::optional<double> compressor_pressure_ratio;
    std::optional<double> compressor_inducer_mm;
    std::optional<double> compressor_exducer_mm;
    std::optional<double> compressor_ar;
};

// -----------------------------------------------------------------------
// Service
// -----------------------------------------------------------------------

class ContextService {
public:
    /// Return the current operator engine context.
    const OperatorEngineContext& get() const { return ctx_; }

    /// Update one or more fields.  Only fields wrapped in an engaged
    /// optional are changed; disengaged optionals leave the field as-is.
    /// Returns the new context.
    struct UpdateFields {
        std::optional<std::optional<double>> displacement_cc;
        std::optional<std::optional<int>> cylinder_count;
        std::optional<std::optional<double>> compression_ratio;
        std::optional<std::optional<double>> cam_duration_deg;
        std::optional<std::string> head_flow_class;
        std::optional<std::string> intake_manifold_style;
        std::optional<std::optional<double>> base_fuel_pressure_psi;
        std::optional<std::string> injector_pressure_model;
        std::optional<std::optional<double>> secondary_injector_reference_pressure_psi;
        std::optional<std::string> injector_preset_key;
        std::optional<std::string> ignition_preset_key;
        std::optional<std::string> wideband_preset_key;
        std::optional<std::string> wideband_reference_table_label;
        std::optional<std::string> turbo_preset_key;
        std::optional<std::string> injector_characterization;
        std::optional<CalibrationIntent> calibration_intent;
        std::optional<ForcedInductionTopology> forced_induction_topology;
        std::optional<std::optional<SuperchargerType>> supercharger_type;
        std::optional<std::optional<double>> boost_target_kpa;
        std::optional<bool> intercooler_present;
        std::optional<std::optional<double>> compressor_corrected_flow_lbmin;
        std::optional<std::optional<double>> compressor_pressure_ratio;
        std::optional<std::optional<double>> compressor_inducer_mm;
        std::optional<std::optional<double>> compressor_exducer_mm;
        std::optional<std::optional<double>> compressor_ar;
    };

    const OperatorEngineContext& update(const UpdateFields& f);

    /// Reset the context to all-default values.
    void clear() { ctx_ = OperatorEngineContext{}; }

    /// Serialise the current context to JSON.
    std::string save_json() const;

    /// Load context from a JSON string.  Missing keys keep defaults.
    /// Invalid JSON or unknown keys are silently ignored.
    void load_json(const std::string& json_text);

private:
    OperatorEngineContext ctx_;
};

}  // namespace tuner_core::operator_engine_context
