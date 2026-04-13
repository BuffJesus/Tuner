// SPDX-License-Identifier: MIT
#include "tuner_core/operator_engine_context.hpp"

#include <nlohmann/json.hpp>

namespace tuner_core::operator_engine_context {

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

namespace {

CalibrationIntent coerce_intent(const std::string& s) {
    if (s == "drivable_base") return CalibrationIntent::DRIVABLE_BASE;
    return CalibrationIntent::FIRST_START;
}

ForcedInductionTopology coerce_topology(const std::string& s) {
    if (s == "single_turbo")           return ForcedInductionTopology::SINGLE_TURBO;
    if (s == "twin_turbo_identical")   return ForcedInductionTopology::TWIN_TURBO_IDENTICAL;
    if (s == "twin_turbo_sequential")  return ForcedInductionTopology::TWIN_TURBO_SEQUENTIAL;
    if (s == "twin_turbo_compound")    return ForcedInductionTopology::TWIN_TURBO_COMPOUND;
    if (s == "twin_turbo_unequal")     return ForcedInductionTopology::TWIN_TURBO_UNEQUAL;
    if (s == "single_supercharger")    return ForcedInductionTopology::SINGLE_SUPERCHARGER;
    if (s == "twin_charge")            return ForcedInductionTopology::TWIN_CHARGE;
    return ForcedInductionTopology::NA;
}

std::optional<SuperchargerType> coerce_sc_type(const std::string& s) {
    if (s == "roots")       return SuperchargerType::ROOTS;
    if (s == "twin_screw")  return SuperchargerType::TWIN_SCREW;
    if (s == "centrifugal") return SuperchargerType::CENTRIFUGAL;
    return std::nullopt;
}

const char* intent_str(CalibrationIntent i) {
    switch (i) {
        case CalibrationIntent::FIRST_START:   return "first_start";
        case CalibrationIntent::DRIVABLE_BASE: return "drivable_base";
    }
    return "first_start";
}

const char* sc_type_str(SuperchargerType t) {
    switch (t) {
        case SuperchargerType::ROOTS:       return "roots";
        case SuperchargerType::TWIN_SCREW:  return "twin_screw";
        case SuperchargerType::CENTRIFUGAL: return "centrifugal";
    }
    return "roots";
}

}  // namespace

// -----------------------------------------------------------------------
// ContextService::update
// -----------------------------------------------------------------------

const OperatorEngineContext& ContextService::update(const UpdateFields& f) {
    if (f.displacement_cc)       ctx_.displacement_cc = *f.displacement_cc;
    if (f.cylinder_count)        ctx_.cylinder_count = *f.cylinder_count;
    if (f.compression_ratio)     ctx_.compression_ratio = *f.compression_ratio;
    if (f.cam_duration_deg)      ctx_.cam_duration_deg = *f.cam_duration_deg;
    if (f.head_flow_class)       ctx_.head_flow_class = *f.head_flow_class;
    if (f.intake_manifold_style) ctx_.intake_manifold_style = *f.intake_manifold_style;
    if (f.base_fuel_pressure_psi) ctx_.base_fuel_pressure_psi = *f.base_fuel_pressure_psi;
    if (f.injector_pressure_model) ctx_.injector_pressure_model = *f.injector_pressure_model;
    if (f.secondary_injector_reference_pressure_psi)
        ctx_.secondary_injector_reference_pressure_psi = *f.secondary_injector_reference_pressure_psi;
    if (f.injector_preset_key)   ctx_.injector_preset_key = *f.injector_preset_key;
    if (f.ignition_preset_key)   ctx_.ignition_preset_key = *f.ignition_preset_key;
    if (f.wideband_preset_key)   ctx_.wideband_preset_key = *f.wideband_preset_key;
    if (f.wideband_reference_table_label)
        ctx_.wideband_reference_table_label = *f.wideband_reference_table_label;
    if (f.turbo_preset_key)      ctx_.turbo_preset_key = *f.turbo_preset_key;
    if (f.injector_characterization) ctx_.injector_characterization = *f.injector_characterization;
    if (f.calibration_intent)    ctx_.calibration_intent = *f.calibration_intent;
    if (f.forced_induction_topology) ctx_.forced_induction_topology = *f.forced_induction_topology;
    if (f.supercharger_type)     ctx_.supercharger_type = *f.supercharger_type;
    if (f.boost_target_kpa)      ctx_.boost_target_kpa = *f.boost_target_kpa;
    if (f.intercooler_present)   ctx_.intercooler_present = *f.intercooler_present;
    if (f.compressor_corrected_flow_lbmin)
        ctx_.compressor_corrected_flow_lbmin = *f.compressor_corrected_flow_lbmin;
    if (f.compressor_pressure_ratio)
        ctx_.compressor_pressure_ratio = *f.compressor_pressure_ratio;
    if (f.compressor_inducer_mm) ctx_.compressor_inducer_mm = *f.compressor_inducer_mm;
    if (f.compressor_exducer_mm) ctx_.compressor_exducer_mm = *f.compressor_exducer_mm;
    if (f.compressor_ar)         ctx_.compressor_ar = *f.compressor_ar;
    return ctx_;
}

// -----------------------------------------------------------------------
// JSON persistence — mirrors Python OperatorEngineContextService.save()
// -----------------------------------------------------------------------

std::string ContextService::save_json() const {
    nlohmann::ordered_json j;
    const auto& c = ctx_;

    if (c.displacement_cc)                          j["displacement_cc"] = *c.displacement_cc;
    if (c.cylinder_count)                            j["cylinder_count"] = *c.cylinder_count;
    if (c.compression_ratio)                         j["compression_ratio"] = *c.compression_ratio;
    if (c.cam_duration_deg)                          j["cam_duration_deg"] = *c.cam_duration_deg;
    if (!c.head_flow_class.empty())                  j["head_flow_class"] = c.head_flow_class;
    if (!c.intake_manifold_style.empty())            j["intake_manifold_style"] = c.intake_manifold_style;
    if (c.base_fuel_pressure_psi)                    j["base_fuel_pressure_psi"] = *c.base_fuel_pressure_psi;
    if (!c.injector_pressure_model.empty())          j["injector_pressure_model"] = c.injector_pressure_model;
    if (c.secondary_injector_reference_pressure_psi)
        j["secondary_injector_reference_pressure_psi"] = *c.secondary_injector_reference_pressure_psi;
    if (!c.injector_preset_key.empty())              j["injector_preset_key"] = c.injector_preset_key;
    if (!c.ignition_preset_key.empty())              j["ignition_preset_key"] = c.ignition_preset_key;
    if (!c.wideband_preset_key.empty())              j["wideband_preset_key"] = c.wideband_preset_key;
    if (!c.wideband_reference_table_label.empty())   j["wideband_reference_table_label"] = c.wideband_reference_table_label;
    if (!c.turbo_preset_key.empty())                 j["turbo_preset_key"] = c.turbo_preset_key;
    if (!c.injector_characterization.empty())        j["injector_characterization"] = c.injector_characterization;
    if (c.calibration_intent != CalibrationIntent::FIRST_START)
        j["calibration_intent"] = intent_str(c.calibration_intent);
    if (c.forced_induction_topology != ForcedInductionTopology::NA)
        j["forced_induction_topology"] = generator_types::topology_value_str(c.forced_induction_topology);
    if (c.supercharger_type)                         j["supercharger_type"] = sc_type_str(*c.supercharger_type);
    if (c.boost_target_kpa)                          j["boost_target_kpa"] = *c.boost_target_kpa;
    if (c.intercooler_present)                       j["intercooler_present"] = true;
    if (c.compressor_corrected_flow_lbmin)           j["compressor_corrected_flow_lbmin"] = *c.compressor_corrected_flow_lbmin;
    if (c.compressor_pressure_ratio)                 j["compressor_pressure_ratio"] = *c.compressor_pressure_ratio;
    if (c.compressor_inducer_mm)                     j["compressor_inducer_mm"] = *c.compressor_inducer_mm;
    if (c.compressor_exducer_mm)                     j["compressor_exducer_mm"] = *c.compressor_exducer_mm;
    if (c.compressor_ar)                             j["compressor_ar"] = *c.compressor_ar;

    return j.dump(2);
}

void ContextService::load_json(const std::string& json_text) {
    nlohmann::json j;
    try {
        j = nlohmann::json::parse(json_text);
    } catch (...) {
        return;  // Corrupt file → keep defaults.
    }
    if (!j.is_object()) return;

    OperatorEngineContext c;

    auto opt_double = [&](const char* key) -> std::optional<double> {
        if (j.contains(key) && !j[key].is_null()) return j[key].get<double>();
        return std::nullopt;
    };
    auto opt_int = [&](const char* key) -> std::optional<int> {
        if (j.contains(key) && !j[key].is_null()) return j[key].get<int>();
        return std::nullopt;
    };
    auto opt_str = [&](const char* key) -> std::string {
        if (j.contains(key) && j[key].is_string()) return j[key].get<std::string>();
        return {};
    };

    c.displacement_cc        = opt_double("displacement_cc");
    c.cylinder_count          = opt_int("cylinder_count");
    c.compression_ratio       = opt_double("compression_ratio");
    c.cam_duration_deg        = opt_double("cam_duration_deg");
    c.head_flow_class         = opt_str("head_flow_class");
    c.intake_manifold_style   = opt_str("intake_manifold_style");
    c.base_fuel_pressure_psi  = opt_double("base_fuel_pressure_psi");
    c.injector_pressure_model = opt_str("injector_pressure_model");
    c.secondary_injector_reference_pressure_psi = opt_double("secondary_injector_reference_pressure_psi");
    c.injector_preset_key     = opt_str("injector_preset_key");
    c.ignition_preset_key     = opt_str("ignition_preset_key");
    c.wideband_preset_key     = opt_str("wideband_preset_key");
    c.wideband_reference_table_label = opt_str("wideband_reference_table_label");
    c.turbo_preset_key        = opt_str("turbo_preset_key");
    c.injector_characterization = opt_str("injector_characterization");
    c.calibration_intent      = coerce_intent(opt_str("calibration_intent"));
    c.forced_induction_topology = coerce_topology(opt_str("forced_induction_topology"));
    c.supercharger_type       = coerce_sc_type(opt_str("supercharger_type"));
    c.boost_target_kpa        = opt_double("boost_target_kpa");
    c.intercooler_present     = j.contains("intercooler_present") && j["intercooler_present"].get<bool>();
    c.compressor_corrected_flow_lbmin = opt_double("compressor_corrected_flow_lbmin");
    c.compressor_pressure_ratio       = opt_double("compressor_pressure_ratio");
    c.compressor_inducer_mm           = opt_double("compressor_inducer_mm");
    c.compressor_exducer_mm           = opt_double("compressor_exducer_mm");
    c.compressor_ar                   = opt_double("compressor_ar");

    ctx_ = c;
}

}  // namespace tuner_core::operator_engine_context
