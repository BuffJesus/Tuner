// SPDX-License-Identifier: MIT
#include "tuner_core/evidence_replay.hpp"

#include <cstdio>
#include <string>

namespace tuner_core::evidence_replay {

namespace se = tuner_core::surface_evidence;

Snapshot build(const Inputs& inputs) {
    // Build the surface evidence first.
    auto evidence = se::build(inputs.surface_inputs);

    Snapshot snap;
    snap.captured_at_iso = inputs.captured_at_iso;
    snap.session_state = inputs.session_state;
    snap.connection_text = evidence.connection_text;
    snap.source_text = evidence.source_text;
    snap.sync_summary_text = evidence.sync_text;
    snap.sync_mismatch_details = inputs.sync_mismatch_details;
    snap.staged_summary_text = inputs.staged_summary_text.empty()
        ? "No staged changes." : inputs.staged_summary_text;
    snap.operation_summary_text = inputs.operation_summary_text.empty()
        ? "No operations recorded this session." : inputs.operation_summary_text;
    snap.operation_session_count = inputs.operation_session_count;
    snap.latest_write_text = inputs.latest_write_text;
    snap.latest_burn_text = inputs.latest_burn_text;
    snap.runtime_summary_text = evidence.runtime_text;
    snap.runtime_channel_count = static_cast<int>(inputs.runtime_channels.size());
    snap.runtime_age_seconds = inputs.runtime_age_seconds;
    snap.runtime_channels = inputs.runtime_channels;

    // Compose the summary text.
    std::string summary;
    summary += "Captured: " + inputs.captured_at_iso + "\n";
    summary += evidence.summary_text;
    if (!inputs.staged_summary_text.empty())
        summary += "\n" + inputs.staged_summary_text;
    if (!inputs.latest_write_text.empty())
        summary += "\nLatest write: " + inputs.latest_write_text;
    if (!inputs.latest_burn_text.empty())
        summary += "\nLatest burn: " + inputs.latest_burn_text;
    for (const auto& m : inputs.sync_mismatch_details)
        summary += "\nSync mismatch: " + m;
    if (!inputs.runtime_channels.empty()) {
        std::string header = "Runtime channels captured: " +
            std::to_string(inputs.runtime_channels.size());
        if (inputs.runtime_age_seconds) {
            std::string age = se::format_age(*inputs.runtime_age_seconds);
            header += " (" + age + " old)";
        }
        summary += "\n" + header;
    } else {
        summary += "\nRuntime channels captured: none";
    }
    snap.evidence_summary_text = summary;
    return snap;
}

}  // namespace tuner_core::evidence_replay
