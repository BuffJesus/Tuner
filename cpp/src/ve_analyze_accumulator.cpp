// SPDX-License-Identifier: MIT
#include "tuner_core/ve_analyze_accumulator.hpp"
#include "tuner_core/wue_analyze_helpers.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <span>
#include <string>

namespace tuner_core::ve_analyze_accumulator {

namespace {

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

std::vector<double> parse_axis(const std::vector<std::string>& labels) {
    std::vector<double> vals;
    for (const auto& l : labels) {
        try { vals.push_back(std::stod(l)); } catch (...) { return {}; }
    }
    return vals;
}

double parse_cell(const std::string& text) {
    try { return std::stod(text); } catch (...) { return 0; }
}

}  // namespace

// -----------------------------------------------------------------------
// Accumulator
// -----------------------------------------------------------------------

bool Accumulator::add_record(
    const Record& record,
    const TableSnapshot& ve_table,
    double lambda_target)
{
    // Extract measured lambda.
    auto measured = extract_lambda(record.values);
    if (!measured || *measured <= 0) {
        rejected_++;
        gate_rejections_["no_lambda_channel"]++;
        return false;
    }

    // Map to a cell via table_replay_context.
    table_replay_context::TablePageSnapshot tps;
    tps.x_parameter_name = ve_table.x_param_name;
    tps.y_parameter_name = ve_table.y_param_name;
    tps.x_labels = ve_table.x_labels;
    tps.y_labels = ve_table.y_labels;
    tps.cells = ve_table.cells;

    std::vector<table_replay_context::RuntimeChannel> channels;
    for (const auto& [name, value] : record.values)
        channels.push_back({name, value});

    auto loc = table_replay_context::build(tps, channels);
    if (!loc) {
        rejected_++;
        gate_rejections_["unmappable_axes"]++;
        return false;
    }

    int row = static_cast<int>(loc->row_index);
    int col = static_cast<int>(loc->column_index);

    // Resolve target lambda.
    double target = (lambda_target > 0) ? lambda_target : 1.0;

    // Compute correction.
    double correction = *measured / target;
    CorrectionSample sample;
    sample.correction_factor = correction;
    sample.weight = 1.0;
    sample.timestamp_seconds = record.timestamp_seconds;
    cell_corrections_[{row, col}].push_back(sample);
    accepted_++;
    return true;
}

Snapshot Accumulator::snapshot(
    const TableSnapshot& ve_table,
    int min_samples,
    double ve_min,
    double ve_max) const
{
    int rows = static_cast<int>(ve_table.cells.size());
    int cols = rows > 0 ? static_cast<int>(ve_table.cells[0].size()) : 0;

    std::vector<CellAccumulation> cells;
    for (const auto& [key, samples] : cell_corrections_) {
        CellAccumulation cell;
        cell.row_index = key.first;
        cell.col_index = key.second;

        // Read current VE from the table.
        if (key.first < rows && key.second < cols)
            cell.current_ve = parse_cell(ve_table.cells[key.first][key.second]);
        else
            cell.current_ve = 0;

        cell.samples = samples;
        cells.push_back(cell);
    }

    return ve_cell_hit_accumulator::build_snapshot(
        cells, rows, cols, accepted_, rejected_, min_samples, ve_min, ve_max);
}

void Accumulator::reset() {
    cell_corrections_.clear();
    accepted_ = 0;
    rejected_ = 0;
    gate_rejections_.clear();
}

}  // namespace tuner_core::ve_analyze_accumulator
