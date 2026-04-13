// SPDX-License-Identifier: MIT
#include "tuner_core/workspace_presenter.hpp"

#include <cstdio>

namespace tuner_core::workspace_presenter {

void Presenter::load(const NativeEcuDefinition& definition,
                      local_tune_edit::TuneFile* tune) {
    groups_ = tuning_page_builder::build_pages(definition);
    has_definition_ = true;

    // Collect all page IDs for the workspace.
    std::vector<std::string> page_ids;
    for (const auto& g : groups_)
        for (const auto& p : g.pages)
            page_ids.push_back(p.page_id);
    workspace_.set_pages(page_ids);

    if (tune) {
        edit_.set_tune_file(tune);
        has_tune_ = true;
    }

    log_.clear();
}

void Presenter::select_page(const std::string& page_id) {
    workspace_.select_page(page_id);
}

void Presenter::stage_scalar(const std::string& param_name, const std::string& value) {
    edit_.stage_scalar_value(param_name, value);
    workspace_.stage_edit(workspace_.active_page(), param_name);
    operation_log::TimeOfDay now{};
    log_.record_staged(param_name, "", value, now);
}

void Presenter::stage_list_cell(const std::string& param_name, int index, double value) {
    edit_.stage_list_cell(param_name, index, value);
    workspace_.stage_edit(workspace_.active_page(), param_name);
    char buf[32]; std::snprintf(buf, sizeof(buf), "[%d]=%.4g", index, value);
    operation_log::TimeOfDay now{};
    log_.record_staged(param_name, "", buf, now);
}

void Presenter::mark_written() {
    workspace_.mark_written(workspace_.active_page());
    operation_log::TimeOfDay now{};
    log_.record_written(workspace_.active_page(), "written", now);
}

void Presenter::mark_burned() {
    workspace_.mark_burned(workspace_.active_page());
    operation_log::TimeOfDay now{};
    log_.record_burned(workspace_.active_page(), "burned", now);
}

void Presenter::revert_active_page() {
    workspace_.revert_page(workspace_.active_page());
    operation_log::TimeOfDay now{};
    log_.record_reverted(workspace_.active_page(), "", "", now);
}

void Presenter::revert_all() {
    workspace_.revert_all();
    operation_log::TimeOfDay now{};
    log_.record_reverted("all", "", "", now);
}

void Presenter::set_sync_state(SyncState state) {
    workspace_.set_sync_state(state);
}

PresenterSnapshot Presenter::snapshot() const {
    auto ws = workspace_.snapshot();
    PresenterSnapshot snap;
    snap.active_page_id = ws.active_page_id;
    snap.total_pages = ws.total_pages;
    snap.staged_count = ws.staged_count;
    snap.active_page_state = ws.active_page_state;
    snap.sync_state = ws.sync_state;
    snap.status_text = ws.status_text;
    snap.operation_summary = log_.summary_text();
    snap.has_definition = has_definition_;
    snap.has_tune = has_tune_;

    // Find active page title.
    if (auto* page = find_page(ws.active_page_id))
        snap.active_page_title = page->title;

    return snap;
}

const TuningPage* Presenter::find_page(const std::string& page_id) const {
    for (const auto& g : groups_)
        for (const auto& p : g.pages)
            if (p.page_id == page_id) return &p;
    return nullptr;
}

}  // namespace tuner_core::workspace_presenter
