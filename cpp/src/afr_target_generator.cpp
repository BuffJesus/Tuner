// SPDX-License-Identifier: MIT
#include "tuner_core/afr_target_generator.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::afr_target_generator {

namespace {

// NA target shaping.
constexpr double NA_CRUISE_AFR = 14.7;
constexpr double NA_LOAD_ENRICHMENT = 1.5;
constexpr double NA_WOT_AFR = NA_CRUISE_AFR - NA_LOAD_ENRICHMENT;  // 13.2
constexpr double NA_HIGH_RPM_BONUS = 0.2;

// Boosted target shaping.
constexpr double BOOST_WOT_AFR = 11.5;
constexpr double BOOST_WOT_AFR_TWIN = 11.5;
constexpr double BOOST_WOT_AFR_COMPOUND = 11.0;
constexpr double BOOST_WOT_AFR_SC = 12.0;
constexpr double BOOST_WOT_AFR_TWIN_CHARGE = 11.5;
constexpr double HIGH_BOOST_RICHER_AFR_STEP = 0.3;
constexpr double HIGH_BOOST_THRESHOLD_KPA_ABS = 200.0;
constexpr double NO_INTERCOOLER_RICHER_AFR_STEP = 0.2;
constexpr double SEQUENTIAL_TRANSITION_BLEND_LOW = 0.35;
constexpr double SEQUENTIAL_TRANSITION_BLEND_HIGH = 0.7;
constexpr double TWIN_CHARGE_TRANSITION_START = 0.55;
constexpr int BOOST_START_ROW = 8;

double base_wot_for_topology(ForcedInductionTopology t) {
    switch (t) {
        case ForcedInductionTopology::NA: return NA_WOT_AFR;
        case ForcedInductionTopology::SINGLE_TURBO: return BOOST_WOT_AFR;
        case ForcedInductionTopology::TWIN_TURBO_IDENTICAL: return BOOST_WOT_AFR_TWIN;
        case ForcedInductionTopology::TWIN_TURBO_SEQUENTIAL: return BOOST_WOT_AFR;
        case ForcedInductionTopology::TWIN_TURBO_COMPOUND: return BOOST_WOT_AFR_COMPOUND;
        case ForcedInductionTopology::TWIN_TURBO_UNEQUAL: return BOOST_WOT_AFR_TWIN;
        case ForcedInductionTopology::SINGLE_SUPERCHARGER: return BOOST_WOT_AFR_SC;
        case ForcedInductionTopology::TWIN_CHARGE: return BOOST_WOT_AFR_TWIN_CHARGE;
    }
    return NA_WOT_AFR;
}

double topology_wot_afr(ForcedInductionTopology t, double base_wot,
                         double rpm_norm, double load_norm) {
    if (t == ForcedInductionTopology::TWIN_TURBO_SEQUENTIAL) {
        double twin_wot = BOOST_WOT_AFR_TWIN;
        if (load_norm < 0.5) return base_wot;
        double blend = std::clamp(
            (rpm_norm - SEQUENTIAL_TRANSITION_BLEND_LOW) /
            (SEQUENTIAL_TRANSITION_BLEND_HIGH - SEQUENTIAL_TRANSITION_BLEND_LOW),
            0.0, 1.0);
        return base_wot + (twin_wot - base_wot) * blend;
    }
    if (t == ForcedInductionTopology::TWIN_CHARGE) {
        double turbo_wot = BOOST_WOT_AFR;
        double sc_wot = BOOST_WOT_AFR_SC;
        double blend = std::clamp(
            (load_norm - TWIN_CHARGE_TRANSITION_START) /
            (1.0 - TWIN_CHARGE_TRANSITION_START),
            0.0, 1.0);
        return sc_wot + (turbo_wot - sc_wot) * blend;
    }
    return base_wot;
}

double na_afr(double load_norm, double rpm_norm, double wot_afr) {
    double base = NA_CRUISE_AFR - load_norm * (NA_CRUISE_AFR - wot_afr);
    double rpm_bonus = (load_norm > 0.7) ? rpm_norm * NA_HIGH_RPM_BONUS : 0.0;
    return base - rpm_bonus;
}

double boosted_afr(double load_norm, double /*rpm_norm*/, double wot_afr, double stoich) {
    double boost_row_norm = static_cast<double>(BOOST_START_ROW) / (ROWS - 1);
    if (load_norm <= boost_row_norm) return stoich;
    double boost_norm = (load_norm - boost_row_norm) / (1.0 - boost_row_norm);
    return stoich - boost_norm * (stoich - wot_afr);
}

}  // namespace

