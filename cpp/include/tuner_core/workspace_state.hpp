// SPDX-License-Identifier: MIT
//
// tuner_core::workspace_state — compact workspace state machine.
// Sub-slice 76 of Phase 14 Slice 4.
//
// Tracks active page, staged edit count, page state (clean/staged/
// written/burned), and sync state.  This is the minimum kernel of
// TuningWorkspacePresenter needed to make the TUNE tab interactive.

#pragma once

#include <map>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::workspace_state {

enum class PageState { CLEAN, STAGED, WRITTEN, BURNED };
enum class SyncState { OFFLINE, SYNCED, RAM_DIRTY, MISMATCH };

struct WorkspaceSnapshot {
    std::string active_page_id;
    int staged_count = 0;
    int total_pages = 0;
    PageState active_page_state = PageState::CLEAN;
    SyncState sync_state = SyncState::OFFLINE;
    std::string status_text;
};

class Workspace {
public:
    void set_pages(const std::vector<std::string>& page_ids);
    void select_page(const std::string& page_id);

    void stage_edit(const std::string& page_id, const std::string& param_name);
    void mark_written(const std::string& page_id);
    void mark_burned(const std::string& page_id);
    void revert_page(const std::string& page_id);
    void revert_all();

    void set_sync_state(SyncState state) { sync_ = state; }

    WorkspaceSnapshot snapshot() const;

    const std::string& active_page() const { return active_page_; }
    int staged_count() const;
    // Per-page staged count — returns 0 for pages with no edits.
    // Sub-slice 92: used by the TUNE tab to show a live per-page
    // indicator chip beside the selected-page title.
    int staged_count_for(const std::string& page_id) const;
    PageState page_state(const std::string& page_id) const;

    // Highest-priority page state across all tracked pages, used by
    // the three-zoom UI helpers (sidebar badge / per-page chip /
    // review chip) to pick color. Priority order is
    //   STAGED > WRITTEN > BURNED > CLEAN
    // so the UI reflects the most-urgent pending work first.
    // Sub-slice 95.
    PageState aggregate_state() const;

    // Enumerate pages currently in the given state, in insertion
    // order of `page_ids_`. Used by the "Write to RAM" button to
    // iterate only the pages that actually need writing.
    std::vector<std::string> pages_in_state(PageState state) const;

private:
    std::vector<std::string> page_ids_;
    std::string active_page_;
    std::map<std::string, PageState> page_states_;
    std::map<std::string, int> staged_counts_;
    SyncState sync_ = SyncState::OFFLINE;
};

}  // namespace tuner_core::workspace_state
