// SPDX-License-Identifier: MIT
//
// tuner_core::sensor_setup_checklist — port of SensorSetupChecklistService.
// Sub-slice 56 of Phase 14 Slice 4.
//
// Nine typed sensor hardware checks: ego type, wideband cal, stoich,
// flex cal, TPS range, MAP range, knock pin, oil cal, baro cal.
// Pure logic, no Qt.

#pragma once

#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::sensor_setup_checklist {

// -----------------------------------------------------------------------
// Domain
// -----------------------------------------------------------------------

enum class Status { OK, INFO, NEEDED, WARNING, ERROR };

struct ChecklistItem {
    std::string key;
    std::string title;
    Status status = Status::OK;
    std::string detail;
    std::string parameter_name;  // empty = not bound to a specific param
};

struct Parameter {
    std::string name;
    std::string label;
    std::vector<std::string> options;        // display labels
    std::vector<std::string> option_values;  // matching raw values
};

struct Page {
    std::vector<Parameter> parameters;
};

/// Callback: returns numeric tune value for a parameter name, or nullopt.
using ValueGetter = std::function<std::optional<double>(const std::string&)>;

/// Callback: returns the display label for the current option value, or empty.
using OptionLabelGetter = std::function<std::string(const Parameter& param)>;

// -----------------------------------------------------------------------
// Service
// -----------------------------------------------------------------------

std::vector<ChecklistItem> validate(
    const std::vector<Page>& pages,
    ValueGetter get_value,
    OptionLabelGetter get_option_label);

}  // namespace tuner_core::sensor_setup_checklist
