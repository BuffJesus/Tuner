// SPDX-License-Identifier: MIT
#include "tuner_core/workspace_state.hpp"

#include <algorithm>
#include <cstdio>
#include <numeric>

namespace tuner_core::workspace_state {

void Workspace::set_pages(const std::vector<std::string>& page_ids) {
    page_ids_ = page_ids;
    page_states_.clear();
    staged_counts_.clear();
    for (const auto& id : page_ids)
        page_states_[id] = PageState::CLEAN;
    if (!page_ids.empty() && active_page_.empty())
        active_page_ = page_ids[0];
}

void Workspace::select_page(const std::string& page_id) {
    active_page_ = page_id;
}

void Workspace::stage_edit(const std::string& page_id, const std::string& /*param_name*/) {
    staged_counts_[page_id]++;
    if (page_states_.count(page_id) && page_states_[page_id] == PageState::CLEAN)
        page_states_[page_id] = PageState::STAGED;
}

void Workspace::mark_written(const std::string& page_id) {
    if (page_states_.count(page_id))
        page_states_[page_id] = PageState::WRITTEN;
}

void Workspace::mark_burned(const std::string& page_id) {
    if (page_states_.count(page_id))
        page_states_[page_id] = PageState::BURNED;
    staged_counts_.erase(page_id);
}

void Workspace::revert_page(const std::string& page_id) {
    if (page_states_.count(page_id))
        page_states_[page_id] = PageState::CLEAN;
    staged_counts_.erase(page_id);
}

void Workspace::revert_all() {
    for (auto& [id, state] : page_states_)
        state = PageState::CLEAN;
    staged_counts_.clear();
}

int Workspace::staged_count() const {
    int total = 0;
    for (const auto& [_, count] : staged_counts_)
        total += count;
    return total;
}

int Workspace::staged_count_for(const std::string& page_id) const {
    auto it = staged_counts_.find(page_id);
    return it != staged_counts_.end() ? it->second : 0;
}

PageState Workspace::aggregate_state() const {
    bool any_staged = false, any_written = false, any_burned = false;
    for (const auto& [_, state] : page_states_) {
        if (state == PageState::STAGED)       any_staged  = true;
        else if (state == PageState::WRITTEN) any_written = true;
        else if (state == PageState::BURNED)  any_burned  = true;
    }
    if (any_staged) return PageState::STAGED;
    if (any_written) return PageState::WRITTEN;
    if (any_burned) return PageState::BURNED;
    return PageState::CLEAN;
}

std::vector<std::string> Workspace::pages_in_state(PageState state) const {
    std::vector<std::string> out;
    for (const auto& id : page_ids_) {
        auto it = page_states_.find(id);
        if (it != page_states_.end() && it->second == state)
            out.push_back(id);
    }
    return out;
}

PageState Workspace::page_state(const std::string& page_id) const {
    auto it = page_states_.find(page_id);
    return (it != page_states_.end()) ? it->second : PageState::CLEAN;
}

WorkspaceSnapshot Workspace::snapshot() const {
    WorkspaceSnapshot snap;
    snap.active_page_id = active_page_;
    snap.staged_count = staged_count();
    snap.total_pages = static_cast<int>(page_ids_.size());
    snap.active_page_state = page_state(active_page_);
    snap.sync_state = sync_;

    const char* state_text =
        (snap.active_page_state == PageState::STAGED) ? "Staged" :
        (snap.active_page_state == PageState::WRITTEN) ? "Written to RAM" :
        (snap.active_page_state == PageState::BURNED) ? "Burned to flash" : "Clean";
    const char* sync_text =
        (sync_ == SyncState::SYNCED) ? "Synced" :
        (sync_ == SyncState::RAM_DIRTY) ? "RAM differs from flash" :
        (sync_ == SyncState::MISMATCH) ? "Signature mismatch" : "Offline";

    char buf[256];
    if (snap.staged_count > 0)
        std::snprintf(buf, sizeof(buf), "%s | %d staged change(s) | %s",
            state_text, snap.staged_count, sync_text);
    else
        std::snprintf(buf, sizeof(buf), "%s | %s", state_text, sync_text);
    snap.status_text = buf;
    return snap;
}

}  // namespace tuner_core::workspace_state
