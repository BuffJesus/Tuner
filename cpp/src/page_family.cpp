// SPDX-License-Identifier: MIT
//
// tuner_core::page_family implementation. Pure logic.

#include "tuner_core/page_family.hpp"

#include <algorithm>
#include <cctype>
#include <regex>
#include <string>
#include <utility>

namespace tuner_core::page_family {

namespace {

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

bool contains(std::string_view haystack, std::string_view needle) noexcept {
    return haystack.find(needle) != std::string_view::npos;
}

// Mirror `_tab_sort_key`. Returns a (group, lowercase title) pair.
// The group is the magic number the Python service hands out per
// page-title category.
std::pair<int, std::string> tab_sort_key(const PageInput& page) {
    auto lower = lowercase(page.title);
    if (contains(lower, "sequential fuel trim (1-4)")) return {10, lower};
    if (contains(lower, "fuel trim table 2")) return {20, lower};
    if (contains(lower, "fuel trim table 3")) return {30, lower};
    if (contains(lower, "fuel trim table 4")) return {40, lower};
    if (contains(lower, "fuel trim table 6")) return {60, lower};
    if (contains(lower, "fuel trim table 7")) return {70, lower};
    if (contains(lower, "fuel trim table 8")) return {80, lower};
    if (contains(lower, "sequential fuel trim (5-8)")) return {90, lower};
    if (contains(lower, "sequential fuel trim settings")) return {100, lower};
    if (lower == "ve table") return {10, lower};
    if (lower == "second fuel table") return {20, lower};
    if (lower == "spark table") return {10, lower};
    if (lower == "second spark table") return {20, lower};
    if (lower == "afr target table") return {10, lower};
    if (lower == "lambda target table") return {20, lower};
    if (lower == "vvt target/duty") return {10, lower};
    if (lower == "vvt2 target/duty") return {20, lower};
    if (lower == "vvt control") return {30, lower};
    return {999, lower};
}

}  // namespace

std::optional<std::string> family_id_for_title(std::string_view title) {
    auto lower = lowercase(title);
    if (contains(lower, "fuel trim") || contains(lower, "sequential fuel trim")) {
        return std::string("fuel-trims");
    }
    if (lower == "ve table" || lower == "second fuel table") {
        return std::string("fuel-tables");
    }
    if (lower == "spark table" || lower == "second spark table") {
        return std::string("spark-tables");
    }
    if (lower == "afr target table" || lower == "lambda target table") {
        return std::string("target-tables");
    }
    if (lower == "vvt target/duty" || lower == "vvt2 target/duty" || lower == "vvt control") {
        return std::string("vvt");
    }
    return std::nullopt;
}

std::string family_title_for(std::string_view family_id) {
    if (family_id == "fuel-trims") return "Fuel Trims";
    if (family_id == "fuel-tables") return "Fuel Tables";
    if (family_id == "spark-tables") return "Spark Tables";
    if (family_id == "target-tables") return "Target Tables";
    if (family_id == "vvt") return "VVT";
    return std::string(family_id);
}

std::string tab_title_for(std::string_view family_id, std::string_view page_title) {
    auto lower = lowercase(page_title);
    if (family_id == "fuel-trims") {
        if (contains(lower, "sequential fuel trim (1-4)")) return "Seq 1-4";
        if (contains(lower, "sequential fuel trim (5-8)")) return "Seq 5-8";
        if (contains(lower, "sequential fuel trim settings")) return "Settings";
        // Match `fuel trim table N` and pull the digit out.
        static const std::regex trim_re(R"(fuel trim table (\d+))");
        std::smatch m;
        std::string lower_str(lower);
        if (std::regex_search(lower_str, m, trim_re)) {
            return std::string("Trim ") + m[1].str();
        }
    } else if (family_id == "fuel-tables") {
        return lower == "ve table" ? "Primary" : "Secondary";
    } else if (family_id == "spark-tables") {
        return lower == "spark table" ? "Primary" : "Secondary";
    } else if (family_id == "target-tables") {
        return lower == "afr target table" ? "AFR" : "Lambda";
    } else if (family_id == "vvt") {
        if (lower == "vvt target/duty") return "VVT1";
        if (lower == "vvt2 target/duty") return "VVT2";
        if (lower == "vvt control") return "Control";
    }
    return std::string(page_title);
}

std::map<std::string, Family> build_index(const std::vector<PageInput>& pages) {
    // Bucket pages by family ID, preserving input order within each bucket.
    std::map<std::string, std::vector<PageInput>> family_buckets;
    for (const auto& page : pages) {
        auto fid = family_id_for_title(page.title);
        if (!fid.has_value()) continue;
        family_buckets[*fid].push_back(page);
    }

    std::map<std::string, Family> result;
    for (auto& [family_id, family_pages] : family_buckets) {
        if (family_pages.size() < 2) continue;
        // Sort by (page_number or 9999, tab_sort_key, lowercased title).
        std::sort(family_pages.begin(), family_pages.end(),
                  [](const PageInput& a, const PageInput& b) {
                      int ap = a.page_number.value_or(9999);
                      int bp = b.page_number.value_or(9999);
                      if (ap != bp) return ap < bp;
                      auto ka = tab_sort_key(a);
                      auto kb = tab_sort_key(b);
                      if (ka.first != kb.first) return ka.first < kb.first;
                      if (ka.second != kb.second) return ka.second < kb.second;
                      return lowercase(a.title) < lowercase(b.title);
                  });

        Family family;
        family.family_id = family_id;
        family.title = family_title_for(family_id);
        for (const auto& page : family_pages) {
            FamilyTab tab;
            tab.page_id = page.page_id;
            tab.title = tab_title_for(family_id, page.title);
            family.tabs.push_back(std::move(tab));
        }
        for (const auto& page : family_pages) {
            result[page.page_id] = family;
        }
    }
    return result;
}

}  // namespace tuner_core::page_family
