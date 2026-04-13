// SPDX-License-Identifier: MIT
#include "tuner_core/startup_enrichment_generator.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::startup_enrichment_generator {

namespace {

// Reference bins and values.
const double WUE_BINS[] = {-40, -26, 10, 19, 28, 37, 46, 58, 63, 64};
const double WUE_RATES_REF[] = {180, 175, 168, 154, 134, 121, 112, 104, 102, 100};
constexpr double WUE_REF_COLD = 180.0;
constexpr int WUE_COUNT = 10;

const double CRANK_BINS[] = {-40, 0, 30, 70};
const double CRANK_RATES_REF[] = {140, 115, 105, 100};
constexpr double CRANK_REF_COLD = 140.0;
constexpr int CRANK_COUNT = 4;

const double ASE_BINS[] = {-20, 0, 40, 80};
const double ASE_PCT_REF[] = {25, 20, 15, 10};
const double ASE_COUNT_REF[] = {25, 20, 15, 6};
constexpr int ASE_COUNT = 4;

// Fuel type thresholds.
constexpr double STOICH_E85_THRESHOLD = 10.5;
constexpr double STOICH_BLEND_THRESHOLD = 13.8;
constexpr double WUE_COLD_PETROL = 180.0;
constexpr double WUE_COLD_E85 = 210.0;

// Intent extras.
constexpr double FIRST_START_WUE_EXTRA = 8.0;
constexpr double FIRST_START_CRANK_EXTRA = 8.0;
constexpr double FIRST_START_ASE_PCT_EXTRA = 5.0;
constexpr double FIRST_START_ASE_COUNT_EXTRA = 5.0;

// CR adjustments.
constexpr double CR_HIGH_THRESHOLD = 11.0;
constexpr double CR_LOW_THRESHOLD = 8.0;
constexpr double CRANK_CR_HIGH_DELTA = -8.0;
constexpr double CRANK_CR_LOW_DELTA = 12.0;

// Injector characterization extras.
constexpr double FLOW_ONLY_WUE_EXTRA = 6.0;
constexpr double FLOW_ONLY_CRANK_EXTRA = 5.0;
constexpr double FLOW_ONLY_ASE_PCT_EXTRA = 4.0;
constexpr double FLOW_ONLY_ASE_COUNT_EXTRA = 3.0;
constexpr double SINGLE_DT_WUE_EXTRA = 3.0;
constexpr double SINGLE_DT_CRANK_EXTRA = 2.0;
constexpr double SINGLE_DT_ASE_PCT_EXTRA = 2.0;
constexpr double SINGLE_DT_ASE_COUNT_EXTRA = 1.0;

constexpr double ITB_ASE_PCT_EXTRA = 3.0;
constexpr double ITB_ASE_COUNT_EXTRA = 2.0;
constexpr double RACE_PORTED_ASE_PCT_EXTRA = 2.0;
constexpr double RACE_PORTED_ASE_COUNT_EXTRA = 1.0;

std::vector<double> scale_from_reference(const double* ref, int count,
                                          double ref_cold, double target_cold) {
    double ref_excess = std::max(1e-6, ref_cold - 100.0);
    double target_excess = target_cold - 100.0;
    double scale = target_excess / ref_excess;
    std::vector<double> out;
    out.reserve(count);
    for (int i = 0; i < count; ++i) {
        out.push_back(100.0 + (ref[i] - 100.0) * scale);
    }
    return out;
}

const char* intent_label(CalibrationIntent i) {
    return (i == CalibrationIntent::FIRST_START) ? "first-start" : "drivable base";
}

double wue_cold_pct(const StartupContext& ctx, CalibrationIntent intent,
                     std::vector<std::string>& warnings) {
    double cold;
    if (!ctx.stoich_ratio.has_value()) {
        warnings.push_back("Stoich ratio not set \xe2\x80\x94 assuming petrol (14.7). "
                           "Review WUE if using E85 or high-ethanol blend.");
        cold = WUE_COLD_PETROL;
    } else if (*ctx.stoich_ratio <= STOICH_E85_THRESHOLD) {
        cold = WUE_COLD_E85;
    } else if (*ctx.stoich_ratio < STOICH_BLEND_THRESHOLD) {
        double blend = (*ctx.stoich_ratio - STOICH_E85_THRESHOLD) /
                       (STOICH_BLEND_THRESHOLD - STOICH_E85_THRESHOLD);
        cold = WUE_COLD_E85 + blend * (WUE_COLD_PETROL - WUE_COLD_E85);
    } else {
        cold = WUE_COLD_PETROL;
    }
    if (intent == CalibrationIntent::FIRST_START) cold += FIRST_START_WUE_EXTRA;
    if (ctx.injector_characterization == "nominal_flow_only") {
        cold += FLOW_ONLY_WUE_EXTRA;
        warnings.push_back("Injector data is flow-only - adding extra cold-start enrichment for low-pulsewidth uncertainty.");
    } else if (ctx.injector_characterization == "flow_plus_deadtime") {
        cold += SINGLE_DT_WUE_EXTRA;
        warnings.push_back("Injector data uses a single dead-time value - adding mild cold-start enrichment margin.");
    }
    return cold;
}

double crank_cold_pct(const StartupContext& ctx, CalibrationIntent intent,
                       std::vector<std::string>& warnings) {
    double cold = CRANK_REF_COLD;
    if (!ctx.compression_ratio.has_value()) {
        warnings.push_back("Compression ratio not set \xe2\x80\x94 using standard cranking enrichment baseline.");
    } else if (*ctx.compression_ratio >= CR_HIGH_THRESHOLD) {
        cold += CRANK_CR_HIGH_DELTA;
    } else if (*ctx.compression_ratio <= CR_LOW_THRESHOLD) {
        cold += CRANK_CR_LOW_DELTA;
    }
    if (intent == CalibrationIntent::FIRST_START) cold += FIRST_START_CRANK_EXTRA;
    if (ctx.injector_characterization == "nominal_flow_only") {
        cold += FLOW_ONLY_CRANK_EXTRA;
        warnings.push_back("Injector data is flow-only - adding extra cranking enrichment for startup safety.");
    } else if (ctx.injector_characterization == "flow_plus_deadtime") {
        cold += SINGLE_DT_CRANK_EXTRA;
    }
    return cold;
}

}  // namespace

