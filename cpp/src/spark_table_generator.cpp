// SPDX-License-Identifier: MIT
#include "tuner_core/spark_table_generator.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::spark_table_generator {

namespace {

constexpr double IDLE_TIMING_BASE = 10.0;
constexpr double NA_WOT_MAX = 28.0;
constexpr double CR_REFERENCE = 9.5;
constexpr double CR_TIMING_PENALTY_PER_UNIT = 1.5;
constexpr double HIGH_CR_THRESHOLD = 11.0;
constexpr double HIGH_CR_WOT_PENALTY = 3.0;
constexpr double DRIVABLE_BONUS = 3.0;
constexpr double TURBO_WOT_RETARD = 10.0;
constexpr double SUPERCHARGER_WOT_RETARD = 6.0;
constexpr double TWIN_CHARGE_WOT_RETARD = 8.0;
constexpr double BOOST_RETARD_BASELINE_KPA_ABS = 170.0;
constexpr double BOOST_RETARD_PER_50KPA = 1.0;
constexpr double NO_INTERCOOLER_EXTRA_RETARD = 1.5;
constexpr double HIGH_RPM_TAPER_DEG = 2.0;

double base_advance(int row, int col) {
    double load_norm = static_cast<double>(row) / (ROWS - 1);
    double load_advance = IDLE_TIMING_BASE + (NA_WOT_MAX - IDLE_TIMING_BASE) * load_norm;

    double rpm_factor;
    if (col < 3) {
        rpm_factor = 0.55 + 0.15 * col;
    } else if (col <= 10) {
        rpm_factor = 1.0;
    } else {
        double taper_progress = static_cast<double>(col - 10) / (COLS - 1 - 10);
        double taper = HIGH_RPM_TAPER_DEG * taper_progress;
        rpm_factor = 1.0 - taper / std::max(load_advance, 1.0);
        rpm_factor = std::max(0.85, rpm_factor);
    }
    return load_advance * rpm_factor;
}

double cr_correction(int row, const std::optional<double>& cr, double cr_penalty) {
    if (!cr.has_value() || cr_penalty <= 0.0) return 0.0;
    double load_norm = static_cast<double>(row) / (ROWS - 1);
    if (load_norm < 0.4) return 0.0;
    double scale = (load_norm - 0.4) / 0.6;
    double penalty = cr_penalty * scale;
    if (*cr > HIGH_CR_THRESHOLD && load_norm > 0.75) {
        penalty += HIGH_CR_WOT_PENALTY * ((load_norm - 0.75) / 0.25);
    }
    return penalty;
}

double topology_retard(int row, ForcedInductionTopology t) {
    double load_norm = static_cast<double>(row) / (ROWS - 1);
    if (t == ForcedInductionTopology::NA) return 0.0;
    if (load_norm < 0.4) return 0.0;
    double scale = (load_norm - 0.4) / 0.6;

    if (t == ForcedInductionTopology::SINGLE_SUPERCHARGER) {
        return -SUPERCHARGER_WOT_RETARD * scale;
    }
    if (t == ForcedInductionTopology::TWIN_CHARGE) {
        return -TWIN_CHARGE_WOT_RETARD * scale;
    }
    // All turbo variants.
    return -TURBO_WOT_RETARD * scale;
}

double boost_target_retard(int row, const SparkGeneratorContext& ctx) {
    if (ctx.forced_induction_topology == ForcedInductionTopology::NA) return 0.0;
    if (!ctx.boost_target_kpa.has_value() ||
        *ctx.boost_target_kpa <= BOOST_RETARD_BASELINE_KPA_ABS) return 0.0;
    double load_norm = static_cast<double>(row) / (ROWS - 1);
    double extra = *ctx.boost_target_kpa - BOOST_RETARD_BASELINE_KPA_ABS;
    double retard = (extra / 50.0) * BOOST_RETARD_PER_50KPA * load_norm;
    if (!ctx.intercooler_present) {
        retard += NO_INTERCOOLER_EXTRA_RETARD * load_norm;
    }
    return retard;
}

// Use shared topology string converters from generator_types.hpp.

}  // namespace

