// SPDX-License-Identifier: MIT
//
// tuner_core::operation_evidence implementation. Pure logic.

#include "tuner_core/operation_evidence.hpp"

#include <algorithm>
#include <string>

namespace tuner_core::operation_evidence {

namespace {

Session build_session(int sequence, const std::vector<OperationEntry>& entries) {
    Session s;
    s.sequence = sequence;
    s.entry_count = entries.size();
    bool any_write_or_burn = false;
    bool any_staged = false;
    for (const auto& e : entries) {
        if (e.kind == OperationKind::BURNED) s.has_burn = true;
        if (e.kind == OperationKind::WRITTEN) s.has_write = true;
        if (e.kind == OperationKind::WRITTEN || e.kind == OperationKind::BURNED) {
            any_write_or_burn = true;
        }
        if (e.kind == OperationKind::STAGED) any_staged = true;
    }
    s.has_unwritten_stage = any_staged && !any_write_or_burn;
    if (!entries.empty()) s.latest_entry = entries.back();
    return s;
}

std::vector<Session> build_sessions(const std::vector<OperationEntry>& entries) {
    std::vector<Session> sessions;
    if (entries.empty()) return sessions;

    std::vector<OperationEntry> current;
    int sequence = 1;
    for (const auto& entry : entries) {
        current.push_back(entry);
        if (entry.kind == OperationKind::BURNED) {
            sessions.push_back(build_session(sequence, current));
            current.clear();
            ++sequence;
        }
    }
    if (!current.empty()) {
        sessions.push_back(build_session(sequence, current));
    }
    return sessions;
}

std::optional<OperationEntry> find_latest(
    const std::vector<OperationEntry>& entries,
    OperationKind kind) {
    for (auto it = entries.rbegin(); it != entries.rend(); ++it) {
        if (it->kind == kind) return *it;
    }
    return std::nullopt;
}

std::string active_status_text(
    const std::vector<Session>& sessions,
    const std::optional<OperationEntry>& latest_write,
    const std::optional<OperationEntry>& latest_burn,
    bool has_unwritten) {
    if (has_unwritten) {
        return "unwritten staged changes are still pending review or RAM write.";
    }
    if (latest_burn.has_value()) {
        return "latest staged work has been burned; verify persisted values before trusting it.";
    }
    if (latest_write.has_value()) {
        return "latest staged work has been written to RAM but not burned.";
    }
    if (!sessions.empty()) {
        return "session history exists, but no writes have been recorded yet.";
    }
    return "idle.";
}

std::string build_summary_text(
    const std::vector<OperationEntry>& entries,
    const std::vector<Session>& sessions,
    const std::optional<OperationEntry>& latest_write,
    const std::optional<OperationEntry>& latest_burn,
    bool has_unwritten,
    std::size_t limit) {
    if (entries.empty()) {
        return "No operations recorded this session.";
    }
    std::string out = "Evidence summary: " +
                      active_status_text(sessions, latest_write, latest_burn, has_unwritten);
    if (latest_write.has_value()) {
        out += "\nLast write: " + latest_write->summary_line();
    }
    if (latest_burn.has_value()) {
        out += "\nLast burn: " + latest_burn->summary_line();
    }
    if (!sessions.empty()) {
        const auto& active = sessions.back();
        out += "\nActive review session: #" + std::to_string(active.sequence) +
               " | " + std::to_string(active.entry_count) + " event(s)" +
               " | " + (active.has_burn ? "burned" : "not burned") +
               " | " + (active.has_write ? "written" : "not written");
    }
    out += "\n\nRecent operations:";
    // Last `limit` entries, reversed (newest first).
    const std::size_t start = entries.size() > limit ? entries.size() - limit : 0;
    for (std::size_t i = entries.size(); i > start; --i) {
        out += "\n" + entries[i - 1].summary_line();
    }
    return out;
}

}  // namespace

Snapshot build(
    const std::vector<OperationEntry>& entries,
    bool has_unwritten,
    std::size_t limit) {
    Snapshot snap;
    auto sessions = build_sessions(entries);
    auto latest_write = find_latest(entries, OperationKind::WRITTEN);
    auto latest_burn = find_latest(entries, OperationKind::BURNED);

    snap.summary_text = build_summary_text(
        entries, sessions, latest_write, latest_burn, has_unwritten, limit);
    snap.session_count = sessions.size();
    snap.latest_write_entry = latest_write;
    snap.latest_burn_entry = latest_burn;
    if (!sessions.empty()) snap.active_session = sessions.back();
    return snap;
}

}  // namespace tuner_core::operation_evidence
