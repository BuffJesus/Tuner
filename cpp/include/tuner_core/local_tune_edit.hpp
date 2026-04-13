// SPDX-License-Identifier: MIT
//
// tuner_core::local_tune_edit — port of LocalTuneEditService.
// Forty-ninth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Stateful staged-edit state machine with undo/redo. Tracks base tune
// values, staged overrides, and per-parameter edit history. Core of the
// workspace editing model: edits are staged → reviewed → written → burned.

#pragma once

#include <optional>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

namespace tuner_core::local_tune_edit {

// Value variant: scalar double, string, or list of doubles.
using Value = std::variant<double, std::string, std::vector<double>>;

struct TuneValue {
    std::string name;
    Value value;
    std::string units;
    int digits = -1;
    int rows = 0;
    int cols = 0;
};

// Simplified tune file — just the constants list.
struct TuneFile {
    std::string signature;
    std::vector<TuneValue> constants;
};

class EditService {
public:
    void set_tune_file(const TuneFile* tune_file);

    // Get the current effective value (staged if exists, else base).
    const TuneValue* get_value(const std::string& name) const;
    const TuneValue* get_base_value(const std::string& name) const;

    // Stage edits.
    void stage_scalar_value(const std::string& name, const std::string& raw_value);
    void stage_list_cell(const std::string& name, int index, double value);
    void replace_list(const std::string& name, const std::vector<double>& values);

    // Undo/redo.
    bool can_undo(const std::string& name) const;
    bool can_redo(const std::string& name) const;
    void undo(const std::string& name);
    void redo(const std::string& name);

    // Revert.
    void revert(const std::string& name);
    void revert_all();

    // State queries.
    bool is_dirty(const std::string& name) const;
    bool has_any_staged() const;
    int staged_count() const;

    // Enumerate currently-staged parameter names in deterministic
    // (alphabetical) order. Used by the workspace review popup
    // (sub-slice 93) to render the pending-edits list.
    std::vector<std::string> staged_names() const;

    // Get all scalar values as a flat map (for visibility expressions).
    std::unordered_map<std::string, double> get_scalar_values_dict() const;

private:
    const TuneFile* base_ = nullptr;
    std::unordered_map<std::string, TuneValue> staged_;
    std::unordered_map<std::string, std::vector<Value>> history_;
    std::unordered_map<std::string, int> history_index_;

    TuneValue& ensure_staged_copy(const std::string& name, const TuneValue& base);
    void commit_history(const std::string& name, const Value& current);
    static Value copy_value(const Value& v);
};

}  // namespace tuner_core::local_tune_edit