Result generate(const SparkGeneratorContext& ctx, CalibrationIntent intent) {
    Result result;
    result.topology = ctx.forced_induction_topology;
    result.compression_ratio = ctx.compression_ratio;
    result.calibration_intent = intent;

    std::vector<std::string> warnings;

    double cr_penalty = 0.0;
    if (!ctx.compression_ratio.has_value()) {
        warnings.push_back("Compression ratio not provided \xe2\x80\x94 using default shaping");
    } else if (*ctx.compression_ratio > CR_REFERENCE) {
        cr_penalty = (*ctx.compression_ratio - CR_REFERENCE) * CR_TIMING_PENALTY_PER_UNIT;
    }

    double intent_bonus = (intent == CalibrationIntent::DRIVABLE_BASE) ? DRIVABLE_BONUS : 0.0;

    if (!ctx.cylinder_count.has_value()) {
        warnings.push_back("Cylinder count not provided \xe2\x80\x94 using default shaping");
    }
    if (!ctx.dwell_ms.has_value()) {
        warnings.push_back("Dwell not provided \xe2\x80\x94 verify coil dwell separately before long key-on testing");
    }

    std::vector<double> values;
    values.reserve(ROWS * COLS);
    for (int row = 0; row < ROWS; ++row) {
        for (int col = 0; col < COLS; ++col) {
            double adv = base_advance(row, col);
            adv -= cr_correction(row, ctx.compression_ratio, cr_penalty);
            adv += topology_retard(row, ctx.forced_induction_topology);
            adv -= boost_target_retard(row, ctx);
            adv += intent_bonus * (static_cast<double>(row) / (ROWS - 1));
            adv = std::max(CRANK_TIMING_FLOOR, adv);
            adv = std::round(std::min(TIMING_MAX, adv) * 10.0) / 10.0;
            values.push_back(adv);
        }
    }

    result.values = std::move(values);
    result.warnings = std::move(warnings);

    // Assumptions.
    auto src = AssumptionSource::FROM_CONTEXT;
    auto fb = AssumptionSource::CONSERVATIVE_FALLBACK;

    if (ctx.compression_ratio.has_value()) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "%.1f:1", *ctx.compression_ratio);
        result.assumptions.push_back({"Compression ratio", buf, src, ""});
    } else {
        result.assumptions.push_back({"Compression ratio", "not set", fb, ""});
    }
    result.assumptions.push_back({
        "Calibration intent",
        intent == CalibrationIntent::FIRST_START ? "first_start" : "drivable_base",
        src, ""
    });
    result.assumptions.push_back({"Induction topology", generator_types::topology_value_str(ctx.forced_induction_topology), src, ""});

    if (ctx.cylinder_count.has_value()) {
        char buf[16];
        std::snprintf(buf, sizeof(buf), "%d", *ctx.cylinder_count);
        result.assumptions.push_back({"Cylinders", buf, src, ""});
    } else {
        result.assumptions.push_back({"Cylinders", "not set", fb, ""});
    }
    if (ctx.dwell_ms.has_value()) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "%.1f ms", *ctx.dwell_ms);
        result.assumptions.push_back({"Dwell", buf, src, ""});
    } else {
        result.assumptions.push_back({"Dwell", "not set", fb, ""});
    }

    if (ctx.forced_induction_topology != ForcedInductionTopology::NA) {
        if (ctx.boost_target_kpa.has_value()) {
            char buf[32];
            std::snprintf(buf, sizeof(buf), "%.0f kPa", *ctx.boost_target_kpa);
            result.assumptions.push_back({"Boost target", buf, src, ""});
        } else {
            result.assumptions.push_back({"Boost target", "not set", fb, ""});
        }
        result.assumptions.push_back({
            "Intercooler",
            ctx.intercooler_present ? "present" : "absent",
            src, ""
        });
    }

    // Summary.
    std::string summary = "Conservative 16 \xc3\x97 16 spark advance table generated.\n";
    char line[128];
    std::snprintf(line, sizeof(line), "Topology: %s", generator_types::topology_title_str(ctx.forced_induction_topology));
    summary += line;
    if (ctx.compression_ratio.has_value()) {
        std::snprintf(line, sizeof(line), "\nCompression ratio: %.1f:1", *ctx.compression_ratio);
        summary += line;
    }
    if (ctx.cylinder_count.has_value()) {
        std::snprintf(line, sizeof(line), "\nCylinders: %d", *ctx.cylinder_count);
        summary += line;
    }
    summary += "\nIntent: ";
    summary += (intent == CalibrationIntent::FIRST_START) ? "First Start" : "Drivable Base";
    if (!result.warnings.empty()) {
        std::snprintf(line, sizeof(line), "\n%d warning(s): ", static_cast<int>(result.warnings.size()));
        summary += line;
        for (std::size_t i = 0; i < std::min(result.warnings.size(), std::size_t{3}); ++i) {
            if (i > 0) summary += "; ";
            summary += result.warnings[i];
        }
    }
    summary += "\nReview staged values before writing to RAM. "
               "WOT advance is very conservative \xe2\x80\x94 verify against knock data before tuning.";
    result.summary = summary;

    return result;
}

}  // namespace tuner_core::spark_table_generator
