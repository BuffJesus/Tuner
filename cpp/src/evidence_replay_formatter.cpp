// SPDX-License-Identifier: MIT
#include "tuner_core/evidence_replay_formatter.hpp"

#include <nlohmann/json.hpp>
#include <cstdio>
#include <string>

namespace tuner_core::evidence_replay_formatter {

std::string to_text(const evidence_replay::Snapshot& s) {
    std::string lines;
    lines += "Captured: " + s.captured_at_iso + "\n";
    lines += "Session: " + s.session_state + "\n";
    lines += s.connection_text + "\n";
    lines += s.source_text + "\n";
    lines += s.sync_summary_text + "\n";
    lines += s.staged_summary_text + "\n";
    char ops[64];
    std::snprintf(ops, sizeof(ops), "Operations: %d session(s)", s.operation_session_count);
    lines += std::string(ops) + "\n";
    if (!s.latest_write_text.empty())
        lines += "Latest write: " + s.latest_write_text + "\n";
    if (!s.latest_burn_text.empty())
        lines += "Latest burn: " + s.latest_burn_text + "\n";
    for (const auto& m : s.sync_mismatch_details)
        lines += "Sync mismatch: " + m + "\n";
    lines += s.runtime_summary_text + "\n";
    char rc[64];
    std::snprintf(rc, sizeof(rc), "Runtime channels captured: %d", s.runtime_channel_count);
    lines += std::string(rc) + "\n";
    if (!s.runtime_channels.empty()) {
        lines += "Runtime values:\n";
        for (const auto& ch : s.runtime_channels) {
            char buf[128];
            if (ch.units.empty())
                std::snprintf(buf, sizeof(buf), "  %s = %g", ch.name.c_str(), ch.value);
            else
                std::snprintf(buf, sizeof(buf), "  %s = %g %s", ch.name.c_str(), ch.value, ch.units.c_str());
            lines += std::string(buf) + "\n";
        }
    }
    lines += "\nEvidence Summary:\n";
    lines += s.evidence_summary_text + "\n";
    lines += "\nOperation Evidence:\n";
    lines += s.operation_summary_text + "\n";
    return lines;
}

std::string to_json(const evidence_replay::Snapshot& s) {
    nlohmann::ordered_json j;
    j["captured_at"] = s.captured_at_iso;
    j["connection_text"] = s.connection_text;
    j["evidence_summary_text"] = s.evidence_summary_text;
    j["latest_burn_text"] = s.latest_burn_text;
    j["latest_write_text"] = s.latest_write_text;
    j["operation_session_count"] = s.operation_session_count;
    j["operation_summary_text"] = s.operation_summary_text;
    nlohmann::ordered_json channels = nlohmann::json::array();
    for (const auto& ch : s.runtime_channels) {
        nlohmann::ordered_json c;
        c["name"] = ch.name;
        c["units"] = ch.units;
        c["value"] = ch.value;
        channels.push_back(c);
    }
    j["runtime_age_seconds"] = s.runtime_age_seconds.has_value()
        ? nlohmann::json(*s.runtime_age_seconds) : nlohmann::json(nullptr);
    j["runtime_channel_count"] = s.runtime_channel_count;
    j["runtime_channels"] = channels;
    j["runtime_summary_text"] = s.runtime_summary_text;
    j["session_state"] = s.session_state;
    j["source_text"] = s.source_text;
    j["staged_summary_text"] = s.staged_summary_text;
    j["sync_mismatch_details"] = s.sync_mismatch_details;
    j["sync_summary_text"] = s.sync_summary_text;
    return j.dump(2);
}

}  // namespace tuner_core::evidence_replay_formatter
