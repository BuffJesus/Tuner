// SPDX-License-Identifier: MIT
//
// tuner_core::live_analyze_session — port of LiveVeAnalyzeSessionService
// and LiveWueAnalyzeSessionService.  Sub-slices 63-64 of Phase 14 Slice 4.
//
// Stateful session wrappers that route live runtime snapshots into the
// VE/WUE accumulators.  Pure logic, no Qt.

#pragma once

#include <cstdio>
#include <string>

namespace tuner_core::live_analyze_session {

// -----------------------------------------------------------------------
// Lightweight status snapshot — shared shape for VE and WUE
// -----------------------------------------------------------------------

struct SessionStatus {
    bool is_active = false;
    int accepted_count = 0;
    int rejected_count = 0;
    int total_count = 0;
    std::string status_text;
};

/// Build inactive VE status.
inline SessionStatus ve_inactive() {
    return {false, 0, 0, 0, "VE Analyze: inactive."};
}

/// Build active VE status.
inline SessionStatus ve_active(int accepted, int rejected) {
    int total = accepted + rejected;
    char buf[128];
    std::snprintf(buf, sizeof(buf),
        "VE Analyze live: %d accepted / %d rejected of %d frame(s).",
        accepted, rejected, total);
    return {true, accepted, rejected, total, buf};
}

/// Build inactive WUE status.
inline SessionStatus wue_inactive() {
    return {false, 0, 0, 0, "WUE Analyze: inactive."};
}

/// Build active WUE status.
inline SessionStatus wue_active(int accepted, int rejected) {
    int total = accepted + rejected;
    char buf[128];
    std::snprintf(buf, sizeof(buf),
        "WUE Analyze live: %d accepted / %d rejected of %d frame(s).",
        accepted, rejected, total);
    return {true, accepted, rejected, total, buf};
}

}  // namespace tuner_core::live_analyze_session
