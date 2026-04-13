// SPDX-License-Identifier: MIT
#include "tuner_core/wue_analyze_accumulator.hpp"
#include "tuner_core/wue_analyze_helpers.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <span>
#include <string>

namespace tuner_core::wue_analyze_accumulator {

namespace {

const std::vector<std::string> CLT_KEYWORDS = {"clt", "coolant", "warmup", "wue", "cold", "temp"};

bool is_clt_name(const std::string& name) {
    std::string lower = name;
    for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    for (const auto& kw : CLT_KEYWORDS)
        if (lower.find(kw) != std::string::npos) return true;
    return false;
}

std::vector<double> parse_axis(const std::vector<std::string>& labels) {
    std::vector<double> vals;
    for (const auto& l : labels) {
        try { vals.push_back(std::stod(l)); } catch (...) { return {}; }
    }
    return vals;
}

std::optional<double> extract_lambda(const std::map<std::string, double>& values) {
    for (const auto& [k, v] : values) {
        std::string lower = k;
        for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (lower.find("lambda") != std::string::npos) return v;
    }
    for (const auto& [k, v] : values) {
        std::string lower = k;
        for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if ((lower.find("afr") != std::string::npos || lower.find("ego") != std::string::npos) && v > 0)
            return v / 14.7;
    }
    return std::nullopt;
}

std::optional<double> extract_clt(const std::map<std::string, double>& values) {
    for (const auto& [k, v] : values) {
        std::string lower = k;
        for (auto& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (lower.find("coolant") != std::string::npos || lower.find("clt") != std::string::npos)
            return v;
    }
    return std::nullopt;
}

double parse_cell(const std::string& text) {
    try { return std::stod(text); } catch (...) { return 0; }
}

}  // namespace

// -----------------------------------------------------------------------
// detect_clt_axis
// -----------------------------------------------------------------------

std::optional<TableAxis> detect_clt_axis(
    const std::string& x_param_name,
    const std::string& y_param_name,
    const std::vector<std::string>& x_labels,
    const std::vector<std::string>& y_labels)
{
    auto y_axis = parse_axis(y_labels);
    auto x_axis = parse_axis(x_labels);

    if (is_clt_name(y_param_name) && !y_axis.empty())
        return TableAxis{y_axis, true};
    if (is_clt_name(x_param_name) && !x_axis.empty())
        return TableAxis{x_axis, false};
    if (y_axis.size() > 1) return TableAxis{y_axis, true};
    if (x_axis.size() > 1) return TableAxis{x_axis, false};
    return std::nullopt;
}

// -----------------------------------------------------------------------
// Accumulator
// -----------------------------------------------------------------------

bool Accumulator::add_record(
    const Record& record,
    const TableAxis& axis,
    const std::vector<std::string>& /*cell_texts*/,
    double lambda_target,
    const GatingConfig& /*gating*/)
{
    auto measured = extract_lambda(record.values);
    if (!measured || *measured <= 0) {
        rejected_++;
        gate_rejections_["no_lambda_channel"]++;
        return false;
    }

    auto clt = extract_clt(record.values);
    if (!clt) {
        rejected_++;
        gate_rejections_["no_clt_channel"]++;
        return false;
    }

    int row = static_cast<int>(wue_analyze_helpers::nearest_index(
        std::span<const double>(axis.bins), *clt));
    double target = (lambda_target > 0) ? lambda_target : 1.0;
    double correction = *measured / target;
    row_corrections_[row].push_back(correction);
    accepted_++;
    return true;
}

Snapshot Accumulator::snapshot(
    const std::vector<std::string>& cell_texts,
    int min_samples,
    double wue_min,
    double wue_max) const
{
    std::vector<RowAccumulation> rows;
    for (const auto& [row_idx, factors] : row_corrections_) {
        RowAccumulation ra;
        ra.row_index = row_idx;
        ra.correction_factors = factors;
        ra.current_enrichment = (row_idx < static_cast<int>(cell_texts.size()))
            ? parse_cell(cell_texts[row_idx]) : std::numeric_limits<double>::quiet_NaN();
        rows.push_back(ra);
    }

    std::vector<std::pair<std::string, int>> rejections(gate_rejections_.begin(), gate_rejections_.end());
    return wue_analyze_snapshot::build_snapshot(
        rows, accepted_, rejected_, rejections, min_samples, wue_min, wue_max);
}

void Accumulator::reset() {
    row_corrections_.clear();
    accepted_ = 0;
    rejected_ = 0;
    gate_rejections_.clear();
}

}  // namespace tuner_core::wue_analyze_accumulator
