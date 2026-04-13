// SPDX-License-Identifier: MIT
//
// tuner_core::tuning_page_grouping — keyword-based page group classifier.
// Forty-eighth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Classifies compiled layout pages into operator-facing groups (Fuel,
// Ignition, AFR, Idle, Startup/Enrich, Boost, Settings, Other) using
// keyword matching on page titles, group titles, and table editor IDs.
// Port of TuningPageService._GROUP_RULES and _group_for_text.

#pragma once

#include "definition_layout.hpp"

#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::tuning_page_grouping {

struct GroupRule {
    int order;
    std::string group_id;
    std::string group_title;
    std::vector<std::string> keywords;
};

struct GroupedPage {
    std::string target;
    std::string title;
    std::string table_editor_id;  // empty = not a table page
    std::string curve_editor_id;  // empty = not a curve page
    int group_order = 99;
    std::string group_id;
    std::string group_title;
};

struct PageGroup {
    int order = 99;
    std::string group_id;
    std::string group_title;
    std::vector<GroupedPage> pages;
};

// Get the built-in group rules (matches Python _GROUP_RULES).
const std::vector<GroupRule>& group_rules();

// Classify a single text blob against the group rules.
// Returns (order, group_id, group_title).
struct GroupMatch {
    int order = 99;
    std::string group_id = "other";
    std::string group_title = "Other";
};
GroupMatch classify_text(std::string_view text);

// Classify and group a set of compiled layout pages.
std::vector<PageGroup> group_pages(
    const std::vector<definition_layout::LayoutPage>& pages);

}  // namespace tuner_core::tuning_page_grouping
