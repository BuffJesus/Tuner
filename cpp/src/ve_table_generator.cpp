// SPDX-License-Identifier: MIT
#include "tuner_core/ve_table_generator.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::ve_table_generator {

namespace {

constexpr double NA_RPM_PEAK_NORM = 0.55;
constexpr double NA_VE_MIN = 38.0;
constexpr double NA_VE_WOT = 85.0;
constexpr double HIGH_CAM_BONUS = 4.0;
constexpr double HIGH_CAM_THRESHOLD_DEG = 270.0;
constexpr double SHORT_CAM_IDLE_BONUS = 3.0;
constexpr double SHORT_CAM_THRESHOLD_DEG = 220.0;
constexpr double HEAD_FLOW_MILD_BONUS = 2.0;
constexpr double HEAD_FLOW_RACE_BONUS = 4.0;
constexpr double HEAD_FLOW_RACE_IDLE_PENALTY = 2.0;
constexpr double LONG_RUNNER_LOW_RPM_BONUS = 2.0;
constexpr double LONG_RUNNER_HIGH_RPM_PENALTY = 1.5;
constexpr double SHORT_RUNNER_LOW_RPM_PENALTY = 1.5;
constexpr double SHORT_RUNNER_HIGH_RPM_BONUS = 2.5;
constexpr double ITB_IDLE_PENALTY = 3.0;
constexpr double ITB_HIGH_RPM_BONUS = 3.0;
constexpr double LOG_MANIFOLD_LOW_RPM_BONUS = 1.5;
constexpr double LOG_MANIFOLD_HIGH_RPM_PENALTY = 1.0;
constexpr double LOW_REQFUEL_THRESHOLD_MS = 6.0;
constexpr double VERY_LOW_REQFUEL_THRESHOLD_MS = 4.0;
constexpr double LOW_REQFUEL_IDLE_REDUCTION = 3.0;
constexpr double VERY_LOW_REQFUEL_IDLE_REDUCTION = 5.0;
constexpr double NOMINAL_FLOW_ONLY_IDLE_REDUCTION = 2.5;
constexpr double SINGLE_DEADTIME_IDLE_REDUCTION = 1.0;
constexpr int SPOOL_START_COL = 5;
constexpr int SPOOL_END_COL = 9;
constexpr double SINGLE_TURBO_PRE_SPOOL_REDUCTION = 12.0;
constexpr double TWIN_TURBO_PRE_SPOOL_REDUCTION = 10.0;
constexpr double COMPOUND_TURBO_PRE_SPOOL_REDUCTION = 7.0;
constexpr double SEQUENTIAL_TWIN_PRE_SPOOL_REDUCTION = 9.0;
constexpr double SUPERCHARGER_LOW_RPM_BOOST = 3.0;
constexpr double SUPERCHARGER_WOT_BOOST = 5.0;
constexpr double TWIN_CHARGE_LOW_RPM_BOOST = 2.0;
constexpr double TWIN_CHARGE_SPOOL_REDUCTION = 5.0;
constexpr double CENTRIFUGAL_SC_PRE_SPOOL_REDUCTION = 4.0;

double base_ve_na(int row, int col, double cam_bonus) {
    double load_norm = static_cast<double>(row) / (ROWS - 1);
    double rpm_norm = static_cast<double>(col) / (COLS - 1);
    double load_ve = NA_VE_MIN + (NA_VE_WOT - NA_VE_MIN) * load_norm;
    double dist = std::abs(rpm_norm - NA_RPM_PEAK_NORM);
    double rpm_factor = 1.0 - 0.18 * (dist / NA_RPM_PEAK_NORM);
    rpm_factor = std::clamp(rpm_factor, 0.82, 1.0);
    double idle_correction = 0.0;
    if (col <= 1 && row <= 2) {
        idle_correction = -6.0 + 2.0 * (col + row);
    }
    double eff_cam = (col >= 10 && row >= 10) ? cam_bonus : 0.0;
    return load_ve * rpm_factor + idle_correction + eff_cam;
}

double turbo_correction(int col, double pre_spool_reduction) {
    if (col < SPOOL_START_COL) return -pre_spool_reduction;
    if (col < SPOOL_END_COL) {
        int spool_bins = SPOOL_END_COL - SPOOL_START_COL;
        double progress = static_cast<double>(col - SPOOL_START_COL) / spool_bins;
        return -pre_spool_reduction * (1.0 - progress);
    }
    return 0.0;
}

double topology_correction(int row, int col, ForcedInductionTopology t,
                             std::optional<SuperchargerType> sc_type,
                             std::vector<std::string>& warnings) {
    if (t == ForcedInductionTopology::NA) return 0.0;
    if (t == ForcedInductionTopology::SINGLE_TURBO)
        return turbo_correction(col, SINGLE_TURBO_PRE_SPOOL_REDUCTION);
    if (t == ForcedInductionTopology::TWIN_TURBO_IDENTICAL)
        return turbo_correction(col, TWIN_TURBO_PRE_SPOOL_REDUCTION);
    if (t == ForcedInductionTopology::TWIN_TURBO_UNEQUAL) {
        const char* note = "Unequal twin turbo sizing not modeled - low-RPM VE is conservative on the larger-turbo side and needs per-cylinder review.";
        bool found = false;
        for (const auto& w : warnings) if (w == note) { found = true; break; }
        if (!found) warnings.push_back(note);
        return turbo_correction(col, TWIN_TURBO_PRE_SPOOL_REDUCTION);
    }
    if (t == ForcedInductionTopology::TWIN_TURBO_SEQUENTIAL)
        return turbo_correction(col, SEQUENTIAL_TWIN_PRE_SPOOL_REDUCTION);
    if (t == ForcedInductionTopology::TWIN_TURBO_COMPOUND)
        return turbo_correction(col, COMPOUND_TURBO_PRE_SPOOL_REDUCTION);
    if (t == ForcedInductionTopology::SINGLE_SUPERCHARGER) {
        if (sc_type.has_value() && *sc_type == SuperchargerType::CENTRIFUGAL)
            return turbo_correction(col, CENTRIFUGAL_SC_PRE_SPOOL_REDUCTION);
        double load_norm = static_cast<double>(row) / (ROWS - 1);
        return SUPERCHARGER_LOW_RPM_BOOST + SUPERCHARGER_WOT_BOOST * load_norm;
    }
    if (t == ForcedInductionTopology::TWIN_CHARGE) {
        if (col < SPOOL_START_COL) return TWIN_CHARGE_LOW_RPM_BOOST;
        if (col < SPOOL_END_COL) return -TWIN_CHARGE_SPOOL_REDUCTION;
        return 0.0;
    }
    return 0.0;
}

double injector_idle_correction(int row, int col, double penalty) {
    if (penalty <= 0.0) return 0.0;
    if (row <= 3 && col <= 4) return -penalty;
    if (row <= 5 && col <= 6) return -(penalty * 0.5);
    return 0.0;
}

double airflow_correction(int row, int col,
                            const std::string& head_flow_class,
                            const std::string& intake_manifold_style) {
    double c = 0.0;
    if (head_flow_class == "mild_ported") {
        if (row >= 10 && col >= 9) c += HEAD_FLOW_MILD_BONUS;
    } else if (head_flow_class == "race_ported") {
        if (row >= 10 && col >= 9) c += HEAD_FLOW_RACE_BONUS;
        if (row <= 3 && col <= 3) c -= HEAD_FLOW_RACE_IDLE_PENALTY;
    }
    if (intake_manifold_style == "long_runner_plenum") {
        if (row >= 6 && col <= 7) c += LONG_RUNNER_LOW_RPM_BONUS;
        if (row >= 10 && col >= 12) c -= LONG_RUNNER_HIGH_RPM_PENALTY;
    } else if (intake_manifold_style == "short_runner_plenum") {
        if (row >= 6 && col <= 4) c -= SHORT_RUNNER_LOW_RPM_PENALTY;
        if (row >= 9 && col >= 10) c += SHORT_RUNNER_HIGH_RPM_BONUS;
    } else if (intake_manifold_style == "itb") {
        if (row <= 3 && col <= 3) c -= ITB_IDLE_PENALTY;
        if (row >= 8 && col >= 9) c += ITB_HIGH_RPM_BONUS;
    } else if (intake_manifold_style == "log_compact") {
        if (row >= 6 && col <= 6) c += LOG_MANIFOLD_LOW_RPM_BONUS;
        if (row >= 10 && col >= 12) c -= LOG_MANIFOLD_HIGH_RPM_PENALTY;
    }
    return c;
}

}  // namespace

