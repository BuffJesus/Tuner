// SPDX-License-Identifier: MIT
#include "tuner_core/tuning_page_grouping.hpp"

#include <algorithm>
#include <cctype>
#include <map>
#include <string>
#include <vector>

namespace tuner_core::tuning_page_grouping {

namespace {

std::string to_lower(std::string_view sv) {
    std::string out;
    out.reserve(sv.size());
    for (char c : sv) out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    return out;
}

}  // namespace

const std::vector<GroupRule>& group_rules() {
    static const std::vector<GroupRule> rules = {
        { 5, "hardware_setup", "Hardware Setup", {"injector", "coil", "trigger", "decoder", "thermistor"}},
        {10, "fuel", "Fuel", {"ve", "fuel", "inject", "reqfuel"}},
        {20, "ignition", "Ignition", {"spark", "ignition", "advance", "timing", "dwell", "knock"}},
        {30, "afr", "AFR / Lambda", {"afr", "lambda", "ego", "o2"}},
        {40, "idle", "Idle", {"idle", "iac"}},
        {50, "enrich", "Startup / Enrich", {"enrich", "warmup", "crank", "afterstart", "prime", "accel", "ase", "wue"}},
        {60, "boost", "Boost / Airflow", {"boost", "map", "baro", "vvt", "turbo"}},
        {70, "settings", "Settings", {"setting", "config", "option", "sensor", "calibration", "general", "engine", "limit"}},
        {99, "other", "Other", {}},
    };
    return rules;
}

GroupMatch classify_text(std::string_view text) {
    std::string haystack = to_lower(text);
    for (const auto& rule : group_rules()) {
        if (rule.keywords.empty()) continue;
        for (const auto& kw : rule.keywords) {
            if (haystack.find(kw) != std::string::npos) {
                return {rule.order, rule.group_id, rule.group_title};
            }
        }
    }
    return {99, "other", "Other"};
}

std::vector<PageGroup> group_pages(
    const std::vector<definition_layout::LayoutPage>& pages)
{
    // Classify each page.
    std::map<int, PageGroup> groups_by_order;

    for (const auto& page : pages) {
        // Build a text blob from title + group_title + table/curve editor ids + target.
        std::string text_blob = page.title + " " + page.group_title + " "
                                + page.table_editor_id + " " + page.curve_editor_id
                                + " " + page.target;
        auto match = classify_text(text_blob);

        GroupedPage gp;
        gp.target = page.target;
        gp.title = page.title;
        gp.table_editor_id = page.table_editor_id;
        gp.curve_editor_id = page.curve_editor_id;
        gp.group_order = match.order;
        gp.group_id = match.group_id;
        gp.group_title = match.group_title;

        auto& group = groups_by_order[match.order];
        group.order = match.order;
        group.group_id = match.group_id;
        group.group_title = match.group_title;
        group.pages.push_back(std::move(gp));
    }

    // Flatten to sorted vector.
    std::vector<PageGroup> result;
    for (auto& [_, group] : groups_by_order) {
        // Sort pages within group by title.
        std::sort(group.pages.begin(), group.pages.end(),
                  [](const GroupedPage& a, const GroupedPage& b) {
                      return a.title < b.title;
                  });
        result.push_back(std::move(group));
    }
    return result;
}

}  // namespace tuner_core::tuning_page_grouping
