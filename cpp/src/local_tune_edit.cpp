// SPDX-License-Identifier: MIT
#include "tuner_core/local_tune_edit.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>

namespace tuner_core::local_tune_edit {

namespace {

// Raw range implied by an INI/MSQ data type. Returns false if the
// data_type isn't recognised — in that case no type-derived bound is
// applied and the explicit min_value/max_value (if any) are the only
// fences.
bool type_range(std::string_view dt, double& lo, double& hi) {
    if (dt == "U08") { lo = 0.0;       hi = 255.0;       return true; }
    if (dt == "U16") { lo = 0.0;       hi = 65535.0;     return true; }
    if (dt == "U32") { lo = 0.0;       hi = 4294967295.0; return true; }
    if (dt == "S08") { lo = -128.0;    hi = 127.0;       return true; }
    if (dt == "S16") { lo = -32768.0;  hi = 32767.0;     return true; }
    if (dt == "S32") { lo = -2147483648.0; hi = 2147483647.0; return true; }
    return false;
}

}  // namespace

void EditService::set_tune_file(const TuneFile* tune_file) {
    base_ = tune_file;
    staged_.clear();
    history_.clear();
    history_index_.clear();
}

void EditService::set_limits_provider(LimitsProvider provider) {
    limits_provider_ = std::move(provider);
}

double EditService::clamp_value(const std::string& name, double raw) const {
    if (!limits_provider_) return raw;
    auto limits = limits_provider_(name);
    if (!limits) return raw;

    double lo = 0.0, hi = 0.0;
    bool has_lo = limits->min_value.has_value();
    bool has_hi = limits->max_value.has_value();
    if (has_lo) lo = *limits->min_value;
    if (has_hi) hi = *limits->max_value;

    // Fall back to data_type implied range for missing bounds, shifted
    // into display units via scale + translate so the fence matches
    // the value the operator actually types.
    if (!has_lo || !has_hi) {
        double type_lo = 0.0, type_hi = 0.0;
        if (type_range(limits->data_type, type_lo, type_hi)) {
            double scale = limits->scale.value_or(1.0);
            double translate = limits->translate.value_or(0.0);
            double disp_lo = type_lo * scale + translate;
            double disp_hi = type_hi * scale + translate;
            if (scale < 0.0) std::swap(disp_lo, disp_hi);
            if (!has_lo) { lo = disp_lo; has_lo = true; }
            if (!has_hi) { hi = disp_hi; has_hi = true; }
        }
    }

    if (has_lo && raw < lo) return lo;
    if (has_hi && raw > hi) return hi;
    return raw;
}

const TuneValue* EditService::get_value(const std::string& name) const {
    auto it = staged_.find(name);
    if (it != staged_.end()) return &it->second;
    return get_base_value(name);
}

const TuneValue* EditService::get_base_value(const std::string& name) const {
    if (base_ == nullptr) return nullptr;
    for (const auto& tv : base_->constants) {
        if (tv.name == name) return &tv;
    }
    return nullptr;
}

void EditService::stage_scalar_value(const std::string& name, const std::string& raw_value,
                                     bool* was_clamped) {
    auto* tv = const_cast<TuneValue*>(get_value(name));
    if (tv == nullptr) {
        throw std::runtime_error("Tune value not found: " + name);
    }
    if (std::holds_alternative<std::vector<double>>(tv->value)) {
        throw std::runtime_error("Tune value is not a scalar: " + name);
    }
    auto& staged = ensure_staged_copy(name, *tv);
    if (was_clamped) *was_clamped = false;
    if (std::holds_alternative<std::string>(tv->value)) {
        staged.value = raw_value;
    } else {
        double parsed = std::stod(raw_value);
        double clamped = clamp_value(name, parsed);
        if (was_clamped && clamped != parsed) *was_clamped = true;
        staged.value = clamped;
    }
    commit_history(name, staged.value);
}

void EditService::stage_list_cell(const std::string& name, int index, double value,
                                  bool* was_clamped) {
    auto* tv = const_cast<TuneValue*>(get_value(name));
    if (tv == nullptr || !std::holds_alternative<std::vector<double>>(tv->value)) {
        throw std::runtime_error("Tune value is not a list: " + name);
    }
    auto& staged = ensure_staged_copy(name, *tv);
    auto& list = std::get<std::vector<double>>(staged.value);
    if (index < 0 || index >= static_cast<int>(list.size())) {
        throw std::out_of_range("Cell index out of range for: " + name);
    }
    double clamped = clamp_value(name, value);
    if (was_clamped) *was_clamped = (clamped != value);
    list[index] = clamped;
    commit_history(name, staged.value);
}

void EditService::replace_list(const std::string& name, const std::vector<double>& values) {
    auto* tv = const_cast<TuneValue*>(get_value(name));
    if (tv == nullptr || !std::holds_alternative<std::vector<double>>(tv->value)) {
        throw std::runtime_error("Tune value is not a list: " + name);
    }
    auto& staged = ensure_staged_copy(name, *tv);
    // Clamp every cell — proposal-generated lists (VE Analyze, table
    // generators, smoothing transforms) all land here, and they can
    // drift out-of-range after compounding floating-point math.
    std::vector<double> clamped;
    clamped.reserve(values.size());
    for (double v : values) clamped.push_back(clamp_value(name, v));
    staged.value = std::move(clamped);
    commit_history(name, staged.value);
}

bool EditService::can_undo(const std::string& name) const {
    auto it = history_index_.find(name);
    return it != history_index_.end() && it->second > 0;
}

bool EditService::can_redo(const std::string& name) const {
    auto hit = history_.find(name);
    if (hit == history_.end()) return false;
    auto iit = history_index_.find(name);
    if (iit == history_index_.end()) return false;
    return iit->second < static_cast<int>(hit->second.size()) - 1;
}

void EditService::undo(const std::string& name) {
    if (!can_undo(name)) return;
    auto& idx = history_index_[name];
    idx--;
    staged_[name].value = copy_value(history_[name][idx]);
}

void EditService::redo(const std::string& name) {
    if (!can_redo(name)) return;
    auto& idx = history_index_[name];
    idx++;
    staged_[name].value = copy_value(history_[name][idx]);
}

void EditService::revert(const std::string& name) {
    staged_.erase(name);
    history_.erase(name);
    history_index_.erase(name);
}

void EditService::revert_all() {
    staged_.clear();
    history_.clear();
    history_index_.clear();
}

bool EditService::is_dirty(const std::string& name) const {
    return staged_.count(name) > 0;
}

bool EditService::has_any_staged() const {
    return !staged_.empty();
}

int EditService::staged_count() const {
    return static_cast<int>(staged_.size());
}

std::vector<std::string> EditService::staged_names() const {
    std::vector<std::string> names;
    names.reserve(staged_.size());
    for (const auto& [name, _] : staged_)
        names.push_back(name);
    std::sort(names.begin(), names.end());
    return names;
}

std::unordered_map<std::string, double> EditService::get_scalar_values_dict() const {
    std::unordered_map<std::string, double> result;
    if (base_ != nullptr) {
        for (const auto& tv : base_->constants) {
            if (std::holds_alternative<double>(tv.value)) {
                result[tv.name] = std::get<double>(tv.value);
            }
        }
    }
    for (const auto& [name, tv] : staged_) {
        if (std::holds_alternative<double>(tv.value)) {
            result[name] = std::get<double>(tv.value);
        }
    }
    return result;
}

TuneValue& EditService::ensure_staged_copy(const std::string& name, const TuneValue& base) {
    auto it = staged_.find(name);
    if (it != staged_.end()) return it->second;
    TuneValue copy = base;
    copy.value = copy_value(base.value);
    staged_[name] = std::move(copy);
    history_[name] = {copy_value(staged_[name].value)};
    history_index_[name] = 0;
    return staged_[name];
}

void EditService::commit_history(const std::string& name, const Value& current) {
    auto& hist = history_[name];
    auto& idx = history_index_[name];
    hist.resize(idx + 1);
    if (hist.back() != current) {
        hist.push_back(copy_value(current));
        idx = static_cast<int>(hist.size()) - 1;
    }
}

Value EditService::copy_value(const Value& v) {
    if (std::holds_alternative<std::vector<double>>(v)) {
        return std::vector<double>(std::get<std::vector<double>>(v));
    }
    return v;
}

}  // namespace tuner_core::local_tune_edit
