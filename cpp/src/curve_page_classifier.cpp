// SPDX-License-Identifier: MIT
//
// tuner_core::curve_page_classifier implementation. Pure logic.

#include "tuner_core/curve_page_classifier.hpp"

#include <array>
#include <cctype>
#include <map>
#include <regex>
#include <string>

namespace tuner_core::curve_page_classifier {

namespace {

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

// Mirror Python's `re.escape` for the keyword characters we use
// (alphanumeric + underscore only — none of the keywords carry
// regex metacharacters, so escape is a no-op for our table).
struct GroupRule {
    int order;
    const char* group_id;
    const char* group_title;
    std::array<const char*, 12> keywords;  // null-terminated within the array
};

// Same 8-rule table as `CurvePageService._GROUP_RULES`. Trailing
// nullptrs pad the keyword list out to a fixed-size array.
constexpr std::array<GroupRule, 8> kRules{{
    {10, "fuel",     "Fuel",
        {"vetable", "fuel", "inject", "reqfuel", "baro", "density", "priming", "flex", "wmi", nullptr, nullptr, nullptr}},
    {20, "ignition", "Ignition",
        {"spark", "ignition", "advance", "timing", "dwell", "knock", "rotary", nullptr, nullptr, nullptr, nullptr, nullptr}},
    {30, "afr",      "AFR / Lambda",
        {"afr", "lambda", "ego", "o2", "warmup_afr", "wue_afr", nullptr, nullptr, nullptr, nullptr, nullptr, nullptr}},
    {40, "idle",     "Idle",
        {"idle", "iac", nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr}},
    {50, "enrich",   "Startup / Enrich",
        {"enrich", "warmup", "crank", "afterstart", "prime", "accel", "ase", "wue", nullptr, nullptr, nullptr, nullptr}},
    {60, "boost",    "Boost / Airflow",
        {"boost", "map", "vvt", "turbo", nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr}},
    {70, "settings", "Settings",
        {"setting", "config", "option", "sensor", "calibration", "engine", "limit", "pwm", "fan", "protection", "oil", "coolant"}},
    {99, "other",    "Other",
        {nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr}},
}};

// Mirror Python `re.search(r'\b' + re.escape(kw) + r'\b', text)`.
// Word boundaries on both sides — caller is responsible for
// lowercasing both `text` and `kw` so the comparison is case-
// insensitive.
bool word_search(const std::string& text, std::string_view kw) {
    if (kw.empty()) return false;
    // Build the regex once per keyword. The keyword table is fixed,
    // so we cache regexes in a static map keyed by string. With
    // ~50 keywords total this is negligible.
    static std::map<std::string, std::regex> cache;
    auto it = cache.find(std::string(kw));
    if (it == cache.end()) {
        std::string pattern = std::string("\\b") + std::string(kw) + "\\b";
        it = cache.emplace(std::string(kw), std::regex(pattern)).first;
    }
    return std::regex_search(text, it->second);
}

}  // namespace

GroupAssignment classify(std::string_view name, std::string_view title) {
    std::string text = lowercase(std::string(name) + " " + std::string(title));
    for (const auto& rule : kRules) {
        for (const auto* kw : rule.keywords) {
            if (kw == nullptr) break;  // end of this rule's keywords
            if (word_search(text, kw)) {
                return {rule.order, rule.group_id, rule.group_title};
            }
        }
    }
    // Should never reach here — the last rule ("other") always matches
    // an empty keyword set, returning via the explicit fallthrough below.
    return {99, "other", "Other"};
}

std::string summary(int y_bins_count, std::string_view x_channel) {
    std::string multi = (y_bins_count > 1)
        ? std::to_string(y_bins_count) + " lines"
        : "1D";
    std::string channel;
    if (!x_channel.empty()) {
        channel = " \xc2\xb7 live: ";  // UTF-8 middle dot
        channel += std::string(x_channel);
    }
    // "Curve \xc2\xb7 {multi}{channel}"
    return std::string("Curve \xc2\xb7 ") + multi + channel;
}

}  // namespace tuner_core::curve_page_classifier
