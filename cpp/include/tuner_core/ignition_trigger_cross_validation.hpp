// SPDX-License-Identifier: MIT
//
// tuner_core::ignition_trigger_cross_validation — port of
// IgnitionTriggerCrossValidationService.  Sub-slice 68 of Phase 14 Slice 4.
//
// Cross-validates ignition and trigger hardware setup: dwell, reference
// angle, trigger geometry, knock pin, coil vs cylinders, sequential cam
// sync, and trigger topology summary.  Pure logic, no Qt.

#pragma once

#include "sensor_setup_checklist.hpp"  // reuse ChecklistItem, Status, Parameter, Page

#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::ignition_trigger_cross_validation {

using sensor_setup_checklist::ChecklistItem;
using sensor_setup_checklist::Status;
using sensor_setup_checklist::Parameter;
using sensor_setup_checklist::Page;
using sensor_setup_checklist::ValueGetter;
using sensor_setup_checklist::OptionLabelGetter;

std::vector<ChecklistItem> validate(
    const Page* ignition_page,      // may be nullptr
    const Page* trigger_page,       // may be nullptr
    ValueGetter get_value,
    OptionLabelGetter get_option_label);

}  // namespace tuner_core::ignition_trigger_cross_validation
