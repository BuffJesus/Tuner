// SPDX-License-Identifier: MIT
//
// tuner_core::hardware_setup_validation — port of the Python
// `HardwareSetupValidationService`. Seventh sub-slice of the Phase 14
// workspace-services port (Slice 4).
//
// Mirrors all 10 validation rules from
// `tuner.services.hardware_setup_validation_service`:
//   - dwell excessive (> 10 ms → ERROR, coil damage risk)
//   - dwell zero (any dwell-named param == 0 → WARNING)
//   - dwell implausible range (`dwellrun` outside 1.5–6.0 ms → WARNING)
//   - trigger geometry (missing teeth >= total teeth → ERROR; >= half → WARNING)
//   - dead time zero (injector dead time == 0 → WARNING)
//   - injector dead time implausibly high (> 5 ms → WARNING, units error)
//   - injector flow zero (rated flow == 0 → WARNING)
//   - required fuel zero (`reqFuel` == 0 → WARNING)
//   - trigger angle zero (TDC reference == 0 → WARNING)
//   - wideband without calibration (egoType >= 2 with no AFR cal table → WARNING)
//
// Each rule's rejection message is reproduced byte-for-byte from the
// Python f-strings, including `{val:.1f}` / `{teeth:.0f}` precision
// formatting.

#pragma once

#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::hardware_setup_validation {

enum class Severity {
    WARNING,
    ERROR,
};

struct Issue {
    Severity severity = Severity::WARNING;
    std::string message;
    std::optional<std::string> parameter_name;  // nullopt = page-level / cross-field
    std::optional<std::string> detail;
};

// Caller-supplied lookup: returns the current numeric value for a
// named parameter, or nullopt if the value is unavailable.
using ValueLookup = std::function<std::optional<double>(std::string_view)>;

// Run every validation rule against the given parameter set. Returns
// the issues in the same order the Python service produces them
// (rule order + per-rule discovery order, which is set-iteration on
// the Python side and `parameter_names` input order on the C++ side
// — see the parity test for the iteration discipline).
std::vector<Issue> validate(
    const std::vector<std::string>& parameter_names,
    const ValueLookup& get_value);

}  // namespace tuner_core::hardware_setup_validation