WueResult generate_wue(const StartupContext& ctx, CalibrationIntent intent) {
    WueResult result;
    std::vector<std::string> warnings;
    double cold = wue_cold_pct(ctx, intent, warnings);
    auto raw = scale_from_reference(WUE_RATES_REF, WUE_COUNT, WUE_REF_COLD, cold);
    result.clt_bins.assign(std::begin(WUE_BINS), std::end(WUE_BINS));
    result.enrichment_pct.reserve(WUE_COUNT);
    for (double v : raw) {
        result.enrichment_pct.push_back(std::round(std::clamp(v, 100.0, 255.0) * 10.0) / 10.0);
    }
    result.warnings = std::move(warnings);

    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "Conservative WUE starter (%s). Cold enrichment: %.0f%% at %.0f\xc2\xb0""C "
        "\xe2\x86\x92 100%% at %.0f\xc2\xb0""C. "
        "Review and adjust for your climate and cold-start idle quality.",
        intent_label(intent), cold, WUE_BINS[0], WUE_BINS[WUE_COUNT - 1]);
    result.summary = buf;

    auto src = AssumptionSource::FROM_CONTEXT;
    auto fb = AssumptionSource::CONSERVATIVE_FALLBACK;
    if (ctx.stoich_ratio.has_value()) {
        char s[32]; std::snprintf(s, sizeof(s), "%.1f", *ctx.stoich_ratio);
        result.assumptions.push_back({"Stoich / fuel type", s, src, ""});
    } else {
        result.assumptions.push_back({"Stoich / fuel type", "not set (defaulted to petrol 14.7)", fb, ""});
    }
    result.assumptions.push_back({"Injector data depth",
        ctx.injector_characterization.empty() ? "not set" : ctx.injector_characterization,
        ctx.injector_characterization.empty() ? fb : src, ""});
    result.assumptions.push_back({"Calibration intent",
        intent == CalibrationIntent::FIRST_START ? "first_start" : "drivable_base", src, ""});

    return result;
}

CrankingResult generate_cranking(const StartupContext& ctx, CalibrationIntent intent) {
    CrankingResult result;
    std::vector<std::string> warnings;
    double cold = crank_cold_pct(ctx, intent, warnings);
    auto raw = scale_from_reference(CRANK_RATES_REF, CRANK_COUNT, CRANK_REF_COLD, cold);
    result.clt_bins.assign(std::begin(CRANK_BINS), std::end(CRANK_BINS));
    result.enrichment_pct.reserve(CRANK_COUNT);
    for (double v : raw) {
        result.enrichment_pct.push_back(std::round(std::clamp(v, 100.0, 255.0) * 10.0) / 10.0);
    }
    result.warnings = std::move(warnings);

    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "Conservative cranking enrichment (%s). Cold: %.0f%% at %.0f\xc2\xb0""C "
        "\xe2\x86\x92 100%% at %.0f\xc2\xb0""C. "
        "Review against your starter motor and cold-start fueling behavior.",
        intent_label(intent), cold, CRANK_BINS[0], CRANK_BINS[CRANK_COUNT - 1]);
    result.summary = buf;

    auto src = AssumptionSource::FROM_CONTEXT;
    auto fb = AssumptionSource::CONSERVATIVE_FALLBACK;
    result.assumptions.push_back({"Compression ratio",
        ctx.compression_ratio.has_value()
            ? [&]{ char b[32]; std::snprintf(b, sizeof(b), "%.1f:1", *ctx.compression_ratio); return std::string(b); }()
            : std::string("not set"),
        ctx.compression_ratio.has_value() ? src : fb, ""});
    if (ctx.stoich_ratio.has_value()) {
        char s[32]; std::snprintf(s, sizeof(s), "%.1f", *ctx.stoich_ratio);
        result.assumptions.push_back({"Stoich / fuel type", s, src, ""});
    } else {
        result.assumptions.push_back({"Stoich / fuel type", "not set (defaulted to petrol 14.7)", fb, ""});
    }
    result.assumptions.push_back({"Calibration intent",
        intent == CalibrationIntent::FIRST_START ? "first_start" : "drivable_base", src, ""});

    return result;
}

