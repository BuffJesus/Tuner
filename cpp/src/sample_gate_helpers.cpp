// SPDX-License-Identifier: MIT
//
// tuner_core::sample_gate_helpers implementation. Pure logic.

#include "tuner_core/sample_gate_helpers.hpp"

#include <cctype>
#include <cstdint>

namespace tuner_core::sample_gate_helpers {

namespace {

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

std::string strip(std::string_view text) {
    while (!text.empty() && std::isspace(static_cast<unsigned char>(text.front()))) {
        text.remove_prefix(1);
    }
    while (!text.empty() && std::isspace(static_cast<unsigned char>(text.back()))) {
        text.remove_suffix(1);
    }
    return std::string(text);
}

bool contains(std::string_view haystack, std::string_view needle) noexcept {
    return haystack.find(needle) != std::string_view::npos;
}

// Mirror of the Python `_CHANNEL_ALIASES` table. The first alias is
// always the canonical token; some entries fall back through related
// channels (e.g. ego → ego, afr, lambda).
const std::vector<std::pair<std::string, std::vector<std::string>>>& alias_table() {
    static const std::vector<std::pair<std::string, std::vector<std::string>>> table = {
        {"lambda",     {"lambda"}},
        {"afr",        {"afr"}},
        {"ego",        {"ego", "afr", "lambda"}},
        {"coolant",    {"coolant", "clt"}},
        {"engine",     {"engine", "status"}},
        {"pulsewidth", {"pulsewidth", "pw"}},
        {"throttle",   {"throttle", "tps"}},
        {"rpm",        {"rpm"}},
        {"map",        {"map"}},
        {"load",       {"load", "map"}},
    };
    return table;
}

const std::vector<std::string>* lookup_aliases(std::string_view name_lower) {
    for (const auto& [key, candidates] : alias_table()) {
        if (key == name_lower) return &candidates;
    }
    return nullptr;
}

}  // namespace

std::string normalise_operator(std::string_view op) {
    auto stripped = strip(op);
    if (stripped == "=") return "==";
    return stripped;
}

bool apply_operator(double channel_value, std::string_view op, double threshold) {
    auto normalised = normalise_operator(op);
    if (normalised == "<")  return channel_value <  threshold;
    if (normalised == ">")  return channel_value >  threshold;
    if (normalised == "<=") return channel_value <= threshold;
    if (normalised == ">=") return channel_value >= threshold;
    if (normalised == "==") return channel_value == threshold;
    if (normalised == "!=") return channel_value != threshold;
    if (normalised == "&") {
        auto lhs = static_cast<std::int64_t>(channel_value);
        auto rhs = static_cast<std::int64_t>(threshold);
        return (lhs & rhs) != 0;
    }
    return false;
}

std::optional<double> resolve_channel(std::string_view name, const ValueMap& values) {
    auto name_lower = lowercase(name);
    const auto* aliases = lookup_aliases(name_lower);
    // Mirror Python's `_CHANNEL_ALIASES.get(name.lower(), (name.lower(),))`:
    // unknown names fall back to a single-alias list of the lowered name.
    std::vector<std::string> fallback{name_lower};
    const std::vector<std::string>& search =
        aliases != nullptr ? *aliases : fallback;

    for (const auto& candidate : search) {
        for (const auto& [key, value] : values) {
            if (contains(lowercase(key), candidate)) {
                return value;
            }
        }
    }
    return std::nullopt;
}

std::optional<double> lambda_value(const ValueMap& values) {
    // Pass 1: any key containing "lambda".
    for (const auto& [key, value] : values) {
        if (contains(lowercase(key), "lambda")) {
            return value;
        }
    }
    // Pass 2: derive from AFR / EGO.
    for (const auto& [key, value] : values) {
        auto k = lowercase(key);
        if (contains(k, "afr") || contains(k, "ego")) {
            return value / 14.7;
        }
    }
    return std::nullopt;
}

std::optional<double> afr_value(const ValueMap& values) {
    for (const auto& [key, value] : values) {
        auto k = lowercase(key);
        if (contains(k, "afr")) return value;
        if (contains(k, "lambda")) return value * 14.7;
    }
    return std::nullopt;
}

}  // namespace tuner_core::sample_gate_helpers
