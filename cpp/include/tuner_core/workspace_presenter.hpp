// SPDX-License-Identifier: MIT
//
// tuner_core::workspace_presenter — compact workspace orchestrator.
// Sub-slice 81 of Phase 14 Slice 4.
//
// Composes LocalTuneEditService, WorkspaceState, OperationLog, and
// TuningPageBuilder into a single presenter that manages the tuning
// workspace lifecycle: load → navigate → edit → write → burn.

#pragma once

#include "local_tune_edit.hpp"
#include "operation_log.hpp"
#include "workspace_state.hpp"
#include "tuning_page_builder.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::workspace_presenter {

using workspace_state::PageState;
using workspace_state::SyncState;
using tuning_page_builder::TuningPage;
using tuning_page_builder::TuningPageGroup;

struct PresenterSnapshot {
    std::string active_page_id;
    std::string active_page_title;
    int total_pages = 0;
    int staged_count = 0;
    PageState active_page_state = PageState::CLEAN;
    SyncState sync_state = SyncState::OFFLINE;
    std::string status_text;
    std::string operation_summary;
    bool has_definition = false;
    bool has_tune = false;
};

class Presenter {
public:
    /// Load a definition and optionally a tune file.
    void load(const NativeEcuDefinition& definition,
              local_tune_edit::TuneFile* tune = nullptr);

    /// Navigate to a page by ID.
    void select_page(const std::string& page_id);

    /// Stage a scalar edit.
    void stage_scalar(const std::string& param_name, const std::string& value);

    /// Stage a list cell edit (table/curve).
    void stage_list_cell(const std::string& param_name, int index, double value);

    /// Mark the active page as written to RAM.
    void mark_written();

    /// Mark the active page as burned to flash.
    void mark_burned();

    /// Revert the active page's staged edits.
    void revert_active_page();

    /// Revert all staged edits across all pages.
    void revert_all();

    /// Set the sync state.
    void set_sync_state(SyncState state);

    /// Get a snapshot of the current presenter state.
    PresenterSnapshot snapshot() const;

    /// Get the page groups.
    const std::vector<TuningPageGroup>& page_groups() const { return groups_; }

    /// Find a page by ID.
    const TuningPage* find_page(const std::string& page_id) const;

    /// Access the edit service.
    local_tune_edit::EditService& edit_service() { return edit_; }
    const local_tune_edit::EditService& edit_service() const { return edit_; }

private:
    local_tune_edit::EditService edit_;
    workspace_state::Workspace workspace_;
    operation_log::OperationLog log_;
    std::vector<TuningPageGroup> groups_;
    bool has_definition_ = false;
    bool has_tune_ = false;
};

}  // namespace tuner_core::workspace_presenter
