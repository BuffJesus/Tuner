// SPDX-License-Identifier: MIT
//
// tuner_core::page_family — port of `PageFamilyService.build_index`.
// Twenty-second sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Groups tuning pages into related "families" (fuel trims, fuel
// tables, spark tables, target tables, VVT) so the workspace
// presenter can render them as tabbed surfaces. Pure logic over a
// minimal `PageInput` POD — only `page_id`, `title`, and optional
// `page_number` are read. Returns a `page_id → Family` map; pages
// not in any family or with fewer than 2 sibling pages are dropped.

#pragma once

#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::page_family {

struct PageInput {
    std::string page_id;
    std::string title;
    std::optional<int> page_number;
};

struct FamilyTab {
    std::string page_id;
    std::string title;
};

struct Family {
    std::string family_id;
    std::string title;
    std::vector<FamilyTab> tabs;
};

// Mirror `PageFamilyService.build_index`. Returns a map keyed by
// `page_id` — every page that belongs to a family with >= 2
// siblings appears in the result, pointing at the (shared) family
// instance for its group. Pages not in any family or in singleton
// families are skipped.
std::map<std::string, Family> build_index(
    const std::vector<PageInput>& pages);

// Mirror `_family_id` — returns the family code for a given page
// title, or nullopt if the page doesn't belong to any family.
std::optional<std::string> family_id_for_title(std::string_view title);

// Mirror `_family_title` — display title for a family code.
// Returns the input string if the family is unknown (the Python
// service raises KeyError; we fail-soft for the C++ side).
std::string family_title_for(std::string_view family_id);

// Mirror `_tab_title` — short tab label for a page within its family.
std::string tab_title_for(std::string_view family_id, std::string_view page_title);

}  // namespace tuner_core::page_family
