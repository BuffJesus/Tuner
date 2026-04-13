// SPDX-License-Identifier: MIT
//
// tuner_core::wue_analyze_helpers implementation. Pure logic.

#include "tuner_core/wue_analyze_helpers.hpp"

#include <array>
#include <cctype>
#include <cmath>
#include <stdexcept>
#include <string>

namespace tuner_core::wue_analyze_helpers {

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

}  // namespace

std::string confidence_label(int sample_count) {
    if (sample_count < kConfidenceLow) return "insufficient";
    if (sample_count < kConfidenceMedium) return "low";
    if (sample_count < kConfidenceHigh) return "medium";
    return "high";
}

bool is_clt_axis(std::string_view param_name) {
    if (param_name.empty()) return false;
    auto lower = lowercase(param_name);
    static constexpr std::array<std::string_view, 6> kKeywords = {
        "clt", "coolant", "warmup", "wue", "cold", "temp",
    };
    for (auto kw : kKeywords) {
        if (contains(lower, kw)) return true;
    }
    return false;
}

std::optional<double> clt_from_record(const ValueMap& values) {
    for (const auto& [key, value] : values) {
        auto k = lowercase(key);
        if (contains(k, "coolant") || contains(k, "clt")) {
            return value;
        }
    }
    return std::nullopt;
}

std::size_t nearest_index(std::span<const double> axis, double value) {
    if (axis.empty()) return 0;
    std::size_t best_index = 0;
    double best_error = std::abs(axis[0] - value);
    for (std::size_t i = 1; i < axis.size(); ++i) {
        double err = std::abs(axis[i] - value);
        if (err < best_error) {
            best_index = i;
            best_error = err;
        }
    }
    return best_index;
}

std::vector<double> numeric_axis(std::span<const std::string> labels) {
    std::vector<double> out;
    out.reserve(labels.size());
    for (const auto& label : labels) {
        try {
            std::size_t consumed = 0;
            double v = std::stod(label, &consumed);
            if (consumed == 0) return {};  // all-or-nothing
            out.push_back(v);
        } catch (...) {
            return {};  // all-or-nothing — empty on any parse failure
        }
    }
    return out;
}

std::optional<double> parse_cell_float(std::string_view cell_text) {
    if (cell_text.empty()) return std::nullopt;
    try {
        std::size_t consumed = 0;
        double v = std::stod(std::string(cell_text), &consumed);
        if (consumed == 0) return std::nullopt;
        return v;
    } catch (...) {
        return std::nullopt;
    }
}

double target_lambda_from_cell(double raw, double scalar_fallback) {
    if (raw <= 0.0) return scalar_fallback;
    if (raw > kAfrUnitMin) return raw / kStoichAfr;
    return raw;
}

}  // namespace tuner_core::wue_analyze_helpers