AseResult generate_ase(const StartupContext& ctx, CalibrationIntent intent) {
    AseResult result;
    std::vector<std::string> warnings;

    double extra_pct = (intent == CalibrationIntent::FIRST_START) ? FIRST_START_ASE_PCT_EXTRA : 0.0;
    double extra_count = (intent == CalibrationIntent::FIRST_START) ? FIRST_START_ASE_COUNT_EXTRA : 0.0;

    if (ctx.injector_characterization == "nominal_flow_only") {
        extra_pct += FLOW_ONLY_ASE_PCT_EXTRA;
        extra_count += FLOW_ONLY_ASE_COUNT_EXTRA;
        warnings.push_back("Injector data is flow-only - ASE increased to cover startup transient uncertainty.");
    } else if (ctx.injector_characterization == "flow_plus_deadtime") {
        extra_pct += SINGLE_DT_ASE_PCT_EXTRA;
        extra_count += SINGLE_DT_ASE_COUNT_EXTRA;
    }
    if (ctx.intake_manifold_style == "itb") {
        extra_pct += ITB_ASE_PCT_EXTRA;
        extra_count += ITB_ASE_COUNT_EXTRA;
        warnings.push_back("ITB manifold selected - ASE increased for low-speed airflow instability during startup.");
    }
    if (ctx.head_flow_class == "race_ported") {
        extra_pct += RACE_PORTED_ASE_PCT_EXTRA;
        extra_count += RACE_PORTED_ASE_COUNT_EXTRA;
    }

    result.clt_bins.assign(std::begin(ASE_BINS), std::end(ASE_BINS));
    result.enrichment_pct.reserve(ASE_COUNT);
    result.duration_seconds.reserve(ASE_COUNT);
    for (int i = 0; i < ASE_COUNT; ++i) {
        result.enrichment_pct.push_back(
            std::round(std::clamp(ASE_PCT_REF[i] + extra_pct, 0.0, 155.0) * 10.0) / 10.0);
        result.duration_seconds.push_back(
            std::round(std::clamp(ASE_COUNT_REF[i] + extra_count, 0.0, 255.0) * 10.0) / 10.0);
    }

    if (ctx.forced_induction_topology != ForcedInductionTopology::NA) {
        warnings.push_back("Forced-induction engine detected: consider increasing ASE duration "
                           "at cold CLT bins \xe2\x80\x94 boost at start can lean out the mixture briefly.");
    }

    result.warnings = std::move(warnings);

    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "Conservative ASE starter (%s). Added enrichment: %.0f%% for %.0fs at %.0f\xc2\xb0""C. "
        "Review enrichment levels against idle stability after first start.",
        intent_label(intent), result.enrichment_pct[0], result.duration_seconds[0], ASE_BINS[0]);
    result.summary = buf;

    auto src = AssumptionSource::FROM_CONTEXT;
    auto fb = AssumptionSource::CONSERVATIVE_FALLBACK;
    result.assumptions.push_back({"Calibration intent",
        intent == CalibrationIntent::FIRST_START ? "first_start" : "drivable_base", src, ""});
    result.assumptions.push_back({"Injector data depth",
        ctx.injector_characterization.empty() ? "not set" : ctx.injector_characterization,
        ctx.injector_characterization.empty() ? fb : src, ""});
    result.assumptions.push_back({"Manifold style",
        ctx.intake_manifold_style.empty() ? "not set" : ctx.intake_manifold_style,
        ctx.intake_manifold_style.empty() ? fb : src, ""});

    const char* topo_val;
    switch (ctx.forced_induction_topology) {
        case ForcedInductionTopology::NA: topo_val = "na"; break;
        case ForcedInductionTopology::SINGLE_TURBO: topo_val = "single_turbo"; break;
        default: topo_val = "boosted"; break;
    }
    result.assumptions.push_back({"Induction topology", topo_val, src, ""});

    return result;
}

}  // namespace tuner_core::startup_enrichment_generator