Result generate(const AfrGeneratorContext& ctx, CalibrationIntent intent) {
    Result result;

    auto topology = ctx.forced_induction_topology;
    double stoich = ctx.stoich_ratio.value_or(STOICH_PETROL);
    bool is_boosted = topology != ForcedInductionTopology::NA;

    // Base WOT AFR with adjustments.
    double base_wot = base_wot_for_topology(topology);
    if (is_boosted && ctx.boost_target_kpa.has_value() &&
        *ctx.boost_target_kpa >= HIGH_BOOST_THRESHOLD_KPA_ABS) {
        base_wot -= HIGH_BOOST_RICHER_AFR_STEP;
    }
    if (is_boosted && !ctx.intercooler_present) {
        base_wot -= NO_INTERCOOLER_RICHER_AFR_STEP;
    }

    // Build table.
    std::vector<double> table;
    table.reserve(ROWS * COLS);
    for (int row = 0; row < ROWS; ++row) {
        double load_norm = static_cast<double>(row) / (ROWS - 1);
        for (int col = 0; col < COLS; ++col) {
            double rpm_norm = static_cast<double>(col) / (COLS - 1);
            double wot = topology_wot_afr(topology, base_wot, rpm_norm, load_norm);
            double afr;
            if (!is_boosted) {
                afr = na_afr(load_norm, rpm_norm, wot);
            } else {
                afr = boosted_afr(load_norm, rpm_norm, wot, stoich);
            }
            table.push_back(afr);
        }
    }

    // First-start enrichment.
    if (intent == CalibrationIntent::FIRST_START) {
        for (auto& v : table) v -= FIRST_START_ENRICHMENT;
    }

    // Clamp and round.
    for (auto& v : table) {
        v = std::max(AFR_MIN, std::min(AFR_MAX, v));
        v = std::round(v * 100.0) / 100.0;
    }

    result.values = std::move(table);
    result.rows = ROWS;
    result.columns = COLS;
    result.topology = topology;
    result.stoich = stoich;

    // Summary.
    const char* intent_label = (intent == CalibrationIntent::FIRST_START)
                                   ? "first-start" : "drivable base";
    char buf[512];
    std::snprintf(buf, sizeof(buf),
        "Conservative AFR targets for %s engine, %s intent. "
        "Stoich: %.1f. Review WOT cells before first run under load.",
        generator_types::topology_title_str(topology), intent_label, stoich);
    result.summary = buf;

    // Assumptions.
    auto src = AssumptionSource::FROM_CONTEXT;
    auto fb = AssumptionSource::CONSERVATIVE_FALLBACK;

    {
        char s[32];
        std::snprintf(s, sizeof(s), "%.1f", stoich);
        result.assumptions.push_back({
            "Stoich ratio", s,
            ctx.stoich_ratio.has_value() ? src : fb,
            ctx.stoich_ratio.has_value() ? "" : "Defaulted to petrol stoich (14.7)"
        });
    }
    result.assumptions.push_back({
        "Calibration intent",
        intent == CalibrationIntent::FIRST_START ? "first_start" : "drivable_base",
        src, ""
    });

    result.assumptions.push_back({"Induction topology",
        generator_types::topology_value_str(topology), src, ""});

    if (is_boosted) {
        if (ctx.boost_target_kpa.has_value()) {
            char b[64];
            std::snprintf(b, sizeof(b), "%.0f kPa", *ctx.boost_target_kpa);
            result.assumptions.push_back({"Boost target", b, src, ""});
        } else {
            result.assumptions.push_back({"Boost target", "not set", fb, ""});
        }
        result.assumptions.push_back({
            "Intercooler",
            ctx.intercooler_present ? "present" : "absent",
            src, ""
        });
        result.assumptions.push_back({
            "Injector pressure model",
            ctx.injector_pressure_model.empty() ? "not set" : ctx.injector_pressure_model,
            ctx.injector_pressure_model.empty() ? fb : src,
            ctx.injector_pressure_model.empty()
                ? "Boosted AFR targets assume a conservative generic pressure model."
                : ""
        });
        if (topology == ForcedInductionTopology::TWIN_TURBO_UNEQUAL) {
            result.assumptions.push_back({
                "Unequal twin sizing",
                "starter table treated like identical twins",
                fb,
                "Unequal turbo sizing was not modeled in AFR shaping; review transition and WOT cells once logs exist."
            });
        }
    }

    return result;
}

}  // namespace tuner_core::afr_target_generator
