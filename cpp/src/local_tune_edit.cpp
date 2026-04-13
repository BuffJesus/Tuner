// SPDX-License-Identifier: MIT
#include "tuner_core/local_tune_edit.hpp"

#include <algorithm>
#include <stdexcept>
#include <string>

namespace tuner_core::local_tune_edit {

void EditService::set_tune_file(const TuneFile* tune_file) {
    base_ = tune_file;
    staged_.clear();
    history_.clear();
    history_index_.clear();
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

void EditService::stage_scalar_value(const std::string& name, const std::string& raw_value) {
    auto* tv = const_cast<TuneValue*>(get_value(name));
    if (tv == nullptr) {
        throw std::runtime_error("Tune value not found: " + name);
    }
    if (std::holds_alternative<std::vector<double>>(tv->value)) {
        throw std::runtime_error("Tune value is not a scalar: " + name);
    }
    auto& staged = ensure_staged_copy(name, *tv);
    if (std::holds_alternative<std::string>(tv->value)) {
        staged.value = raw_value;
    } else {
        staged.value = std::stod(raw_value);
    }
    commit_history(name, staged.value);
}

void EditService::stage_list_cell(const std::string& name, int index, double value) {
    auto* tv = const_cast<TuneValue*>(get_value(name));
    if (tv == nullptr || !std::holds_alternative<std::vector<double>>(tv->value)) {
        throw std::runtime_error("Tune value is not a list: " + name);
    }
    auto& staged = ensure_staged_copy(name, *tv);
    auto& list = std::get<std::vector<double>>(staged.value);
    if (index < 0 || index >= static_cast<int>(list.size())) {
        throw std::out_of_range("Cell index out of range for: " + name);
    }
    list[index] = value;
    commit_history(name, staged.value);
}

void EditService::replace_list(const std::string& name, const std::vector<double>& values) {
    auto* tv = const_cast<TuneValue*>(get_value(name));
    if (tv == nullptr || !std::holds_alternative<std::vector<double>>(tv->value)) {
        throw std::runtime_error("Tune value is not a list: " + name);
    }
    auto& staged = ensure_staged_copy(name, *tv);
    staged.value = values;
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
