// SPDX-License-Identifier: MIT
#include "tuner_core/idle_rpm_generator.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::idle_rpm_generator {

namespace {

// Reference CLT breakpoints (Ford300 / Speeduino u16p2).
const double IAC_BINS[BIN_COUNT] = {
    -26.0, 2.0, 22.0, 39.0, 53.0, 66.0, 79.0, 94.0, 107.0, 117.0
};

// Normalised cold-fraction at each bin (1.0 = full cold bump, 0.0 = warm).
const double IAC_SHAPE[BIN_COUNT] = {
    1.000, 0.762, 0.643, 0.524, 0.381, 0.143, 0.119, 0.024, 0.024, 0.000
};

// Adjustment constants.
constexpr double HIGH_CAM_RPM_EXTRA = 100.0;
constexpr double MILD_PORTED_IDLE_EXTRA = 20.0;
constexpr double RACE_PORTED_IDLE_EXTRA = 50.0;
constexpr double SHORT_RUNNER_IDLE_EXTRA = 20.0;
constexpr double ITB_IDLE_EXTRA = 80.0;
constexpr double LOG_COMPACT_IDLE_EXTRA = 10.0;
constexpr double LONG_RUNNER_IDLE_REDUCTION = 10.0;

struct RpmParams {
    double warm_rpm;
    double cold_bump;
};

RpmParams compute_rpm_params(
    const GeneratorContext& ctx,
    CalibrationIntent intent,
    std::vector<std::string>& warnings)
{
    bool is_boosted = ctx.forced_induction_topology != ForcedInductionTopology::NA;
    double warm_rpm = is_boosted ? WARM_RPM_BOOSTED : WARM_RPM_NA;
    double cold_bump = (intent == CalibrationIntent::FIRST_START)
                           ? COLD_BUMP_FIRST_START
                           : COLD_BUMP_DRIVABLE;

    if (ctx.cam_duration_deg.has_value()) {
        double cam = *ctx.cam_duration_deg;
        if (cam >= HIGH_CAM_THRESHOLD_DEG) {
            warm_rpm += HIGH_CAM_RPM_EXTRA;
            cold_bump += HIGH_CAM_RPM_EXTRA;
            char buf[256];
            std::snprintf(buf, sizeof(buf),
                "High cam duration (%.0f\xc2\xb0) detected: warm idle target raised by "
                "%.0f RPM for stability.", cam, HIGH_CAM_RPM_EXTRA);
            warnings.push_back(buf);
        }
    } else {
        warnings.push_back(
            "Cam duration not set \xe2\x80\x94 using standard idle RPM targets. "
            "Raise warm idle if the engine has an aggressive cam profile.");
    }

    if (ctx.head_flow_class == "mild_ported") {
        warm_rpm += MILD_PORTED_IDLE_EXTRA;
        cold_bump += MILD_PORTED_IDLE_EXTRA * 0.5;
    } else if (ctx.head_flow_class == "race_ported") {
        warm_rpm += RACE_PORTED_IDLE_EXTRA;
        cold_bump += RACE_PORTED_IDLE_EXTRA * 0.6;
        warnings.push_back(
            "Race-ported head selected - warm idle target raised for first-start stability.");
    }

    if (ctx.intake_manifold_style == "long_runner_plenum") {
        warm_rpm -= LONG_RUNNER_IDLE_REDUCTION;
    } else if (ctx.intake_manifold_style == "short_runner_plenum") {
        warm_rpm += SHORT_RUNNER_IDLE_EXTRA;
        cold_bump += SHORT_RUNNER_IDLE_EXTRA * 0.5;
    } else if (ctx.intake_manifold_style == "itb") {
        warm_rpm += ITB_IDLE_EXTRA;
        cold_bump += ITB_IDLE_EXTRA * 0.75;
        warnings.push_back(
            "ITB manifold selected - idle targets raised because low-load airflow "
            "and MAP signal are less forgiving.");
    } else if (ctx.intake_manifold_style == "log_compact") {
        warm_rpm += LOG_COMPACT_IDLE_EXTRA;
    }

    return {warm_rpm, cold_bump};
}

}  // namespace

Result generate(const GeneratorContext& ctx, CalibrationIntent intent) {
    Result result;

    std::vector<std::string> warnings;
    auto [warm_rpm, cold_bump] = compute_rpm_params(ctx, intent, warnings);

    // Build CLT bins.
    result.clt_bins.assign(std::begin(IAC_BINS), std::end(IAC_BINS));

    // Build RPM targets.
    result.rpm_targets.reserve(BIN_COUNT);
    for (int i = 0; i < BIN_COUNT; ++i) {
        double raw = warm_rpm + cold_bump * IAC_SHAPE[i];
        raw = std::max(RPM_MIN, std::min(RPM_MAX, raw));
        // Round to nearest 10 RPM (Speeduino U08 ×10 quantization).
        double rounded = std::round(raw / 10.0) * 10.0;
        result.rpm_targets.push_back(rounded);
    }

    // Summary text.
    const char* intent_label = (intent == CalibrationIntent::FIRST_START)
                                   ? "first-start" : "drivable base";
    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "Conservative idle RPM targets (%s). "
        "Warm idle: %.0f RPM; cold idle: %.0f RPM at %.0f\xc2\xb0""C. "
        "Review after first cold start \xe2\x80\x94 adjust warm target to match desired idle quality.",
        intent_label, warm_rpm, result.rpm_targets[0], IAC_BINS[0]);
    result.summary = buf;
    result.warnings = std::move(warnings);

    // Assumptions.
    auto src = AssumptionSource::FROM_CONTEXT;
    auto fb = AssumptionSource::CONSERVATIVE_FALLBACK;

    result.assumptions.push_back({
        "Calibration intent",
        intent == CalibrationIntent::FIRST_START ? "first_start" : "drivable_base",
        src, ""
    });
    result.assumptions.push_back({
        "Induction topology",
        generator_types::topology_value_str(ctx.forced_induction_topology),
        src, ""
    });

    if (ctx.cam_duration_deg.has_value()) {
        char cam_buf[64];
        std::snprintf(cam_buf, sizeof(cam_buf), "%.0f deg", *ctx.cam_duration_deg);
        result.assumptions.push_back({"Cam duration", cam_buf, src, ""});
    } else {
        result.assumptions.push_back({"Cam duration", "not set", fb, ""});
    }

    result.assumptions.push_back({
        "Head flow class",
        ctx.head_flow_class.empty() ? "not set" : ctx.head_flow_class,
        ctx.head_flow_class.empty() ? fb : src, ""
    });
    result.assumptions.push_back({
        "Manifold style",
        ctx.intake_manifold_style.empty() ? "not set" : ctx.intake_manifold_style,
        ctx.intake_manifold_style.empty() ? fb : src, ""
    });

    return result;
}

}  // namespace tuner_core::idle_rpm_generator
