// SPDX-License-Identifier: MIT
#include "tuner_core/hardware_setup_generator_context.hpp"
#include "tuner_core/hardware_presets.hpp"
#include "tuner_core/required_fuel_calculator.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <string>
#include <vector>

namespace tuner_core::hardware_setup_generator_context {

// -----------------------------------------------------------------------
// Keyword sets — mirrors Python _KW_* tuples
// -----------------------------------------------------------------------

using KW = std::vector<std::string>;

const KW KW_INJECTOR_FLOW     = {"injectorflow", "injflow", "injsizepri", "injsize"};
const KW KW_INJECTOR_FLOW_SEC = {"injsizesec", "injflowsec", "injectorflowsec", "secondaryinjector"};
const KW KW_DEAD_TIME         = {"deadtime", "injopen", "opentime", "injectoropen"};
const KW KW_REQ_FUEL          = {"reqfuel"};
const KW KW_INJECTOR_COUNT    = {"ninjectors", "injectorcount", "injcount"};
const KW KW_DISPLACEMENT      = {"enginesize", "displacement", "enginecc"};
const KW KW_CYLINDER_COUNT    = {"ncylinders", "cylindercount", "cylcount"};
const KW KW_COMPRESSION       = {"compression", "compressionratio", "compratio"};
const KW KW_REV_LIMIT         = {"rpmhard", "revlimit", "maxrpm"};
const KW KW_BOOST_ENABLED     = {"boostenabled", "turboenabled", "boostcontrol"};
const KW KW_BOOST_TARGET      = {"boosttarget", "boostlimit", "targetboost"};
const KW KW_STOICH            = {"stoich"};
const KW KW_EGO_TYPE          = {"egotype", "afrsensortype", "o2sensortype", "lambdatype"};
const KW KW_AFR_CAL           = {"afrcal", "widebandcal", "lambdacal"};
const KW KW_DWELL             = {"dwellrun", "dwell", "sparkdur", "coildwell"};
const KW KW_MAP_RANGE         = {"maprange", "mapmax", "mapmin", "mapsensor"};
const KW KW_FUEL_PRESSURE     = {"fuelpressure", "fuelpress", "fprpressure"};

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

bool any_keyword_in(const std::string& haystack, const KW& keywords) {
    for (const auto& kw : keywords) {
        if (haystack.find(kw) != std::string::npos) return true;
    }
    return false;
}

// -----------------------------------------------------------------------
// Parameter discovery helpers
// -----------------------------------------------------------------------

std::optional<double> find_numeric(
    const std::vector<Page>& pages,
    ValueGetter get_value, void* user,
    const KW& keywords)
{
    for (const auto& page : pages) {
        for (const auto& param : page.parameters) {
            std::string haystack = to_lower(param.name + " " + param.label);
            if (any_keyword_in(haystack, keywords)) {
                auto v = get_value(param.name, user);
                if (v.has_value()) return v;
            }
        }
    }
    return std::nullopt;
}

bool find_bool_enabled(
    const std::vector<Page>& pages,
    ValueGetter get_value, void* user,
    const KW& keywords,
    double min_numeric = 0.5)
{
    for (const auto& page : pages) {
        for (const auto& param : page.parameters) {
            std::string haystack = to_lower(param.name + " " + param.label);
            if (any_keyword_in(haystack, keywords)) {
                auto v = get_value(param.name, user);
                if (v.has_value()) return *v >= min_numeric;
            }
        }
    }
    return false;
}

bool any_param_present(
    const std::vector<Page>& pages,
    const KW& keywords)
{
    for (const auto& page : pages) {
        for (const auto& param : page.parameters) {
            std::string haystack = to_lower(param.name + " " + param.label);
            if (any_keyword_in(haystack, keywords)) return true;
        }
    }
    return false;
}

// -----------------------------------------------------------------------
// Missing-input checkers
// -----------------------------------------------------------------------

std::vector<std::string> ve_missing(
    const std::optional<double>& displacement,
    const std::optional<int>& cylinder_count,
    const std::optional<double>& injector_flow,
    const std::optional<double>& req_fuel,
    const std::optional<double>& rev_limit)
{
    std::vector<std::string> m;
    if (!displacement || *displacement == 0)     m.push_back("Engine displacement");
    if (!cylinder_count || *cylinder_count == 0)  m.push_back("Cylinder count");
    if (!injector_flow || *injector_flow == 0)    m.push_back("Injector flow rate");
    if (!req_fuel || *req_fuel == 0)              m.push_back("Required fuel (ms)");
    if (!rev_limit || *rev_limit == 0)            m.push_back("RPM limit / redline");
    return m;
}

std::vector<std::string> injector_missing(
    const std::optional<double>& injector_flow,
    const std::optional<int>& cylinder_count,
    const std::optional<double>& displacement,
    const std::optional<double>& stoich)
{
    std::vector<std::string> m;
    if (!injector_flow || *injector_flow == 0)   m.push_back("Injector flow rate");
    if (!cylinder_count || *cylinder_count == 0) m.push_back("Cylinder count");
    if (!displacement || *displacement == 0)     m.push_back("Engine displacement");
    if (!stoich || *stoich == 0)                 m.push_back("Stoich ratio");
    return m;
}

std::vector<std::string> spark_missing(
    const std::optional<double>& compression,
    const std::optional<double>& rev_limit)
{
    std::vector<std::string> m;
    if (!compression || *compression == 0) m.push_back("Compression ratio");
    if (!rev_limit || *rev_limit == 0)     m.push_back("RPM limit / redline");
    return m;
}

// -----------------------------------------------------------------------
// build()
// -----------------------------------------------------------------------

GeneratorInputContext build(
    const std::vector<Page>& pages,
    ValueGetter get_value,
    void* get_value_user,
    const OperatorEngineContext* op)
{
    namespace hp = tuner_core::hardware_presets;
    namespace rfc = tuner_core::required_fuel_calculator;

    auto gv = [&](const std::string& name) { return get_value(name, get_value_user); };
    (void)gv;  // suppress unused if we inline all calls

    // -- Injector --
    auto injector_flow     = find_numeric(pages, get_value, get_value_user, KW_INJECTOR_FLOW);
    auto injector_flow_sec = find_numeric(pages, get_value, get_value_user, KW_INJECTOR_FLOW_SEC);
    auto dead_time         = find_numeric(pages, get_value, get_value_user, KW_DEAD_TIME);
    auto req_fuel          = find_numeric(pages, get_value, get_value_user, KW_REQ_FUEL);
    auto inj_count_raw     = find_numeric(pages, get_value, get_value_user, KW_INJECTOR_COUNT);
    std::optional<int> injector_count;
    if (inj_count_raw) injector_count = static_cast<int>(*inj_count_raw);

    std::string injector_pressure_model;
    std::optional<double> secondary_injector_pressure_kpa;

    // -- Engine geometry --
    auto displacement = find_numeric(pages, get_value, get_value_user, KW_DISPLACEMENT);
    auto cyl_raw      = find_numeric(pages, get_value, get_value_user, KW_CYLINDER_COUNT);
    std::optional<int> cylinder_count;
    if (cyl_raw) cylinder_count = static_cast<int>(*cyl_raw);
    auto compression = find_numeric(pages, get_value, get_value_user, KW_COMPRESSION);
    auto rev_limit   = find_numeric(pages, get_value, get_value_user, KW_REV_LIMIT);

    std::optional<double> cam_duration;
    std::string head_flow_class;
    std::string intake_manifold_style;
    std::string injector_characterization;
    std::optional<SuperchargerType> supercharger_type;

    if (op) {
        if (!displacement)   displacement = op->displacement_cc;
        if (!cylinder_count) cylinder_count = op->cylinder_count;
        if (!compression)    compression = op->compression_ratio;
        cam_duration          = op->cam_duration_deg;
        head_flow_class       = op->head_flow_class;
        intake_manifold_style = op->intake_manifold_style;
        injector_characterization = op->injector_characterization;
        injector_pressure_model   = op->injector_pressure_model;
        supercharger_type         = op->supercharger_type;
        if (op->secondary_injector_reference_pressure_psi)
            secondary_injector_pressure_kpa = *op->secondary_injector_reference_pressure_psi * 6.89476;

        // Injector preset lookup — deferred until injector preset catalog
        // is ported to C++ (only ignition presets are in hardware_presets.hpp
        // currently).  The Python path falls back to preset-based flow/deadtime
        // when injector_flow is still null and the operator has selected a
        // preset key.  For now the C++ side relies on the tune-page discovery
        // path above which handles the majority case.
    }

    // -- Airflow / induction --
    bool boost_enabled = find_bool_enabled(pages, get_value, get_value_user, KW_BOOST_ENABLED);
    auto boost_target = find_numeric(pages, get_value, get_value_user, KW_BOOST_TARGET);
    auto map_range    = find_numeric(pages, get_value, get_value_user, KW_MAP_RANGE);
    bool intercooler_present = false;

    ForcedInductionTopology topology = ForcedInductionTopology::NA;
    if (op && op->forced_induction_topology != ForcedInductionTopology::NA) {
        topology = op->forced_induction_topology;
    } else {
        topology = boost_enabled ? ForcedInductionTopology::SINGLE_TURBO : ForcedInductionTopology::NA;
    }
    if (op) {
        if (!boost_target) boost_target = op->boost_target_kpa;
        intercooler_present = op->intercooler_present;
    }

    // -- Fuel --
    auto stoich = find_numeric(pages, get_value, get_value_user, KW_STOICH);
    auto fuel_pressure = find_numeric(pages, get_value, get_value_user, KW_FUEL_PRESSURE);
    if (!fuel_pressure && op && op->base_fuel_pressure_psi)
        fuel_pressure = *op->base_fuel_pressure_psi * 6.89476;

    // -- Ignition --
    auto dwell = find_numeric(pages, get_value, get_value_user, KW_DWELL);
    if (!dwell && op && !op->ignition_preset_key.empty()) {
        auto presets = hp::ignition_presets();
        for (const auto& p : presets) {
            if (p.key == op->ignition_preset_key) {
                dwell = p.running_dwell_ms;
                break;
            }
        }
    }

    // -- Sensor --
    auto ego_raw = find_numeric(pages, get_value, get_value_user, KW_EGO_TYPE);
    std::optional<int> ego_type_index;
    if (ego_raw) ego_type_index = static_cast<int>(*ego_raw);
    bool afr_cal_present = any_param_present(pages, KW_AFR_CAL);

    // -- Computed reqFuel --
    std::optional<double> computed_req_fuel;
    if (displacement && *displacement > 0 && cylinder_count && *cylinder_count > 0
        && injector_flow && *injector_flow > 0)
    {
        double effective_stoich = (stoich && *stoich > 0) ? *stoich : 14.7;
        auto result = rfc::calculate(*displacement, *cylinder_count, *injector_flow, effective_stoich);
        if (result.is_valid) computed_req_fuel = result.req_fuel_ms;
    }

    GeneratorInputContext ctx;
    ctx.injector_flow_ccmin           = injector_flow;
    ctx.injector_flow_secondary_ccmin = injector_flow_sec;
    ctx.injector_dead_time_ms         = dead_time;
    ctx.required_fuel_ms              = req_fuel;
    ctx.injector_count                = injector_count;
    ctx.displacement_cc               = displacement;
    ctx.cylinder_count                = cylinder_count;
    ctx.compression_ratio             = compression;
    ctx.cam_duration_deg              = cam_duration;
    ctx.head_flow_class               = head_flow_class;
    ctx.intake_manifold_style         = intake_manifold_style;
    ctx.injector_characterization     = injector_characterization;
    ctx.rev_limit_rpm                 = rev_limit;
    ctx.forced_induction_topology     = topology;
    ctx.boost_target_kpa              = boost_target;
    ctx.map_range_kpa                 = map_range;
    ctx.intercooler_present           = intercooler_present;
    ctx.supercharger_type             = supercharger_type;
    ctx.stoich_ratio                  = stoich;
    ctx.fuel_pressure_kpa             = fuel_pressure;
    ctx.injector_pressure_model       = injector_pressure_model;
    ctx.secondary_injector_pressure_kpa = secondary_injector_pressure_kpa;
    ctx.dwell_ms                      = dwell;
    ctx.ego_type_index                = ego_type_index;
    ctx.afr_calibration_present       = afr_cal_present;
    ctx.computed_req_fuel_ms          = computed_req_fuel;
    ctx.missing_for_ve_generation     = ve_missing(displacement, cylinder_count, injector_flow, req_fuel, rev_limit);
    ctx.missing_for_injector_helper   = injector_missing(injector_flow, cylinder_count, displacement, stoich);
    ctx.missing_for_spark_helper      = spark_missing(compression, rev_limit);
    return ctx;
}

}  // namespace tuner_core::hardware_setup_generator_context
