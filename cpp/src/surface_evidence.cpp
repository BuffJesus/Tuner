// SPDX-License-Identifier: MIT
//
// tuner_core::surface_evidence implementation. Pure logic.

#include "tuner_core/surface_evidence.hpp"

#include <cmath>
#include <sstream>
#include <string>
#include <vector>

namespace tuner_core::surface_evidence {

namespace {

std::string latest_operation_text(const std::string& summary) {
    std::size_t i = 0;
    while (i < summary.size()) {
        std::size_t j = summary.find('\n', i);
        std::string line = summary.substr(i, j == std::string::npos ? std::string::npos : j - i);
        // strip
        std::size_t a = line.find_first_not_of(" \t\r");
        std::size_t b = line.find_last_not_of(" \t\r");
        if (a != std::string::npos) return line.substr(a, b - a + 1);
        if (j == std::string::npos) break;
        i = j + 1;
    }
    return "";
}

struct RuntimeStatus {
    std::string text;
    std::string severity;
    std::string detail;
};

RuntimeStatus runtime_status(const Inputs& in) {
    if (!in.runtime_present || in.runtime_value_count == 0) {
        if (in.connected) return {"Runtime  waiting", "warning", ""};
        return {"Runtime  offline", "info", ""};
    }
    if (!in.connected) {
        return {"Runtime  " + std::to_string(in.runtime_value_count) + " cached",
                "info",
                "Runtime snapshot is cached from an earlier session."};
    }
    if (!in.runtime_age_seconds.has_value()) {
        return {"Runtime  " + std::to_string(in.runtime_value_count) + " channel(s)",
                "accent", ""};
    }
    double age = *in.runtime_age_seconds;
    if (age < 0) age = 0;
    std::string age_text = format_age(age);
    if (age > 30) {
        return {"Runtime  stale (" + age_text + ")", "warning",
                "Latest runtime sample is " + age_text + " old."};
    }
    return {"Runtime  " + std::to_string(in.runtime_value_count) + " channel(s)",
            "accent",
            "Latest runtime sample is " + age_text + " old."};
}

}  // namespace

std::string format_age(double age_seconds) {
    long rounded = static_cast<long>(std::lround(age_seconds));
    if (rounded < 60) return std::to_string(rounded) + "s";
    long minutes = rounded / 60;
    long seconds = rounded % 60;
    if (minutes < 60) {
        return std::to_string(minutes) + "m " + std::to_string(seconds) + "s";
    }
    long hours = minutes / 60;
    minutes = minutes % 60;
    return std::to_string(hours) + "h " + std::to_string(minutes) + "m";
}

Snapshot build(const Inputs& in) {
    Snapshot s;

    s.connection_text = "Connection  " + in.connection_state_text;
    s.connection_severity = in.connected ? "accent" : "info";

    if (in.connected && in.sync_state_present && in.sync_has_ecu_ram) {
        s.source_text = "Source  ECU RAM";
        s.source_severity = "accent";
    } else if (in.staged_count) {
        s.source_text = "Source  Staged Tune";
        s.source_severity = "accent";
    } else {
        s.source_text = "Source  Project Tune";
        s.source_severity = "ok";
    }

    if (in.mismatch_count) {
        s.sync_text = "Sync  " + std::to_string(in.mismatch_count) + " mismatch(s)";
        s.sync_severity = "warning";
    } else if (in.sync_state_present) {
        s.sync_text = "Sync  clean";
        s.sync_severity = "ok";
    } else {
        s.sync_text = "Sync  unavailable";
        s.sync_severity = "info";
    }

    s.changes_text = "Changes  " + std::to_string(in.staged_count) + " staged";
    s.changes_severity = in.staged_count ? "accent" : "ok";

    if (in.log_count) {
        s.log_text = "Ops  " + std::to_string(in.log_count) + " event(s)";
        if (in.has_unwritten) s.log_text += " pending";
        s.log_severity = in.has_unwritten ? "warning" : "info";
    } else {
        s.log_text = "Ops  idle";
        s.log_severity = "ok";
    }

    auto rs = runtime_status(in);
    s.runtime_text = rs.text;
    s.runtime_severity = rs.severity;

    std::string log_detail = latest_operation_text(in.operation_log_summary_text);

    std::vector<std::string> parts;
    if (in.mismatch_count) {
        parts.push_back("Review sync mismatches before trusting runtime evidence or applying writes.");
    } else if (in.staged_count && in.connected) {
        parts.push_back("Runtime data is live while staged changes remain pending review or write.");
    } else if (in.staged_count) {
        parts.push_back("Staged changes exist, but runtime evidence is offline until a controller is connected.");
    } else if (in.connected && in.runtime_present && in.runtime_value_count) {
        if (s.runtime_severity == "warning") {
            parts.push_back("Runtime evidence is present but stale. Refresh channels before trusting live conditions.");
        } else {
            parts.push_back("Live runtime evidence is available. Cross-check channels, sync state, and recent operations before making changes.");
        }
    } else if (in.connected) {
        parts.push_back("Connected, but runtime evidence has not populated yet. Refresh channels or verify the controller is streaming.");
    } else {
        parts.push_back("Offline context only. Connect to gather runtime evidence and compare it against the current tune state.");
    }

    if (in.has_unwritten) parts.push_back("Unwritten operation history exists in this session.");
    if (!rs.detail.empty()) parts.push_back(rs.detail);
    if (!log_detail.empty()) parts.push_back("Latest op: " + log_detail);

    std::ostringstream out;
    for (std::size_t i = 0; i < parts.size(); ++i) {
        if (i) out << ' ';
        out << parts[i];
    }
    s.summary_text = out.str();
    return s;
}

}  // namespace tuner_core::surface_evidence