Result generate(const VeGeneratorContext& ctx) {
    Result result;
    result.topology = ctx.forced_induction_topology;
    std::vector<std::string> warnings;

    // Cam bonus.
    double cam_bonus = 0.0;
    if (ctx.cam_duration_deg.has_value()) {
        if (*ctx.cam_duration_deg > HIGH_CAM_THRESHOLD_DEG) cam_bonus = HIGH_CAM_BONUS;
        else if (*ctx.cam_duration_deg < SHORT_CAM_THRESHOLD_DEG) cam_bonus = -SHORT_CAM_IDLE_BONUS;
    } else {
        warnings.push_back("Cam duration not provided \xe2\x80\x94 using stock cam shaping");
    }

    // Injector idle penalty.
    double effective_req = ctx.required_fuel_ms.value_or(
        ctx.computed_req_fuel_ms.value_or(-1.0));
    double injector_idle_penalty = 0.0;
    if (effective_req < 0) {
        warnings.push_back("Required fuel not available \xe2\x80\x94 injector sizing could not influence idle shaping");
    } else if (effective_req < VERY_LOW_REQFUEL_THRESHOLD_MS) {
        injector_idle_penalty = VERY_LOW_REQFUEL_IDLE_REDUCTION;
        warnings.push_back("Very low reqFuel detected \xe2\x80\x94 applying extra idle VE reduction for oversized injectors");
    } else if (effective_req < LOW_REQFUEL_THRESHOLD_MS) {
        injector_idle_penalty = LOW_REQFUEL_IDLE_REDUCTION;
        warnings.push_back("Low reqFuel detected \xe2\x80\x94 applying mild idle VE reduction for oversized injectors");
    }

    if (!ctx.injector_dead_time_ms.has_value()) {
        warnings.push_back("Injector dead time not provided \xe2\x80\x94 idle and low pulsewidth regions may need extra review");
    }

    double characterization_penalty = 0.0;
    if (ctx.injector_characterization == "nominal_flow_only") {
        characterization_penalty = NOMINAL_FLOW_ONLY_IDLE_REDUCTION;
        warnings.push_back("Injector characterization is flow-only - applying extra low-pulsewidth conservatism.");
    } else if (ctx.injector_characterization == "flow_plus_deadtime") {
        characterization_penalty = SINGLE_DEADTIME_IDLE_REDUCTION;
        warnings.push_back("Injector characterization uses only a single dead-time value - low-voltage idle may need review.");
    } else if (ctx.injector_characterization.empty()) {
        warnings.push_back("Injector characterization depth not set - using generic low-pulsewidth assumptions.");
    }

    if (!ctx.displacement_cc.has_value()) {
        warnings.push_back("Engine displacement not provided \xe2\x80\x94 using default shaping");
    }
    if (!ctx.cylinder_count.has_value()) {
        warnings.push_back("Cylinder count not provided \xe2\x80\x94 using default shaping");
    }

    // Build table.
    std::vector<double> values;
    values.reserve(ROWS * COLS);
    for (int row = 0; row < ROWS; ++row) {
        for (int col = 0; col < COLS; ++col) {
            double ve = base_ve_na(row, col, cam_bonus);
            ve += injector_idle_correction(row, col, injector_idle_penalty);
            ve += injector_idle_correction(row, col, characterization_penalty);
            ve += airflow_correction(row, col, ctx.head_flow_class, ctx.intake_manifold_style);
            ve += topology_correction(row, col, ctx.forced_induction_topology,
                                       ctx.supercharger_type, warnings);
            ve = std::round(std::clamp(ve, VE_MIN, VE_MAX) * 10.0) / 10.0;
            values.push_back(ve);
        }
    }
    result.values = std::move(values);
    result.warnings = std::move(warnings);

    // Assumptions.
    auto src = AssumptionSource::FROM_CONTEXT;
    auto fb = AssumptionSource::CONSERVATIVE_FALLBACK;
    auto computed = AssumptionSource::COMPUTED;

    auto opt_str = [](const std::optional<double>& v, const char* fmt) -> std::string {
        if (!v.has_value()) return "not set";
        char buf[64];
        std::snprintf(buf, sizeof(buf), fmt, *v);
        return buf;
    };

    result.assumptions.push_back({"Displacement", opt_str(ctx.displacement_cc, "%.0f cc"),
        ctx.displacement_cc.has_value() ? src : fb, ""});
    result.assumptions.push_back({"Cylinders",
        ctx.cylinder_count.has_value() ? std::to_string(*ctx.cylinder_count) : "not set",
        ctx.cylinder_count.has_value() ? src : fb, ""});
    result.assumptions.push_back({"Compression ratio", opt_str(ctx.compression_ratio, "%.1f:1"),
        ctx.compression_ratio.has_value() ? src : fb, ""});
    result.assumptions.push_back({"Injector flow", opt_str(ctx.injector_flow_ccmin, "%.0f cc/min"),
        ctx.injector_flow_ccmin.has_value() ? src : fb, ""});

    if (effective_req >= 0) {
        auto req_src = ctx.required_fuel_ms.has_value() ? src : computed;
        char buf[32];
        std::snprintf(buf, sizeof(buf), "%.2f ms", effective_req);
        result.assumptions.push_back({"Required fuel", buf, req_src,
            req_src == computed ? "Computed from displacement + injector flow" : ""});
    } else {
        result.assumptions.push_back({"Required fuel", "not set", fb, ""});
    }

    result.assumptions.push_back({"Injector dead time", opt_str(ctx.injector_dead_time_ms, "%.3f ms"),
        ctx.injector_dead_time_ms.has_value() ? src : fb, ""});
    result.assumptions.push_back({"Injector pressure model",
        ctx.injector_pressure_model.empty() ? "not set" : ctx.injector_pressure_model,
        ctx.injector_pressure_model.empty() ? fb : src,
        ctx.injector_pressure_model.empty() ? "Used conservative generic fuel-pressure behavior." : ""});
    result.assumptions.push_back({"Cam duration", opt_str(ctx.cam_duration_deg, "%.0f deg"),
        ctx.cam_duration_deg.has_value() ? src : fb, ""});
    result.assumptions.push_back({"Head flow class",
        ctx.head_flow_class.empty() ? "not set" : ctx.head_flow_class,
        ctx.head_flow_class.empty() ? fb : src, ""});
    result.assumptions.push_back({"Manifold style",
        ctx.intake_manifold_style.empty() ? "not set" : ctx.intake_manifold_style,
        ctx.intake_manifold_style.empty() ? fb : src, ""});

    const char* topo_val = generator_types::topology_value_str(ctx.forced_induction_topology);
    result.assumptions.push_back({"Induction topology", topo_val, src, ""});

    // Summary.
    result.summary = "Conservative 16 \xc3\x97 16 VE table generated.";
    char line[128];
    std::snprintf(line, sizeof(line), "\nTopology: %s",
        generator_types::topology_title_str(ctx.forced_induction_topology));
    result.summary += line;
    if (ctx.displacement_cc.has_value()) {
        std::snprintf(line, sizeof(line), "\nDisplacement: %.0f cc", *ctx.displacement_cc);
        result.summary += line;
    }
    if (ctx.cylinder_count.has_value()) {
        std::snprintf(line, sizeof(line), "\nCylinders: %d", *ctx.cylinder_count);
        result.summary += line;
    }
    if (ctx.cam_duration_deg.has_value()) {
        std::snprintf(line, sizeof(line), "\nCam duration: %.0f\xc2\xb0", *ctx.cam_duration_deg);
        result.summary += line;
    }
    if (!ctx.head_flow_class.empty()) {
        std::string hf = ctx.head_flow_class;
        for (auto& c : hf) if (c == '_') c = ' ';
        std::snprintf(line, sizeof(line), "\nHead flow: %s", hf.c_str());
        result.summary += line;
    }
    if (!ctx.intake_manifold_style.empty()) {
        std::string ms = ctx.intake_manifold_style;
        for (auto& c : ms) if (c == '_') c = ' ';
        std::snprintf(line, sizeof(line), "\nManifold: %s", ms.c_str());
        result.summary += line;
    }
    if (!result.warnings.empty()) {
        std::snprintf(line, sizeof(line), "\n%d warning(s): ", static_cast<int>(result.warnings.size()));
        result.summary += line;
        for (std::size_t i = 0; i < std::min(result.warnings.size(), std::size_t{3}); ++i) {
            if (i > 0) result.summary += "; ";
            result.summary += result.warnings[i];
        }
    }
    result.summary += "\nReview staged values before writing to RAM. "
                      "WOT cells are conservative \xe2\x80\x94 tune up with real data.";

    return result;
}

}  // namespace tuner_core::ve_table_generator
