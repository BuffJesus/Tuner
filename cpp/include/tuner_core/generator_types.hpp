// SPDX-License-Identifier: MIT
//
// tuner_core::generator_types — shared domain types for all generator
// services. Extracted from idle_rpm_generator.hpp during the simplify
// pass so that downstream generators don't need to include idle-RPM-
// specific logic just to get CalibrationIntent or ForcedInductionTopology.

#pragma once

#include <optional>
#include <string>

namespace tuner_core::generator_types {

enum class CalibrationIntent { FIRST_START, DRIVABLE_BASE };

enum class ForcedInductionTopology {
    NA,
    SINGLE_TURBO,
    TWIN_TURBO_IDENTICAL,
    TWIN_TURBO_SEQUENTIAL,
    TWIN_TURBO_COMPOUND,
    TWIN_TURBO_UNEQUAL,
    SINGLE_SUPERCHARGER,
    TWIN_CHARGE,
};

enum class AssumptionSource {
    FROM_CONTEXT,
    COMPUTED,
    CONSERVATIVE_FALLBACK,
};

struct Assumption {
    std::string label;
    std::string value_str;
    AssumptionSource source = AssumptionSource::FROM_CONTEXT;
    std::string note;
};

// Topology enum → string value (e.g. "single_turbo"). Used by all
// generators for assumption and summary text building.
inline const char* topology_value_str(ForcedInductionTopology t) {
    switch (t) {
        case ForcedInductionTopology::NA: return "na";
        case ForcedInductionTopology::SINGLE_TURBO: return "single_turbo";
        case ForcedInductionTopology::TWIN_TURBO_IDENTICAL: return "twin_turbo_identical";
        case ForcedInductionTopology::TWIN_TURBO_SEQUENTIAL: return "twin_turbo_sequential";
        case ForcedInductionTopology::TWIN_TURBO_COMPOUND: return "twin_turbo_compound";
        case ForcedInductionTopology::TWIN_TURBO_UNEQUAL: return "twin_turbo_unequal";
        case ForcedInductionTopology::SINGLE_SUPERCHARGER: return "single_supercharger";
        case ForcedInductionTopology::TWIN_CHARGE: return "twin_charge";
    }
    return "na";
}

// Topology enum → display title (e.g. "Single Turbo").
inline const char* topology_title_str(ForcedInductionTopology t) {
    switch (t) {
        case ForcedInductionTopology::NA: return "Na";
        case ForcedInductionTopology::SINGLE_TURBO: return "Single Turbo";
        case ForcedInductionTopology::TWIN_TURBO_IDENTICAL: return "Twin Turbo Identical";
        case ForcedInductionTopology::TWIN_TURBO_SEQUENTIAL: return "Twin Turbo Sequential";
        case ForcedInductionTopology::TWIN_TURBO_COMPOUND: return "Twin Turbo Compound";
        case ForcedInductionTopology::TWIN_TURBO_UNEQUAL: return "Twin Turbo Unequal";
        case ForcedInductionTopology::SINGLE_SUPERCHARGER: return "Single Supercharger";
        case ForcedInductionTopology::TWIN_CHARGE: return "Twin Charge";
    }
    return "Na";
}

// Confidence label thresholds — shared by VE and WUE analyze services.
constexpr int CONFIDENCE_LOW = 3;
constexpr int CONFIDENCE_MEDIUM = 10;
constexpr int CONFIDENCE_HIGH = 30;

inline const char* confidence_label(int sample_count) {
    if (sample_count < CONFIDENCE_LOW) return "insufficient";
    if (sample_count < CONFIDENCE_MEDIUM) return "low";
    if (sample_count < CONFIDENCE_HIGH) return "medium";
    return "high";
}

}  // namespace tuner_core::generator_types
