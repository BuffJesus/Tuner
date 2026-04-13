// SPDX-License-Identifier: MIT
//
// tuner_core::hardware_setup_summary — port of HardwareSetupSummaryService
// card builders.  Sub-slice 80 of Phase 14 Slice 4.
//
// Builds contextual summary cards for hardware setup pages (injector,
// trigger, ignition, sensor).  Pure logic, no Qt.

#pragma once

#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::hardware_setup_summary {

struct Card {
    std::string key;
    std::string title;
    std::string summary;
    std::vector<std::string> detail_lines;
    std::string severity = "info";  // "info", "warning", "error"
};

struct Parameter {
    std::string name;
    std::string label;
};

struct Page {
    std::string page_kind;  // "injector", "trigger", "ignition", "sensor", ""
    std::vector<Parameter> parameters;
};

using ValueGetter = std::function<std::optional<double>(const std::string&)>;

/// Build summary cards for a hardware setup page.
std::vector<Card> build_cards(
    const Page& page,
    ValueGetter get_value);

}  // namespace tuner_core::hardware_setup_summary
